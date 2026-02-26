import re
from datetime import date, datetime, timedelta

_PATTERNS = [
    re.compile(r"(?P<y>\d{4})-(?P<m>\d{2})-(?P<d>\d{2})"),
    re.compile(r"(?P<y>\d{4})\.(?P<m>\d{2})\.(?P<d>\d{2})"),
    re.compile(r"(?P<y>\d{4})/(?P<m>\d{2})/(?P<d>\d{2})"),
    re.compile(r"(?P<y>\d{4})(?P<m>\d{2})(?P<d>\d{2})"),
]
_PATTERN_YYMMDD = re.compile(r"(?<!\d)(?P<y>\d{2})(?P<m>\d{2})(?P<d>\d{2})(?!\d)")


def _safe_date(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def _infer_century(two_digit_year: int, ingested_at: datetime) -> int:
    base = ingested_at.year % 100
    year = 2000 + two_digit_year if two_digit_year <= base + 1 else 1900 + two_digit_year
    candidate = date(year, 1, 1)
    if candidate > (ingested_at + timedelta(days=365)).date():
        year -= 100
    return year


def parse_event_date_from_text(text: str | None, ingested_at: datetime) -> date | None:
    if not text:
        return None

    for pattern in _PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        y = int(match.group("y"))
        m = int(match.group("m"))
        d = int(match.group("d"))
        parsed = _safe_date(y, m, d)
        if parsed:
            return parsed

    match_yy = _PATTERN_YYMMDD.search(text)
    if match_yy:
        y = _infer_century(int(match_yy.group("y")), ingested_at)
        m = int(match_yy.group("m"))
        d = int(match_yy.group("d"))
        return _safe_date(y, m, d)

    return None
