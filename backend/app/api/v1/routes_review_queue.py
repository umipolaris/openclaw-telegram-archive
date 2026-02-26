from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, require_roles
from app.db.models import AuditLog, Document, DocumentTag, DocumentVersion, ReviewStatus, Tag
from app.db.models import UserRole
from app.db.session import get_db
from app.schemas.document import (
    ReviewQueueBulkRequest,
    ReviewQueueBulkResponse,
    ReviewQueueItem,
    ReviewQueueResponse,
    ReviewQueueUpdateRequest,
    ReviewQueueUpdateResult,
)
from app.services.search_sync_service import enqueue_document_index_sync, enqueue_document_index_sync_many
from app.services.taxonomy_service import upsert_category, upsert_tags

router = APIRouter()


_REASON_CLASSIFY_FAIL = "CLASSIFY_FAIL"
_REASON_DATE_MISSING = "DATE_MISSING"


def _get_tag_names(db: Session, document_id: UUID) -> list[str]:
    stmt = (
        select(Tag.name)
        .join(DocumentTag, DocumentTag.tag_id == Tag.id)
        .where(DocumentTag.document_id == document_id)
        .order_by(Tag.name.asc())
    )
    return list(db.execute(stmt).scalars().all())


def _replace_document_tags(db: Session, document_id: UUID, tag_names: list[str]) -> list[str]:
    db.query(DocumentTag).filter(DocumentTag.document_id == document_id).delete(synchronize_session=False)

    tags = upsert_tags(db, tag_names)
    for tag in tags:
        db.add(DocumentTag(document_id=document_id, tag_id=tag.id))

    db.flush()
    return [t.name for t in tags]


def _apply_review_update(
    db: Session,
    doc: Document,
    req: ReviewQueueUpdateRequest,
    source: str,
    actor: CurrentUser,
) -> ReviewQueueUpdateResult:
    old_tag_names = _get_tag_names(db, doc.id)
    before_json = {
        "category_id": str(doc.category_id) if doc.category_id else None,
        "event_date": doc.event_date.isoformat() if doc.event_date else None,
        "review_status": doc.review_status.value,
        "review_reasons": list(doc.review_reasons),
        "tags": old_tag_names,
    }

    changed = False

    if req.category_id is not None:
        if doc.category_id != req.category_id:
            doc.category_id = req.category_id
            changed = True
    elif req.category_name:
        category = upsert_category(db, req.category_name)
        category_id = category.id if category else None
        if doc.category_id != category_id:
            doc.category_id = category_id
            changed = True

    if (req.category_id is not None or req.category_name) and _REASON_CLASSIFY_FAIL in doc.review_reasons:
        doc.review_reasons = [r for r in doc.review_reasons if r != _REASON_CLASSIFY_FAIL]
        changed = True

    if req.event_date is not None and doc.event_date != req.event_date:
        doc.event_date = req.event_date
        changed = True

    if req.event_date is not None and _REASON_DATE_MISSING in doc.review_reasons:
        doc.review_reasons = [r for r in doc.review_reasons if r != _REASON_DATE_MISSING]
        changed = True

    if req.reason_remove:
        before = list(doc.review_reasons)
        remove_set = set(req.reason_remove)
        doc.review_reasons = [r for r in doc.review_reasons if r not in remove_set]
        if before != doc.review_reasons:
            changed = True

    new_tag_names = old_tag_names
    if req.tags is not None:
        normalized = sorted(set(tag.strip() for tag in req.tags if tag.strip()))
        if sorted(old_tag_names) != normalized:
            new_tag_names = _replace_document_tags(db, doc.id, normalized)
            changed = True

    if req.approve:
        if doc.review_reasons:
            doc.review_reasons = []
            changed = True
        if doc.review_status != ReviewStatus.RESOLVED:
            doc.review_status = ReviewStatus.RESOLVED
            changed = True
    else:
        desired_status = ReviewStatus.NEEDS_REVIEW if doc.review_reasons else ReviewStatus.RESOLVED
        if doc.review_status != desired_status:
            doc.review_status = desired_status
            changed = True

    if not changed:
        return ReviewQueueUpdateResult(
            document_id=doc.id,
            updated=False,
            review_status=doc.review_status,
            review_reasons=doc.review_reasons,
        )

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
            tags_snapshot=new_tag_names,
            change_reason=f"review_queue_{source}",
            created_by=actor.id,
        )
    )

    after_json = {
        "category_id": str(doc.category_id) if doc.category_id else None,
        "event_date": doc.event_date.isoformat() if doc.event_date else None,
        "review_status": doc.review_status.value,
        "review_reasons": list(doc.review_reasons),
        "tags": new_tag_names,
        "note": req.note,
    }

    db.add(
        AuditLog(
            action="REVIEW_QUEUE_UPDATE",
            target_type="document",
            target_id=doc.id,
            actor_user_id=actor.id,
            before_json=before_json,
            after_json=after_json,
        )
    )

    return ReviewQueueUpdateResult(
        document_id=doc.id,
        updated=True,
        review_status=doc.review_status,
        review_reasons=doc.review_reasons,
    )


