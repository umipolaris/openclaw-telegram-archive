# Restore Runbook

## 1) DB 복구
1. 백업 파일 확인 (`infra/data/backup/db/*.dump`)
2. 실행:
   - `make restore-db BACKUP_FILE=./infra/data/backup/db/archive_YYYYMMDD_HHMMSS.dump CONFIRM=YES`
3. 점검:
   - `/api/health`
   - 아카이브 목록/검색/상세

## 2) 첨부파일(Object) 복구
1. 백업 파일 확인 (`infra/data/backup/objects/*.tar.gz`)
2. 실행:
   - `make restore-objects BACKUP_FILE=./infra/data/backup/objects/objects_minio_YYYYMMDD_HHMMSS.tar.gz CONFIRM=YES`
3. 점검:
   - 샘플 문서 다운로드/뷰어 열기
   - MinIO 데이터 폴더 용량/파일 수 확인

## 3) 설정파일 복구
1. 백업 파일 확인 (`infra/data/backup/config/*.tar.gz`)
2. 미리보기 복구:
   - `make restore-config BACKUP_FILE=./infra/data/backup/config/config_YYYYMMDD_HHMMSS.tar.gz MODE=preview`
3. 실제 적용(주의):
   - `make restore-config BACKUP_FILE=... MODE=apply CONFIRM=YES`
4. compose 재기동 후 점검:
   - `make up`
   - `/api/health`

## 4) 최종 점검
1. `/api/health` 정상
2. 최근 ingest_jobs 100건 상태 확인
3. 검색/상세/첨부 다운로드 확인
