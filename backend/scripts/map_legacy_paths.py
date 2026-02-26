#!/usr/bin/env python3
"""기존 파일 경로 -> sha256 경로 매핑 생성."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    args = parser.parse_args()

    root = Path(args.root)
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        digest = sha256_of(p)
        ext = p.suffix.lstrip(".") or "bin"
        mapped = f"{digest[0:2]}/{digest[2:4]}/{digest}.{ext}"
        print(f"{p}\t{mapped}")


if __name__ == "__main__":
    main()
