#!/bin/sh
set -eu

TS=$(date +%Y%m%d_%H%M%S)
OUT_DIR="/backup/objects_${TS}"
mkdir -p "$OUT_DIR"

# 운영에서는 mc mirror 또는 스토리지 스냅샷을 사용.
echo "object backup placeholder: $OUT_DIR"
