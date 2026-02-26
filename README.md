# OpenClaw + Telegram Document Archive

체크리스트 문서: `docs/IMPLEMENTATION_CHECKLIST.md`
이관 런북: `docs/MIGRATION_RUNBOOK.md`
릴리즈 체크리스트: `docs/RELEASE_CHECKLIST.md`

## 실행 전 요구사항
- Docker Engine 또는 Docker Desktop (daemon 실행 상태)
- Docker Compose (`docker compose` 또는 `docker-compose`)
- `curl`
- 선택: `make` (없어도 `./scripts/quickstart.sh` 사용 가능)

## 빠른 시작
아래 순서만 실행하면 됩니다.

```bash
# 1) 사전 점검 + 전체 스택 실행 + API 헬스체크 대기
make first-run

# 2) 초기 관리자 생성 (최초 1회)
make bootstrap-admin ADMIN_USER=admin ADMIN_PASS='ChangeMe123!'
```

또는 단일 스크립트:

```bash
./scripts/quickstart.sh
make bootstrap-admin ADMIN_USER=admin ADMIN_PASS='ChangeMe123!'
```

접속 URL:
- 프론트: `http://localhost:3000/archive`
- API: `http://localhost:8000/api/health`
- MinIO Console: `http://localhost:9001`
- Prometheus: `http://localhost:9090`

정지/로그:

```bash
make logs
make down
```

참고:
- `make`가 없으면 `cd infra && ./scripts/compose.sh up -d --build`로 동일 실행 가능합니다.
- `./scripts/compose.sh`는 `docker compose`와 `docker-compose`를 자동 감지합니다.

## 로컬 데이터 저장 위치
Docker Compose는 운영 데이터(파일/DB/캐시/검색인덱스)를 `infra/data` 아래에 저장합니다.

- PostgreSQL: `infra/data/postgres`
- MinIO object 파일: `infra/data/minio`
- Redis: `infra/data/redis`
- Meilisearch index: `infra/data/meili`
- ingest 임시파일: `infra/data/ingest_tmp`

## 읽기 전용 모드 (cut-over/점검용)
`READ_ONLY_MODE=true`이면 API 쓰기 요청(`POST/PUT/PATCH/DELETE`)을 차단합니다.
허용 예외: 로그인/로그아웃, 조회성 `GET/HEAD/OPTIONS`.

```bash
# infra/env/.env.common 또는 .env.dev
READ_ONLY_MODE=true

cd infra
./scripts/compose.sh up -d --build api
```

## 데이터 정합성 검사 (이관/운영 점검)
`validate_integrity.py`는 아래 항목을 자동 점검하고 텍스트/JSON 리포트를 생성합니다.

- 참조 무결성(문서-카테고리, document_files/document_tags/document_versions, ingest jobs/events)
- 문서 버전 일관성(`current_version_no` vs `document_versions` 최대 버전)
- `files.checksum_sha256` 형식
- telegram `source_ref` 중복
- 저장소 실물 파일 존재 여부(disk/minio, 옵션)

권장 실행(컨테이너 내부):

```bash
cd infra
./scripts/compose.sh exec -T api sh -lc '
  cd /app &&
  PYTHONPATH=/app python scripts/validate_integrity.py \
    --report /tmp/integrity_report.txt \
    --json-report /tmp/integrity_report.json \
    --check-storage auto \
    --storage-probe-limit 2000 \
    --max-samples 20
'
```

주요 옵션:
- `--check-storage {auto|none|disk|minio}`
- `--storage-probe-limit <N>`
- `--max-samples <N>`
- `--fail-on-error` (ERROR 발견 시 종료코드 2)

## 레거시 `index.json` 이관
`import_index_json.py`는 기존 JSON 인덱스를 신규 스키마(`documents/files/document_versions/...`)로 적재합니다.

주요 동작:
- `source+source_ref` 기준 기존 문서는 중복 생성하지 않고 skip
- 파일은 `sha256` 기준 dedupe 후 현재 저장 백엔드(minio/disk)에 재저장
- 캡션/규칙 엔진을 적용해 제목/설명/날짜/태그/분류를 생성
- 텍스트/JSON 리포트 생성 가능

권장 실행(먼저 dry-run):

