from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, literal, select
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, require_roles
from app.db.models import Category, Document, IngestJob, IngestState, ReviewStatus, UserRole
from app.db.session import get_db
from app.schemas.dashboard import (
    DashboardCategoryCount,
    DashboardErrorCodeCount,
    DashboardRecentDocument,
    DashboardSummaryResponse,
)

router = APIRouter()


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


@router.get("/dashboard/summary", response_model=DashboardSummaryResponse)
def get_dashboard_summary(
    recent_limit: int = Query(10, ge=1, le=50),
    _: CurrentUser = Depends(require_roles(UserRole.VIEWER, UserRole.REVIEWER, UserRole.EDITOR, UserRole.ADMIN)),
    db: Session = Depends(get_db),
) -> DashboardSummaryResponse:
    now = _now()
    recent_cutoff = now - timedelta(days=7)

    total_documents = db.execute(select(func.count(Document.id))).scalar_one()
    recent_uploads_7d = db.execute(
        select(func.count(Document.id)).where(Document.ingested_at >= recent_cutoff)
    ).scalar_one()
    needs_review_count = db.execute(
        select(func.count(Document.id)).where(Document.review_status == ReviewStatus.NEEDS_REVIEW)
    ).scalar_one()
    failed_jobs_count = db.execute(
        select(func.count(IngestJob.id)).where(IngestJob.state == IngestState.FAILED)
    ).scalar_one()
    retry_scheduled_count = db.execute(
        select(func.count(IngestJob.id)).where(
            IngestJob.state == IngestState.RECEIVED,
            IngestJob.retry_after.is_not(None),
        )
    ).scalar_one()
    dead_letter_count = db.execute(
        select(func.count(IngestJob.id)).where(
            IngestJob.state == IngestState.FAILED,
            IngestJob.last_error_code == "DLQ_MAX_ATTEMPTS",
        )
    ).scalar_one()

    error_code_label = func.coalesce(IngestJob.last_error_code, literal("UNKNOWN")).label("error_code")
    error_rows = db.execute(
        select(error_code_label, func.count(IngestJob.id).label("count"))
        .where(IngestJob.state == IngestState.FAILED)
        .group_by(error_code_label)
        .order_by(func.count(IngestJob.id).desc(), error_code_label.asc())
        .limit(10)
    ).all()
    failed_error_codes = [
        DashboardErrorCodeCount(error_code=row.error_code, count=row.count)
        for row in error_rows
    ]

    category_label = func.coalesce(Category.name, literal("미분류")).label("category")
    category_rows = db.execute(
        select(category_label, func.count(Document.id).label("count"))
        .select_from(Document)
        .outerjoin(Category, Category.id == Document.category_id)
        .group_by(category_label)
        .order_by(func.count(Document.id).desc(), category_label.asc())
        .limit(20)
    ).all()
    categories = [DashboardCategoryCount(category=row.category, count=row.count) for row in category_rows]

    recent_rows = db.execute(
        select(
            Document.id,
            Document.title,
            Document.event_date,
            Document.ingested_at,
            Document.review_status,
            func.coalesce(Category.name, literal("미분류")).label("category"),
        )
        .select_from(Document)
        .outerjoin(Category, Category.id == Document.category_id)
        .order_by(Document.ingested_at.desc())
        .limit(recent_limit)
    ).all()
    recent_documents = [
        DashboardRecentDocument(
            id=row.id,
            title=row.title,
            category=row.category,
            event_date=row.event_date,
            ingested_at=row.ingested_at,
            review_status=row.review_status,
        )
        for row in recent_rows
    ]

    return DashboardSummaryResponse(
        total_documents=total_documents,
        recent_uploads_7d=recent_uploads_7d,
        needs_review_count=needs_review_count,
        failed_jobs_count=failed_jobs_count,
        retry_scheduled_count=retry_scheduled_count,
        dead_letter_count=dead_letter_count,
        failed_error_codes=failed_error_codes,
        categories=categories,
        recent_documents=recent_documents,
        generated_at=now,
    )
