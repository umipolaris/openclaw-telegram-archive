from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.db.models import IngestState, SourceType


class IngestAcceptedResponse(BaseModel):
    job_id: UUID
    state: IngestState
    source: SourceType
    source_ref: str | None
    queued_at: datetime


class IngestJobStatusResponse(BaseModel):
    job_id: UUID
    state: IngestState
    source: SourceType
    source_ref: str | None = None
    document_id: UUID | None = None
    attempt_count: int
    max_attempts: int
    last_error_code: str | None = None
    last_error_message: str | None = None
    received_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    is_terminal: bool
    success: bool


class IngestBatchRejectedItem(BaseModel):
    index: int
    filename: str
    source_ref: str | None = None
    error: str


class IngestBatchAcceptedResponse(BaseModel):
    total_files: int
    accepted_count: int
    rejected_count: int
    accepted: list[IngestAcceptedResponse] = Field(default_factory=list)
    rejected: list[IngestBatchRejectedItem] = Field(default_factory=list)


class TelegramIngestPayload(BaseModel):
    source: SourceType = SourceType.telegram
    source_ref: str
    message_id: str
    chat_id: str
    sent_at: datetime | None = None
    caption: str | None = None


class ManualIngestPayload(BaseModel):
    source: SourceType
    caption: str | None = None
    title: str | None = None
    description: str | None = None


class IngestResultAction(BaseModel):
    kind: str
    action: str
    label: str
    method: str | None = None
    url: str | None = None
    token: str | None = None
    expires_at: datetime | None = None
    command: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class IngestResultPayload(BaseModel):
    job_id: UUID
    state: IngestState
    success: bool
    document_id: UUID | None = None
    title: str | None = None
    category: str | None = None
    event_date: str | None = None
    review_needed: bool = False
    error_code: str | None = None
    error_message: str | None = None
    dashboard_url: str | None = None
    actions: list[IngestResultAction] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)


class IngestActionRequest(BaseModel):
    reset_attempts: bool = False
    clear_error: bool = True
    force: bool = False
    caption_override: str | None = None


class IngestActionResponse(BaseModel):
    job_id: UUID
    action: str
    previous_state: IngestState
    state: IngestState
    enqueued: bool
    queued_at: datetime
    attempt_count: int
