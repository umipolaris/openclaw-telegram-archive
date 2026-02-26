from datetime import datetime, timezone

from app.services.date_parser import parse_event_date_from_text


def test_parse_supported_patterns():
    ingested_at = datetime(2026, 2, 24, tzinfo=timezone.utc)

    assert parse_event_date_from_text("2026-02-24", ingested_at).isoformat() == "2026-02-24"
    assert parse_event_date_from_text("2026.02.24", ingested_at).isoformat() == "2026-02-24"
    assert parse_event_date_from_text("2026/02/24", ingested_at).isoformat() == "2026-02-24"
    assert parse_event_date_from_text("20260224", ingested_at).isoformat() == "2026-02-24"


def test_parse_yymmdd_with_century_inference():
    ingested_at = datetime(2026, 2, 24, tzinfo=timezone.utc)
    assert parse_event_date_from_text("260224", ingested_at).isoformat() == "2026-02-24"
    assert parse_event_date_from_text("990101", ingested_at).isoformat() == "1999-01-01"
