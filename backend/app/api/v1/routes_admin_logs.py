import os
import shutil
import tempfile
import csv
import io
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, require_roles
from app.db.models import AuditLog, IngestEvent, IngestJob, IngestState, SourceType, User, UserRole
from app.db.session import get_db
from app.schemas.admin_log import (
    AuditLogItem,
    AuditLogsResponse,
    IngestEventItem,
    IngestEventsResponse,
    IngestJobItem,
    IngestJobsResponse,
    OpsReportGenerateResponse,
    OpsReportItem,
    OpsReportsResponse,
    RecoverIngestJobUploadResponse,
    RequeueIngestJobRequest,
    RequeueIngestJobResponse,
)
from app.worker.tasks_ingest import process_ingest_job_task
from app.worker.tasks_reports import generate_weekly_ops_report_task

router = APIRouter()
_TMP_DIR = Path(tempfile.gettempdir()) / "doc-archive-ingest"
_TMP_DIR.mkdir(parents=True, exist_ok=True)


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _save_upload_temp(upload: UploadFile) -> Path:
    suffix = Path(upload.filename or "upload.bin").suffix
    fd, temp_path_str = tempfile.mkstemp(prefix="ing_", suffix=suffix, dir=_TMP_DIR)
    temp_path = Path(temp_path_str)
    with os.fdopen(fd, "wb") as out_file:
        shutil.copyfileobj(upload.file, out_file)
    return temp_path


def _build_audit_filters(
    *,
    action: str | None,
    target_type: str | None,
    target_id: UUID | None,
    actor_user_id: UUID | None,
    source: SourceType | None,
    source_ref: str | None,
    q: str | None,
    created_from: datetime | None,
    created_to: datetime | None,
):
    filters = []
    if action and action.strip():
        filters.append(AuditLog.action.ilike(f"%{action.strip()}%"))
    if target_type and target_type.strip():
        filters.append(AuditLog.target_type.ilike(f"%{target_type.strip()}%"))
    if target_id:
        filters.append(AuditLog.target_id == target_id)
    if actor_user_id:
        filters.append(AuditLog.actor_user_id == actor_user_id)
    if source:
        filters.append(AuditLog.source == source)
    if source_ref and source_ref.strip():
        filters.append(AuditLog.source_ref.ilike(f"%{source_ref.strip()}%"))
    if q and q.strip():
        keyword = q.strip()
        filters.append(
            (
                AuditLog.action.ilike(f"%{keyword}%")
                | AuditLog.target_type.ilike(f"%{keyword}%")
                | AuditLog.source_ref.ilike(f"%{keyword}%")
            )
        )
    if created_from:
        filters.append(AuditLog.created_at >= created_from)
    if created_to:
        filters.append(AuditLog.created_at <= created_to)
    return filters


