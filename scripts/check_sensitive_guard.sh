#!/usr/bin/env bash
set -euo pipefail

MODE="${1:---staged}"

if [[ "${MODE}" != "--staged" && "${MODE}" != "--all" ]]; then
  echo "usage: $0 [--staged|--all]" >&2
  exit 2
fi

if [[ "${MODE}" == "--staged" ]]; then
  FILES="$(git diff --cached --name-only --diff-filter=ACMR)"
else
  FILES="$(git ls-files)"
fi

if [[ -z "${FILES}" ]]; then
  echo "[guard] 점검 대상 파일이 없습니다."
  exit 0
fi

BLOCKED_PATH_REGEX='^(infra/data/|backend/tmp/|docs/screenshots/.*\.png$)|(\.cookie$|\.session$|\.har$|\.pem$|\.p12$|\.pfx$|\.key$)'
SECRET_REGEX='(ghp_[A-Za-z0-9]{36}|gho_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9]{20,}|BEGIN [A-Z ]*PRIVATE KEY)'

VIOLATIONS_TMP="$(mktemp)"
trap 'rm -f "${VIOLATIONS_TMP}"' EXIT

file_content() {
  local path="$1"
  if [[ "${MODE}" == "--staged" ]]; then
    git show ":${path}" 2>/dev/null || true
  else
    cat "${path}" 2>/dev/null || true
  fi
}

while IFS= read -r path; do
  [[ -z "${path}" ]] && continue
  if [[ "${path}" =~ ${BLOCKED_PATH_REGEX} ]]; then
    echo "금지 경로/파일 유형: ${path}" >> "${VIOLATIONS_TMP}"
    continue
  fi

  content="$(file_content "${path}")"
  if [[ -z "${content}" ]]; then
    continue
  fi

  if grep -aEq "${SECRET_REGEX}" <<<"${content}"; then
    echo "비밀정보 패턴 감지: ${path}" >> "${VIOLATIONS_TMP}"
  fi

  if [[ "${path}" == infra/env/.env* ]]; then
    session_secret="$(grep -aE '^SESSION_SECRET=' <<<"${content}" | head -n1 | cut -d'=' -f2- || true)"
    if [[ -n "${session_secret}" && ! "${session_secret}" =~ change-me ]]; then
      echo "SESSION_SECRET는 placeholder 값만 허용: ${path}" >> "${VIOLATIONS_TMP}"
    fi

    action_secret="$(grep -aE '^OPENCLAW_ACTION_SECRET=' <<<"${content}" | head -n1 | cut -d'=' -f2- || true)"
    if [[ -n "${action_secret}" && ! "${action_secret}" =~ change-me ]]; then
      echo "OPENCLAW_ACTION_SECRET는 placeholder 값만 허용: ${path}" >> "${VIOLATIONS_TMP}"
    fi
  fi
done <<EOF
${FILES}
EOF

if [[ -s "${VIOLATIONS_TMP}" ]]; then
  echo "[guard] 커밋/푸시 차단: 민감정보 또는 운영데이터가 포함되었습니다." >&2
  while IFS= read -r item; do
    echo " - ${item}" >&2
  done < "${VIOLATIONS_TMP}"
  exit 1
fi

echo "[guard] 민감정보 점검 통과 (${MODE})"
