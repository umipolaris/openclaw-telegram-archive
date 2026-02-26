#!/usr/bin/env sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
APP_PROFILE="${APP_PROFILE:-dev}"

cd "$ROOT_DIR"
./infra/scripts/doctor.sh

cd infra
APP_PROFILE="$APP_PROFILE" ./scripts/compose.sh up -d --build

echo "API 헬스체크 대기 중..."
i=0
until curl -fsS http://localhost:8000/api/health >/dev/null 2>&1; do
  i=$((i + 1))
  if [ "$i" -ge 60 ]; then
    echo "ERROR: API 헬스체크 타임아웃(120초)" >&2
    exit 1
  fi
  sleep 2
done

echo "완료:"
echo " - 프론트: http://localhost:3000/archive"
echo " - API: http://localhost:8000/api/health"
echo " - 다음 단계(관리자 생성):"
echo "   make bootstrap-admin ADMIN_USER=admin ADMIN_PASS='ChangeMe123!'"
