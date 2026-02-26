from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Literal
from uuid import UUID

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.models import Category, Document, DocumentTag, ReviewStatus, Tag

logger = structlog.get_logger(__name__)
_INDEX_READY: set[str] = set()


class MeiliSearchError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, code: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code


@dataclass(slots=True)
class MeiliSearchResult:
    ids: list[UUID]
    total: int


def is_meili_enabled(settings: Settings | None = None) -> bool:
    cfg = settings or get_settings()
    return cfg.search_backend.strip().lower() == "meili"


def _meili_headers(settings: Settings) -> dict[str, str]:
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if settings.meili_api_key:
        headers["Authorization"] = f"Bearer {settings.meili_api_key}"
    return headers


def _meili_error(response: httpx.Response) -> MeiliSearchError:
    detail = ""
    code = None
    try:
        payload = response.json()
        detail = payload.get("message") or payload.get("error") or ""
        code = payload.get("code")
    except Exception:  # noqa: BLE001
        detail = response.text
    msg = f"meili request failed ({response.status_code})"
    if detail:
        msg = f"{msg}: {detail}"
    return MeiliSearchError(msg, status_code=response.status_code, code=code)


def _request_json(
    method: str,
    path: str,
    *,
    settings: Settings,
    json_body: dict | list | None = None,
) -> dict[str, Any]:
    base_url = settings.meili_url.rstrip("/")
    with httpx.Client(
        base_url=base_url,
        headers=_meili_headers(settings),
        timeout=settings.meili_timeout_seconds,
    ) as client:
        response = client.request(method, path, json=json_body)
    if response.status_code >= 400:
        raise _meili_error(response)
    if not response.content:
        return {}
    return response.json()


def ensure_document_index(settings: Settings | None = None) -> None:
    cfg = settings or get_settings()
    if not is_meili_enabled(cfg):
        return

    index_uid = cfg.meili_index_documents
    cache_key = f"{cfg.meili_url.rstrip('/')}/{index_uid}"
    if cache_key in _INDEX_READY:
        return

    try:
        _request_json(
            "POST",
            "/indexes",
            settings=cfg,
            json_body={"uid": index_uid, "primaryKey": "id"},
        )
    except MeiliSearchError as exc:
        if exc.code not in {"index_already_exists"} and exc.status_code != 409:
            raise

    _request_json(
        "PATCH",
        f"/indexes/{index_uid}/settings",
        settings=cfg,
        json_body={
            "searchableAttributes": [
                "title",
                "description",
                "summary",
                "caption_raw",
                "category",
                "tags",
                "source_ref",
            ],
            "filterableAttributes": [
                "category_id",
                "category",
                "review_status",
                "source",
                "source_ref",
                "event_date",
                "tag_slugs",
                "is_uncategorized",
            ],
            "sortableAttributes": ["event_date", "ingested_at", "title", "created_at"],
        },
    )
    _INDEX_READY.add(cache_key)


def _escape_filter_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def build_filter_expression(
    *,
    category_id: UUID | None = None,
    category_name: str | None = None,
    tag_slug: str | None = None,
    event_date_from: date | None = None,
    event_date_to: date | None = None,
    review_status: ReviewStatus | str | None = None,
) -> str | None:
    clauses: list[str] = []

    if category_id:
        clauses.append(f'category_id = "{category_id}"')
    if category_name:
        if category_name == "미분류":
            clauses.append("is_uncategorized = true")
        else:
            clauses.append(f'category = "{_escape_filter_value(category_name)}"')
    if tag_slug:
        clauses.append(f'tag_slugs = "{_escape_filter_value(tag_slug)}"')
    if event_date_from:
        clauses.append(f'event_date >= "{event_date_from.isoformat()}"')
    if event_date_to:
        clauses.append(f'event_date <= "{event_date_to.isoformat()}"')
    if review_status:
        value = review_status.value if isinstance(review_status, ReviewStatus) else str(review_status)
        clauses.append(f'review_status = "{_escape_filter_value(value)}"')

    if not clauses:
        return None
    return " AND ".join(clauses)


def search_document_ids(
    query: str,
    *,
    page: int,
    size: int,
    sort_by: Literal["event_date", "ingested_at", "title", "created_at"] = "event_date",
    sort_order: Literal["asc", "desc"] = "desc",
    category_id: UUID | None = None,
    category_name: str | None = None,
    tag_slug: str | None = None,
    event_date_from: date | None = None,
    event_date_to: date | None = None,
    review_status: ReviewStatus | None = None,
    settings: Settings | None = None,
) -> MeiliSearchResult:
    cfg = settings or get_settings()
    if not is_meili_enabled(cfg):
        raise MeiliSearchError("search backend is not meili")

    ensure_document_index(cfg)

    payload: dict[str, Any] = {
        "q": query,
        "offset": max(0, (page - 1) * size),
        "limit": max(1, size),
    }
    filter_expr = build_filter_expression(
        category_id=category_id,
        category_name=category_name,
        tag_slug=tag_slug,
        event_date_from=event_date_from,
        event_date_to=event_date_to,
        review_status=review_status,
    )
    if filter_expr:
        payload["filter"] = filter_expr
    payload["sort"] = [f"{sort_by}:{sort_order}"]

    index_uid = cfg.meili_index_documents
    try:
        body = _request_json(
            "POST",
            f"/indexes/{index_uid}/search",
            settings=cfg,
            json_body=payload,
        )
    except MeiliSearchError as exc:
        if exc.code == "index_not_found":
            _INDEX_READY.discard(f"{cfg.meili_url.rstrip('/')}/{index_uid}")
            ensure_document_index(cfg)
            body = _request_json(
                "POST",
                f"/indexes/{index_uid}/search",
                settings=cfg,
                json_body=payload,
            )
        else:
            raise

    ids: list[UUID] = []
    for hit in body.get("hits", []):
        raw_id = hit.get("id")
        if raw_id is None:
            continue
        try:
            ids.append(UUID(str(raw_id)))
        except ValueError:
            continue

    total = int(body.get("totalHits") or body.get("estimatedTotalHits") or len(ids))
    return MeiliSearchResult(ids=ids, total=total)


