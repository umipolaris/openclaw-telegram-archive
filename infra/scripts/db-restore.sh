#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
COMPOSE="$SCRIPT_DIR/compose.sh"

BACKUP_FILE=${1:-${BACKUP_FILE:-}}
TARGET_DB=${TARGET_DB:-${POSTGRES_DB:-archive}}
CONFIRM=${CONFIRM:-}
RESTART_SERVICES=${RESTART_SERVICES:-true}

if [ -z "$BACKUP_FILE" ]; then
  echo "usage: $0 <backup-file(.dump|.sql)>"
  echo "or: BACKUP_FILE=... CONFIRM=YES $0"
  exit 1
fi

if [ ! -f "$BACKUP_FILE" ]; then
  echo "backup file not found: $BACKUP_FILE"
  exit 1
fi

case "$TARGET_DB" in
  *[!A-Za-z0-9_-]* | "")
    echo "invalid TARGET_DB: $TARGET_DB"
    exit 1
    ;;
esac

if [ "$CONFIRM" != "YES" ]; then
  echo "This will DROP and recreate database '$TARGET_DB'."
  echo "Run again with CONFIRM=YES to continue."
  exit 1
fi

echo "stopping write services..."
"$COMPOSE" stop api worker beat >/dev/null

echo "drop & recreate database: $TARGET_DB"
"$COMPOSE" exec -T postgres sh -lc "PGPASSWORD=\"\$POSTGRES_PASSWORD\" psql -U \"\$POSTGRES_USER\" -d postgres -v ON_ERROR_STOP=1 -c \"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='${TARGET_DB}' AND pid <> pg_backend_pid();\" -c \"DROP DATABASE IF EXISTS \\\"${TARGET_DB}\\\";\" -c \"CREATE DATABASE \\\"${TARGET_DB}\\\";\""

case "$BACKUP_FILE" in
  *.dump)
    echo "restoring custom dump..."
    cat "$BACKUP_FILE" | "$COMPOSE" exec -T postgres sh -lc "PGPASSWORD=\"\$POSTGRES_PASSWORD\" pg_restore -U \"\$POSTGRES_USER\" -d \"${TARGET_DB}\" --clean --if-exists --no-owner --no-privileges"
    ;;
  *.sql)
    echo "restoring sql dump..."
    cat "$BACKUP_FILE" | "$COMPOSE" exec -T postgres sh -lc "PGPASSWORD=\"\$POSTGRES_PASSWORD\" psql -U \"\$POSTGRES_USER\" -d \"${TARGET_DB}\" -v ON_ERROR_STOP=1"
    ;;
  *)
    echo "unsupported backup extension: $BACKUP_FILE"
    echo "supported: .dump, .sql"
    exit 1
    ;;
esac

if [ "$RESTART_SERVICES" = "true" ]; then
  echo "restarting services..."
  "$COMPOSE" up -d api worker beat >/dev/null
fi

echo "db restore done"
echo "  backup: $BACKUP_FILE"
echo "  target_db: $TARGET_DB"
