# today's deal

네이버 쇼핑 `https://shopping.naver.com/promotion`의 `스페셜딜` 상품을 매일 수집해서 JSON으로 저장하고, 정적 웹 페이지에서 바로 보여주는 프로젝트입니다.

## 구성

- `scripts/naver_special_deals.py`: 스페셜딜 크롤러
- `api/snapshot.py`: 파일 기반 스냅샷 API (`/api/snapshot?date=YYYY-MM-DD`)
- `api/live-snapshot/index.py`: 실시간 수집 API (자동 수집 워크플로 용도)
- `data/latest.json`: 최신 스냅샷
- `data/daily/YYYY-MM-DD.json`: 날짜별 스냅샷
- `.github/workflows/update-special-deals.yml`: GitHub Actions 자동 수집
- `index.html`, `app.js`, `styles.css`: Vercel에 배포할 정적 웹 페이지

## 로컬 실행

```bash
.venv/bin/python scripts/naver_special_deals.py
```

저장된 HTML로 테스트:

```bash
.venv/bin/python scripts/naver_special_deals.py --html-file /tmp/naver_promotion.html
```

## GitHub Actions

워크플로는 매일 `11:06 KST`에 실행되도록 설정되어 있습니다.

실행 흐름:

1. Vercel의 `/api/live-snapshot` 호출
2. 받은 JSON으로 `latest.json`, `daily/YYYY-MM-DD.json` 갱신
3. `data` 변경사항 커밋
4. `main` 브랜치에 push

필수 설정:

- `VERCEL_LIVE_SNAPSHOT_URL` (권장) 또는 `VERCEL_SNAPSHOT_URL`
- 예시 값: `https://your-project.vercel.app/api/live-snapshot`

## Vercel

이 저장소를 Vercel에 Import 하면 정적 사이트로 바로 배포할 수 있습니다.

- 홈 화면: `/`
- 파일 스냅샷 API: `/api/snapshot`
- 날짜 조회 API: `/api/snapshot?date=2026-04-15`
- 실시간 수집 API: `/api/live-snapshot`
- 최신 데이터: `/data/latest.json`
