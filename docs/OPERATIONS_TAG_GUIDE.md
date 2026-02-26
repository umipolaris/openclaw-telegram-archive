# 운영자 태그 표준 가이드 (2026-02-24)

## 목적
- Archive `세트/개정 보기`를 일관되게 만들기 위한 운영 태그 표준입니다.
- Telegram 캡션 `#태그:` 또는 수동 게시글 `tags`에 동일 규칙을 적용합니다.

## 필수 권장 태그
- `set:<세트키>`: 문서군(예: `set:dcp`)
- `dockey:<문서키>`: 같은 문서의 개정본을 묶는 키(예: `dockey:document-control-procedure`)
- `rev:<개정값>`: 개정/버전(예: `rev:0`, `rev:1`, `rev:2`)
- `kind:<종류>`: 문서 성격(예: `kind:main`, `kind:manual`, `kind:drawing`)
- `lang:<언어>`: 문서 언어(예: `lang:ko`, `lang:en`)

## 작성 규칙
- 태그는 소문자 권장
- 공백 대신 `-` 사용 권장
- 다중 값은 쉼표 구분
- `set/dockey/rev` 3종은 가능하면 항상 같이 입력

## 캡션 예시
```text
Sample Control Procedure rev.2
최종 개정본 반영
#분류:절차서
#날짜:2025-08-20
#태그:set:scp,dockey:sample-control-procedure,rev:2,kind:main,lang:en
```

## General Arrangement Drawing 예시
```text
X42-77-900-XYZ Rev.0
Draft 버전
#분류:도면
#날짜:2025-07-23
#태그:set:ga-drawing,dockey:x42-77-900-xyz,rev:0,kind:drawing,lang:en
```

## 운영 체크 포인트
- `Review Queue`에서 `set/dockey/rev` 누락 문서 우선 보정
- Rules에서 제목 패턴 기반으로 `rev:*` 자동 추론 규칙 유지
- 월 1회 백필 실행으로 과거 문서 태그 일관성 보정
