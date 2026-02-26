from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.db.models import IngestState, SourceType


class AuditLogItem(BaseModel):
    id: int
    created_at: datetime
    actor_user_id: UUID | None = None
    actor_username: str | None = None
    action: str
    target_type: str
    target_id: UUID | None = None
    source: SourceType | None = None
    source_ref: str | None = None
    masked_fields: list[str] = Field(default_factory=list)
    before_json: dict[str, Any] | None = None
    after_json: dict[str, Any] | None = None


class AuditLogsResponse(BaseModel):
    items: list[AuditLogItem]
    page: int
    size: int
    total: int


class IngestJobItem(BaseModel):
    id: UUID
    source: SourceType
    source_ref: str | None = None
    state: IngestState
    document_id: UUID | None = None
    attempt_count: int
    max_attempts: int
    last_error_code: str | None = None
    last_error_message: str | None = None
    retry_after: datetime | None = None
    received_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class IngestJobsResponse(BaseModel):
    items: list[IngestJobItem]
    page: int
    size: int
    total: int


class IngestEventItem(BaseModel):
    id: int
    ingest_job_id: UUID
    from_state: IngestState | None = None
    to_state: IngestState
    event_type: str
    event_message: str
    event_payload: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime


class IngestEventsResponse(BaseModel):
    ingest_job_id: UUID
    items: list[IngestEventItem]


class RequeueIngestJobRequest(BaseModel):
    force: bool = False
    reset_attempts: bool = False
    clear_error: bool = True


class RequeueIngestJobResponse(BaseModel):
    job_id: UUID
    previous_state: IngestState
    state: IngestState
    enqueued: bool
    queued_at: datetime


class RecoverIngestJobUploadResponse(BaseModel):
    job_id: UUID
    previous_state: IngestState
    state: IngestState
    enqueued: bool
    queued_at: datetime
    uploaded_filename: str
    uploaded_size_bytes: int


class OpsReportItem(BaseModel):
    id: int
    created_at: datetime
    period_start: datetime
    period_end: datetime
    ingest_total: int
    failed_jobs: int
    failure_rate_pct: float
    classified_docs: int
    auto_classified_docs: int
    classification_accuracy_pct: float
    needs_review_open: int
    review_resolution_count: int
    review_queue_avg_resolution_hours: float | None = None


class OpsReportsResponse(BaseModel):
    items: list[OpsReportItem]
    page: int
    size: int
    total: int


class OpsReportGenerateResponse(BaseModel):
    task_id: str
    status: str
