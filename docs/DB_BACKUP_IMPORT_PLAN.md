# 백업/복구(import) 실행 계획

기준일: 2026-02-26

## 1) 목표
- 운영 DB(PostgreSQL) 백업을 정기적으로 생성하고 보관한다.
- 첨부파일(Object Storage: MinIO 또는 disk fallback) 백업을 정기적으로 생성한다.
- 설정파일(env/compose/monitoring) 백업을 정기적으로 생성한다.
- 장애/오류 시 특정 백업 파일을 사용해 빠르게 복구(import)한다.
- 복구 후 기능 정상 여부를 표준 체크리스트로 확인한다.

## 2) 현재 구현된 실행 명령
- 백업: `make backup-db`
- 첨부 백업: `make backup-objects`
- 설정 백업: `make backup-config`
- 전체 백업: `make backup-all`
- DB 복구(import): `make restore-db BACKUP_FILE=./infra/data/backup/db/archive_YYYYMMDD_HHMMSS.dump CONFIRM=YES`
- 첨부 복구(import): `make restore-objects BACKUP_FILE=./infra/data/backup/objects/objects_minio_YYYYMMDD_HHMMSS.tar.gz CONFIRM=YES`
- 설정 복구(import): `make restore-config BACKUP_FILE=./infra/data/backup/config/config_YYYYMMDD_HHMMSS.tar.gz MODE=preview`

추가 스크립트:
- `infra/scripts/db-backup.sh`
- `infra/scripts/db-restore.sh`
- `infra/scripts/backup-objects.sh`
- `infra/scripts/restore-objects.sh`
- `infra/scripts/backup-config.sh`
- `infra/scripts/restore-config.sh`

## 3) 백업 정책
- 포맷: PostgreSQL custom dump(`.dump`, `pg_dump -Fc`)
- 기본 경로: `infra/data/backup/db`
- 파일명: `archive_<db명>_<YYYYMMDD_HHMMSS>.dump`
- 메타 파일: `<dump파일>.meta` (sha256, profile, timestamp 포함)
- 보관기간: 기본 30일 (`BACKUP_RETENTION_DAYS`로 조정)

첨부파일 백업:
- 경로: `infra/data/backup/objects`
- 파일명: `objects_<label>_<YYYYMMDD_HHMMSS>.tar.gz` (`label=minio|disk`)
- 메타 파일: `<tar>.meta`

설정파일 백업:
- 경로: `infra/data/backup/config`
- 파일명: `config_<YYYYMMDD_HHMMSS>.tar.gz`
- 포함 대상: `infra/env`, `infra/docker-compose.yml`, `infra/monitoring`

권장 주기:
1. 매일 1회 정기 백업 (새벽 비업무 시간)
2. 대규모 규칙 변경/마이그레이션 직전 수동 백업 1회
3. 릴리즈 직전 백업 1회

## 4) 복구(import) 표준 절차
1. 백업 파일 확인
- 대상 파일 존재 여부, 생성 시각, sha256 확인

2. 서비스 쓰기 중지
- `db-restore.sh`가 `api/worker/beat`를 자동으로 중지함

3. DB 드롭/재생성 후 import
- `CONFIRM=YES` 필수
- `.dump`: `pg_restore`
- `.sql`: `psql`

4. 서비스 재기동
- `api/worker/beat` 자동 재기동

5. 복구 검증
- `curl http://localhost:8000/api/health`
- 아카이브 목록/검색/문서상세 열람
- 최근 `ingest_jobs` 상태 점검

## 5) 운영 점검 루프 (중간 점검 포함)
1. 백업 실행
- `make backup-all`

2. 백업 검증
- 파일 크기 0이 아닌지 확인
- 메타 파일 sha256 기록 확인

3. 월 1회 복구 리허설
- 스테이징 DB에 import 실행
- Health/API/검색/다운로드 점검

4. 문제 발생 시 수정
- 원인 수정 후 동일 리허설 재실행

## 6) 실패/롤백 대응
- 복구 실패 시:
1. `docker compose -f infra/docker-compose.yml logs postgres --tail=200` 확인
2. 대상 dump 파일 재검증
3. 직전 정상 dump로 재복구

- 복구 후 이상 시:
1. 즉시 이전 dump로 재복귀
2. 원인 분석 후 신규 백업 정책 보정

## 7) 바로 적용 체크리스트
1. `chmod +x infra/scripts/db-backup.sh infra/scripts/db-restore.sh`
2. `chmod +x infra/scripts/backup-objects.sh infra/scripts/restore-objects.sh`
3. `chmod +x infra/scripts/backup-config.sh infra/scripts/restore-config.sh`
4. `make backup-all` 1회 실행
5. 생성된 백업/메타 확인
6. 스테이징에서 `restore-db`, `restore-objects` 리허설
7. 운영 배포 체크리스트에 백업 항목 고정
