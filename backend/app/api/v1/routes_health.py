from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.schemas.common import HealthResponse
from app.services.meili_service import meili_health_status

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health_check(db: Session = Depends(get_db)) -> HealthResponse:
    settings = get_settings()
    db_status = "ok"
    try:
        db.execute(text("select 1"))
    except Exception:  # noqa: BLE001
        db_status = "error"

    dependencies = {"database": db_status}
    if settings.search_backend.strip().lower() == "meili":
        dependencies["meilisearch"] = meili_health_status(settings)
    dependencies["read_only_mode"] = "enabled" if settings.read_only_mode else "disabled"

    status = "ok"
    if any(value == "error" for value in dependencies.values()):
        status = "degraded"
    return HealthResponse(
        status=status,
        timestamp=datetime.now(tz=timezone.utc),
        dependencies=dependencies,
    )
