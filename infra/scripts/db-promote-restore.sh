#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
COMPOSE="$SCRIPT_DIR/compose.sh"

SOURCE_DB=${1:-${SOURCE_DB:-}}
ACTIVE_DB=${ACTIVE_DB:-${POSTGRES_DB:-archive}}
CONFIRM=${CONFIRM:-}
RESTART_SERVICES=${RESTART_SERVICES:-true}

if [ -z "$SOURCE_DB" ]; then
  echo "usage: $0 <source-db-name>"
  echo "or: SOURCE_DB=archive_restore_test CONFIRM=YES $0"
  exit 1
fi

case "$SOURCE_DB" in
  *[!A-Za-z0-9_-]* | "")
    echo "invalid SOURCE_DB: $SOURCE_DB"
    exit 1
    ;;
esac

case "$ACTIVE_DB" in
  *[!A-Za-z0-9_-]* | "")
    echo "invalid ACTIVE_DB: $ACTIVE_DB"
    exit 1
    ;;
esac

if [ "$SOURCE_DB" = "$ACTIVE_DB" ]; then
  echo "SOURCE_DB and ACTIVE_DB are identical: $SOURCE_DB"
  exit 1
fi

if [ "$CONFIRM" != "YES" ]; then
  echo "This will replace active database '$ACTIVE_DB' with '$SOURCE_DB'."
  echo "Run again with CONFIRM=YES to continue."
  exit 1
fi

echo "checking source database exists: $SOURCE_DB"
SOURCE_EXISTS=$(
  "$COMPOSE" exec -T postgres sh -lc "PGPASSWORD=\"\$POSTGRES_PASSWORD\" psql -U \"\$POSTGRES_USER\" -d postgres -Atc \"SELECT 1 FROM pg_database WHERE datname='${SOURCE_DB}' LIMIT 1;\""
)
if [ "$SOURCE_EXISTS" != "1" ]; then
  echo "source database not found: $SOURCE_DB"
  exit 1
fi

echo "stopping write services..."
"$COMPOSE" stop api worker beat >/dev/null

echo "promoting database..."
"$COMPOSE" exec -T postgres sh -lc "PGPASSWORD=\"\$POSTGRES_PASSWORD\" psql -U \"\$POSTGRES_USER\" -d postgres -v ON_ERROR_STOP=1 -c \"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname IN ('${ACTIVE_DB}','${SOURCE_DB}') AND pid <> pg_backend_pid();\" -c \"DROP DATABASE IF EXISTS \\\"${ACTIVE_DB}\\\";\" -c \"ALTER DATABASE \\\"${SOURCE_DB}\\\" RENAME TO \\\"${ACTIVE_DB}\\\";\""

if [ "$RESTART_SERVICES" = "true" ]; then
  echo "restarting services..."
  "$COMPOSE" up -d api worker beat >/dev/null
fi

echo "database promote done"
echo "  active_db: $ACTIVE_DB"
echo "  source_db: $SOURCE_DB"
