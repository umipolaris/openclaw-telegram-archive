#!/bin/sh
set -eu

TS=$(date +%Y%m%d_%H%M%S)
OUT="/backup/archive_${TS}.dump"

PGHOST=${PGHOST:-postgres}
PGPORT=${PGPORT:-5432}
PGUSER=${POSTGRES_USER:-archive}
PGDATABASE=${POSTGRES_DB:-archive}
PGPASSWORD=${POSTGRES_PASSWORD:-archive_pw}
export PGPASSWORD

pg_dump -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -Fc "$PGDATABASE" > "$OUT"
echo "db backup done: $OUT"
