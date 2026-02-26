#!/usr/bin/env python3
"""실패/검토 잡 수동 재처리 트리거."""

from __future__ import annotations

import argparse

from app.worker.tasks_ingest import process_ingest_job_task


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("job_id")
    args = parser.parse_args()
    process_ingest_job_task.delay(args.job_id)
    print(f"requeued: {args.job_id}")


if __name__ == "__main__":
    main()
