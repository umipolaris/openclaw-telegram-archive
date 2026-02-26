from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import AuditLog, Document, IngestJob, IngestState, ReviewStatus


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _round_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round((numerator / denominator) * 100.0, 2)


def build_ops_report_payload(db: Session, *, days: int = 7) -> dict[str, Any]:
    period_end = _now()
    period_start = period_end - timedelta(days=max(1, int(days)))

    ingest_total = db.execute(
        select(func.count(IngestJob.id)).where(
            IngestJob.received_at >= period_start,
            IngestJob.received_at < period_end,
        )
    ).scalar_one()
    failed_jobs = db.execute(
        select(func.count(IngestJob.id)).where(
            IngestJob.received_at >= period_start,
            IngestJob.received_at < period_end,
            IngestJob.state == IngestState.FAILED,
        )
    ).scalar_one()

    classified_docs = db.execute(
        select(func.count(Document.id)).where(
            Document.ingested_at >= period_start,
            Document.ingested_at < period_end,
        )
    ).scalar_one()
    class_fail_docs = db.execute(
        select(func.count(Document.id)).where(
            Document.ingested_at >= period_start,
            Document.ingested_at < period_end,
            Document.review_reasons.any("CLASSIFY_FAIL"),
        )
    ).scalar_one()
    auto_classified_docs = max(0, int(classified_docs) - int(class_fail_docs))

    needs_review_open = db.execute(
        select(func.count(Document.id)).where(Document.review_status == ReviewStatus.NEEDS_REVIEW)
    ).scalar_one()

    review_updates = db.execute(
        select(AuditLog.target_id, AuditLog.created_at, AuditLog.after_json)
        .where(
            AuditLog.action == "REVIEW_QUEUE_UPDATE",
            AuditLog.created_at >= period_start,
            AuditLog.created_at < period_end,
            AuditLog.target_type == "document",
            AuditLog.target_id.is_not(None),
        )
        .order_by(AuditLog.created_at.asc())
    ).all()

    resolved_doc_ids: set[UUID] = set()
    for target_id, _, after_json in review_updates:
        if not isinstance(after_json, dict):
            continue
        if str(after_json.get("review_status")) == "RESOLVED":
            resolved_doc_ids.add(target_id)

    resolution_count = len(resolved_doc_ids)
    resolution_avg_hours: float | None = None
    if resolved_doc_ids:
        docs = db.execute(
            select(Document.id, Document.ingested_at).where(Document.id.in_(list(resolved_doc_ids)))
        ).all()
        ingested_map = {row.id: row.ingested_at for row in docs}
        durations: list[float] = []
        for target_id, occurred_at, after_json in review_updates:
            if target_id not in resolved_doc_ids:
                continue
            if not isinstance(after_json, dict) or str(after_json.get("review_status")) != "RESOLVED":
                continue
            ingested_at = ingested_map.get(target_id)
            if not ingested_at:
                continue
            diff = occurred_at - ingested_at
            durations.append(round(diff.total_seconds() / 3600.0, 3))
        if durations:
            resolution_avg_hours = round(sum(durations) / len(durations), 2)

    return {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "ingest_total": int(ingest_total),
        "failed_jobs": int(failed_jobs),
        "failure_rate_pct": _round_ratio(int(failed_jobs), int(ingest_total)),
        "classified_docs": int(classified_docs),
        "auto_classified_docs": int(auto_classified_docs),
        "classification_accuracy_pct": _round_ratio(int(auto_classified_docs), int(classified_docs)),
        "needs_review_open": int(needs_review_open),
        "review_resolution_count": int(resolution_count),
        "review_queue_avg_resolution_hours": resolution_avg_hours,
        "generated_at": _now().isoformat(),
    }


def persist_ops_report(db: Session, payload: dict[str, Any], actor_user_id: UUID | None = None) -> AuditLog:
    row = AuditLog(
        actor_user_id=actor_user_id,
        action="OPS_REPORT_WEEKLY",
        target_type="ops_report",
        target_id=None,
        after_json=payload,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