@router.get("/review-queue", response_model=ReviewQueueResponse)
def get_review_queue(
    reason: str | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    _: CurrentUser = Depends(require_roles(UserRole.REVIEWER, UserRole.ADMIN)),
    db: Session = Depends(get_db),
) -> ReviewQueueResponse:
    filters = [Document.review_status == ReviewStatus.NEEDS_REVIEW]
    if reason:
        filters.append(Document.review_reasons.any(reason))

    where_clause = and_(*filters)
    total = db.execute(select(func.count(Document.id)).where(where_clause)).scalar_one()

    docs = db.execute(
        select(Document)
        .where(where_clause)
        .order_by(Document.ingested_at.desc())
        .offset((page - 1) * size)
        .limit(size)
    ).scalars().all()

    items = [
        ReviewQueueItem(
            document_id=d.id,
            reasons=d.review_reasons,
            title=d.title,
            source_ref=d.source_ref,
            suggested_actions=["set_category", "set_event_date", "set_tags", "approve"],
        )
        for d in docs
    ]

    return ReviewQueueResponse(items=items, total=total)


@router.patch("/review-queue/{document_id}", response_model=ReviewQueueUpdateResult)
def patch_review_queue_item(
    document_id: UUID,
    req: ReviewQueueUpdateRequest,
    current_user: CurrentUser = Depends(require_roles(UserRole.REVIEWER, UserRole.ADMIN)),
    db: Session = Depends(get_db),
) -> ReviewQueueUpdateResult:
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="document not found")

    result = _apply_review_update(db, doc, req, source="single", actor=current_user)
    db.commit()
    if result.updated:
        enqueue_document_index_sync(doc.id)
    return result


@router.post("/review-queue/bulk", response_model=ReviewQueueBulkResponse)
def bulk_update_review_queue(
    req: ReviewQueueBulkRequest,
    current_user: CurrentUser = Depends(require_roles(UserRole.REVIEWER, UserRole.ADMIN)),
    db: Session = Depends(get_db),
) -> ReviewQueueBulkResponse:
    if not req.document_ids:
        raise HTTPException(status_code=400, detail="document_ids required")

    existing_docs = db.execute(
        select(Document).where(Document.id.in_(req.document_ids))
    ).scalars().all()
    found_ids = {doc.id for doc in existing_docs}

    not_found = [doc_id for doc_id in req.document_ids if doc_id not in found_ids]

    results: list[ReviewQueueUpdateResult] = []
    updated_count = 0
    for doc in existing_docs:
        result = _apply_review_update(db, doc, req.update, source="bulk", actor=current_user)
        results.append(result)
        if result.updated:
            updated_count += 1

    db.add(
        AuditLog(
            action="REVIEW_QUEUE_BULK_UPDATE",
            target_type="review_queue",
            actor_user_id=current_user.id,
            after_json={
                "requested": len(req.document_ids),
                "updated": updated_count,
                "not_found": [str(x) for x in not_found],
                "update": req.update.model_dump(mode="json"),
            },
        )
    )

    db.commit()
    if updated_count > 0:
        updated_doc_ids = [result.document_id for result in results if result.updated]
        enqueue_document_index_sync_many(updated_doc_ids)

    return ReviewQueueBulkResponse(
        requested=len(req.document_ids),
        updated=updated_count,
        not_found=not_found,
        results=results,
    )
