# today's deal

네이버 쇼핑 `https://shopping.naver.com/promotion`의 `스페셜딜` 상품을 매일 수집해서 JSON으로 저장하고, 정적 웹 페이지에서 바로 보여주는 프로젝트입니다.

## 구성

- `scripts/naver_special_deals.py`: 스페셜딜 크롤러
- `data/naver_special_deals/latest.json`: 최신 스냅샷
- `data/naver_special_deals/daily/YYYY-MM-DD.json`: 날짜별 최신 스냅샷
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

1. Python 3.12 준비
2. 크롤러 실행
3. `data/naver_special_deals` 변경사항 커밋
4. `main` 브랜치에 push

## Vercel

이 저장소를 Vercel에 Import 하면 정적 사이트로 바로 배포할 수 있습니다.

- 홈 화면: `/`
- 최신 데이터: `/data/naver_special_deals/latest.json`