@router.get(
    "/admin/audit-logs",
    response_model=AuditLogsResponse,
    dependencies=[Depends(require_roles(UserRole.ADMIN))],
)
def list_audit_logs(
    action: str | None = Query(None),
    target_type: str | None = Query(None),
    target_id: UUID | None = Query(None),
    actor_user_id: UUID | None = Query(None),
    source: SourceType | None = Query(None),
    source_ref: str | None = Query(None),
    q: str | None = Query(None),
    created_from: datetime | None = Query(None),
    created_to: datetime | None = Query(None),
    include_payload: bool = Query(False),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> AuditLogsResponse:
    filters = _build_audit_filters(
        action=action,
        target_type=target_type,
        target_id=target_id,
        actor_user_id=actor_user_id,
        source=source,
        source_ref=source_ref,
        q=q,
        created_from=created_from,
        created_to=created_to,
    )

    count_stmt = select(func.count(AuditLog.id))
    if filters:
        count_stmt = count_stmt.where(*filters)
    total = db.execute(count_stmt).scalar_one()

    stmt = (
        select(AuditLog, User.username)
        .outerjoin(User, User.id == AuditLog.actor_user_id)
        .order_by(
            desc(AuditLog.created_at) if sort_order == "desc" else AuditLog.created_at.asc(),
            desc(AuditLog.id) if sort_order == "desc" else AuditLog.id.asc(),
        )
        .offset((page - 1) * size)
        .limit(size)
    )
    if filters:
        stmt = stmt.where(*filters)

    rows = db.execute(stmt).all()
    items = [
        AuditLogItem(
            id=row.id,
            created_at=row.created_at,
            actor_user_id=row.actor_user_id,
            actor_username=username,
            action=row.action,
            target_type=row.target_type,
            target_id=row.target_id,
            source=row.source,
            source_ref=row.source_ref,
            masked_fields=row.masked_fields or [],
            before_json=row.before_json if include_payload else None,
            after_json=row.after_json if include_payload else None,
        )
        for row, username in rows
    ]
    return AuditLogsResponse(items=items, page=page, size=size, total=total)


@router.get(
    "/admin/audit-logs/export",
    dependencies=[Depends(require_roles(UserRole.ADMIN))],
)
def export_audit_logs(
    action: str | None = Query(None),
    target_type: str | None = Query(None),
    target_id: UUID | None = Query(None),
    actor_user_id: UUID | None = Query(None),
    source: SourceType | None = Query(None),
    source_ref: str | None = Query(None),
    q: str | None = Query(None),
    created_from: datetime | None = Query(None),
    created_to: datetime | None = Query(None),
    include_payload: bool = Query(False),
    fmt: str = Query("csv", pattern="^(csv|json)$"),
    limit: int = Query(5000, ge=1, le=20000),
    db: Session = Depends(get_db),
):
    filters = _build_audit_filters(
        action=action,
        target_type=target_type,
        target_id=target_id,
        actor_user_id=actor_user_id,
        source=source,
        source_ref=source_ref,
        q=q,
        created_from=created_from,
        created_to=created_to,
    )
    stmt = (
        select(AuditLog, User.username)
        .outerjoin(User, User.id == AuditLog.actor_user_id)
        .order_by(desc(AuditLog.created_at), desc(AuditLog.id))
        .limit(limit)
    )
    if filters:
        stmt = stmt.where(*filters)
    rows = db.execute(stmt).all()
    items: list[dict] = []
    for row, username in rows:
        items.append(
            {
                "id": row.id,
                "created_at": row.created_at.isoformat(),
                "actor_user_id": str(row.actor_user_id) if row.actor_user_id else None,
                "actor_username": username,
                "action": row.action,
                "target_type": row.target_type,
                "target_id": str(row.target_id) if row.target_id else None,
                "source": row.source.value if row.source else None,
                "source_ref": row.source_ref,
                "masked_fields": row.masked_fields or [],
                "before_json": row.before_json if include_payload else None,
                "after_json": row.after_json if include_payload else None,
            }
        )

    timestamp = _now().strftime("%Y%m%d_%H%M%S")
    if fmt == "json":
        import json

        content = json.dumps(items, ensure_ascii=False, indent=2)
        headers = {"Content-Disposition": f'attachment; filename="audit_logs_{timestamp}.json"'}
        return Response(content=content, media_type="application/json", headers=headers)

    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "id",
            "created_at",
            "actor_user_id",
            "actor_username",
            "action",
            "target_type",
            "target_id",
            "source",
            "source_ref",
            "masked_fields",
            "before_json",
            "after_json",
        ],
    )
    writer.writeheader()
    for item in items:
        writer.writerow(
            {
                **item,
                "masked_fields": ",".join(item["masked_fields"] or []),
                "before_json": item["before_json"],
                "after_json": item["after_json"],
            }
        )
    headers = {"Content-Disposition": f'attachment; filename="audit_logs_{timestamp}.csv"'}
    return Response(content=output.getvalue(), media_type="text/csv", headers=headers)


