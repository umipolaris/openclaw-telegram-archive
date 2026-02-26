#!/usr/bin/env python3
"""Run basic UAT smoke checks against archive API.

Example:
  python scripts/smoke_uat.py \
    --api http://localhost:8000/api \
    --username admin \
    --password 'ChangeMe123!' \
    --include-download
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

import httpx


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Archive API smoke UAT")
    parser.add_argument("--api", default="http://localhost:8000/api")
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--include-download", action="store_true")
    return parser.parse_args()


def _expect_status(resp: httpx.Response, expected: int, step: str) -> None:
    if resp.status_code != expected:
        raise RuntimeError(
            f"{step} failed: expected {expected}, got {resp.status_code}, body={resp.text[:500]}"
        )


def _get_json(resp: httpx.Response, step: str) -> dict[str, Any]:
    try:
        body = resp.json()
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{step} returned non-json: {resp.text[:500]}") from exc
    if not isinstance(body, dict):
        raise RuntimeError(f"{step} returned non-object json: {type(body).__name__}")
    return body


def main() -> None:
    args = parse_args()
    results: list[str] = []

    with httpx.Client(timeout=args.timeout, follow_redirects=True) as client:
        health_resp = client.get(f"{args.api}/health")
        _expect_status(health_resp, 200, "health")
        health = _get_json(health_resp, "health")
        results.append(f"health.status={health.get('status')}")
        results.append(f"health.read_only_mode={health.get('dependencies', {}).get('read_only_mode')}")

        login_resp = client.post(
            f"{args.api}/auth/login",
            json={"username": args.username, "password": args.password},
        )
        _expect_status(login_resp, 200, "login")
        me_resp = client.get(f"{args.api}/auth/me")
        _expect_status(me_resp, 200, "auth/me")
        me = _get_json(me_resp, "auth/me")
        results.append(f"user={me.get('username')} role={me.get('role')}")

        docs_resp = client.get(f"{args.api}/documents", params={"page": 1, "size": 5})
        _expect_status(docs_resp, 200, "documents")
        docs = _get_json(docs_resp, "documents")
        items = docs.get("items", [])
        total = docs.get("total")
        results.append(f"documents.total={total} page_items={len(items)}")

        first_doc_id = None
        if items:
            first_doc_id = items[0].get("id")
            detail_resp = client.get(f"{args.api}/documents/{first_doc_id}")
            _expect_status(detail_resp, 200, "document_detail")
            detail = _get_json(detail_resp, "document_detail")
            results.append(f"document.detail.id={detail.get('id')} files={len(detail.get('files', []))}")

            if args.include_download and detail.get("files"):
                first_file = detail["files"][0]
                file_id = first_file.get("id")
                download_resp = client.get(f"{args.api}/files/{file_id}/download")
                _expect_status(download_resp, 200, "file_download")
                size = len(download_resp.content)
                results.append(f"file.download.id={file_id} bytes={size}")

        review_resp = client.get(f"{args.api}/review-queue", params={"page": 1, "size": 20})
        _expect_status(review_resp, 200, "review_queue")
        review = _get_json(review_resp, "review_queue")
        results.append(f"review_queue.total={review.get('total')}")

        dashboard_resp = client.get(f"{args.api}/dashboard/summary")
        _expect_status(dashboard_resp, 200, "dashboard_summary")
        dashboard = _get_json(dashboard_resp, "dashboard_summary")
        results.append(f"dashboard.total_documents={dashboard.get('total_documents')}")

        logout_resp = client.post(f"{args.api}/auth/logout")
        _expect_status(logout_resp, 200, "logout")
        results.append("logout=ok")

    print("smoke_uat: ok")
    for line in results:
        print(f"- {line}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(f"smoke_uat: failed: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
