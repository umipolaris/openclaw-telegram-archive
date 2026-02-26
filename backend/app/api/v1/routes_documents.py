import hashlib
import mimetypes
from difflib import unified_diff
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, File as UploadFormFile, Form, HTTPException, Query, UploadFile, status
from minio.error import S3Error
from sqlalchemy import and_, asc, desc, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.responses import FileResponse, StreamingResponse

from app.core.auth import CurrentUser, require_roles
from app.core.config import get_settings
from app.db.models import (
    AuditLog,
    Category,
    Document,
    DocumentFile,
    DocumentTag,
    DocumentVersion,
    File as StoredFile,
    IngestJob,
    ReviewStatus,
    RuleVersion,
    SourceType,
    Tag,
    User,
    UserRole,
)
from app.db.session import get_db
from app.schemas.document import (
    DocumentDeleteResponse,
    DocumentDetailResponse,
    DocumentHistoryItem,
    DocumentHistoryResponse,
    DocumentFileItem,
    DocumentListFileItem,
    DocumentListItem,
    DocumentListResponse,
    DocumentVersionDiffResponse,
    DocumentVersionSnapshotResponse,
    DocumentUpdateRequest,
    DocumentVersionItem,
    ManualPostCategoryOptionsResponse,
    ManualPostCreateRequest,
    ReclassifyRequest,
)
from app.services.dedupe_service import find_by_checksum
from app.services.meili_service import MeiliSearchError, is_meili_enabled, search_document_ids
from app.services.caption_parser import parse_caption
from app.services.rule_categories import extract_categories_from_rules_json
from app.services.rule_engine import RuleInput, apply_rules
from app.services.search_sync_service import enqueue_document_index_delete, enqueue_document_index_sync
from app.services.storage_disk import delete_file as delete_file_disk, put_file as put_file_disk
from app.services.storage_minio import (
    delete_file as delete_file_minio,
    ensure_bucket,
    get_minio_client,
    put_file as put_file_minio,
)

router = APIRouter()


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _slugify(text: str) -> str:
    return text.strip().lower().replace(" ", "-")


