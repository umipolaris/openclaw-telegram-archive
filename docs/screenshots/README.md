# 스크린샷 가이드

이 폴더는 README에 연결되는 제품 화면 캡처 이미지를 저장합니다.

## 생성 방법
```bash
./scripts/capture_screenshots.sh
```

## 기본 생성 파일
- `login.png`
- `archive.png`
- `timeline.png`
- `search.png`
- `rules.png`
- `mind-map.png`

## 참고
- 캡처는 `localhost`의 실행 중인 서비스(`3000`, `8000`)를 사용합니다.
- 임시 세션 스토리지는 `mktemp`로 생성되며 저장소에 남지 않습니다.
