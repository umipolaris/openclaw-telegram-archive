from __future__ import annotations

from app.db.session import SessionLocal
from app.services.ops_report_service import build_ops_report_payload, persist_ops_report
from app.worker.celery_app import celery_app


@celery_app.task(bind=True)
def generate_weekly_ops_report_task(self, days: int = 7):  # noqa: ANN201
    with SessionLocal() as db:
        payload = build_ops_report_payload(db, days=days)
        row = persist_ops_report(db, payload)
        return {
            "status": "ok",
            "audit_log_id": row.id,
            "action": row.action,
            "generated_at": payload.get("generated_at"),
            "period_start": payload.get("period_start"),
            "period_end": payload.get("period_end"),
        }