def _normalize_tag_names(names: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for raw in names:
        name = raw.strip()
        if not name:
            continue
        slug = _slugify(name)
        if slug in seen:
            continue
        seen.add(slug)
        normalized.append(name)
    return normalized


def _get_active_rules(db: Session) -> dict:
    rv = (
        db.execute(
            select(RuleVersion)
            .where(RuleVersion.is_active.is_(True))
            .order_by(RuleVersion.published_at.desc().nulls_last(), RuleVersion.created_at.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )
    return rv.rules_json if rv else {"default_category": "기타", "category_rules": []}


def _storage_key(checksum: str, extension: str | None) -> str:
    ext = (extension or "bin").lower().lstrip(".")
    return f"{checksum[0:2]}/{checksum[2:4]}/{checksum}.{ext}"


def _file_download_path(file_id: UUID) -> str:
    return f"/files/{file_id}/download"


def _download_name(filename: str) -> str:
    normalized = Path(filename).name.strip()
    return normalized or "download.bin"


def _content_disposition(filename: str) -> str:
    encoded = quote(_download_name(filename))
    return f"attachment; filename*=UTF-8''{encoded}"


def _get_tag_names(db: Session, document_id: UUID) -> list[str]:
    stmt = (
        select(Tag.name)
        .join(DocumentTag, DocumentTag.tag_id == Tag.id)
        .where(DocumentTag.document_id == document_id)
        .order_by(Tag.name.asc())
    )
    return list(db.execute(stmt).scalars().all())


def _get_document_files(db: Session, document_id: UUID) -> list[DocumentFileItem]:
    stmt = (
        select(StoredFile)
        .join(DocumentFile, DocumentFile.file_id == StoredFile.id)
        .where(DocumentFile.document_id == document_id)
        .order_by(DocumentFile.created_at.desc())
    )
    rows = db.execute(stmt).scalars().all()
    return [
        DocumentFileItem(
            id=row.id,
            original_filename=row.original_filename,
            mime_type=row.mime_type,
            size_bytes=row.size_bytes,
            checksum_sha256=row.checksum_sha256,
            storage_backend=row.storage_backend,
            download_path=_file_download_path(row.id),
        )
        for row in rows
    ]


def _get_document_file_previews(
    db: Session,
    document_ids: list[UUID],
    *,
    per_document_limit: int = 3,
) -> tuple[dict[UUID, int], dict[UUID, list[DocumentListFileItem]]]:
    if not document_ids:
        return {}, {}

    rows = db.execute(
        select(DocumentFile.document_id, StoredFile.id, StoredFile.original_filename)
        .join(StoredFile, StoredFile.id == DocumentFile.file_id)
        .where(DocumentFile.document_id.in_(document_ids))
        .order_by(DocumentFile.document_id.asc(), DocumentFile.created_at.desc())
    ).all()

    counts: dict[UUID, int] = {}
    previews: dict[UUID, list[DocumentListFileItem]] = {}
    for document_id, file_id, original_filename in rows:
        counts[document_id] = counts.get(document_id, 0) + 1
        items = previews.setdefault(document_id, [])
        if len(items) >= per_document_limit:
            continue
        items.append(
            DocumentListFileItem(
                id=file_id,
                original_filename=original_filename,
                download_path=_file_download_path(file_id),
            )
        )

    return counts, previews


def _get_document_tags_map(db: Session, document_ids: list[UUID]) -> dict[UUID, list[str]]:
    if not document_ids:
        return {}

    rows = db.execute(
        select(DocumentTag.document_id, Tag.name)
        .join(Tag, Tag.id == DocumentTag.tag_id)
        .where(DocumentTag.document_id.in_(document_ids))
        .order_by(DocumentTag.document_id.asc(), Tag.name.asc())
    ).all()

    tags_map: dict[UUID, list[str]] = {}
    for document_id, tag_name in rows:
        tags_map.setdefault(document_id, []).append(tag_name)
    return tags_map


def _get_document_versions(db: Session, document_id: UUID) -> list[DocumentVersionItem]:
    rows = db.execute(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == document_id)
        .order_by(DocumentVersion.version_no.desc())
        .limit(50)
    ).scalars().all()
    return [
        DocumentVersionItem(
            version_no=row.version_no,
            changed_at=row.changed_at,
            change_reason=row.change_reason,
            title=row.title,
            event_date=row.event_date,
        )
        for row in rows
    ]


def _get_document_version_row(db: Session, document_id: UUID, version_no: int) -> DocumentVersion | None:
    return db.execute(
        select(DocumentVersion)
        .where(
            and_(
                DocumentVersion.document_id == document_id,
                DocumentVersion.version_no == version_no,
            )
        )
        .limit(1)
    ).scalar_one_or_none()


def _make_unified_diff(from_text: str, to_text: str, *, from_label: str, to_label: str) -> str:
    from_lines = (from_text or "").splitlines()
    to_lines = (to_text or "").splitlines()
    lines = list(
        unified_diff(
            from_lines,
            to_lines,
            fromfile=from_label,
            tofile=to_label,
            lineterm="",
        )
    )
    if not lines:
        return "(no text diff)"
    return "\n".join(lines)


def _document_search_vector_expr():  # noqa: ANN202
    return func.coalesce(
        Document.search_vector,
        func.to_tsvector(
            "simple",
            func.concat_ws(" ", Document.title, Document.description, Document.summary, Document.caption_raw),
        ),
    )


def _refresh_document_search_vector(db: Session, document_id: UUID) -> None:
    db.execute(
        update(Document)
        .where(Document.id == document_id)
        .values(
            search_vector=func.to_tsvector(
                "simple",
                func.concat_ws(" ", Document.title, Document.description, Document.summary, Document.caption_raw),
            )
        )
    )
    db.flush()


def _last_modified_expr():  # noqa: ANN202
    latest_version_subquery = (
        select(func.max(DocumentVersion.changed_at))
        .where(DocumentVersion.document_id == Document.id)
        .correlate(Document)
        .scalar_subquery()
    )
    return func.coalesce(latest_version_subquery, Document.updated_at, Document.created_at, Document.ingested_at)


def _get_document_last_modified_map(db: Session, document_ids: list[UUID]) -> dict[UUID, datetime]:
    if not document_ids:
        return {}

    rows = db.execute(
        select(DocumentVersion.document_id, func.max(DocumentVersion.changed_at))
        .where(DocumentVersion.document_id.in_(document_ids))
        .group_by(DocumentVersion.document_id)
    ).all()
    return {document_id: changed_at for document_id, changed_at in rows if changed_at is not None}


def _build_order_by(
    *,
    sort_by: Literal["event_date", "ingested_at", "title", "created_at", "last_modified_at"],
    sort_order: Literal["asc", "desc"],
) -> list:
    primary = asc if sort_order == "asc" else desc
    secondary = asc if sort_order == "asc" else desc

    if sort_by == "title":
        return [primary(func.lower(Document.title)), secondary(Document.ingested_at)]
    if sort_by == "created_at":
        return [primary(Document.created_at), secondary(Document.ingested_at)]
    if sort_by == "ingested_at":
        return [primary(Document.ingested_at)]
    if sort_by == "last_modified_at":
        return [primary(_last_modified_expr()), secondary(Document.ingested_at)]
    return [primary(Document.event_date).nullslast(), secondary(Document.ingested_at)]


def _to_document_detail_response(db: Session, doc: Document) -> DocumentDetailResponse:
    tags = _get_tag_names(db, doc.id)
    category = db.get(Category, doc.category_id) if doc.category_id else None
    files = _get_document_files(db, doc.id)
    versions = _get_document_versions(db, doc.id)

    return DocumentDetailResponse(
        id=doc.id,
        source=doc.source.value,
        source_ref=doc.source_ref,
        title=doc.title,
        description=doc.description,
        caption_raw=doc.caption_raw,
        summary=doc.summary,
        category_id=doc.category_id,
        category=category.name if category else None,
        event_date=doc.event_date,
        ingested_at=doc.ingested_at,
        review_status=doc.review_status,
        review_reasons=doc.review_reasons,
        current_version_no=doc.current_version_no,
        tags=tags,
        files=files,
        versions=versions,
    )


def _upsert_category(db: Session, category_name: str, created_by: UUID) -> Category:
    normalized = category_name.strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="category_name is empty")
    slug = _slugify(normalized)
    existing = db.execute(select(Category).where(Category.slug == slug)).scalar_one_or_none()
    if existing:
        return existing

    category = Category(name=normalized, slug=slug, is_active=True, created_by=created_by)
    db.add(category)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        recovered = db.execute(select(Category).where(Category.slug == slug)).scalar_one_or_none()
        if recovered:
            return recovered
        raise HTTPException(status_code=409, detail="failed to create category") from exc
    return category


def _upsert_tags(db: Session, names: list[str], created_by: UUID) -> list[Tag]:
    seen: set[str] = set()
    rows: list[Tag] = []
    for raw in names:
        name = raw.strip()
        if not name:
            continue
        slug = _slugify(name)
        if slug in seen:
            continue
        seen.add(slug)
        tag = db.execute(select(Tag).where(Tag.slug == slug)).scalar_one_or_none()
        if not tag:
            tag = Tag(name=name, slug=slug, created_by=created_by)
            db.add(tag)
            db.flush()
        rows.append(tag)
    return rows


def _append_document_version(
    db: Session,
    doc: Document,
    *,
    change_reason: str,
    tags_snapshot: list[str],
    created_by: UUID,
) -> None:
    doc.current_version_no += 1
    db.add(doc)
    db.add(
        DocumentVersion(
            document_id=doc.id,
            version_no=doc.current_version_no,
            title=doc.title,
            description=doc.description,
            summary=doc.summary,
            category_id=doc.category_id,
            event_date=doc.event_date,
            tags_snapshot=tags_snapshot,
            change_reason=change_reason,
            created_by=created_by,
        )
    )


def _store_uploaded_file(
    db: Session,
    *,
    source: SourceType,
    source_ref: str | None,
    upload: UploadFile,
    created_by: UUID,
) -> StoredFile:
    filename = upload.filename or "upload.bin"
    content = upload.file.read()
    checksum_sha256 = hashlib.sha256(content).hexdigest()
    existing = find_by_checksum(db, checksum_sha256)
    if existing:
        return existing

    mime_type, _ = mimetypes.guess_type(filename)
    mime_type = mime_type or "application/octet-stream"
    extension = Path(filename).suffix.lstrip(".") or None
    storage_key = _storage_key(checksum_sha256, extension)
    settings = get_settings()

    if settings.storage_backend == "minio":
        client = get_minio_client(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        ensure_bucket(client, settings.storage_bucket)
        put_file_minio(client, settings.storage_bucket, storage_key, content, mime_type)
    else:
        put_file_disk(settings.storage_disk_root, storage_key, content)

    row = StoredFile(
        source=source,
        source_ref=source_ref,
        storage_backend=settings.storage_backend,
        bucket=settings.storage_bucket,
        storage_key=storage_key,
        original_filename=filename,
        uploaded_filename=filename,
        extension=extension,
        checksum_sha256=checksum_sha256,
        mime_type=mime_type,
        size_bytes=len(content),
        metadata_json={},
        created_by=created_by,
    )
    db.add(row)
    db.flush()
    return row


def _delete_stored_object(file_row: StoredFile) -> None:
    settings = get_settings()
    if file_row.storage_backend == "minio":
        client = get_minio_client(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        delete_file_minio(client, file_row.bucket, file_row.storage_key)
        return
    delete_file_disk(settings.storage_disk_root, file_row.storage_key)


def _cleanup_orphan_file(db: Session, file_row: StoredFile | None) -> bool:
    if not file_row:
        return False
    linked_count = db.execute(
        select(func.count()).select_from(DocumentFile).where(DocumentFile.file_id == file_row.id)
    ).scalar_one()
    if linked_count > 0:
        return False
    _delete_stored_object(file_row)
    db.delete(file_row)
    db.flush()
    return True


@router.get("/documents", response_model=DocumentListResponse)
def list_documents(
    q: str | None = Query(None),
    category_id: UUID | None = Query(None),
    category_name: str | None = Query(None),
    tag: str | None = Query(None),
    event_date_from: date | None = Query(None),
    event_date_to: date | None = Query(None),
    review_status: ReviewStatus | None = Query(None),
    sort_by: Literal["event_date", "ingested_at", "title", "created_at", "last_modified_at"] = Query("event_date"),
    sort_order: Literal["asc", "desc"] = Query("desc"),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    _: CurrentUser = Depends(require_roles(UserRole.VIEWER, UserRole.REVIEWER, UserRole.EDITOR, UserRole.ADMIN)),
    db: Session = Depends(get_db),
) -> DocumentListResponse:
    order_by = _build_order_by(sort_by=sort_by, sort_order=sort_order)
    settings = get_settings()
    if q and sort_by != "last_modified_at" and is_meili_enabled(settings):
        try:
            meili_result = search_document_ids(
                q,
                page=page,
                size=size,
                category_id=category_id,
                category_name=category_name,
                tag_slug=tag,
                event_date_from=event_date_from,
                event_date_to=event_date_to,
                review_status=review_status,
                sort_by=sort_by,
                sort_order=sort_order,
                settings=settings,
            )
            total = meili_result.total
            doc_ids = meili_result.ids
            if not doc_ids:
                return DocumentListResponse(items=[], page=page, size=size, total=total)

            rows = db.execute(
                select(Document, Category.name.label("category_name"))
                .outerjoin(Category, Category.id == Document.category_id)
                .where(Document.id.in_(doc_ids))
                .order_by(*order_by)
            ).all()
            docs = [row[0] for row in rows]
            category_names = {row[0].id: row.category_name for row in rows}

            loaded_doc_ids = [doc.id for doc in docs]
            file_counts, file_previews = _get_document_file_previews(db, loaded_doc_ids)
            tags_map = _get_document_tags_map(db, loaded_doc_ids)
            last_modified_map = _get_document_last_modified_map(db, loaded_doc_ids)

            items: list[DocumentListItem] = []
            for doc in docs:
                items.append(
                    DocumentListItem(
                        id=doc.id,
                        title=doc.title,
                        description=doc.description,
                        category=category_names.get(doc.id),
                        event_date=doc.event_date,
                        ingested_at=doc.ingested_at,
                        last_modified_at=last_modified_map.get(doc.id, doc.updated_at or doc.created_at or doc.ingested_at),
                        tags=tags_map.get(doc.id, []),
                        file_count=file_counts.get(doc.id, 0),
                        files=file_previews.get(doc.id, []),
                        review_status=doc.review_status,
                        review_reasons=list(doc.review_reasons or []),
                    )
                )
            return DocumentListResponse(items=items, page=page, size=size, total=total)
        except MeiliSearchError:
            pass

    stmt = select(Document, Category.name.label("category_name")).outerjoin(Category, Category.id == Document.category_id)
    count_stmt = select(func.count(Document.id)).select_from(Document).outerjoin(Category, Category.id == Document.category_id)
    count_use_distinct = False

    filters = []
    ts_query = None
    if q:
        ts_query = func.plainto_tsquery("simple", q)
        filters.append(_document_search_vector_expr().op("@@")(ts_query))
    if category_id:
        filters.append(Document.category_id == category_id)
    if category_name:
        if category_name == "미분류":
            filters.append(Document.category_id.is_(None))
        else:
            filters.append(Category.name == category_name)
    if event_date_from:
        filters.append(Document.event_date >= event_date_from)
    if event_date_to:
        filters.append(Document.event_date <= event_date_to)
    if review_status:
        filters.append(Document.review_status == review_status)

    if tag:
        stmt = stmt.join(DocumentTag, DocumentTag.document_id == Document.id).join(Tag, Tag.id == DocumentTag.tag_id)
        count_stmt = count_stmt.join(DocumentTag, DocumentTag.document_id == Document.id).join(Tag, Tag.id == DocumentTag.tag_id)
        count_use_distinct = True
        filters.append(Tag.slug == tag)

    if filters:
        stmt = stmt.where(and_(*filters))
        count_stmt = count_stmt.where(and_(*filters))
    if count_use_distinct:
        count_stmt = count_stmt.with_only_columns(func.count(func.distinct(Document.id)))

    if q and ts_query is not None and sort_by == "event_date" and sort_order == "desc":
        rank = func.ts_rank_cd(_document_search_vector_expr(), ts_query)
        order_by_stmt = [desc(rank), *order_by]
    else:
        order_by_stmt = order_by

    total = db.execute(count_stmt).scalar_one()
    rows = db.execute(
        stmt.order_by(*order_by_stmt)
        .offset((page - 1) * size)
        .limit(size)
    ).all()
    docs = [row[0] for row in rows]
    category_names = {row[0].id: row.category_name for row in rows}
    doc_ids = [doc.id for doc in docs]
    file_counts, file_previews = _get_document_file_previews(db, doc_ids)
    tags_map = _get_document_tags_map(db, doc_ids)
    last_modified_map = _get_document_last_modified_map(db, doc_ids)

    items: list[DocumentListItem] = []
    for doc in docs:
        items.append(
            DocumentListItem(
                id=doc.id,
                title=doc.title,
                description=doc.description,
                category=category_names.get(doc.id),
                event_date=doc.event_date,
                ingested_at=doc.ingested_at,
                last_modified_at=last_modified_map.get(doc.id, doc.updated_at or doc.created_at or doc.ingested_at),
                tags=tags_map.get(doc.id, []),
                file_count=file_counts.get(doc.id, 0),
                files=file_previews.get(doc.id, []),
                review_status=doc.review_status,
                review_reasons=list(doc.review_reasons or []),
            )
        )

    return DocumentListResponse(items=items, page=page, size=size, total=total)


@router.get("/documents/manual-post/category-options", response_model=ManualPostCategoryOptionsResponse)
def get_manual_post_category_options(
    _: CurrentUser = Depends(require_roles(UserRole.EDITOR, UserRole.ADMIN)),
    db: Session = Depends(get_db),
) -> ManualPostCategoryOptionsResponse:
    categories = extract_categories_from_rules_json(_get_active_rules(db))
    return ManualPostCategoryOptionsResponse(categories=categories)


@router.post("/documents/manual-post", response_model=DocumentDetailResponse, status_code=status.HTTP_201_CREATED)
def create_manual_post(
    req: ManualPostCreateRequest,
    current_user: CurrentUser = Depends(require_roles(UserRole.EDITOR, UserRole.ADMIN)),
    db: Session = Depends(get_db),
) -> DocumentDetailResponse:
    title = req.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="title is required")
    normalized_tags = _normalize_tag_names(req.tags)

    category_id = req.category_id
    category_name_for_caption: str | None = None
    if category_id:
        category = db.get(Category, category_id)
        if not category:
            raise HTTPException(status_code=400, detail="category_id not found")
        category_name_for_caption = category.name
    elif req.category_name:
        category = _upsert_category(db, req.category_name, current_user.id)
        category_id = category.id
        category_name_for_caption = category.name

    description = req.description or ""
    caption_raw = req.caption_raw
    if caption_raw is None:
        caption_lines = [title]
        if description:
            caption_lines.append(description)
        if category_name_for_caption:
            caption_lines.append(f"#분류:{category_name_for_caption}")
        if req.event_date:
            caption_lines.append(f"#날짜:{req.event_date.isoformat()}")
        if normalized_tags:
            caption_lines.append(f"#태그:{','.join(normalized_tags)}")
        caption_raw = "\n".join(caption_lines)

    ingested_at = _now()
    try:
        parsed_caption = parse_caption(caption_raw, "manual-post.txt")
        auto_rule_out = apply_rules(
            RuleInput(
                caption=parsed_caption,
                title=title,
                description=description,
                filename="manual-post.txt",
                body_text=description,
                metadata_date_text=req.event_date.isoformat() if req.event_date else None,
                ingested_at=ingested_at,
            ),
            _get_active_rules(db),
        )
        normalized_tags = _normalize_tag_names([*normalized_tags, *auto_rule_out.tags])
        if category_id is None and auto_rule_out.category and auto_rule_out.category.strip():
            inferred_category = _upsert_category(db, auto_rule_out.category, current_user.id)
            category_id = inferred_category.id
            category_name_for_caption = inferred_category.name
    except Exception:
        # Smart tag/category generation is best-effort and must not block manual posting.
        pass

    summary = req.summary.strip() if req.summary else ""
    if not summary:
        summary = description[:400] if description else title[:400]

    doc = Document(
        source=SourceType.manual,
        source_ref=None,
        title=title,
        description=description,
        caption_raw=caption_raw,
        summary=summary,
        category_id=category_id,
        event_date=req.event_date,
        ingested_at=ingested_at,
        review_status=req.review_status,
        review_reasons=[],
        current_version_no=1,
        created_by=current_user.id,
    )
    db.add(doc)
    db.flush()

    tag_rows = _upsert_tags(db, normalized_tags, current_user.id)
    for tag in tag_rows:
        db.add(DocumentTag(document_id=doc.id, tag_id=tag.id, created_by=current_user.id))

    db.add(
        DocumentVersion(
            document_id=doc.id,
            version_no=1,
            title=doc.title,
            description=doc.description,
            summary=doc.summary,
            category_id=doc.category_id,
            event_date=doc.event_date,
            tags_snapshot=[tag.name for tag in tag_rows],
            change_reason="manual_post_create",
            created_by=current_user.id,
        )
    )
    db.add(
        AuditLog(
            actor_user_id=current_user.id,
            action="DOCUMENT_MANUAL_POST_CREATE",
            target_type="document",
            target_id=doc.id,
            source=doc.source,
            source_ref=doc.source_ref,
            after_json={
                "title": doc.title,
                "category_id": str(doc.category_id) if doc.category_id else None,
                "event_date": doc.event_date.isoformat() if doc.event_date else None,
                "tags": [tag.name for tag in tag_rows],
            },
        )
    )
    _refresh_document_search_vector(db, doc.id)
    db.commit()
    db.refresh(doc)
    enqueue_document_index_sync(doc.id)
    return _to_document_detail_response(db, doc)


@router.get("/documents/{id}", response_model=DocumentDetailResponse)
def get_document(
    id: UUID,
    _: CurrentUser = Depends(require_roles(UserRole.VIEWER, UserRole.REVIEWER, UserRole.EDITOR, UserRole.ADMIN)),
    db: Session = Depends(get_db),
) -> DocumentDetailResponse:
    doc = db.get(Document, id)
    if not doc:
        raise HTTPException(status_code=404, detail="document not found")

    return _to_document_detail_response(db, doc)


@router.get("/documents/{id}/history", response_model=DocumentHistoryResponse)
def get_document_history(
    id: UUID,
    page: int = Query(1, ge=1),
    size: int = Query(30, ge=1, le=200),
    _: CurrentUser = Depends(require_roles(UserRole.VIEWER, UserRole.REVIEWER, UserRole.EDITOR, UserRole.ADMIN)),
    db: Session = Depends(get_db),
) -> DocumentHistoryResponse:
    doc = db.get(Document, id)
    if not doc:
        raise HTTPException(status_code=404, detail="document not found")

    base_filters = [AuditLog.target_type == "document", AuditLog.target_id == id]
    total = db.execute(select(func.count(AuditLog.id)).where(and_(*base_filters))).scalar_one()
    rows = db.execute(
        select(AuditLog, User.username.label("actor_username"))
        .outerjoin(User, User.id == AuditLog.actor_user_id)
        .where(and_(*base_filters))
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    ).all()

    return DocumentHistoryResponse(
        items=[
            DocumentHistoryItem(
                id=row[0].id,
                action=row[0].action,
                actor_username=row.actor_username,
                source=row[0].source.value if row[0].source else None,
                source_ref=row[0].source_ref,
                created_at=row[0].created_at,
                before_json=row[0].before_json,
                after_json=row[0].after_json,
                masked_fields=list(row[0].masked_fields or []),
            )
            for row in rows
        ],
        page=page,
        size=size,
        total=total,
    )


@router.get("/documents/{id}/versions/diff", response_model=DocumentVersionDiffResponse)
def get_document_version_diff(
    id: UUID,
    from_version_no: int | None = Query(None, ge=1),
    to_version_no: int | None = Query(None, ge=1),
    _: CurrentUser = Depends(require_roles(UserRole.VIEWER, UserRole.REVIEWER, UserRole.EDITOR, UserRole.ADMIN)),
    db: Session = Depends(get_db),
) -> DocumentVersionDiffResponse:
    doc = db.get(Document, id)
    if not doc:
        raise HTTPException(status_code=404, detail="document not found")

    target_to = to_version_no or doc.current_version_no
    target_from = from_version_no if from_version_no is not None else max(1, target_to - 1)
    if target_from > target_to:
        raise HTTPException(status_code=400, detail="from_version_no must be <= to_version_no")

    from_row = _get_document_version_row(db, doc.id, target_from)
    to_row = _get_document_version_row(db, doc.id, target_to)
    if not from_row or not to_row:
        raise HTTPException(status_code=404, detail="requested version not found")

    changed_fields: list[str] = []
    if from_row.title != to_row.title:
        changed_fields.append("title")
    if from_row.description != to_row.description:
        changed_fields.append("description")
    if from_row.summary != to_row.summary:
        changed_fields.append("summary")
    if from_row.event_date != to_row.event_date:
        changed_fields.append("event_date")
    if from_row.category_id != to_row.category_id:
        changed_fields.append("category_id")
    if sorted(from_row.tags_snapshot or []) != sorted(to_row.tags_snapshot or []):
        changed_fields.append("tags")

    description_diff = _make_unified_diff(
        from_row.description,
        to_row.description,
        from_label=f"v{from_row.version_no}:description",
        to_label=f"v{to_row.version_no}:description",
    )
    summary_diff = _make_unified_diff(
        from_row.summary,
        to_row.summary,
        from_label=f"v{from_row.version_no}:summary",
        to_label=f"v{to_row.version_no}:summary",
    )

    return DocumentVersionDiffResponse(
        document_id=doc.id,
        from_version_no=from_row.version_no,
        to_version_no=to_row.version_no,
        changed_fields=changed_fields,
        title_from=from_row.title,
        title_to=to_row.title,
        description_diff=description_diff,
        summary_diff=summary_diff,
        tags_from=list(from_row.tags_snapshot or []),
        tags_to=list(to_row.tags_snapshot or []),
        event_date_from=from_row.event_date,
        event_date_to=to_row.event_date,
        category_id_from=from_row.category_id,
        category_id_to=to_row.category_id,
    )


@router.get("/documents/{id}/versions/{version_no}/snapshot", response_model=DocumentVersionSnapshotResponse)
def get_document_version_snapshot(
    id: UUID,
    version_no: int,
    _: CurrentUser = Depends(require_roles(UserRole.VIEWER, UserRole.REVIEWER, UserRole.EDITOR, UserRole.ADMIN)),
    db: Session = Depends(get_db),
) -> DocumentVersionSnapshotResponse:
    if version_no < 1:
        raise HTTPException(status_code=400, detail="version_no must be >= 1")

    doc = db.get(Document, id)
    if not doc:
        raise HTTPException(status_code=404, detail="document not found")

    version_row = _get_document_version_row(db, doc.id, version_no)
    if not version_row:
        raise HTTPException(status_code=404, detail="requested version not found")

    category_name: str | None = None
    if version_row.category_id:
        category = db.get(Category, version_row.category_id)
        category_name = category.name if category else None

    tags = [str(tag).strip() for tag in (version_row.tags_snapshot or []) if str(tag).strip()]

    return DocumentVersionSnapshotResponse(
        document_id=doc.id,
        version_no=version_row.version_no,
        changed_at=version_row.changed_at,
        change_reason=version_row.change_reason,
        title=version_row.title,
        description=version_row.description,
        summary=version_row.summary,
        category_id=version_row.category_id,
        category=category_name,
        event_date=version_row.event_date,
        tags=tags,
    )


@router.get("/files/{file_id}/download")
def download_file(
    file_id: UUID,
    _: CurrentUser = Depends(require_roles(UserRole.VIEWER, UserRole.REVIEWER, UserRole.EDITOR, UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    file_row = db.get(StoredFile, file_id)
    if not file_row:
        raise HTTPException(status_code=404, detail="file not found")

    settings = get_settings()
    if file_row.storage_backend == "minio":
        client = get_minio_client(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        try:
            minio_resp = client.get_object(bucket_name=file_row.bucket, object_name=file_row.storage_key)
        except S3Error as exc:
            if exc.code in {"NoSuchKey", "NoSuchObject", "NoSuchBucket"}:
                raise HTTPException(status_code=404, detail="file object not found") from exc
            raise

        def stream_chunks():  # noqa: ANN202
            try:
                for chunk in minio_resp.stream(32 * 1024):
                    if chunk:
                        yield chunk
            finally:
                minio_resp.close()
                minio_resp.release_conn()

        return StreamingResponse(
            stream_chunks(),
            media_type=file_row.mime_type or "application/octet-stream",
            headers={"Content-Disposition": _content_disposition(file_row.original_filename)},
        )

    file_path = Path(settings.storage_disk_root) / file_row.storage_key
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="file object not found")
    return FileResponse(
        path=str(file_path),
        media_type=file_row.mime_type or "application/octet-stream",
        filename=_download_name(file_row.original_filename),
    )


@router.patch("/documents/{id}", response_model=DocumentDetailResponse)
def patch_document(
    id: UUID,
    req: DocumentUpdateRequest,
    current_user: CurrentUser = Depends(require_roles(UserRole.EDITOR, UserRole.ADMIN)),
    db: Session = Depends(get_db),
) -> DocumentDetailResponse:
    doc = db.get(Document, id)
    if not doc:
        raise HTTPException(status_code=404, detail="document not found")

    before = {
        "title": doc.title,
        "description": doc.description,
        "category_id": doc.category_id,
        "event_date": doc.event_date,
        "review_status": doc.review_status,
    }

    fields_set = req.model_fields_set
    if "title" in fields_set:
        if req.title is None or not req.title.strip():
            raise HTTPException(status_code=400, detail="title cannot be empty")
        doc.title = req.title.strip()
    if "description" in fields_set:
        doc.description = req.description or ""
    if "event_date" in fields_set:
        doc.event_date = req.event_date
    if "review_status" in fields_set and req.review_status is not None:
        doc.review_status = req.review_status

    category_id_provided = "category_id" in fields_set
    category_name_provided = "category_name" in fields_set
    resolved_category_id = None
    if category_name_provided:
        if req.category_name and req.category_name.strip():
            resolved_category_id = _upsert_category(db, req.category_name, current_user.id).id
        else:
            resolved_category_id = None

    if category_id_provided:
        if req.category_id:
            category_row = db.get(Category, req.category_id)
            if not category_row:
                raise HTTPException(status_code=400, detail="category_id not found")
            doc.category_id = category_row.id
        elif category_name_provided:
            doc.category_id = resolved_category_id
        else:
            doc.category_id = None
    elif category_name_provided:
        doc.category_id = resolved_category_id

    if "tags" in fields_set:
        db.query(DocumentTag).filter(DocumentTag.document_id == doc.id).delete()
        for tag in _upsert_tags(db, req.tags or [], current_user.id):
            db.add(DocumentTag(document_id=doc.id, tag_id=tag.id, created_by=current_user.id))

    tags_snapshot = (req.tags or []) if "tags" in fields_set else _get_tag_names(db, doc.id)
    _append_document_version(
        db,
        doc,
        change_reason="manual_update",
        tags_snapshot=tags_snapshot,
        created_by=current_user.id,
    )
    db.add(
        AuditLog(
            actor_user_id=current_user.id,
            action="DOCUMENT_UPDATE",
            target_type="document",
            target_id=doc.id,
            before_json={
                "title": before["title"],
                "description": before["description"],
                "category_id": str(before["category_id"]) if before["category_id"] else None,
                "event_date": before["event_date"].isoformat() if before["event_date"] else None,
                "review_status": before["review_status"].value,
            },
            after_json={
                "title": doc.title,
                "description": doc.description,
                "category_id": str(doc.category_id) if doc.category_id else None,
                "event_date": doc.event_date.isoformat() if doc.event_date else None,
                "review_status": doc.review_status.value,
                "tags": tags_snapshot,
            },
        )
    )
    _refresh_document_search_vector(db, doc.id)
    db.commit()
    db.refresh(doc)
    enqueue_document_index_sync(doc.id)

    return _to_document_detail_response(db, doc)


@router.delete("/documents/{id}", response_model=DocumentDeleteResponse)
def delete_document(
    id: UUID,
    current_user: CurrentUser = Depends(require_roles(UserRole.EDITOR, UserRole.ADMIN)),
    db: Session = Depends(get_db),
) -> DocumentDeleteResponse:
    doc = db.get(Document, id)
    if not doc:
        raise HTTPException(status_code=404, detail="document not found")

    file_ids = list(
        db.execute(
            select(DocumentFile.file_id).where(DocumentFile.document_id == doc.id)
        ).scalars().all()
    )
    unique_file_ids = list(dict.fromkeys(file_ids))
    file_rows: list[StoredFile] = []
    if unique_file_ids:
        file_rows = list(
            db.execute(select(StoredFile).where(StoredFile.id.in_(unique_file_ids))).scalars().all()
        )

    before_json = {
        "title": doc.title,
        "category_id": str(doc.category_id) if doc.category_id else None,
        "event_date": doc.event_date.isoformat() if doc.event_date else None,
        "file_link_count": len(file_ids),
    }

    db.execute(
        update(IngestJob)
        .where(IngestJob.document_id == doc.id)
        .values(document_id=None)
    )
    db.delete(doc)
    db.flush()

    deleted_orphan_files = 0
    for file_row in file_rows:
        if _cleanup_orphan_file(db, file_row):
            deleted_orphan_files += 1

    db.add(
        AuditLog(
            actor_user_id=current_user.id,
            action="DOCUMENT_DELETE",
            target_type="document",
            target_id=id,
            source=doc.source,
            source_ref=doc.source_ref,
            before_json=before_json,
            after_json={
                "deleted_file_links": len(file_ids),
                "deleted_orphan_files": deleted_orphan_files,
            },
        )
    )
    db.commit()
    enqueue_document_index_delete(id)

    return DocumentDeleteResponse(
        status="deleted",
        document_id=id,
        deleted_file_links=len(file_ids),
        deleted_orphan_files=deleted_orphan_files,
    )


@router.delete("/documents/{id}/files/{file_id}", response_model=DocumentDetailResponse)
def delete_document_file(
    id: UUID,
    file_id: UUID,
    current_user: CurrentUser = Depends(require_roles(UserRole.EDITOR, UserRole.ADMIN)),
    db: Session = Depends(get_db),
) -> DocumentDetailResponse:
    doc = db.get(Document, id)
    if not doc:
        raise HTTPException(status_code=404, detail="document not found")

    link = db.execute(
        select(DocumentFile).where(
            and_(DocumentFile.document_id == doc.id, DocumentFile.file_id == file_id),
        )
    ).scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="file link not found for document")

    file_row = db.get(StoredFile, file_id)
    db.delete(link)
    db.flush()
    _cleanup_orphan_file(db, file_row)

    tags_snapshot = _get_tag_names(db, doc.id)
    _append_document_version(
        db,
        doc,
        change_reason="manual_file_delete",
        tags_snapshot=tags_snapshot,
        created_by=current_user.id,
    )
    remaining_file_count = db.execute(
        select(func.count()).select_from(DocumentFile).where(DocumentFile.document_id == doc.id)
    ).scalar_one()
    db.add(
        AuditLog(
            actor_user_id=current_user.id,
            action="DOCUMENT_FILE_DELETE",
            target_type="document",
            target_id=doc.id,
            before_json={
                "file_id": str(file_id),
            },
            after_json={
                "remaining_file_count": remaining_file_count,
            },
        )
    )
    db.commit()
    db.refresh(doc)
    enqueue_document_index_sync(doc.id)
    return _to_document_detail_response(db, doc)


@router.post("/documents/{id}/files", response_model=DocumentDetailResponse)
def add_document_files(
    id: UUID,
    files: list[UploadFile] = UploadFormFile(...),
    change_reason: str = Form("manual_file_add"),
    current_user: CurrentUser = Depends(require_roles(UserRole.EDITOR, UserRole.ADMIN)),
    db: Session = Depends(get_db),
) -> DocumentDetailResponse:
    doc = db.get(Document, id)
    if not doc:
        raise HTTPException(status_code=404, detail="document not found")
    if not files:
        raise HTTPException(status_code=400, detail="files is required")

    existing_links = db.execute(
        select(DocumentFile.file_id, DocumentFile.is_primary).where(DocumentFile.document_id == doc.id)
    ).all()
    linked_file_ids: set[UUID] = {row.file_id for row in existing_links}
    has_primary = any(bool(row.is_primary) for row in existing_links)
    before_file_count = len(linked_file_ids)

    added_file_ids: list[UUID] = []
    skipped_duplicates = 0
    for upload in files:
        stored = _store_uploaded_file(
            db,
            source=doc.source,
            source_ref=doc.source_ref,
            upload=upload,
            created_by=current_user.id,
        )
        if stored.id in linked_file_ids:
            skipped_duplicates += 1
            continue

        db.add(
            DocumentFile(
                document_id=doc.id,
                file_id=stored.id,
                is_primary=not has_primary,
                created_by=current_user.id,
            )
        )
        linked_file_ids.add(stored.id)
        added_file_ids.append(stored.id)
        has_primary = True

    if added_file_ids:
        tags_snapshot = _get_tag_names(db, doc.id)
        normalized_reason = change_reason.strip() or "manual_file_add"
        _append_document_version(
            db,
            doc,
            change_reason=normalized_reason,
            tags_snapshot=tags_snapshot,
            created_by=current_user.id,
        )
        db.add(
            AuditLog(
                actor_user_id=current_user.id,
                action="DOCUMENT_FILE_ADD",
                target_type="document",
                target_id=doc.id,
                before_json={
                    "file_count": before_file_count,
                },
                after_json={
                    "file_count": len(linked_file_ids),
                    "added_file_ids": [str(file_id) for file_id in added_file_ids],
                    "skipped_duplicates": skipped_duplicates,
                    "change_reason": normalized_reason,
                },
            )
        )
        db.commit()
        db.refresh(doc)
        enqueue_document_index_sync(doc.id)

    return _to_document_detail_response(db, doc)


@router.post("/documents/{id}/files/{file_id}/replace", response_model=DocumentDetailResponse)
def replace_document_file(
    id: UUID,
    file_id: UUID,
    file: UploadFile = UploadFormFile(...),
    change_reason: str = Form("manual_file_replace"),
    current_user: CurrentUser = Depends(require_roles(UserRole.EDITOR, UserRole.ADMIN)),
    db: Session = Depends(get_db),
) -> DocumentDetailResponse:
    doc = db.get(Document, id)
    if not doc:
        raise HTTPException(status_code=404, detail="document not found")

    link = db.execute(
        select(DocumentFile).where(
            and_(DocumentFile.document_id == doc.id, DocumentFile.file_id == file_id),
        )
    ).scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="file link not found for document")

    old_file = db.get(StoredFile, file_id)
    new_file = _store_uploaded_file(
        db,
        source=doc.source,
        source_ref=doc.source_ref,
        upload=file,
        created_by=current_user.id,
    )

    if new_file.id == link.file_id:
        return _to_document_detail_response(db, doc)

    duplicate_link = db.execute(
        select(DocumentFile).where(
            and_(
                DocumentFile.document_id == doc.id,
                DocumentFile.file_id == new_file.id,
                DocumentFile.id != link.id,
            )
        )
    ).scalar_one_or_none()
    if duplicate_link:
        db.delete(link)
    else:
        link.file_id = new_file.id
        db.add(link)
    db.flush()
    _cleanup_orphan_file(db, old_file)

    tags_snapshot = _get_tag_names(db, doc.id)
    normalized_reason = change_reason.strip() or "manual_file_replace"
    _append_document_version(
        db,
        doc,
        change_reason=normalized_reason,
        tags_snapshot=tags_snapshot,
        created_by=current_user.id,
    )
    db.add(
        AuditLog(
            actor_user_id=current_user.id,
            action="DOCUMENT_FILE_REPLACE",
            target_type="document",
            target_id=doc.id,
            before_json={
                "old_file_id": str(file_id),
                "old_file_name": old_file.original_filename if old_file else None,
            },
            after_json={
                "new_file_id": str(new_file.id),
                "new_file_name": new_file.original_filename,
                "change_reason": normalized_reason,
            },
        )
    )
    db.commit()
    db.refresh(doc)
    enqueue_document_index_sync(doc.id)
    return _to_document_detail_response(db, doc)


@router.post("/documents/{id}/reclassify")
def reclassify_document(
    id: UUID,
    req: ReclassifyRequest,
    current_user: CurrentUser = Depends(require_roles(UserRole.REVIEWER, UserRole.EDITOR, UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    doc = db.get(Document, id)
    if not doc:
        raise HTTPException(status_code=404, detail="document not found")

    db.add(
        AuditLog(
            actor_user_id=current_user.id,
            action="DOCUMENT_RECLASSIFY_REQUEST",
            target_type="document",
            target_id=doc.id,
            after_json={
                "rule_version_id": str(req.rule_version_id),
                "dry_run": req.dry_run,
            },
        )
    )
    db.commit()

    return {
        "status": "accepted",
        "document_id": str(id),
        "rule_version_id": str(req.rule_version_id),
        "dry_run": req.dry_run,
    }
