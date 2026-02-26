#!/usr/bin/env python3
"""
OpenClaw/Telegram bridge uploader for Archive API.

Usage:
  python scripts/openclaw_ingest_bridge.py \
    --file /abs/path/to/file.xlsx \
    --caption "샘플 점검 문서 요약본" \
    --message-id 663 \
    --chat-id telegram:1000000000

Auth defaults can come from env:
  ARCHIVE_API=http://localhost:8000/api
  ARCHIVE_USERNAME=admin
  ARCHIVE_PASSWORD=ChangeMe123!
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

import httpx


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Upload Telegram file to archive ingest endpoint with login session")
    p.add_argument("--api", default=os.getenv("ARCHIVE_API", "http://localhost:8000/api"))
    p.add_argument("--username", default=os.getenv("ARCHIVE_USERNAME", "admin"))
    p.add_argument("--password", default=os.getenv("ARCHIVE_PASSWORD", "ChangeMe123!"))
    p.add_argument("--file", required=True, help="absolute or relative file path")
    p.add_argument("--caption", default="")
    p.add_argument("--message-id", required=True)
    p.add_argument("--chat-id", required=True)
    p.add_argument("--sent-at", default="")
    p.add_argument("--source", default="telegram", choices=["telegram"])  # bridge is telegram-focused
    p.add_argument("--source-ref", default="")
    p.add_argument("--original-name", default="", help="override uploaded filename shown to backend")
    p.add_argument("--retries", type=int, default=3, help="retry count for transient failures")
    p.add_argument("--retry-wait", type=float, default=1.5, help="seconds between retries")
    return p.parse_args()


def ensure_exists(path: Path) -> Path:
    path = path.expanduser().resolve()
    if not path.exists():
        raise SystemExit(f"File not found: {path}")
    return path


def login(client: httpx.Client, api: str, username: str, password: str) -> None:
    resp = client.post(
        f"{api}/auth/login",
        json={"username": username, "password": password},
        headers={"Content-Type": "application/json"},
    )
    if resp.status_code >= 400:
        raise SystemExit(f"Login failed ({resp.status_code}): {resp.text}")


def _slug(text: str, max_len: int = 40) -> str:
    text = (text or "").strip()
    text = re.sub(r"\s+", "_", text)
    text = re.sub(r"[^\w\-가-힣_]", "", text)
    text = text.strip("._-")
    if not text:
        return ""
    return text[:max_len]


def _auto_filename(file_path: Path, caption: str) -> str:
    ext = file_path.suffix if file_path.suffix else ".bin"
    first_line = (caption or "").strip().splitlines()[0] if (caption or "").strip() else ""
    title = _slug(first_line, max_len=40)
    if title:
        return f"{title}{ext}"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{ts}{ext}"


def ingest_telegram(
    client: httpx.Client,
    api: str,
    file_path: Path,
    caption: str,
    source_ref: str,
    message_id: str,
    chat_id: str,
    sent_at: str,
    original_name: str,
) -> dict:
    data = {
        "source": "telegram",
        "source_ref": source_ref,
        "message_id": message_id,
        "chat_id": chat_id,
        "caption": caption,
    }
    if sent_at:
        data["sent_at"] = sent_at

    upload_name = (original_name or _auto_filename(file_path, caption)).strip()
    with file_path.open("rb") as f:
        resp = client.post(
            f"{api}/ingest/telegram",
            data=data,
            files={"file": (upload_name, f, "application/octet-stream")},
        )

    if resp.status_code >= 400:
        raise RuntimeError(f"Ingest failed ({resp.status_code}): {resp.text}")
    return resp.json()


def main() -> None:
    args = parse_args()
    file_path = ensure_exists(Path(args.file))
    source_ref = args.source_ref or f"msg:{args.message_id}"

    last_err = None
    with httpx.Client(timeout=60.0) as client:
        login(client, args.api, args.username, args.password)
        for attempt in range(1, max(1, args.retries) + 1):
            try:
                result = ingest_telegram(
                    client,
                    api=args.api,
                    file_path=file_path,
                    caption=args.caption,
                    source_ref=source_ref,
                    message_id=args.message_id,
                    chat_id=args.chat_id,
                    sent_at=args.sent_at,
                    original_name=args.original_name,
                )
                print(json.dumps({
                    "ok": True,
                    "attempt": attempt,
                    "source_ref": source_ref,
                    "file": str(file_path),
                    "result": result,
                }, ensure_ascii=False, indent=2))
                return
            except Exception as e:
                last_err = e
                if attempt < max(1, args.retries):
                    time.sleep(max(0.1, args.retry_wait))

    raise SystemExit(f"Bridge upload failed after {max(1,args.retries)} attempts: {last_err}")


if __name__ == "__main__":
    main()
