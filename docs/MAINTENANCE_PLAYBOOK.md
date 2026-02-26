# 유지보수 플레이북 (단계형 점검/수정 루프)

기준일: 2026-02-25

## 1) 목적
- 기능 추가 시 바로 운영 반영하지 않고, 단계별 점검 후 다음 단계로 진행합니다.
- 중간 점검에서 문제가 발견되면 즉시 수정 후 동일 단계 검증을 재실행합니다.

## 2) 단계별 실행 순서
1. 구현 단계
- 기능을 작은 단위로 나눠 반영합니다.
- 예: `아카이브 컬럼 설정` + `밀도 토글` + `키보드 이동`.

2. 중간 점검 단계
- 아래 체크포인트 스크립트를 실행합니다.
- `infra/scripts/checkpoint-verify.sh`

3. 수정 단계
- 실패 항목만 우선 수정합니다.
- 수정 후 같은 체크포인트를 다시 실행합니다.

4. 확정 단계
- 체크포인트가 모두 통과하면 다음 기능 단계로 이동합니다.

## 3) 체크포인트 기준
- Backend: `pytest -q` 통과
- Frontend: `npm run lint` + `npm run build` 통과
- Infra: `cd infra && ./scripts/compose.sh config` 파싱 통과

## 4) 장애 대응 규칙
1. 빌드 실패
- 타입 오류/라우팅 오류를 우선 수정
- 동일 명령 재실행으로 회귀 확인

2. 테스트 실패
- 신규 변경 영향 범위를 먼저 확인
- 실패 테스트를 고친 뒤 전체 테스트 재실행

3. 인프라 검증 실패
- 환경변수/Compose 문법/서비스명 참조 우선 점검

## 5) 아카이브 UI 유지보수 규칙
1. 사용자 선호 설정
- `frontend/lib/archive-list-preferences.ts`에서만 관리
- 로컬 저장 키: `archive-list-preferences.v1`

2. 컬럼 추가 시 필수 업데이트
- `ARCHIVE_COLUMN_ORDER_DEFAULT`
- `ARCHIVE_COLUMN_LABELS`
- `ARCHIVE_COLUMN_WIDTHS`
- `ARCHIVE_COLUMN_MIN_WIDTH`

3. 회귀 방지
- 아카이브 화면 수정 후에는 반드시 체크포인트 스크립트를 실행합니다.

## 6) 카테고리 정합성 점검
1. 점검 명령
- `python scripts/check_out_of_rules_categories.py`

2. 자동 재분류
- `python scripts/check_out_of_rules_categories.py --fix --batch-size 200`

3. 기준
- 활성 ruleset에 없는 카테고리로 분류된 문서가 0건이어야 합니다.

## 7) API 계약 고정 규칙
1. OpenAPI/프론트 타입 생성
- `cd frontend && npm run gen:api-types`

2. 생성 산출물
- `frontend/openapi/openapi.json`
- `frontend/lib/api-types.generated.ts`

3. CI 정책
- 생성 후 diff가 있으면 PR 실패
- 수동 타입 선언 추가 전, 생성 타입(alias) 우선 사용

## 8) 배포 환경 규칙(dev/stage/prod)
1. 환경파일
- `infra/env/.env.dev`
- `infra/env/.env.stage`
- `infra/env/.env.prod`

2. Stage 검증
- prod 전에는 stage에서 ingest/search/review UAT 수행
- 상세 절차: `docs/RELEASE_CHECKLIST.md`
