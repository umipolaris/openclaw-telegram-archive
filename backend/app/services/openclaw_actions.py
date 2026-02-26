import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone
from uuid import UUID

from app.core.config import get_settings
from app.db.models import IngestJob, IngestState, SourceType
from app.schemas.ingest import IngestResultAction
from app.services.error_codes import IngestErrorCode


class OpenClawActionTokenError(ValueError):
    pass


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(raw: str) -> bytes:
    padding = "=" * ((4 - len(raw) % 4) % 4)
    return base64.urlsafe_b64decode((raw + padding).encode("ascii"))


def _sign(payload_raw: bytes, secret: str) -> bytes:
    return hmac.new(secret.encode("utf-8"), payload_raw, hashlib.sha256).digest()


def _build_action_url(job_id: UUID, action: str) -> str:
    settings = get_settings()
    base = settings.api_base_url.rstrip("/")
    return f"{base}/ingest/actions/{job_id}/{action}"


def issue_action_token(
    job_id: UUID,
    action: str,
    *,
    now: datetime | None = None,
    ttl_seconds: int | None = None,
) -> tuple[str, datetime]:
    settings = get_settings()
    now_dt = now or _utc_now()
    token_ttl_seconds = ttl_seconds or settings.openclaw_action_ttl_seconds
    exp = int(now_dt.timestamp()) + max(1, token_ttl_seconds)
    payload = {
        "v": 1,
        "job_id": str(job_id),
        "action": action,
        "exp": exp,
    }
    payload_raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    signature = _sign(payload_raw, settings.openclaw_action_secret)
    token = f"{_b64url_encode(payload_raw)}.{_b64url_encode(signature)}"
    expires_at = datetime.fromtimestamp(exp, tz=timezone.utc)
    return token, expires_at


def verify_action_token(
    token: str,
    *,
    job_id: UUID,
    action: str,
    now: datetime | None = None,
) -> dict:
    settings = get_settings()
    if "." not in token:
        raise OpenClawActionTokenError("invalid token format")

    payload_b64, signature_b64 = token.split(".", 1)

    try:
        payload_raw = _b64url_decode(payload_b64)
        signature = _b64url_decode(signature_b64)
    except Exception as exc:  # noqa: BLE001
        raise OpenClawActionTokenError("invalid token encoding") from exc

    expected_signature = _sign(payload_raw, settings.openclaw_action_secret)
    if not hmac.compare_digest(signature, expected_signature):
        raise OpenClawActionTokenError("invalid token signature")

    try:
        payload = json.loads(payload_raw.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise OpenClawActionTokenError("invalid token payload") from exc

    if str(payload.get("job_id")) != str(job_id):
        raise OpenClawActionTokenError("token job mismatch")
    if payload.get("action") != action:
        raise OpenClawActionTokenError("token action mismatch")

    now_ts = int((now or _utc_now()).timestamp())
    exp = int(payload.get("exp", 0))
    if now_ts > exp:
        raise OpenClawActionTokenError("token expired")

    return payload


def build_result_actions(job: IngestJob, error_code: str | None) -> list[IngestResultAction]:
    if job.source != SourceType.telegram:
        return []
    if job.state not in {IngestState.FAILED, IngestState.NEEDS_REVIEW}:
        return []

    retry_token, retry_expires_at = issue_action_token(job.id, "retry")
    reprocess_token, reprocess_expires_at = issue_action_token(job.id, "reprocess")

    actions = [
        IngestResultAction(
            kind="button",
            action="retry",
            label="재시도",
            method="POST",
            url=_build_action_url(job.id, "retry"),
            token=retry_token,
            expires_at=retry_expires_at,
            payload={"clear_error": True},
        ),
        IngestResultAction(
            kind="button",
            action="reprocess",
            label="재처리",
            method="POST",
            url=_build_action_url(job.id, "reprocess"),
            token=reprocess_token,
            expires_at=reprocess_expires_at,
            payload={"reset_attempts": True, "clear_error": True},
        ),
    ]

    if error_code == IngestErrorCode.STORAGE_TEMP_FILE_MISSING:
        actions.append(
            IngestResultAction(
                kind="command",
                action="recover_upload",
                label="파일 재업로드",
                command=f"/recover_upload {job.id}",
                payload={"reason": IngestErrorCode.STORAGE_TEMP_FILE_MISSING},
            )
        )

    return actions
