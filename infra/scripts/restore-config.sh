#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
INFRA_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)

BACKUP_FILE=${1:-${BACKUP_FILE:-}}
MODE=${MODE:-preview}
CONFIRM=${CONFIRM:-}

if [ -z "$BACKUP_FILE" ]; then
  echo "usage: $0 <config-backup.tar.gz>"
  echo "mode: MODE=preview(default) | MODE=apply"
  exit 1
fi

if [ ! -f "$BACKUP_FILE" ]; then
  echo "backup file not found: $BACKUP_FILE"
  exit 1
fi

if [ "$MODE" = "preview" ]; then
  TS=$(date +%Y%m%d_%H%M%S)
  OUT_DIR="$INFRA_DIR/data/restore/config_preview_${TS}"
  mkdir -p "$OUT_DIR"
  tar -xzf "$BACKUP_FILE" -C "$OUT_DIR"
  echo "config preview restore done"
  echo "  backup: $BACKUP_FILE"
  echo "  extracted_to: $OUT_DIR"
  exit 0
fi

if [ "$MODE" = "apply" ]; then
  if [ "$CONFIRM" != "YES" ]; then
    echo "MODE=apply will overwrite infra config files."
    echo "Run again with MODE=apply CONFIRM=YES to continue."
    exit 1
  fi
  tar -xzf "$BACKUP_FILE" -C "$INFRA_DIR"
  echo "config apply restore done"
  echo "  backup: $BACKUP_FILE"
  echo "  target: $INFRA_DIR"
  exit 0
fi

echo "invalid MODE: $MODE (use preview or apply)"
exit 1
