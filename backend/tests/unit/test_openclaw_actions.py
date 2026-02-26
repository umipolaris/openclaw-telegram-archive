from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

pytest.importorskip("sqlalchemy")

from app.db.models import IngestJob, IngestState, SourceType
from app.services.error_codes import IngestErrorCode
from app.services.openclaw_actions import (
    OpenClawActionTokenError,
    build_result_actions,
    issue_action_token,
    verify_action_token,
)


def test_issue_and_verify_action_token_success():
    job_id = uuid4()
    now = datetime(2026, 2, 24, 12, 0, tzinfo=timezone.utc)
    token, expires_at = issue_action_token(job_id, "retry", now=now, ttl_seconds=120)

    payload = verify_action_token(token, job_id=job_id, action="retry", now=now + timedelta(seconds=30))
    assert payload["job_id"] == str(job_id)
    assert payload["action"] == "retry"
    assert expires_at == datetime(2026, 2, 24, 12, 2, tzinfo=timezone.utc)


def test_verify_action_token_expired():
    job_id = uuid4()
    now = datetime(2026, 2, 24, 12, 0, tzinfo=timezone.utc)
    token, _ = issue_action_token(job_id, "retry", now=now, ttl_seconds=1)

    with pytest.raises(OpenClawActionTokenError) as exc_info:
        verify_action_token(token, job_id=job_id, action="retry", now=now + timedelta(seconds=2))
    assert "expired" in str(exc_info.value)


def test_verify_action_token_mismatch_and_tamper():
    job_id = uuid4()
    token, _ = issue_action_token(job_id, "retry")

    with pytest.raises(OpenClawActionTokenError) as exc_info:
        verify_action_token(token, job_id=uuid4(), action="retry")
    assert "job mismatch" in str(exc_info.value)

    payload_b64, signature_b64 = token.split(".", 1)
    tampered_payload_b64 = ("A" if payload_b64[0] != "A" else "B") + payload_b64[1:]
    tampered = f"{tampered_payload_b64}.{signature_b64}"
    with pytest.raises(OpenClawActionTokenError) as exc_info:
        verify_action_token(tampered, job_id=job_id, action="retry")
    assert "signature" in str(exc_info.value)


def test_build_result_actions_for_failed_telegram_job():
    job = IngestJob(id=uuid4(), source=SourceType.telegram, state=IngestState.FAILED, payload_json={})
    actions = build_result_actions(job, IngestErrorCode.STORAGE_TEMP_FILE_MISSING)

    action_names = {item.action for item in actions}
    assert "retry" in action_names
    assert "reprocess" in action_names
    assert "recover_upload" in action_names
