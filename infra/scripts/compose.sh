#!/usr/bin/env sh
set -eu

if docker compose version >/dev/null 2>&1; then
  exec docker compose "$@"
fi

if command -v docker-compose >/dev/null 2>&1; then
  exec docker-compose "$@"
fi

echo "ERROR: Docker Compose를 찾을 수 없습니다." >&2
echo " - Docker Desktop(Compose plugin 포함) 설치 또는" >&2
echo " - docker-compose 바이너리 설치 후 다시 시도하세요." >&2
exit 1
