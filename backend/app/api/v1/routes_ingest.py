import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, require_roles
from app.db.models import AuditLog, IngestEvent, IngestJob, IngestState, SourceType
from app.db.session import get_db
from app.schemas.ingest import (
    IngestAcceptedResponse,
    IngestActionRequest,
    IngestActionResponse,
    IngestBatchAcceptedResponse,
    IngestBatchRejectedItem,
    IngestJobStatusResponse,
)
from app.services.openclaw_actions import OpenClawActionTokenError, verify_action_token
from app.worker.tasks_ingest import process_ingest_job_task
from app.db.models import UserRole

router = APIRouter()

_TMP_DIR = Path(tempfile.gettempdir()) / "doc-archive-ingest"
_TMP_DIR.mkdir(parents=True, exist_ok=True)
_MAX_BATCH_FILES = 50


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _save_upload_temp(upload: UploadFile) -> Path:
    suffix = Path(upload.filename or "upload.bin").suffix
    fd, temp_path_str = tempfile.mkstemp(prefix="ing_", suffix=suffix, dir=_TMP_DIR)
    temp_path = Path(temp_path_str)
    with os.fdopen(fd, "wb") as out_file:
        shutil.copyfileobj(upload.file, out_file)
    return temp_path


def _cleanup_temp_file(path_str: str) -> None:
    try:
        Path(path_str).unlink(missing_ok=True)
    except Exception:
        return


def _validate_batch_files(files: list[UploadFile]) -> None:
    if not files:
        raise HTTPException(status_code=400, detail="files is required")
    if len(files) > _MAX_BATCH_FILES:
        raise HTTPException(status_code=400, detail=f"too many files: max {_MAX_BATCH_FILES}")


def _build_batch_source_ref(prefix: str, index: int) -> str:
    return f"{prefix}:{index + 1}"


def _queue_ingest_job(
    db: Session,
    *,
    source: SourceType,
    source_ref: str | None,
    file_path_temp: str,
    caption: str | None,
    payload: dict[str, Any],
    created_by: UUID,
) -> tuple[IngestAcceptedResponse | None, str | None]:
    job = IngestJob(
        source=source,
        source_ref=source_ref,
        state=IngestState.RECEIVED,
        file_path_temp=file_path_temp,
        caption=caption,
        payload_json=payload,
        received_at=_now(),
        created_by=created_by,
    )
    db.add(job)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        _cleanup_temp_file(file_path_temp)
        return None, "duplicate source_ref"

    db.refresh(job)

    db.add(
        IngestEvent(
            ingest_job_id=job.id,
            from_state=None,
            to_state=IngestState.RECEIVED,
            event_type="STATE_TRANSITION",
            event_message="job received",
            event_payload=payload,
            created_by=created_by,
        )
    )
    db.commit()
    process_ingest_job_task.delay(str(job.id))

    return (
        IngestAcceptedResponse(
            job_id=job.id,
            state=job.state,
            source=job.source,
            source_ref=job.source_ref,
            queued_at=job.received_at,
        ),
        None,
    )


def _require_action_token(job_id: UUID, action: str, header_token: str | None, query_token: str | None) -> None:
    token = header_token or query_token
    if not token:
        raise HTTPException(status_code=401, detail="missing action token")
    try:
        verify_action_token(token, job_id=job_id, action=action)
    except OpenClawActionTokenError as exc:
        raise HTTPException(status_code=401, detail=f"invalid action token: {exc}") from exc


def _requeue_job_with_action(
    db: Session,
    *,
    job: IngestJob,
    action: str,
    req: IngestActionRequest,
    event_payload_extra: dict | None = None,
) -> IngestActionResponse:
    previous_state = job.state
    previous_attempt_count = job.attempt_count
    previous_last_error_code = job.last_error_code

    if previous_state in {IngestState.STORED, IngestState.EXTRACTED, IngestState.CLASSIFIED, IngestState.INDEXED} and not req.force:
        raise HTTPException(status_code=409, detail=f"cannot {action} while state={previous_state.value}; set force=true")
    if previous_state == IngestState.PUBLISHED and not req.force:
        raise HTTPException(status_code=409, detail="published job requires force=true")

    if action == "reprocess" and req.caption_override is not None:
        job.caption = req.caption_override

    job.state = IngestState.RECEIVED
    job.retry_after = None
    job.started_at = None
    job.finished_at = None
    if req.reset_attempts:
        job.attempt_count = 0
    if req.clear_error:
        job.last_error_code = None
        job.last_error_message = None

    event_payload = {
        "force": req.force,
        "reset_attempts": req.reset_attempts,
        "clear_error": req.clear_error,
        "source": "openclaw_action",
    }
    if action == "reprocess":
        event_payload["caption_overridden"] = req.caption_override is not None
    if event_payload_extra:
        event_payload.update(event_payload_extra)

    db.add(job)
    db.add(
        IngestEvent(
            ingest_job_id=job.id,
            from_state=previous_state,
            to_state=IngestState.RECEIVED,
            event_type=f"OPENCLAW_ACTION_{action.upper()}",
            event_message=f"job {action} requested by openclaw callback action",
            event_payload=event_payload,
        )
    )
    db.commit()

    process_ingest_job_task.delay(str(job.id))

    db.add(
        AuditLog(
            actor_user_id=None,
            action=f"INGEST_JOB_ACTION_{action.upper()}",
            target_type="ingest_job",
            target_id=job.id,
            source=job.source,
            source_ref=job.source_ref,
            before_json={
                "state": previous_state.value,
                "attempt_count": previous_attempt_count,
                "last_error_code": previous_last_error_code,
            },
            after_json={
                "state": job.state.value,
                "force": req.force,
                "reset_attempts": req.reset_attempts,
                "clear_error": req.clear_error,
                "caption_overridden": req.caption_override is not None,
            },
            masked_fields=["caption_override"] if req.caption_override is not None else [],
        )
    )
    db.commit()

    return IngestActionResponse(
        job_id=job.id,
        action=action,
        previous_state=previous_state,
        state=job.state,
        enqueued=True,
        queued_at=_now(),
        attempt_count=job.attempt_count,
    )


