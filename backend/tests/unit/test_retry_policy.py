from datetime import datetime, timezone

from app.services.retry_policy import compute_backoff_seconds, compute_retry_after, should_retry


def test_should_retry_respects_attempt_limits():
    assert should_retry(attempt_count=0, max_attempts=5) is True
    assert should_retry(attempt_count=4, max_attempts=5) is True
    assert should_retry(attempt_count=5, max_attempts=5) is False
    assert should_retry(attempt_count=1, max_attempts=0) is False


def test_compute_backoff_seconds_exponential_and_clamp():
    assert compute_backoff_seconds(attempt_count=1, base_seconds=30, max_seconds=1800) == 30
    assert compute_backoff_seconds(attempt_count=2, base_seconds=30, max_seconds=1800) == 60
    assert compute_backoff_seconds(attempt_count=3, base_seconds=30, max_seconds=1800) == 120
    assert compute_backoff_seconds(attempt_count=10, base_seconds=30, max_seconds=1800) == 1800


def test_compute_retry_after_uses_backoff_seconds():
    now = datetime(2026, 2, 24, tzinfo=timezone.utc)
    retry_after = compute_retry_after(attempt_count=2, base_seconds=30, max_seconds=1800, now=now)
    assert retry_after.isoformat() == "2026-02-24T00:01:00+00:00"