```bash
cd infra
./scripts/compose.sh exec -T api sh -lc '
  cd /app &&
  PYTHONPATH=/app python scripts/import_index_json.py \
    --index-json /app/tmp/legacy_import_sample/index.json \
    --legacy-root /app/tmp/legacy_import_sample \
    --dry-run \
    --report /tmp/import_report.txt \
    --json-report /tmp/import_report.json
'
```

실제 반영 실행:

```bash
cd infra
./scripts/compose.sh exec -T api sh -lc '
  cd /app &&
  PYTHONPATH=/app python scripts/import_index_json.py \
    --index-json /app/tmp/legacy_import_sample/index.json \
    --legacy-root /app/tmp/legacy_import_sample \
    --missing-file skip \
    --report /tmp/import_report.txt \
    --json-report /tmp/import_report.json
'
```

옵션:
- `--source-mode {auto|telegram|wiki|manual|api}`: 레거시 source 해석 방식
- `--source-ref-prefix <prefix>`: source_ref가 비어있는 행의 기본 prefix
- `--missing-file {skip|fail|document-only}`: 원본 파일 누락 처리 정책
- `--created-by-username <username>`: 생성자 사용자 지정
- `--stop-on-error`: 첫 오류에서 즉시 중단

## 검토 큐 자동 정리 (중복 의심 사유)
`DUPLICATE_SUSPECT`처럼 반복되는 검토 사유는 운영 스크립트로 일괄 해소할 수 있습니다.

```bash
cd infra

# 미리보기(반영 없음)
./scripts/compose.sh exec -T api sh -lc '
  cd /app &&
  PYTHONPATH=/app python scripts/review_queue_auto_resolve.py \
    --reason DUPLICATE_SUSPECT \
    --dry-run
'

# 실제 반영
./scripts/compose.sh exec -T api sh -lc '
  cd /app &&
  PYTHONPATH=/app python scripts/review_queue_auto_resolve.py \
    --reason DUPLICATE_SUSPECT
'

# 혼합 사유 문서에서도 해당 사유만 제거(예: CLASSIFY_FAIL+DATE_MISSING+DUPLICATE_SUSPECT)
./scripts/compose.sh exec -T api sh -lc '
  cd /app &&
  PYTHONPATH=/app python scripts/review_queue_auto_resolve.py \
    --reason DUPLICATE_SUSPECT \
    --include-mixed-reasons
'
```

## UAT 스모크 점검
로그인/목록/상세/다운로드/검토큐/대시보드를 한 번에 점검합니다.

```bash
cd infra
./scripts/compose.sh exec -T api sh -lc '
  cd /app &&
  PYTHONPATH=/app python scripts/smoke_uat.py \
    --api http://localhost:8000/api \
    --username uat_admin \
    --password "UatPass123!" \
    --include-download
'
```

## Meilisearch 옵션 검색 활성화
기본값은 `SEARCH_BACKEND=postgres`입니다. Meilisearch를 쓰려면 아래처럼 변경 후 재기동하세요.

```bash
# infra/env/.env.common 또는 .env.dev
SEARCH_BACKEND=meili
SEARCH_AUTO_SYNC=true
MEILI_URL=http://meilisearch:7700
MEILI_API_KEY=
MEILI_INDEX_DOCUMENTS=documents
```

```bash
cd infra
./scripts/compose.sh up -d --build
```

최초 활성화 시 기존 문서를 한번 재인덱싱하는 것을 권장합니다.

```bash
cd backend
python scripts/reindex_search.py --batch-size 500
```

## 인증 시작 (필수)
보호된 API(`/api/documents`, `/api/review-queue`, `/api/rules*`, `/api/ingest*`)는 로그인 세션이 필요합니다.

