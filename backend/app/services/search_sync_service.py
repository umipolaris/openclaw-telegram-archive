from __future__ import annotations

from uuid import UUID

import structlog

from app.core.config import get_settings

logger = structlog.get_logger(__name__)


def _is_sync_enabled() -> bool:
    settings = get_settings()
    return settings.search_backend.strip().lower() == "meili" and settings.search_auto_sync


def enqueue_document_index_sync(document_id: UUID) -> None:
    if not _is_sync_enabled():
        return
    try:
        from app.worker.tasks_search import sync_document_index_task

        sync_document_index_task.delay(str(document_id))
    except Exception as exc:  # noqa: BLE001
        logger.warning("enqueue_document_index_sync_failed", document_id=str(document_id), error=str(exc))


def enqueue_document_index_sync_many(document_ids: list[UUID]) -> None:
    if not _is_sync_enabled():
        return

    unique_ids = list(dict.fromkeys(str(doc_id) for doc_id in document_ids))
    if not unique_ids:
        return

    try:
        if len(unique_ids) == 1:
            from app.worker.tasks_search import sync_document_index_task

            sync_document_index_task.delay(unique_ids[0])
            return

        from app.worker.tasks_search import sync_documents_index_batch_task

        chunk_size = 500
        for idx in range(0, len(unique_ids), chunk_size):
            sync_documents_index_batch_task.delay(unique_ids[idx : idx + chunk_size])
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "enqueue_document_index_sync_many_failed",
            document_count=len(unique_ids),
            error=str(exc),
        )


def enqueue_document_index_delete(document_id: UUID) -> None:
    if not _is_sync_enabled():
        return
    try:
        from app.worker.tasks_search import delete_document_index_task

        delete_document_index_task.delay(str(document_id))
    except Exception as exc:  # noqa: BLE001
        logger.warning("enqueue_document_index_delete_failed", document_id=str(document_id), error=str(exc))
