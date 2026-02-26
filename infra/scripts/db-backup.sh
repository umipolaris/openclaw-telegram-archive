#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
INFRA_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
COMPOSE="$SCRIPT_DIR/compose.sh"

BACKUP_DIR=${BACKUP_DIR:-"$INFRA_DIR/data/backup/db"}
RETENTION_DAYS=${BACKUP_RETENTION_DAYS:-30}
TS=$(date +%Y%m%d_%H%M%S)

mkdir -p "$BACKUP_DIR"

DB_NAME=${POSTGRES_DB:-archive}
OUT_FILE="$BACKUP_DIR/archive_${DB_NAME}_${TS}.dump"
TMP_FILE="${OUT_FILE}.tmp"
META_FILE="${OUT_FILE}.meta"

"$COMPOSE" exec -T postgres sh -lc \
  'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc --no-owner --no-privileges' \
  > "$TMP_FILE"

mv "$TMP_FILE" "$OUT_FILE"

if command -v sha256sum >/dev/null 2>&1; then
  SHA256=$(sha256sum "$OUT_FILE" | awk "{print \$1}")
elif command -v shasum >/dev/null 2>&1; then
  SHA256=$(shasum -a 256 "$OUT_FILE" | awk "{print \$1}")
else
  SHA256="unavailable"
fi

{
  echo "timestamp=$TS"
  echo "db_name=$DB_NAME"
  echo "file=$(basename "$OUT_FILE")"
  echo "sha256=$SHA256"
  echo "app_profile=${APP_PROFILE:-dev}"
} > "$META_FILE"

if [ "$RETENTION_DAYS" -gt 0 ] 2>/dev/null; then
  find "$BACKUP_DIR" -type f \( -name "*.dump" -o -name "*.dump.meta" \) -mtime +"$RETENTION_DAYS" -delete
fi

echo "db backup done"
echo "  file: $OUT_FILE"
echo "  meta: $META_FILE"
echo "  sha256: $SHA256"