```bash
# 1) 초기 관리자 계정 생성 (최초 1회)
cd backend
python scripts/bootstrap_admin.py --username admin --password 'ChangeMe123!'

# 2) 로그인 + 세션 쿠키 저장
curl -i -c /tmp/archive.cookie \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"ChangeMe123!"}' \
  http://localhost:8000/api/auth/login

# 3) 보호 API 호출 (쿠키 사용)
curl -b /tmp/archive.cookie "http://localhost:8000/api/review-queue?page=1&size=20"

# 3-1) 문서 목록 조회(서버사이드 정렬/필터)
curl -b /tmp/archive.cookie \
  "http://localhost:8000/api/documents?page=1&size=20&q=테스트&category_name=회의&sort_by=event_date&sort_order=desc"

# 4) 대시보드 집계 조회
curl -b /tmp/archive.cookie "http://localhost:8000/api/dashboard/summary?recent_limit=8"

# 5) 아카이브 트리 조회 (카테고리/연/월)
curl -b /tmp/archive.cookie "http://localhost:8000/api/archive/tree"

# 5-1) 아카이브 세트/개정 집계 조회
curl -b /tmp/archive.cookie \
  "http://localhost:8000/api/archive/sets?page=1&size=10&include_unmapped=true"

# 6) 관리자 사용자 목록 조회
curl -b /tmp/archive.cookie "http://localhost:8000/api/admin/users"

# (옵션) 사용자 목록 검색/필터/페이지네이션
curl -b /tmp/archive.cookie \
  "http://localhost:8000/api/admin/users?page=1&size=20&q=viewer&role=REVIEWER&is_active=true"

# 7) 사용자 역할 변경/활성화 토글
curl -X PATCH http://localhost:8000/api/admin/users/<USER_ID> \
  -b /tmp/archive.cookie \
  -H 'Content-Type: application/json' \
  -d '{"role":"REVIEWER","is_active":true}'

# 8) 사용자 비밀번호 재설정
curl -X PATCH http://localhost:8000/api/admin/users/<USER_ID> \
  -b /tmp/archive.cookie \
  -H 'Content-Type: application/json' \
  -d '{"password":"TempPass123!"}'

# 9) 저장 필터 생성/조회/삭제
curl -X POST http://localhost:8000/api/saved-filters \
  -b /tmp/archive.cookie \
  -H 'Content-Type: application/json' \
  -d '{"name":"검토큐","filter_json":{"review_status":"NEEDS_REVIEW"},"is_shared":false}'

curl -b /tmp/archive.cookie "http://localhost:8000/api/saved-filters?page=1&size=20&include_shared=true"

curl -X DELETE http://localhost:8000/api/saved-filters/<FILTER_ID> \
  -b /tmp/archive.cookie

# 10) 감사 로그 조회 (ADMIN)
curl -b /tmp/archive.cookie \
  "http://localhost:8000/api/admin/audit-logs?page=1&size=20&action=AUTH&include_payload=false"

# 10-1) 감사 로그 고급 검색 + export
curl -b /tmp/archive.cookie \
  "http://localhost:8000/api/admin/audit-logs?page=1&size=20&q=DOCUMENT&target_type=document&source_ref=msg:"

curl -L -b /tmp/archive.cookie \
  "http://localhost:8000/api/admin/audit-logs/export?fmt=csv&include_payload=false&limit=5000" \
  -o ./audit_logs.csv

# 11) 운영 로그(ingest jobs/events) 조회 (ADMIN)
curl -b /tmp/archive.cookie \
  "http://localhost:8000/api/admin/ingest-jobs?page=1&size=20&state=FAILED"

curl -b /tmp/archive.cookie \
  "http://localhost:8000/api/admin/ingest-jobs/<JOB_ID>/events?limit=100"

# 12) ingest job 재처리 큐잉 (ADMIN)
curl -X POST http://localhost:8000/api/admin/ingest-jobs/<JOB_ID>/requeue \
  -b /tmp/archive.cookie \
  -H 'Content-Type: application/json' \
  -d '{"force":false,"reset_attempts":false,"clear_error":true}'

# 13) 실패 job 파일 업로드 복구 + 재처리 (ADMIN)
curl -X POST http://localhost:8000/api/admin/ingest-jobs/<JOB_ID>/recover-upload \
  -b /tmp/archive.cookie \
  -F "file=@./sample.pdf" \
  -F "caption=복구 업로드 캡션\n#분류:회의\n#날짜:2026-02-24" \
  -F "reset_attempts=true" \
  -F "clear_error=true"

# 14) 운영 리포트 생성/조회 (ADMIN)
curl -X POST -b /tmp/archive.cookie \
  "http://localhost:8000/api/admin/ops-reports/generate?days=7"

curl -b /tmp/archive.cookie \
  "http://localhost:8000/api/admin/ops-reports?page=1&size=20"
```

