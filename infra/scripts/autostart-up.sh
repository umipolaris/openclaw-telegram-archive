#!/usr/bin/env bash
set -euo pipefail

INFRA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_SCRIPT="$INFRA_DIR/scripts/compose.sh"

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"
export APP_PROFILE="${APP_PROFILE:-dev}"
AUTO_START_BUILD="${AUTO_START_BUILD:-false}"
AUTO_START_WAIT_SECONDS="${AUTO_START_WAIT_SECONDS:-300}"
AUTO_START_POLL_SECONDS="${AUTO_START_POLL_SECONDS:-3}"
AUTO_START_MAX_RETRIES="${AUTO_START_MAX_RETRIES:-6}"
AUTO_START_RETRY_INTERVAL="${AUTO_START_RETRY_INTERVAL:-20}"
AUTO_START_ALLOW_BUILD_ON_MISS="${AUTO_START_ALLOW_BUILD_ON_MISS:-true}"

if [[ ! -x "$COMPOSE_SCRIPT" ]]; then
  echo "compose script not found: $COMPOSE_SCRIPT" >&2
  exit 1
fi

# Try launching Docker Desktop in case it is not running yet.
if ! docker info >/dev/null 2>&1; then
  if [[ -d "/Applications/Docker.app" ]]; then
    /usr/bin/open -gj -a Docker || true
  fi
fi

start_ts="$(date +%s)"
while ! docker info >/dev/null 2>&1; do
  now_ts="$(date +%s)"
  elapsed="$((now_ts - start_ts))"
  if (( elapsed >= AUTO_START_WAIT_SECONDS )); then
    echo "docker daemon is not ready within ${AUTO_START_WAIT_SECONDS}s" >&2
    exit 1
  fi
  sleep "$AUTO_START_POLL_SECONDS"
done

build_flag="$(printf '%s' "$AUTO_START_BUILD" | tr '[:upper:]' '[:lower:]')"
allow_build_on_miss="$(printf '%s' "$AUTO_START_ALLOW_BUILD_ON_MISS" | tr '[:upper:]' '[:lower:]')"

run_compose_up_once() {
  if [[ "$build_flag" == "true" ]]; then
    "$COMPOSE_SCRIPT" up -d --build
    return $?
  fi

  if "$COMPOSE_SCRIPT" up -d --no-build; then
    return 0
  fi

  if [[ "$allow_build_on_miss" == "true" ]]; then
    "$COMPOSE_SCRIPT" up -d
    return $?
  fi
  return 1
}

cd "$INFRA_DIR"

attempt=1
while (( attempt <= AUTO_START_MAX_RETRIES )); do
  echo "[autostart] compose up attempt ${attempt}/${AUTO_START_MAX_RETRIES}"
  if run_compose_up_once; then
    "$COMPOSE_SCRIPT" ps
    exit 0
  fi
  if (( attempt == AUTO_START_MAX_RETRIES )); then
    break
  fi
  sleep "$AUTO_START_RETRY_INTERVAL"
  attempt=$((attempt + 1))
done

echo "[autostart] failed after ${AUTO_START_MAX_RETRIES} attempts" >&2
exit 1
