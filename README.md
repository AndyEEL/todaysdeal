# today's deal analytics

네이버 쇼핑 `https://shopping.naver.com/promotion`의 `스페셜딜` 데이터를 매일 수집하고,  
상품/브랜드의 **진입 → 유지 → 이탈 → 재진입(관측 시)** 흐름을 JSON 기반으로 분석하는 프로젝트입니다.

## 핵심 구조

- 수집: `scripts/naver_special_deals.py`
- 파생 분석 생성: `scripts/build_derived_data.py`
- API:
  - `api/snapshot.py` → `/api/snapshot?date=YYYY-MM-DD`
  - `api/live-snapshot/index.py` → `/api/live-snapshot`
  - `api/insights/*` → 일별/브랜드/상품 요약
  - `api/products.py` → 상품 타임라인 상세
  - `api/brands.py` → 브랜드 상세
- 저장:
  - `data/latest.json`
  - `data/daily/YYYY-MM-DD.json`
  - `data/derived/...` (insights, summaries, indices)
  - `data/products/{product_id}.json` (상품 lifecycle 상세)

## 로컬 실행

수집:

```bash
.venv/bin/python scripts/naver_special_deals.py --output-dir data --skip-history
```

파생 분석 생성:

```bash
.venv/bin/python scripts/build_derived_data.py --data-dir data
```

## API 예시

- 스냅샷:
  - `/api/snapshot`
  - `/api/snapshot?date=2026-04-15`
- 일별 인사이트:
  - `/api/insights/daily`
  - `/api/insights/daily?date=2026-04-15`
- 상품/브랜드 요약:
  - `/api/insights/products`
  - `/api/insights/brands`
- 상품/브랜드 상세:
  - `/api/products?productId=12808256836`
  - `/api/brands?brand=채널102655931`
  - rewrite 지원: `/api/products/12808256836`, `/api/brands/{slug}`

## GitHub Actions 자동화

`.github/workflows/update-special-deals.yml`

매일 `11:15 KST` 실행:
1. `/api/live-snapshot` 호출
2. `data/latest.json`, `data/daily/YYYY-MM-DD.json` 갱신
3. `scripts/build_derived_data.py` 실행
4. `data` 변경사항 커밋 후 `main`에 push

필수 Repository Variable:
- `VERCEL_LIVE_SNAPSHOT_URL` (권장)
- 또는 `VERCEL_SNAPSHOT_URL` (자동 fallback 지원)