## OpenClaw 연동 브리지(텔레그램 파일 즉시 업로드)
```bash
cd backend

# 환경변수(최초 1회)
export ARCHIVE_API=http://localhost:8000/api
export ARCHIVE_USERNAME=admin
export ARCHIVE_PASSWORD='ChangeMe123!'

# OpenClaw가 받은 파일 경로 + 캡션 + message/chat id로 업로드
python scripts/openclaw_ingest_bridge.py \
  --file /absolute/path/from/openclaw.xlsx \
  --caption "샘플 점검 문서 요약본" \
  --message-id 663 \
  --chat-id telegram:1000000000
```

`source_ref`는 기본적으로 `msg:<message-id>`가 자동 생성됩니다.

## CLI 수집 예시
```bash
cd backend

# 단일 업로드
python scripts/ingest_cli.py \
  --api http://localhost:8000/api \
  --file ./sample.pdf \
  --caption "주간 운영회의\n진행상황\n#분류:회의\n#날짜:2026-02-24\n#태그:alpha,beta" \
  --source telegram \
  --msg-id 12345 \
  --chat-id -100000000

# 다중 업로드(배치): --file 반복
python scripts/ingest_cli.py \
  --api http://localhost:8000/api \
  --file ./docs/a.pdf \
  --file ./docs/b.pdf \
  --file ./docs/c.pdf \
  --caption "DCP 배치 등록\n#분류:DCP\n#날짜:2026-02-24" \
  --source telegram \
  --msg-id 12346 \
  --chat-id -100000000 \
  --source-ref-prefix msg:12346
```

## 배치 업로드 API
```bash
# Telegram batch
curl -X POST http://localhost:8000/api/ingest/telegram/batch \
  -b /tmp/archive.cookie \
  -F "source=telegram" \
  -F "source_ref_prefix=msg:90001" \
  -F "message_id=90001" \
  -F "chat_id=-100000000" \
  -F "caption=배치 업로드\n#분류:회의" \
  -F "files=@./a.pdf" \
  -F "files=@./b.pdf"

# Manual/API batch
curl -X POST http://localhost:8000/api/ingest/manual/batch \
  -b /tmp/archive.cookie \
  -F "source=manual" \
  -F "source_ref_prefix=manual:2026-02-24" \
  -F "caption=일괄 등록" \
  -F "title=일괄 등록 문서" \
  -F "description=같은 설명을 여러 파일에 적용" \
  -F "files=@./1.pdf" \
  -F "files=@./2.pdf"
```

## 수동 게시글 생성 (파일 없이 등록)
```bash
curl -X POST http://localhost:8000/api/documents/manual-post \
  -b /tmp/archive.cookie \
  -H "Content-Type: application/json" \
  -d '{
    "source": "manual",
    "source_ref": "manual:2026-02-24:notice-001",
    "title": "문서 포털 운영 공지",
    "description": "이번 주 점검 일정 공지",
    "category_name": "공지",
    "event_date": "2026-02-24",
    "tags": ["set:ops-notice", "dockey:portal-maintenance-notice", "rev:1", "kind:notice", "lang:ko"],
    "review_status": "NONE"
  }'
```

- `Manual Post` 화면은 기본적으로 템플릿 고정 모드로 동작하며 캡션을 아래 구조로 생성합니다.
```text
1행: 제목
2행: 설명
#분류:<카테고리>
#날짜:<YYYY-MM-DD>
#태그:set:<...>,dockey:<...>,rev:<...>,kind:<...>,lang:<...>
```

