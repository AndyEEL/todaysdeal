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
  - `data/derived/todaysdeal-analysis.xlsx` (`Summary`, `Raw` 2시트 Excel 결과물)
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

Excel 결과물 열기:

```bash
open data/derived/todaysdeal-analysis.xlsx
```

Airtable 동기화(dry-run):

```bash
.venv/bin/python scripts/sync_airtable.py --data-dir data --dry-run
```

Airtable 동기화(live):

```bash
cp .env.example .env
# .env에 AIRTABLE_API_KEY / AIRTABLE_BASE_ID 입력 후
.venv/bin/python scripts/sync_airtable.py --data-dir data
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

## 자동화

### 1) 호스트 자동화 (Primary)

`cron/naver_special_deals.cron`

매일 `11:15 KST`에 아래 흐름을 실행합니다.
1. 원본 작업 디렉터리와 분리된 **임시 git worktree** 생성
2. 네이버 스페셜딜 직접 수집 (기본 3회 재시도)
3. `scripts/check_snapshot.py`로 **당일 스냅샷 / 상품 수 / 탭값** 검증
4. `data/latest.json`, `data/daily/YYYY-MM-DD.json` 갱신
5. `scripts/build_derived_data.py` 실행
6. 변경된 `data/`만 commit
7. `main`에 push → Vercel 자동 재배포

실행 스크립트:
- `scripts/update_and_publish.sh`

보조 검증 스크립트:
- `scripts/check_snapshot.py`

로그 파일:
- `logs/naver_special_deals.log`

crontab 설치:

```bash
crontab cron/naver_special_deals.cron
```

> 핵심 포인트: 자동화가 **현재 작업 중인 로컬 repo를 hard reset 하지 않고**, 별도 worktree에서 안전하게 실행됩니다.

### 2) GitHub Actions 자동화 (Backup / Rescue)

`.github/workflows/update-special-deals.yml`

매일 `11:35 KST` 실행:
1. 배포된 `/api/snapshot`의 `snapshot_date`가 오늘인지 먼저 확인
2. 이미 최신이면 종료
3. 최신이 아니면 GitHub Actions 환경에서 **rescue crawl** 2회 시도
4. `scripts/check_snapshot.py`로 결과 검증
5. `scripts/build_derived_data.py` 실행
6. `data` 변경사항 커밋 후 `main`에 push

선택 Repository Variable:
- `VERCEL_SNAPSHOT_URL` (미설정 시 `https://todaysdeal.vercel.app/api/snapshot` 사용)

> `/api/live-snapshot`는 현재 Vercel 환경에서 `__NEXT_DATA__` 수집 실패가 발생할 수 있어, 운영 primary 경로에서 제외했습니다.

## Airtable 운영 레이어 (v1)

Airtable은 **원본 저장소가 아니라 운영용 뷰 레이어**로 사용합니다.
원본 데이터는 계속 `data/*.json`과 Git history에 남기고, Airtable에는 사람이 보기 좋은 구조만 sync합니다.

### 현재 범위
- `Daily Deals`
- `Products`
- `Runs`

> `Stores` 테이블은 일부 스토어명 정규화 규칙이 더 정리된 뒤 v1.1에서 추가하는 것을 권장합니다.

### 준비

1. Airtable base를 하나 만든다.
2. repo 루트에서 `.env.example`을 복사해 `.env`를 만든다.
3. `.env`에 아래 값을 채운다.
   - `TODAYSDEAL_ENABLE_AIRTABLE_SYNC=1`
   - `AIRTABLE_API_KEY`
   - `AIRTABLE_BASE_ID`
   - 호스트 자동화는 worktree에서 실행되므로, `scripts/update_and_publish.sh`는 **원본 repo의 `.env`** 를 읽도록 연결되어 있다.
4. 아래 명령으로 필요한 테이블/필드 구조를 확인한다.

```bash
python scripts/sync_airtable.py --print-schema
```

5. 반복 수동 작업을 줄이려면 bootstrap 스크립트로 필요한 테이블을 자동 생성한다.

```bash
python scripts/bootstrap_airtable.py --env-file .env
```

6. dry-run으로 레코드 수를 확인한다.

```bash
python scripts/sync_airtable.py --dry-run --env-file .env
```

7. live sync를 실행한다.

```bash
python scripts/sync_airtable.py --env-file .env
```

### 자동화 연결

`scripts/update_and_publish.sh` 는 파생 데이터 생성 후 `scripts/sync_airtable.py`를 호출합니다.
- `TODAYSDEAL_ENABLE_AIRTABLE_SYNC=0` 또는 미설정: sync skip
- `TODAYSDEAL_ENABLE_AIRTABLE_SYNC=1`: Airtable sync 수행
- sync가 실패하면 자동화도 실패로 처리

### View 세팅

- 추천 View 구성은 `AIRTABLE-VIEWS.md` 참고
- 현재 Airtable Web API 운영 흐름에서는 **테이블/필드/레코드 sync는 자동화**, 저장된 View 구성은 **수동 1회 세팅**으로 두는 편이 안정적입니다.
