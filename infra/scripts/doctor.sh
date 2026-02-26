#!/usr/bin/env sh
set -eu

ok() {
  printf "[OK] %s\n" "$1"
}

warn() {
  printf "[WARN] %s\n" "$1"
}

fail() {
  printf "[ERROR] %s\n" "$1" >&2
  exit 1
}

command -v docker >/dev/null 2>&1 || fail "docker 명령을 찾을 수 없습니다."
ok "docker 발견: $(docker --version)"

if docker compose version >/dev/null 2>&1; then
  ok "docker compose plugin 사용 가능"
elif command -v docker-compose >/dev/null 2>&1; then
  ok "docker-compose 사용 가능"
else
  fail "docker compose 또는 docker-compose가 필요합니다."
fi

docker info >/dev/null 2>&1 || fail "Docker daemon에 연결할 수 없습니다. Docker Desktop 실행 상태를 확인하세요."
ok "Docker daemon 연결 성공"

if docker buildx version >/dev/null 2>&1; then
  ok "docker buildx 사용 가능"
else
  warn "docker buildx 미설치 (compose 빌드 시 경고가 표시될 수 있음)"
fi

if command -v lsof >/dev/null 2>&1; then
  for port in 3000 5432 6379 7700 8000 9000 9001 9090; do
    if lsof -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
      warn "포트 $port 이미 사용 중 (충돌 가능)"
    fi
  done
fi

ok "사전 점검 완료"
