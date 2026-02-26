#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_BASE_URL="${APP_BASE_URL:-http://localhost:3000}"
API_BASE_URL="${API_BASE_URL:-http://localhost:8000/api}"
SCREENSHOT_USER="${SCREENSHOT_USER:-admin}"
SCREENSHOT_PASSWORD="${SCREENSHOT_PASSWORD:-ChangeMe123!}"
OUT_DIR="${OUT_DIR:-${ROOT_DIR}/docs/screenshots}"

mkdir -p "${OUT_DIR}"

COOKIE_JAR="$(mktemp)"
STORAGE_JSON="$(mktemp)"

cleanup() {
  rm -f "${COOKIE_JAR}" "${STORAGE_JSON}"
}
trap cleanup EXIT

echo "[1/4] API 로그인 세션 발급"
HTTP_CODE="$(
  curl -sS -o /dev/null -w "%{http_code}" \
    -c "${COOKIE_JAR}" \
    -H "Content-Type: application/json" \
    -d "{\"username\":\"${SCREENSHOT_USER}\",\"password\":\"${SCREENSHOT_PASSWORD}\"}" \
    "${API_BASE_URL}/auth/login"
)"

if [[ "${HTTP_CODE}" != "200" ]]; then
  echo "로그인 실패: ${HTTP_CODE}" >&2
  exit 1
fi

SESSION_COOKIE="$(awk '$6 == "archive_session" {print $7}' "${COOKIE_JAR}")"
if [[ -z "${SESSION_COOKIE}" ]]; then
  echo "archive_session 쿠키를 찾지 못했습니다." >&2
  exit 1
fi

cat > "${STORAGE_JSON}" <<EOF
{
  "cookies": [
    {
      "name": "archive_session",
      "value": "${SESSION_COOKIE}",
      "domain": "localhost",
      "path": "/",
      "expires": -1,
      "httpOnly": true,
      "secure": false,
      "sameSite": "Lax"
    }
  ],
  "origins": []
}
EOF

echo "[2/4] 공개 페이지 캡처"
npx -y playwright screenshot --full-page \
  "${APP_BASE_URL}/login" "${OUT_DIR}/login.png"

echo "[3/4] 인증 필요 페이지 캡처"
npx -y playwright screenshot --load-storage "${STORAGE_JSON}" --full-page \
  "${APP_BASE_URL}/archive" "${OUT_DIR}/archive.png"
npx -y playwright screenshot --load-storage "${STORAGE_JSON}" --full-page \
  "${APP_BASE_URL}/timeline" "${OUT_DIR}/timeline.png"
npx -y playwright screenshot --load-storage "${STORAGE_JSON}" --full-page \
  "${APP_BASE_URL}/search" "${OUT_DIR}/search.png"
npx -y playwright screenshot --load-storage "${STORAGE_JSON}" --full-page \
  "${APP_BASE_URL}/rules" "${OUT_DIR}/rules.png"
npx -y playwright screenshot --load-storage "${STORAGE_JSON}" --full-page \
  "${APP_BASE_URL}/mind-map" "${OUT_DIR}/mind-map.png"

echo "[4/4] 완료"
echo "생성 위치: ${OUT_DIR}"