@router.get("/ingest/jobs/{job_id}", response_model=IngestJobStatusResponse)
def get_ingest_job_status(
    job_id: UUID,
    current_user: CurrentUser = Depends(require_roles(UserRole.EDITOR, UserRole.ADMIN)),
    db: Session = Depends(get_db),
) -> IngestJobStatusResponse:
    job = db.get(IngestJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="ingest job not found")

    if current_user.role != UserRole.ADMIN and job.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="forbidden")

    success_states = {IngestState.PUBLISHED, IngestState.NEEDS_REVIEW}
    terminal_states = {IngestState.PUBLISHED, IngestState.NEEDS_REVIEW, IngestState.FAILED}

    return IngestJobStatusResponse(
        job_id=job.id,
        state=job.state,
        source=job.source,
        source_ref=job.source_ref,
        document_id=job.document_id,
        attempt_count=job.attempt_count,
        max_attempts=job.max_attempts,
        last_error_code=job.last_error_code,
        last_error_message=job.last_error_message,
        received_at=job.received_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        is_terminal=job.state in terminal_states,
        success=job.state in success_states,
    )


@router.post("/ingest/telegram", response_model=IngestAcceptedResponse, status_code=status.HTTP_202_ACCEPTED)
def ingest_telegram(
    file: UploadFile = File(...),
    source: SourceType = Form(SourceType.telegram),
    source_ref: str = Form(...),
    message_id: str = Form(...),
    chat_id: str = Form(...),
    sent_at: str | None = Form(None),
    caption: str | None = Form(None),
    current_user: CurrentUser = Depends(require_roles(UserRole.EDITOR, UserRole.ADMIN)),
    db: Session = Depends(get_db),
) -> IngestAcceptedResponse:
    if source != SourceType.telegram:
        raise HTTPException(status_code=400, detail="source must be telegram")

    temp_path = _save_upload_temp(file)
    payload = {
        "filename": file.filename,
        "message_id": message_id,
        "chat_id": chat_id,
        "sent_at": sent_at,
    }

    accepted, error = _queue_ingest_job(
        db,
        source=source,
        source_ref=source_ref,
        file_path_temp=str(temp_path),
        caption=caption,
        payload=payload,
        created_by=current_user.id,
    )
    if not accepted:
        raise HTTPException(status_code=409, detail=error or "ingest enqueue failed")
    return accepted


@router.post("/ingest/telegram/batch", response_model=IngestBatchAcceptedResponse, status_code=status.HTTP_202_ACCEPTED)
def ingest_telegram_batch(
    files: list[UploadFile] = File(...),
    source: SourceType = Form(SourceType.telegram),
    source_ref_prefix: str | None = Form(None),
    message_id: str = Form(...),
    chat_id: str = Form(...),
    sent_at: str | None = Form(None),
    caption: str | None = Form(None),
    current_user: CurrentUser = Depends(require_roles(UserRole.EDITOR, UserRole.ADMIN)),
    db: Session = Depends(get_db),
) -> IngestBatchAcceptedResponse:
    if source != SourceType.telegram:
        raise HTTPException(status_code=400, detail="source must be telegram")
    _validate_batch_files(files)

    prefix = (source_ref_prefix or f"msg:{message_id}").strip()
    if not prefix:
        raise HTTPException(status_code=400, detail="source_ref_prefix resolved empty")

    accepted_items: list[IngestAcceptedResponse] = []
    rejected_items: list[IngestBatchRejectedItem] = []
    total_files = len(files)

    for idx, upload in enumerate(files):
        temp_path = _save_upload_temp(upload)
        source_ref = _build_batch_source_ref(prefix, idx)
        payload = {
            "filename": upload.filename,
            "message_id": message_id,
            "chat_id": chat_id,
            "sent_at": sent_at,
            "batch_index": idx + 1,
            "batch_total": total_files,
        }

        accepted, error = _queue_ingest_job(
            db,
            source=source,
            source_ref=source_ref,
            file_path_temp=str(temp_path),
            caption=caption,
            payload=payload,
            created_by=current_user.id,
        )
        if accepted:
            accepted_items.append(accepted)
            continue

        rejected_items.append(
            IngestBatchRejectedItem(
                index=idx + 1,
                filename=upload.filename or "upload.bin",
                source_ref=source_ref,
                error=error or "ingest enqueue failed",
            )
        )

    return IngestBatchAcceptedResponse(
        total_files=total_files,
        accepted_count=len(accepted_items),
        rejected_count=len(rejected_items),
        accepted=accepted_items,
        rejected=rejected_items,
    )


