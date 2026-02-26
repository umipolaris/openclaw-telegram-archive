# Release Checklist (dev/stage/prod)

## 1) Dev
1. `backend pytest -q` 통과
2. `frontend npm run lint && npm run build` 통과
3. `cd infra && ./scripts/compose.sh config` 파싱 통과
4. OpenAPI/타입 생성 후 변경분 없음 확인

## 2) Stage
1. `APP_PROFILE=stage`로 구동
2. 샘플 ingest 30건 수행
3. Archive/Search/Review Queue/Rules 주요 흐름 UAT
4. `/metrics` 지표 확인
5. 알림 규칙(`ApiDown`, `HighIngestFailureRate`, `SearchLatencyP95High`) 확인

## 3) Prod
1. 배포 전 백업 수행
2. `READ_ONLY_MODE=true` 전환 후 마이그레이션
3. 서비스 재기동 및 `/api/health` 확인
4. `READ_ONLY_MODE=false` 복귀
5. 운영 점검: 최근 ingest 20건, 검색 응답, 문서 다운로드

## 4) Rollback
1. `api/worker/beat` 중지
2. DB 백업 복원
3. Object storage snapshot 복원
4. `cd infra && ./scripts/compose.sh up -d --build` 재기동
5. `/api/health`, 샘플 조회/다운로드 검증