def _build_documents_payload(db: Session, document_ids: list[UUID]) -> list[dict[str, Any]]:
    if not document_ids:
        return []

    unique_ids = list(dict.fromkeys(document_ids))
    rows = db.execute(
        select(Document, Category.name.label("category_name"))
        .outerjoin(Category, Category.id == Document.category_id)
        .where(Document.id.in_(unique_ids))
    ).all()
    row_map: dict[UUID, tuple[Document, str | None]] = {}
    for row in rows:
        row_map[row[0].id] = (row[0], row.category_name)

    tag_rows = db.execute(
        select(DocumentTag.document_id, Tag.name, Tag.slug)
        .join(Tag, Tag.id == DocumentTag.tag_id)
        .where(DocumentTag.document_id.in_(unique_ids))
        .order_by(DocumentTag.document_id.asc(), Tag.name.asc())
    ).all()
    tag_names_map: dict[UUID, list[str]] = {}
    tag_slugs_map: dict[UUID, list[str]] = {}
    for document_id, tag_name, tag_slug in tag_rows:
        tag_names_map.setdefault(document_id, []).append(tag_name)
        tag_slugs_map.setdefault(document_id, []).append(tag_slug)

    payloads: list[dict[str, Any]] = []
    for doc_id in unique_ids:
        row = row_map.get(doc_id)
        if not row:
            continue
        doc, category_name = row
        payloads.append(
            {
                "id": str(doc.id),
                "title": doc.title,
                "description": doc.description,
                "summary": doc.summary,
                "caption_raw": doc.caption_raw,
                "source": doc.source.value,
                "source_ref": doc.source_ref,
                "category_id": str(doc.category_id) if doc.category_id else None,
                "category": category_name,
                "event_date": doc.event_date.isoformat() if doc.event_date else None,
                "ingested_at": doc.ingested_at.isoformat() if doc.ingested_at else None,
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
                "review_status": doc.review_status.value,
                "tags": tag_names_map.get(doc.id, []),
                "tag_slugs": tag_slugs_map.get(doc.id, []),
                "is_uncategorized": doc.category_id is None,
            }
        )
    return payloads


def upsert_documents(db: Session, document_ids: list[UUID], *, settings: Settings | None = None) -> int:
    cfg = settings or get_settings()
    if not is_meili_enabled(cfg):
        return 0
    if not document_ids:
        return 0

    payloads = _build_documents_payload(db, document_ids)
    if not payloads:
        return 0

    ensure_document_index(cfg)
    _request_json(
        "POST",
        f"/indexes/{cfg.meili_index_documents}/documents",
        settings=cfg,
        json_body=payloads,
    )
    return len(payloads)


def delete_document(document_id: UUID, *, settings: Settings | None = None) -> None:
    cfg = settings or get_settings()
    if not is_meili_enabled(cfg):
        return
    ensure_document_index(cfg)
    _request_json(
        "DELETE",
        f"/indexes/{cfg.meili_index_documents}/documents/{document_id}",
        settings=cfg,
    )


def rebuild_documents_index(
    db: Session,
    *,
    batch_size: int = 500,
    limit: int | None = None,
    settings: Settings | None = None,
) -> dict[str, int]:
    cfg = settings or get_settings()
    if not is_meili_enabled(cfg):
        return {"processed": 0, "indexed": 0}

    size = max(1, int(batch_size))
    processed = 0
    indexed = 0
    offset = 0

    while True:
        remaining = None if limit is None else max(0, int(limit) - processed)
        if remaining == 0:
            break
        chunk_size = size if remaining is None else min(size, remaining)
        ids = list(
            db.execute(
                select(Document.id)
                .order_by(Document.created_at.asc())
                .offset(offset)
                .limit(chunk_size)
            ).scalars().all()
        )
        if not ids:
            break

        indexed += upsert_documents(db, ids, settings=cfg)
        processed += len(ids)
        offset += len(ids)

    return {"processed": processed, "indexed": indexed}


def meili_health_status(settings: Settings | None = None) -> str:
    cfg = settings or get_settings()
    if not is_meili_enabled(cfg):
        return "disabled"
    try:
        body = _request_json("GET", "/health", settings=cfg)
        if body.get("status") == "available":
            return "ok"
        return "degraded"
    except Exception as exc:  # noqa: BLE001
        logger.warning("meili_healthcheck_failed", error=str(exc))
        return "error"
