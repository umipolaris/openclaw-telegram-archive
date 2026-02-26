# Restore Runbook

## 1) DB 복구
1. 대상 환경에서 API/Worker 중지
2. `createdb archive_restore` 실행
3. `pg_restore -d archive_restore /backup/archive_YYYYMMDD_HHMMSS.dump`
4. 무결성 확인 후 서비스 재기동

## 2) Object 복구
1. MinIO 버킷 `archive` 백업본 동기화
2. 샘플 문서 20건 presigned URL 테스트

## 3) 점검
1. `/api/health` 정상
2. 최근 ingest_jobs 100건 상태 확인
3. 감사로그에 복구 이벤트 기록