@router.post("/ingest/actions/{job_id}/retry", response_model=IngestActionResponse)
def ingest_action_retry(
    job_id: UUID,
    req: IngestActionRequest | None = None,
    x_openclaw_action_token: str | None = Header(None, alias="X-OpenClaw-Action-Token"),
    token: str | None = Query(None),
    db: Session = Depends(get_db),
) -> IngestActionResponse:
    request_model = req or IngestActionRequest()
    _require_action_token(job_id, "retry", x_openclaw_action_token, token)

    job = db.get(IngestJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="ingest job not found")

    return _requeue_job_with_action(db, job=job, action="retry", req=request_model)


@router.post("/ingest/actions/{job_id}/reprocess", response_model=IngestActionResponse)
def ingest_action_reprocess(
    job_id: UUID,
    req: IngestActionRequest | None = None,
    x_openclaw_action_token: str | None = Header(None, alias="X-OpenClaw-Action-Token"),
    token: str | None = Query(None),
    db: Session = Depends(get_db),
) -> IngestActionResponse:
    request_model = req or IngestActionRequest(reset_attempts=True, clear_error=True)
    _require_action_token(job_id, "reprocess", x_openclaw_action_token, token)

    job = db.get(IngestJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="ingest job not found")

    return _requeue_job_with_action(db, job=job, action="reprocess", req=request_model)


@router.post("/ingest/manual", response_model=IngestAcceptedResponse, status_code=status.HTTP_202_ACCEPTED)
def ingest_manual(
    file: UploadFile = File(...),
    source: SourceType = Form(SourceType.manual),
    source_ref: str | None = Form(None),
    caption: str | None = Form(None),
    title: str | None = Form(None),
    description: str | None = Form(None),
    current_user: CurrentUser = Depends(require_roles(UserRole.EDITOR, UserRole.ADMIN)),
    db: Session = Depends(get_db),
) -> IngestAcceptedResponse:
    if source not in {SourceType.manual, SourceType.api}:
        raise HTTPException(status_code=400, detail="source must be manual or api")

    temp_path = _save_upload_temp(file)
    payload = {
        "filename": file.filename,
        "title": title,
        "description": description,
    }

    accepted, error = _queue_ingest_job(
        db,
        source=source,
        source_ref=source_ref,
        file_path_temp=str(temp_path),
        caption=caption,
        payload=payload,
        created_by=current_user.id,
    )
    if not accepted:
        raise HTTPException(status_code=409, detail=error or "ingest enqueue failed")
    return accepted


@router.post("/ingest/manual/batch", response_model=IngestBatchAcceptedResponse, status_code=status.HTTP_202_ACCEPTED)
def ingest_manual_batch(
    files: list[UploadFile] = File(...),
    source: SourceType = Form(SourceType.manual),
    source_ref_prefix: str | None = Form(None),
    caption: str | None = Form(None),
    title: str | None = Form(None),
    description: str | None = Form(None),
    current_user: CurrentUser = Depends(require_roles(UserRole.EDITOR, UserRole.ADMIN)),
    db: Session = Depends(get_db),
) -> IngestBatchAcceptedResponse:
    if source not in {SourceType.manual, SourceType.api}:
        raise HTTPException(status_code=400, detail="source must be manual or api")
    _validate_batch_files(files)

    prefix = source_ref_prefix.strip() if source_ref_prefix else None
    total_files = len(files)
    accepted_items: list[IngestAcceptedResponse] = []
    rejected_items: list[IngestBatchRejectedItem] = []

    for idx, upload in enumerate(files):
        temp_path = _save_upload_temp(upload)
        source_ref = _build_batch_source_ref(prefix, idx) if prefix else None
        payload = {
            "filename": upload.filename,
            "title": title,
            "description": description,
            "batch_index": idx + 1,
            "batch_total": total_files,
        }
        accepted, error = _queue_ingest_job(
            db,
            source=source,
            source_ref=source_ref,
            file_path_temp=str(temp_path),
            caption=caption,
            payload=payload,
            created_by=current_user.id,
        )
        if accepted:
            accepted_items.append(accepted)
            continue

        rejected_items.append(
            IngestBatchRejectedItem(
                index=idx + 1,
                filename=upload.filename or "upload.bin",
                source_ref=source_ref,
                error=error or "ingest enqueue failed",
            )
        )

    return IngestBatchAcceptedResponse(
        total_files=total_files,
        accepted_count=len(accepted_items),
        rejected_count=len(rejected_items),
        accepted=accepted_items,
        rejected=rejected_items,
    )
