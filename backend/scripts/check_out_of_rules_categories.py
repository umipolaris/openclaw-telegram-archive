#!/usr/bin/env python
"""
활성 ruleset 기준으로 문서 카테고리 정합성을 점검합니다.

Usage:
  python scripts/check_out_of_rules_categories.py
  python scripts/check_out_of_rules_categories.py --fix --batch-size 200
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import sys
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.models import Category, Document, RuleVersion
from app.db.session import SessionLocal
from app.services.backfill_service import process_backfill_payload
from app.services.rule_categories import extract_categories_from_rules_json


@dataclass
class OffendingCategory:
    category_id: UUID
    category_name: str
    doc_count: int


def _get_active_rule_version(db) -> RuleVersion | None:
    stmt = (
        select(RuleVersion)
        .where(RuleVersion.is_active.is_(True))
        .order_by(RuleVersion.published_at.desc().nulls_last(), RuleVersion.created_at.desc())
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def _find_offending_categories(db, rules_json: dict) -> list[OffendingCategory]:
    allowed = extract_categories_from_rules_json(rules_json)
    allowed_keys = {name.strip().lower() for name in allowed}

    rows = (
        db.execute(
            select(Category.id, Category.name, func.count(Document.id))
            .join(Document, Document.category_id == Category.id)
            .group_by(Category.id, Category.name)
            .order_by(Category.name.asc())
        )
        .all()
    )

    out: list[OffendingCategory] = []
    for category_id, category_name, doc_count in rows:
        if category_name.strip().lower() not in allowed_keys:
            out.append(OffendingCategory(category_id=category_id, category_name=category_name, doc_count=int(doc_count)))
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fix", action="store_true", help="규칙 밖 카테고리 문서를 백필 재분류합니다.")
    parser.add_argument("--batch-size", type=int, default=200)
    args = parser.parse_args()

    with SessionLocal() as db:
        rv = _get_active_rule_version(db)
        if not rv:
            print("활성 ruleset 없음")
            return

        offending = _find_offending_categories(db, rv.rules_json)
        if not offending:
            print("규칙 밖 카테고리 문서 없음")
            return

        print("규칙 밖 카테고리:")
        for row in offending:
            print(f"- {row.category_name} ({row.doc_count}건)")

        if not args.fix:
            return

        print("")
        print("백필 재분류 실행:")
        for row in offending:
            payload = {
                "rule_version_id": str(rv.id),
                "batch_size": max(1, args.batch_size),
                "filter": {"category_id": str(row.category_id)},
            }
            result = process_backfill_payload(db, payload)
            print(f"- {row.category_name}: updated={result.get('updated')} skipped={result.get('skipped')} failed={result.get('failed')}")


if __name__ == "__main__":
    main()