## 업로드 파일 교체/삭제 API
```bash
# 0) 게시물(문서) 메타 편집
curl -X PATCH http://localhost:8000/api/documents/<DOC_ID> \
  -b /tmp/archive.cookie \
  -H "Content-Type: application/json" \
  -d '{
    "title":"수정된 제목",
    "description":"수정된 설명",
    "category_name":"공지",
    "event_date":"2026-02-24",
    "tags":["공지","운영"],
    "review_status":"NONE"
  }'

# 0-1) 게시물(문서) 삭제
curl -X DELETE http://localhost:8000/api/documents/<DOC_ID> \
  -b /tmp/archive.cookie

# 1) 문서 파일 교체
curl -X POST http://localhost:8000/api/documents/<DOC_ID>/files/<FILE_ID>/replace \
  -b /tmp/archive.cookie \
  -F "file=@./replacement.pdf" \
  -F "change_reason=manual_file_replace"

# 2) 문서 파일 삭제
curl -X DELETE http://localhost:8000/api/documents/<DOC_ID>/files/<FILE_ID> \
  -b /tmp/archive.cookie

# 3) 파일 다운로드(링크 열기)
curl -L http://localhost:8000/api/files/<FILE_ID>/download \
  -b /tmp/archive.cookie \
  -o ./downloaded.bin

# 4) 버전 diff 조회
curl -b /tmp/archive.cookie \
  "http://localhost:8000/api/documents/<DOC_ID>/versions/diff?from_version_no=1&to_version_no=3"
```

Archive 화면 목록/상세에서 파일명을 클릭하면 다운로드(또는 브라우저 미리보기)할 수 있고, 우측 Detail 패널에서 게시물 편집/삭제, 파일 교체/삭제도 수행할 수 있습니다.

## 상태 머신
`RECEIVED -> STORED -> EXTRACTED -> CLASSIFIED -> INDEXED -> PUBLISHED`

검토 필요 시 `NEEDS_REVIEW`, 오류 시 `FAILED`.

재시도 중인 job은 `FAILED -> RECEIVED(RETRY_SCHEDULED)`로 전이되며 `retry_after`가 설정됩니다.  
`attempt_count >= max_attempts` 도달 시 `DEAD_LETTER` 이벤트를 기록하고 `last_error_code=DLQ_MAX_ATTEMPTS`로 종료합니다.

Meilisearch 활성화 시 문서 생성/수정/삭제, Review Queue 변경, Rules Backfill 변경 결과가 `search` 큐 워커를 통해 인덱스에 비동기 반영됩니다.

## 구조 태그 자동 보강
- 룰엔진은 문서 제목/설명/파일명에서 `set:*`, `dockey:*`, `rev:*`, `kind:*`, `lang:*` 태그를 자동 추론합니다.
- 이미 캡션 `#태그`에 구조 태그가 있으면 운영자 입력값을 우선 유지합니다.
- 수동 업로드에서 `\\n` 형태 캡션이 들어오면 제목/설명 파싱 시 개행으로 정규화합니다.

## Rules 고급 기능
- `POST /api/rules/simulate/batch`: 선택 rule version으로 기존 문서 배치 시뮬레이션(변경 건수/샘플 비교)
- `GET /api/rules/conflicts/{rule_version_id}`: 키워드 충돌 규칙 탐지
- Rules 화면에서 충돌 탐지/배치 시뮬레이션 UI를 제공합니다.

## 주간 운영 리포트 자동 생성
- Celery beat가 매주 월요일 00:15(UTC)에 `OPS_REPORT_WEEKLY` 리포트를 자동 생성합니다.
- worker는 `reports` 큐를 같이 실행합니다: `-Q ingest,backfill,search,reports`
- 수동 생성 스크립트:
```bash
cd backend
python scripts/generate_ops_report.py --days 7
```

## 재시도 백오프 설정
- `INGEST_RETRY_BASE_SECONDS` (기본 `30`)
- `INGEST_RETRY_MAX_SECONDS` (기본 `1800`)
- `.env.common`에서 조정할 수 있습니다.

## 장애코드 표준화
- ingest 실패는 단계별 코드로 기록됩니다: `STORAGE_TEMP_FILE_MISSING`, `STORAGE_WRITE_FAIL`, `CAPTION_PARSE_FAIL`, `RULE_CLASSIFY_FAIL`, `DB_WRITE_FAIL`, `NOTIFY_CALLBACK_FAIL`, `PIPELINE_UNEXPECTED`.
- Dashboard는 실패 작업의 `error_code` 분포와 `DLQ` 건수를 함께 표시합니다.

