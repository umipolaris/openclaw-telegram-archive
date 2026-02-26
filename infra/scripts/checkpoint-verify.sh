#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

echo "[1/5] Backend migration rule checkpoint"
(
  cd "${ROOT_DIR}/backend"
  python scripts/check_migration_rules.py
)

echo "[2/5] Backend test checkpoint"
(
  cd "${ROOT_DIR}/backend"
  pytest -q
)

echo "[3/5] Frontend lint checkpoint"
(
  cd "${ROOT_DIR}/frontend"
  npm run lint
)

echo "[4/5] Frontend build checkpoint"
(
  cd "${ROOT_DIR}/frontend"
  npm run build
)

echo "[5/5] Infra compose checkpoint"
if command -v docker >/dev/null 2>&1; then
  (
    cd "${ROOT_DIR}/infra"
    docker compose config >/dev/null
  )
  echo "docker compose config: OK"
else
  echo "docker command not found: compose check skipped"
fi

echo "All checkpoints passed."
