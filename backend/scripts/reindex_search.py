#!/usr/bin/env python3
"""Meilisearch 문서 인덱스 재빌드 작업을 큐잉한다.

사용 예시:
  python scripts/reindex_search.py
  python scripts/reindex_search.py --batch-size 1000 --limit 5000
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.worker.tasks_search import rebuild_documents_index_task


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Queue rebuild for search index")
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--limit", type=int, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    job = rebuild_documents_index_task.delay(batch_size=args.batch_size, limit=args.limit)
    print(f"queued search reindex task_id={job.id} batch_size={args.batch_size} limit={args.limit}")


if __name__ == "__main__":
    main()
