from uuid import UUID

from celery.exceptions import Retry

from app.core.config import get_settings
from app.db.models import AuditLog, IngestEvent, IngestJob, IngestState
from app.db.session import SessionLocal
from app.services.backfill_service import process_backfill_payload
from app.services.ingest_service import process_ingest_job
from app.services.retry_policy import compute_backoff_seconds, compute_retry_after, should_retry
from app.worker.celery_app import celery_app


def _parse_job_uuid(job_id: str) -> UUID | None:
    try:
        return UUID(str(job_id))
    except ValueError:
        return None


def _load_job(db, job_id: str) -> IngestJob | None:
    job_uuid = _parse_job_uuid(job_id)
    if not job_uuid:
        return None
    return db.get(IngestJob, job_uuid)


def _schedule_retry(db, job: IngestJob, reason: str) -> int:
    settings = get_settings()
    delay_seconds = compute_backoff_seconds(
        attempt_count=job.attempt_count,
        base_seconds=settings.ingest_retry_base_seconds,
        max_seconds=settings.ingest_retry_max_seconds,
    )
    retry_after = compute_retry_after(
        attempt_count=job.attempt_count,
        base_seconds=settings.ingest_retry_base_seconds,
        max_seconds=settings.ingest_retry_max_seconds,
    )

    from_state = job.state
    job.state = IngestState.RECEIVED
    job.retry_after = retry_after
    job.started_at = None
    job.finished_at = None
    db.add(job)
    db.add(
        IngestEvent(
            ingest_job_id=job.id,
            from_state=from_state,
            to_state=IngestState.RECEIVED,
            event_type="RETRY_SCHEDULED",
            event_message="job failed, scheduled retry",
            event_payload={
                "attempt_count": job.attempt_count,
                "max_attempts": job.max_attempts,
                "delay_seconds": delay_seconds,
                "retry_after": retry_after.isoformat(),
                "reason": reason,
            },
        )
    )
    db.commit()

    return delay_seconds


def _move_to_dead_letter(db, job: IngestJob, reason: str) -> None:
    from_state = job.state
    job.state = IngestState.FAILED
    job.retry_after = None

    if not job.last_error_code or job.last_error_code == "INGEST_FAILED":
        job.last_error_code = "DLQ_MAX_ATTEMPTS"
    if not job.last_error_message:
        job.last_error_message = reason

    db.add(job)

    payload = {
        "attempt_count": job.attempt_count,
        "max_attempts": job.max_attempts,
        "reason": reason,
        "last_error_code": job.last_error_code,
    }
    db.add(
        IngestEvent(
            ingest_job_id=job.id,
            from_state=from_state,
            to_state=IngestState.FAILED,
            event_type="DEAD_LETTER",
            event_message="max attempts exceeded; moved to dead-letter",
            event_payload=payload,
        )
    )
    db.add(
        AuditLog(
            action="INGEST_JOB_DEAD_LETTER",
            target_type="ingest_job",
            target_id=job.id,
            after_json=payload,
        )
    )
    db.commit()


@celery_app.task(bind=True, max_retries=None)
def process_ingest_job_task(self, job_id: str):  # noqa: ANN201
    db = SessionLocal()
    try:
        result = process_ingest_job(db, job_id=job_id)
        if result.get("ok"):
            return result

        reason = str(result.get("reason", "ingest_failed"))
        if reason == "job_not_found":
            return result

        job = _load_job(db, job_id)
        if not job:
            return result

        if should_retry(job.attempt_count, job.max_attempts):
            delay_seconds = _schedule_retry(db, job, reason)
            raise self.retry(exc=RuntimeError(reason), countdown=delay_seconds)

        _move_to_dead_letter(db, job, reason)
        return {
            "ok": False,
            "job_id": str(job.id),
            "reason": reason,
            "dead_lettered": True,
            "attempt_count": job.attempt_count,
            "max_attempts": job.max_attempts,
        }

    except Retry:
        raise
    except Exception as exc:  # noqa: BLE001
        reason = f"task_exception:{exc}"
        job = _load_job(db, job_id)
        if job and should_retry(job.attempt_count, job.max_attempts):
            delay_seconds = _schedule_retry(db, job, reason)
            raise self.retry(exc=exc, countdown=delay_seconds)
        if job:
            _move_to_dead_letter(db, job, reason)
            return {
                "ok": False,
                "job_id": str(job.id),
                "reason": reason,
                "dead_lettered": True,
                "attempt_count": job.attempt_count,
                "max_attempts": job.max_attempts,
            }
        raise
    finally:
        db.close()


@celery_app.task(bind=True)
def run_backfill_task(self, payload: dict):  # noqa: ANN201
    db = SessionLocal()
    try:
        return process_backfill_payload(db, payload)
    finally:
        db.close()
