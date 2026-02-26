#!/usr/bin/env python3
"""Auto-resolve review queue documents by reason.

Examples:
  python scripts/review_queue_auto_resolve.py --reason DUPLICATE_SUSPECT --dry-run
  python scripts/review_queue_auto_resolve.py --reason DUPLICATE_SUSPECT --limit 100
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.models import AuditLog, Document, DocumentTag, DocumentVersion, ReviewStatus, Tag
from app.db.session import SessionLocal
from app.services.search_sync_service import enqueue_document_index_sync_many


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Auto-resolve review queue items by reason")
    parser.add_argument("--reason", action="append", default=["DUPLICATE_SUSPECT"], help="review reason to remove")
    parser.add_argument(
        "--match-mode",
        choices=["contains-any", "contains-all"],
        default="contains-all",
        help="target match condition for review reasons",
    )
    parser.add_argument(
        "--only-single-reason",
        action="store_true",
        default=True,
        help="process only documents whose reasons are exactly the target reasons",
    )
    parser.add_argument(
        "--include-mixed-reasons",
        action="store_true",
        help="allow processing documents that contain extra reasons",
    )
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def _normalized_reasons(reasons: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in reasons:
        value = str(raw).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _get_tag_names(db: Session, document_id: UUID) -> list[str]:
    stmt = (
        select(Tag.name)
        .join(DocumentTag, DocumentTag.tag_id == Tag.id)
        .where(DocumentTag.document_id == document_id)
        .order_by(Tag.name.asc())
    )
    return list(db.execute(stmt).scalars().all())


def _is_target(
    review_reasons: list[str],
    *,
    target_reasons: set[str],
    match_mode: str,
    only_single_reason: bool,
) -> bool:
    if not review_reasons:
        return False
    reason_set = set(review_reasons)
    if match_mode == "contains-any":
        matched = bool(reason_set & target_reasons)
    else:
        matched = target_reasons.issubset(reason_set)
    if not matched:
        return False
    if only_single_reason and reason_set != target_reasons:
        return False
    return True


def main() -> None:
    args = parse_args()
    target_reasons = set(_normalized_reasons(args.reason))
    if not target_reasons:
        raise SystemExit("at least one --reason is required")
    only_single_reason = args.only_single_reason and not args.include_mixed_reasons

    printed_rows: list[str] = []

    with SessionLocal() as db:
        docs = db.execute(
            select(Document)
            .where(Document.review_status == ReviewStatus.NEEDS_REVIEW)
            .order_by(Document.created_at.desc())
            .limit(args.limit)
        ).scalars().all()

        matched_docs: list[Document] = [
            doc
            for doc in docs
            if _is_target(
                list(doc.review_reasons),
                target_reasons=target_reasons,
                match_mode=args.match_mode,
                only_single_reason=only_single_reason,
            )
        ]

        if not matched_docs:
            print(
                f"no target documents found "
                f"(reason={sorted(target_reasons)} match_mode={args.match_mode} only_single_reason={only_single_reason})"
            )
            return

        updated_doc_ids: list[UUID] = []
        for doc in matched_docs:
            printed_rows.append(f"- doc_id={doc.id} source_ref={doc.source_ref} title={doc.title!r}")

            before = {
                "review_status": doc.review_status.value,
                "review_reasons": list(doc.review_reasons),
            }

            next_reasons = [reason for reason in doc.review_reasons if reason not in target_reasons]
            if next_reasons == list(doc.review_reasons):
                continue

            doc.review_reasons = next_reasons
            doc.review_status = ReviewStatus.RESOLVED if not next_reasons else ReviewStatus.NEEDS_REVIEW
            doc.current_version_no += 1
            db.add(doc)

            tag_names = _get_tag_names(db, doc.id)
            db.add(
                DocumentVersion(
                    document_id=doc.id,
                    version_no=doc.current_version_no,
                    title=doc.title,
                    description=doc.description,
                    summary=doc.summary,
                    category_id=doc.category_id,
                    event_date=doc.event_date,
                    tags_snapshot=tag_names,
                    change_reason="review_queue_auto_resolve",
                    created_by=None,
                )
            )
            db.add(
                AuditLog(
                    actor_user_id=None,
                    action="REVIEW_QUEUE_AUTO_RESOLVE",
                    target_type="document",
                    target_id=doc.id,
                    source=doc.source,
                    source_ref=doc.source_ref,
                    before_json=before,
                    after_json={
                        "review_status": doc.review_status.value,
                        "review_reasons": list(doc.review_reasons),
                        "removed_reasons": sorted(target_reasons),
                        "dry_run": args.dry_run,
                    },
                )
            )
            updated_doc_ids.append(doc.id)

        if args.dry_run:
            db.rollback()
        else:
            db.commit()
            if updated_doc_ids:
                enqueue_document_index_sync_many(updated_doc_ids)

    print(
        f"review_queue_auto_resolve "
        f"dry_run={args.dry_run} "
        f"target={sorted(target_reasons)} "
        f"matched={len(matched_docs)} "
        f"updated={len(updated_doc_ids)}"
    )
    for row in printed_rows:
        print(row)


if __name__ == "__main__":
    main()