@router.get(
    "/admin/ops-reports",
    response_model=OpsReportsResponse,
    dependencies=[Depends(require_roles(UserRole.ADMIN))],
)
def list_ops_reports(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> OpsReportsResponse:
    where_clause = (AuditLog.action == "OPS_REPORT_WEEKLY") & (AuditLog.target_type == "ops_report")
    total = db.execute(select(func.count(AuditLog.id)).where(where_clause)).scalar_one()
    rows = db.execute(
        select(AuditLog)
        .where(where_clause)
        .order_by(desc(AuditLog.created_at), desc(AuditLog.id))
        .offset((page - 1) * size)
        .limit(size)
    ).scalars().all()

    items: list[OpsReportItem] = []
    for row in rows:
        payload = row.after_json if isinstance(row.after_json, dict) else {}
        try:
            period_start = datetime.fromisoformat(str(payload.get("period_start")))
            period_end = datetime.fromisoformat(str(payload.get("period_end")))
        except Exception:  # noqa: BLE001
            continue
        items.append(
            OpsReportItem(
                id=row.id,
                created_at=row.created_at,
                period_start=period_start,
                period_end=period_end,
                ingest_total=int(payload.get("ingest_total", 0)),
                failed_jobs=int(payload.get("failed_jobs", 0)),
                failure_rate_pct=float(payload.get("failure_rate_pct", 0.0)),
                classified_docs=int(payload.get("classified_docs", 0)),
                auto_classified_docs=int(payload.get("auto_classified_docs", 0)),
                classification_accuracy_pct=float(payload.get("classification_accuracy_pct", 0.0)),
                needs_review_open=int(payload.get("needs_review_open", 0)),
                review_resolution_count=int(payload.get("review_resolution_count", 0)),
                review_queue_avg_resolution_hours=(
                    float(payload.get("review_queue_avg_resolution_hours"))
                    if payload.get("review_queue_avg_resolution_hours") is not None
                    else None
                ),
            )
        )
    return OpsReportsResponse(items=items, page=page, size=size, total=total)


@router.post(
    "/admin/ops-reports/generate",
    response_model=OpsReportGenerateResponse,
    dependencies=[Depends(require_roles(UserRole.ADMIN))],
)
def generate_ops_report(
    days: int = Query(7, ge=1, le=30),
) -> OpsReportGenerateResponse:
    job = generate_weekly_ops_report_task.delay(days=days)
    return OpsReportGenerateResponse(task_id=job.id, status="queued")


@router.get(
    "/admin/ingest-jobs",
    response_model=IngestJobsResponse,
    dependencies=[Depends(require_roles(UserRole.ADMIN))],
)
def list_ingest_jobs(
    state: IngestState | None = Query(None),
    source: SourceType | None = Query(None),
    source_ref: str | None = Query(None),
    received_from: datetime | None = Query(None),
    received_to: datetime | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> IngestJobsResponse:
    filters = []
    if state:
        filters.append(IngestJob.state == state)
    if source:
        filters.append(IngestJob.source == source)
    if source_ref and source_ref.strip():
        filters.append(IngestJob.source_ref.ilike(f"%{source_ref.strip()}%"))
    if received_from:
        filters.append(IngestJob.received_at >= received_from)
    if received_to:
        filters.append(IngestJob.received_at <= received_to)

    count_stmt = select(func.count(IngestJob.id))
    if filters:
        count_stmt = count_stmt.where(*filters)
    total = db.execute(count_stmt).scalar_one()

    stmt = (
        select(IngestJob)
        .order_by(desc(IngestJob.received_at), desc(IngestJob.id))
        .offset((page - 1) * size)
        .limit(size)
    )
    if filters:
        stmt = stmt.where(*filters)

    rows = db.execute(stmt).scalars().all()
    return IngestJobsResponse(
        items=[
            IngestJobItem(
                id=row.id,
                source=row.source,
                source_ref=row.source_ref,
                state=row.state,
                document_id=row.document_id,
                attempt_count=row.attempt_count,
                max_attempts=row.max_attempts,
                last_error_code=row.last_error_code,
                last_error_message=row.last_error_message,
                retry_after=row.retry_after,
                received_at=row.received_at,
                started_at=row.started_at,
                finished_at=row.finished_at,
            )
            for row in rows
        ],
        page=page,
        size=size,
        total=total,
    )


@router.get(
    "/admin/ingest-jobs/{job_id}/events",
    response_model=IngestEventsResponse,
    dependencies=[Depends(require_roles(UserRole.ADMIN))],
)
def list_ingest_job_events(
    job_id: UUID,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> IngestEventsResponse:
    rows = db.execute(
        select(IngestEvent)
        .where(IngestEvent.ingest_job_id == job_id)
        .order_by(desc(IngestEvent.occurred_at), desc(IngestEvent.id))
        .limit(limit)
    ).scalars().all()

    return IngestEventsResponse(
        ingest_job_id=job_id,
        items=[
            IngestEventItem(
                id=row.id,
                ingest_job_id=row.ingest_job_id,
                from_state=row.from_state,
                to_state=row.to_state,
                event_type=row.event_type,
                event_message=row.event_message,
                event_payload=row.event_payload or {},
                occurred_at=row.occurred_at,
            )
            for row in rows
        ],
    )


@router.post(
    "/admin/ingest-jobs/{job_id}/requeue",
    response_model=RequeueIngestJobResponse,
)
def requeue_ingest_job(
    job_id: UUID,
    req: RequeueIngestJobRequest,
    current_user: CurrentUser = Depends(require_roles(UserRole.ADMIN)),
    db: Session = Depends(get_db),
) -> RequeueIngestJobResponse:
    job = db.get(IngestJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="ingest job not found")

    if job.document_id and not req.force:
        raise HTTPException(
            status_code=409,
            detail="job already has document_id; set force=true to requeue",
        )

    if job.state in {IngestState.PUBLISHED, IngestState.INDEXED, IngestState.CLASSIFIED, IngestState.EXTRACTED, IngestState.STORED} and not req.force:
        raise HTTPException(
            status_code=409,
            detail=f"cannot requeue state={job.state.value} without force=true",
        )

    previous_state = job.state
    previous_attempt_count = job.attempt_count
    previous_last_error_code = job.last_error_code
    job.state = IngestState.RECEIVED
    job.retry_after = None
    job.started_at = None
    job.finished_at = None
    if req.reset_attempts:
        job.attempt_count = 0
    if req.clear_error:
        job.last_error_code = None
        job.last_error_message = None

    db.add(job)
    db.add(
        IngestEvent(
            ingest_job_id=job.id,
            from_state=previous_state,
            to_state=IngestState.RECEIVED,
            event_type="MANUAL_REQUEUE",
            event_message="job requeued by admin",
            event_payload={
                "force": req.force,
                "reset_attempts": req.reset_attempts,
                "clear_error": req.clear_error,
                "actor_user_id": str(current_user.id),
            },
            created_by=current_user.id,
        )
    )
    db.commit()

    process_ingest_job_task.delay(str(job.id))

    db.add(
        AuditLog(
            actor_user_id=current_user.id,
            action="INGEST_JOB_REQUEUE",
            target_type="ingest_job",
            target_id=job.id,
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
            },
        )
    )
    db.commit()

    return RequeueIngestJobResponse(
        job_id=job.id,
        previous_state=previous_state,
        state=job.state,
        enqueued=True,
        queued_at=_now(),
    )


@router.post(
    "/admin/ingest-jobs/{job_id}/recover-upload",
    response_model=RecoverIngestJobUploadResponse,
)
def recover_ingest_job_with_upload(
    job_id: UUID,
    file: UploadFile = File(...),
    caption: str | None = Form(None),
    reset_attempts: bool = Form(False),
    clear_error: bool = Form(True),
    current_user: CurrentUser = Depends(require_roles(UserRole.ADMIN)),
    db: Session = Depends(get_db),
) -> RecoverIngestJobUploadResponse:
    job = db.get(IngestJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="ingest job not found")

    previous_state = job.state
    previous_attempt_count = job.attempt_count
    previous_last_error_code = job.last_error_code
    previous_file_path = job.file_path_temp

    temp_path = _save_upload_temp(file)
    uploaded_size_bytes = temp_path.stat().st_size

    payload = dict(job.payload_json or {})
    payload["filename"] = file.filename
    payload["recovered_upload"] = True

    job.file_path_temp = str(temp_path)
    job.payload_json = payload
    if caption is not None:
        job.caption = caption

    job.state = IngestState.RECEIVED
    job.retry_after = None
    job.started_at = None
    job.finished_at = None
    if reset_attempts:
        job.attempt_count = 0
    if clear_error:
        job.last_error_code = None
        job.last_error_message = None

    db.add(job)
    db.add(
        IngestEvent(
            ingest_job_id=job.id,
            from_state=previous_state,
            to_state=IngestState.RECEIVED,
            event_type="MANUAL_RECOVER_UPLOAD",
            event_message="job recovered with uploaded file and requeued",
            event_payload={
                "uploaded_filename": file.filename,
                "uploaded_size_bytes": uploaded_size_bytes,
                "caption_overridden": caption is not None,
                "reset_attempts": reset_attempts,
                "clear_error": clear_error,
                "actor_user_id": str(current_user.id),
            },
            created_by=current_user.id,
        )
    )
    db.commit()

    process_ingest_job_task.delay(str(job.id))

    db.add(
        AuditLog(
            actor_user_id=current_user.id,
            action="INGEST_JOB_RECOVER_UPLOAD",
            target_type="ingest_job",
            target_id=job.id,
            before_json={
                "state": previous_state.value,
                "attempt_count": previous_attempt_count,
                "last_error_code": previous_last_error_code,
                "file_path_temp_exists": bool(previous_file_path),
            },
            after_json={
                "state": job.state.value,
                "uploaded_filename": file.filename,
                "uploaded_size_bytes": uploaded_size_bytes,
                "caption_overridden": caption is not None,
                "reset_attempts": reset_attempts,
                "clear_error": clear_error,
            },
            masked_fields=["file_path_temp"],
        )
    )
    db.commit()

    return RecoverIngestJobUploadResponse(
        job_id=job.id,
        previous_state=previous_state,
        state=job.state,
        enqueued=True,
        queued_at=_now(),
        uploaded_filename=file.filename or "upload.bin",
        uploaded_size_bytes=uploaded_size_bytes,
    )
