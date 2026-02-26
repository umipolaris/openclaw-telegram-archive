import httpx

from app.core.config import get_settings
from app.schemas.ingest import IngestResultPayload


def notify_openclaw(result: IngestResultPayload) -> None:
    settings = get_settings()
    if not settings.openclaw_notify_enabled:
        return
    with httpx.Client(timeout=10.0) as client:
        response = client.post(settings.openclaw_callback_url, json=result.model_dump(mode="json"))
        response.raise_for_status()
