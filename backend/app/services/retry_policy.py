from datetime import datetime, timedelta, timezone


def now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def should_retry(attempt_count: int, max_attempts: int) -> bool:
    if max_attempts <= 0:
        return False
    return attempt_count < max_attempts


def compute_backoff_seconds(attempt_count: int, base_seconds: int, max_seconds: int) -> int:
    safe_attempt = max(1, int(attempt_count))
    safe_base = max(1, int(base_seconds))
    safe_max = max(safe_base, int(max_seconds))

    # attempt=1 -> base, attempt=2 -> 2*base, ...
    backoff = safe_base * (2 ** (safe_attempt - 1))
    return min(backoff, safe_max)


def compute_retry_after(attempt_count: int, base_seconds: int, max_seconds: int, now: datetime | None = None) -> datetime:
    ref = now or now_utc()
    delay = compute_backoff_seconds(attempt_count, base_seconds, max_seconds)
    return ref + timedelta(seconds=delay)
