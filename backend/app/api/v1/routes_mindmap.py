from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Date, cast, func, literal, or_, select
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, require_roles
from app.db.models import Category, Document, DocumentFile, DocumentTag, Tag, UserRole
from app.db.session import get_db
from app.schemas.mindmap import (
    MindMapCategoryNode,
    MindMapDocumentNode,
    MindMapTagNode,
    MindMapTreeResponse,
)

router = APIRouter()

UNTAGGED_LABEL = "(태그없음)"


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _apply_keyword_filter(stmt, q: str | None):
    if not q or not q.strip():
        return stmt
    keyword = f"%{q.strip().lower()}%"
    return stmt.where(
        or_(
            func.lower(Document.title).like(keyword),
            func.lower(Document.description).like(keyword),
        )
    )


@router.get("/mindmap/tree", response_model=MindMapTreeResponse)
def get_mindmap_tree(
    category_name: str | None = Query(None, description="선택된 카테고리명"),
    tag_name: str | None = Query(None, description="선택된 태그명"),
    q: str | None = Query(None, description="제목/설명 키워드"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    tag_limit: int = Query(120, ge=1, le=500),
    _: CurrentUser = Depends(require_roles(UserRole.VIEWER, UserRole.REVIEWER, UserRole.EDITOR, UserRole.ADMIN)),
    db: Session = Depends(get_db),
) -> MindMapTreeResponse:
    if tag_name and not category_name:
        raise HTTPException(status_code=400, detail="tag_name은 category_name과 함께 사용해야 합니다.")

    category_label_expr = func.coalesce(Category.name, literal("미분류"))
    category_label = category_label_expr.label("category")
    base_date_expr = func.coalesce(Document.event_date, cast(Document.ingested_at, Date))

    category_doc_count = func.count(Document.id).label("document_count")
    category_latest_date = func.max(base_date_expr).label("latest_event_date")

    category_stmt = (
        select(category_label, category_doc_count, category_latest_date)
        .select_from(Document)
        .outerjoin(Category, Category.id == Document.category_id)
        .group_by(category_label)
        .order_by(category_doc_count.desc(), category_label.asc())
    )
    category_stmt = _apply_keyword_filter(category_stmt, q)
    category_rows = db.execute(category_stmt).all()
    categories = [
        MindMapCategoryNode(
            category=row.category,
            document_count=int(row.document_count or 0),
            latest_event_date=row.latest_event_date,
        )
        for row in category_rows
    ]

    tags: list[MindMapTagNode] = []
    documents: list[MindMapDocumentNode] = []
    total_documents = 0

    if category_name:
        tag_label = func.coalesce(Tag.name, literal(UNTAGGED_LABEL)).label("tag")
        tag_doc_count = func.count(func.distinct(Document.id)).label("document_count")
        tag_latest_date = func.max(base_date_expr).label("latest_event_date")

        tag_stmt = (
            select(tag_label, tag_doc_count, tag_latest_date)
            .select_from(Document)
            .outerjoin(Category, Category.id == Document.category_id)
            .outerjoin(DocumentTag, DocumentTag.document_id == Document.id)
            .outerjoin(Tag, Tag.id == DocumentTag.tag_id)
            .where(category_label_expr == category_name)
            .group_by(tag_label)
            .order_by(tag_doc_count.desc(), tag_label.asc())
            .limit(tag_limit)
        )
        tag_stmt = _apply_keyword_filter(tag_stmt, q)
        tag_rows = db.execute(tag_stmt).all()
        tags = [
            MindMapTagNode(
                tag=row.tag,
                document_count=int(row.document_count or 0),
                latest_event_date=row.latest_event_date,
            )
            for row in tag_rows
        ]

        selected_tag = tag_name
        if selected_tag is None and tags:
            selected_tag = tags[0].tag

        if selected_tag:
            tag_exists_expr = (
                select(1)
                .select_from(DocumentTag)
                .join(Tag, Tag.id == DocumentTag.tag_id)
                .where(
                    DocumentTag.document_id == Document.id,
                    Tag.name == selected_tag,
                )
                .exists()
            )
            untagged_exists_expr = (
                select(1)
                .select_from(DocumentTag)
                .where(DocumentTag.document_id == Document.id)
                .exists()
            )

            document_count_stmt = (
                select(func.count(func.distinct(Document.id)))
                .select_from(Document)
                .outerjoin(Category, Category.id == Document.category_id)
                .where(category_label_expr == category_name)
            )
            document_count_stmt = _apply_keyword_filter(document_count_stmt, q)
            if selected_tag == UNTAGGED_LABEL:
                document_count_stmt = document_count_stmt.where(~untagged_exists_expr)
            else:
                document_count_stmt = document_count_stmt.where(tag_exists_expr)
            total_documents = int(db.execute(document_count_stmt).scalar_one() or 0)

            file_count_col = func.count(func.distinct(DocumentFile.file_id)).label("file_count")
            document_stmt = (
                select(
                    Document.id,
                    Document.title,
                    category_label,
                    Document.event_date,
                    Document.updated_at,
                    file_count_col,
                )
                .select_from(Document)
                .outerjoin(Category, Category.id == Document.category_id)
                .outerjoin(DocumentFile, DocumentFile.document_id == Document.id)
                .where(category_label_expr == category_name)
                .group_by(
                    Document.id,
                    Document.title,
                    category_label,
                    Document.event_date,
                    Document.updated_at,
                    Document.ingested_at,
                )
                .order_by(base_date_expr.desc(), Document.updated_at.desc(), Document.title.asc())
                .offset((page - 1) * size)
                .limit(size)
            )
            document_stmt = _apply_keyword_filter(document_stmt, q)
            if selected_tag == UNTAGGED_LABEL:
                document_stmt = document_stmt.where(~untagged_exists_expr)
            else:
                document_stmt = document_stmt.where(tag_exists_expr)

            document_rows = db.execute(document_stmt).all()
            document_ids = [row.id for row in document_rows]

            tag_map: dict = {}
            if document_ids:
                tag_rows_for_docs = db.execute(
                    select(DocumentTag.document_id, Tag.name)
                    .join(Tag, Tag.id == DocumentTag.tag_id)
                    .where(DocumentTag.document_id.in_(document_ids))
                    .order_by(DocumentTag.document_id.asc(), Tag.name.asc())
                ).all()
                for document_id, tag in tag_rows_for_docs:
                    tag_map.setdefault(document_id, []).append(tag)

            documents = [
                MindMapDocumentNode(
                    id=row.id,
                    title=row.title,
                    category=row.category,
                    event_date=row.event_date,
                    updated_at=row.updated_at,
                    file_count=int(row.file_count or 0),
                    tags=tag_map.get(row.id, []),
                )
                for row in document_rows
            ]

            tag_name = selected_tag

    return MindMapTreeResponse(
        generated_at=_now(),
        selected_category=category_name,
        selected_tag=tag_name,
        categories=categories,
        tags=tags,
        documents=documents,
        page=page,
        size=size,
        total_documents=total_documents,
    )