## OpenClaw 콜백 액션 규약 (재시도/재처리 버튼)
- 콜백 payload(`POST OPENCLAW_CALLBACK_URL`)에 `actions[]`를 포함합니다.
- 각 action은 `url/method/token/expires_at`를 가지며, OpenClaw는 Telegram 버튼 클릭 시 해당 URL로 호출합니다.
- 액션 토큰은 HMAC(`OPENCLAW_ACTION_SECRET`) 기반이며 TTL(`OPENCLAW_ACTION_TTL_SECONDS`)이 지나면 만료됩니다.

```json
{
  "job_id": "3f55d87f-63c8-4bc0-b472-8ee7a4f1f1ca",
  "state": "FAILED",
  "success": false,
  "error_code": "STORAGE_TEMP_FILE_MISSING",
  "actions": [
    {
      "kind": "button",
      "action": "retry",
      "label": "재시도",
      "method": "POST",
      "url": "http://localhost:8000/api/ingest/actions/<JOB_ID>/retry",
      "token": "<signed-token>",
      "expires_at": "2026-02-25T12:00:00+00:00",
      "payload": {"clear_error": true}
    },
    {
      "kind": "button",
      "action": "reprocess",
      "label": "재처리",
      "method": "POST",
      "url": "http://localhost:8000/api/ingest/actions/<JOB_ID>/reprocess",
      "token": "<signed-token>",
      "expires_at": "2026-02-25T12:00:00+00:00",
      "payload": {"reset_attempts": true, "clear_error": true}
    },
    {
      "kind": "command",
      "action": "recover_upload",
      "label": "파일 재업로드",
      "command": "/recover_upload <JOB_ID>",
      "payload": {"reason": "STORAGE_TEMP_FILE_MISSING"}
    }
  ]
}
```

```bash
# Telegram 버튼(재시도) 처리 시 OpenClaw가 호출할 API 예시
curl -X POST http://localhost:8000/api/ingest/actions/<JOB_ID>/retry \
  -H "X-OpenClaw-Action-Token: <signed-token>" \
  -H "Content-Type: application/json" \
  -d '{"clear_error":true}'
```

## 운영자 규칙 관리 + 백필 예시
```bash
# 1) ruleset 생성
curl -X POST http://localhost:8000/api/rulesets \
  -H 'Content-Type: application/json' \
  -d '{"name":"default-rules","description":"운영 기본 규칙셋"}'

# 2) rule version 추가
curl -X POST http://localhost:8000/api/rulesets/<RULESET_ID>/versions \
  -H 'Content-Type: application/json' \
  -d '{"rules_json":{"default_category":"기타","category_rules":[{"category":"회의","keywords":{"title":["회의"]},"tags":["회의"]}]}}'

# 3) 버전 활성화
curl -X POST http://localhost:8000/api/rule-versions/<RULE_VERSION_ID>/activate

# 4) 기존 데이터 백필
curl -X POST http://localhost:8000/api/rules/backfill \
  -H 'Content-Type: application/json' \
  -d '{"rule_version_id":"<RULE_VERSION_ID>","batch_size":500}'
```

## 구조 태그 백필(기존 문서 정리)
```bash
# 1) dry-run: 어떤 문서에 어떤 태그가 추가될지 미리 확인
python scripts/backfill_structured_tags.py --dry-run --limit 200

# 2) set 태그가 없는 문서만 실제 보강
python scripts/backfill_structured_tags.py --only-without-set --batch-size 500

# 3) telegram 소스 문서만 보강
python scripts/backfill_structured_tags.py --source telegram
```

## 리뷰 큐 일괄 처리 예시
```bash
# 검토 큐 조회
curl "http://localhost:8000/api/review-queue?page=1&size=50"

# 선택 문서 일괄 승인
curl -X POST http://localhost:8000/api/review-queue/bulk \
  -H 'Content-Type: application/json' \
  -d '{"document_ids":["<DOC_ID_1>","<DOC_ID_2>"],"update":{"approve":true,"note":"운영자 승인"}}'

# 단일 문서 수정(분류 + 날짜 보정)
curl -X PATCH http://localhost:8000/api/review-queue/<DOC_ID> \
  -H 'Content-Type: application/json' \
  -d '{"category_name":"회의","event_date":"2026-02-24","reason_remove":["CLASSIFY_FAIL","DATE_MISSING"]}'
```
