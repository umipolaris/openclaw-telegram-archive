#!/usr/bin/env python3
"""운영 리포트 생성 작업을 큐잉한다.

사용 예시:
  python scripts/generate_ops_report.py --days 7
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.worker.tasks_reports import generate_weekly_ops_report_task


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Queue ops report generation task")
    parser.add_argument("--days", type=int, default=7)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    job = generate_weekly_ops_report_task.delay(days=args.days)
    print(f"queued ops report task_id={job.id} days={args.days}")


if __name__ == "__main__":
    main()
