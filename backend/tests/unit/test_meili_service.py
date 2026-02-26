from datetime import date
from uuid import UUID

import pytest

pytest.importorskip("sqlalchemy")

from app.services.meili_service import build_filter_expression


def test_build_filter_expression_with_all_supported_fields():
    expr = build_filter_expression(
        category_id=UUID("11111111-1111-1111-1111-111111111111"),
        category_name="회의",
        tag_slug="set:dcp",
        event_date_from=date(2026, 2, 1),
        event_date_to=date(2026, 2, 24),
        review_status="NEEDS_REVIEW",
    )

    assert expr is not None
    assert 'category_id = "11111111-1111-1111-1111-111111111111"' in expr
    assert 'category = "회의"' in expr
    assert 'tag_slugs = "set:dcp"' in expr
    assert 'event_date >= "2026-02-01"' in expr
    assert 'event_date <= "2026-02-24"' in expr
    assert 'review_status = "NEEDS_REVIEW"' in expr


def test_build_filter_expression_uncategorized_clause():
    expr = build_filter_expression(category_name="미분류")
    assert expr == "is_uncategorized = true"


def test_build_filter_expression_returns_none_if_empty():
    assert build_filter_expression() is None
