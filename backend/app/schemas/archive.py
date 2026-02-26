from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.db.models import ReviewStatus


class ArchiveMonthNode(BaseModel):
    month: int
    count: int


class ArchiveYearNode(BaseModel):
    year: int
    count: int
    months: list[ArchiveMonthNode] = Field(default_factory=list)


class ArchiveCategoryNode(BaseModel):
    category: str
    count: int
    years: list[ArchiveYearNode] = Field(default_factory=list)


class ArchiveTreeResponse(BaseModel):
    categories: list[ArchiveCategoryNode] = Field(default_factory=list)
    generated_at: datetime


class ArchiveSetRevisionItem(BaseModel):
    document_id: UUID
    title: str
    category: str | None = None
    event_date: date | None = None
    ingested_at: datetime
    review_status: ReviewStatus
    file_count: int
    tags: list[str] = Field(default_factory=list)
    revision: str | None = None
    kind: str | None = None
    language: str | None = None
    source_ref: str | None = None


class ArchiveSetDocumentNode(BaseModel):
    document_key: str
    display_title: str
    latest_event_date: date | None = None
    revision_count: int
    needs_review_count: int
    kinds: list[str] = Field(default_factory=list)
    revisions: list[ArchiveSetRevisionItem] = Field(default_factory=list)
    has_more_revisions: bool = False


class ArchiveSetNode(BaseModel):
    set_key: str
    set_label: str
    latest_event_date: date | None = None
    document_count: int
    revision_count: int
    needs_review_count: int
    documents: list[ArchiveSetDocumentNode] = Field(default_factory=list)
    has_more_documents: bool = False


class ArchiveSetsResponse(BaseModel):
    items: list[ArchiveSetNode] = Field(default_factory=list)
    page: int
    size: int
    total_sets: int
    generated_at: datetime
    truncated: bool = False
    max_documents_scanned: int
