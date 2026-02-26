#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
INFRA_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
COMPOSE="$SCRIPT_DIR/compose.sh"

BACKUP_FILE=${1:-${BACKUP_FILE:-}}
TARGET_DIR=${TARGET_DIR:-"$INFRA_DIR/data/minio"}
CONFIRM=${CONFIRM:-}
RESTART_SERVICES=${RESTART_SERVICES:-true}

if [ -z "$BACKUP_FILE" ]; then
  echo "usage: $0 <objects-backup.tar.gz>"
  exit 1
fi

if [ ! -f "$BACKUP_FILE" ]; then
  echo "backup file not found: $BACKUP_FILE"
  exit 1
fi

if [ "$CONFIRM" != "YES" ]; then
  echo "This will replace all files in '$TARGET_DIR'."
  echo "Run again with CONFIRM=YES to continue."
  exit 1
fi

mkdir -p "$TARGET_DIR"

echo "stopping related services..."
"$COMPOSE" stop api worker beat minio >/dev/null

echo "restoring object files into $TARGET_DIR"
rm -rf "$TARGET_DIR"/*
tar -xzf "$BACKUP_FILE" -C "$TARGET_DIR"

if [ "$RESTART_SERVICES" = "true" ]; then
  echo "restarting services..."
  "$COMPOSE" up -d minio api worker beat >/dev/null
fi

echo "objects restore done"
echo "  backup: $BACKUP_FILE"
echo "  target_dir: $TARGET_DIR"
