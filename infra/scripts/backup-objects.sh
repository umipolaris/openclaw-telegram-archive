#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
INFRA_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)

if [ -d /backup ]; then
  BACKUP_BASE=${BACKUP_BASE:-/backup}
else
  BACKUP_BASE=${BACKUP_BASE:-"$INFRA_DIR/data/backup"}
fi

RETENTION_DAYS=${BACKUP_RETENTION_DAYS:-30}
TS=$(date +%Y%m%d_%H%M%S)
OUT_DIR="$BACKUP_BASE/objects"
mkdir -p "$OUT_DIR"

sha256_file() {
  target=$1
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$target" | awk "{print \$1}"
    return
  fi
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$target" | awk "{print \$1}"
    return
  fi
  echo "unavailable"
}

backup_dir() {
  label=$1
  source_dir=$2
  out_file="$OUT_DIR/objects_${label}_${TS}.tar.gz"
  meta_file="${out_file}.meta"
  tmp_file="${out_file}.tmp"

  tar -czf "$tmp_file" -C "$source_dir" .
  mv "$tmp_file" "$out_file"
  digest=$(sha256_file "$out_file")

  {
    echo "timestamp=$TS"
    echo "type=objects"
    echo "label=$label"
    echo "source_dir=$source_dir"
    echo "file=$(basename "$out_file")"
    echo "sha256=$digest"
    echo "app_profile=${APP_PROFILE:-dev}"
  } > "$meta_file"

  echo "objects backup done"
  echo "  label: $label"
  echo "  file: $out_file"
  echo "  meta: $meta_file"
  echo "  sha256: $digest"
}

did_backup=false

for candidate in "/data/minio" "$INFRA_DIR/data/minio"; do
  if [ -d "$candidate" ] && [ "$(ls -A "$candidate" 2>/dev/null || true)" != "" ]; then
    backup_dir "minio" "$candidate"
    did_backup=true
    break
  fi
done

for candidate in "/data/archive" "$INFRA_DIR/data/archive"; do
  if [ -d "$candidate" ] && [ "$(ls -A "$candidate" 2>/dev/null || true)" != "" ]; then
    backup_dir "disk" "$candidate"
    did_backup=true
    break
  fi
done

if [ "$did_backup" = false ]; then
  echo "no object storage data found (minio or disk storage)"
  exit 1
fi

if [ "$RETENTION_DAYS" -gt 0 ] 2>/dev/null; then
  find "$OUT_DIR" -type f \( -name "*.tar.gz" -o -name "*.tar.gz.meta" \) -mtime +"$RETENTION_DAYS" -delete
fi
