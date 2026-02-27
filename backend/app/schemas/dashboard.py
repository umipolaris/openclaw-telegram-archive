from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.db.models import ReviewStatus


class DashboardCategoryCount(BaseModel):
    category: str
    count: int


class DashboardErrorCodeCount(BaseModel):
    error_code: str
    count: int


class DashboardRecentDocument(BaseModel):
    id: UUID
    title: str
    category: str
    event_date: date | None = None
    ingested_at: datetime
    review_status: ReviewStatus


class DashboardPinnedDocument(BaseModel):
    id: UUID
    title: str
    category: str
    event_date: date | None = None
    ingested_at: datetime
    review_status: ReviewStatus


class DashboardPinnedCategory(BaseModel):
    category: str
    count: int
    documents: list[DashboardPinnedDocument] = Field(default_factory=list)


class DashboardSummaryResponse(BaseModel):
    total_documents: int
    recent_uploads_7d: int
    needs_review_count: int
    failed_jobs_count: int
    retry_scheduled_count: int
    dead_letter_count: int
    failed_error_codes: list[DashboardErrorCodeCount] = Field(default_factory=list)
    categories: list[DashboardCategoryCount] = Field(default_factory=list)
    pinned_by_category: list[DashboardPinnedCategory] = Field(default_factory=list)
    recent_documents: list[DashboardRecentDocument] = Field(default_factory=list)
    generated_at: datetime
