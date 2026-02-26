from __future__ import annotations

from uuid import UUID

import structlog

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.meili_service import MeiliSearchError, delete_document, rebuild_documents_index, upsert_documents
from app.worker.celery_app import celery_app

logger = structlog.get_logger(__name__)


def _parse_uuid(raw: str) -> UUID | None:
    try:
        return UUID(str(raw))
    except ValueError:
        return None


@celery_app.task(bind=True)
def sync_document_index_task(self, document_id: str):  # noqa: ANN201
    settings = get_settings()
    if settings.search_backend.strip().lower() != "meili":
        return {"status": "skipped", "reason": "search_backend_not_meili", "document_id": document_id}

    doc_id = _parse_uuid(document_id)
    if not doc_id:
        return {"status": "skipped", "reason": "invalid_document_id", "document_id": document_id}

    with SessionLocal() as db:
        try:
            indexed = upsert_documents(db, [doc_id], settings=settings)
            if indexed == 0:
                delete_document(doc_id, settings=settings)
            return {
                "status": "ok",
                "document_id": str(doc_id),
                "indexed": indexed,
                "deleted_stale": indexed == 0,
            }
        except MeiliSearchError as exc:
            logger.warning("sync_document_index_task_failed", document_id=str(doc_id), error=str(exc))
            raise


@celery_app.task(bind=True)
def sync_documents_index_batch_task(self, document_ids: list[str]):  # noqa: ANN201
    settings = get_settings()
    if settings.search_backend.strip().lower() != "meili":
        return {"status": "skipped", "reason": "search_backend_not_meili", "count": len(document_ids)}

    parsed_ids: list[UUID] = []
    for raw in document_ids:
        parsed = _parse_uuid(raw)
        if parsed:
            parsed_ids.append(parsed)
    unique_ids = list(dict.fromkeys(parsed_ids))
    if not unique_ids:
        return {"status": "skipped", "reason": "no_valid_document_ids", "count": 0}

    with SessionLocal() as db:
        try:
            indexed = upsert_documents(db, unique_ids, settings=settings)
            return {
                "status": "ok",
                "count": len(unique_ids),
                "indexed": indexed,
            }
        except MeiliSearchError as exc:
            logger.warning(
                "sync_documents_index_batch_task_failed",
                count=len(unique_ids),
                error=str(exc),
            )
            raise


@celery_app.task(bind=True)
def delete_document_index_task(self, document_id: str):  # noqa: ANN201
    settings = get_settings()
    if settings.search_backend.strip().lower() != "meili":
        return {"status": "skipped", "reason": "search_backend_not_meili", "document_id": document_id}

    doc_id = _parse_uuid(document_id)
    if not doc_id:
        return {"status": "skipped", "reason": "invalid_document_id", "document_id": document_id}

    try:
        delete_document(doc_id, settings=settings)
        return {"status": "ok", "document_id": str(doc_id)}
    except MeiliSearchError as exc:
        logger.warning("delete_document_index_task_failed", document_id=str(doc_id), error=str(exc))
        raise


@celery_app.task(bind=True)
def rebuild_documents_index_task(self, batch_size: int = 500, limit: int | None = None):  # noqa: ANN201
    settings = get_settings()
    if settings.search_backend.strip().lower() != "meili":
        return {"status": "skipped", "reason": "search_backend_not_meili"}

    with SessionLocal() as db:
        try:
            summary = rebuild_documents_index(db, batch_size=batch_size, limit=limit, settings=settings)
            return {"status": "ok", **summary}
        except MeiliSearchError as exc:
            logger.warning("rebuild_documents_index_task_failed", error=str(exc))
            raise
