# TODAYSDEAL V1 Implementation Notes

## 1) Category Mapping Approach (v1)
프론트엔드에서 상품별 `v1 카테고리`를 아래 6개 라벨로 강제 매핑합니다.

- 식품·신선식품
- 생활용품·뷰티
- 디지털·가전
- 리빙·주방·레저
- 홈·문구·취미
- 패션·잡화

매핑 우선순위:
1. `product_name` 키워드 기반 규칙 매칭
2. 기존 `category`(legacy 값) 별칭 매칭
3. 위 조건 미충족 시 `홈·문구·취미` fallback

이 방식으로 현재 API 응답 필드 변경 없이 실제 화면에서 v1 카테고리를 적용했습니다.

## 2) Store / Brand Distinction Approach
### 운영 스토어(store)
우선순위:
1. `/data/daily/{date}.json` 로드 후 `product_id -> channel_no` 매핑 (`채널{번호}`)
2. 상품 `brand`가 이미 `채널123...` 형식이면 이를 스토어로 사용
3. `product_url` 경로에서 스토어 slug 추론
4. 그래도 없으면 `{brand} 운영` 또는 `스토어 미확인`

### 브랜드(brand)
우선순위:
1. `brand` 필드가 채널 형식이 아니면 그대로 사용
2. 상품명 `[브랜드]` prefix 추출
3. 상품명 첫 토큰 fallback
4. `브랜드 미확인`

브랜드 플로우 테이블은 상품 워크벤치와 **동일한 필터 결과 집합**을 사용해 계산되도록 맞췄습니다.

## 3) Remaining Caveats
- 카테고리 분류는 키워드 기반이라 일부 경계 상품 오분류 가능성이 있습니다.
- 현재 원천 데이터는 판매자 표시명이 아니라 `channel_no` 중심이라, 스토어 필터 표시가 `채널{번호}` 형태로 남을 수 있습니다.
- `removed_products`는 일별 인사이트에서 채널 정보가 제한적이어서 이탈 목록에는 카테고리 중심으로만 표시합니다.
- 현재 데이터셋은 `deal_type`이 대부분(사실상 전부) `스페셜딜`이라 딜유형 필터 분산 효과가 작습니다.

## 4) Data Collection Stability Recommendation
검토한 파일:
- `.github/workflows/update-special-deals.yml`
- `scripts/update_and_publish.sh`
- `cron/naver_special_deals.cron`

2026-04-17 점검 결과:
- 로컬/호스트 환경의 직접 수집은 정상 동작 확인
- `https://todaysdeal.vercel.app/api/live-snapshot` 는 현재 `Could not fetch HTML containing __NEXT_DATA__...`로 500 응답 확인
- 따라서 **Vercel live-snapshot 경로는 운영 primary로 쓰지 않는 쪽이 맞음**

적용 방향:
1. **1순위: 호스트 자동화(primary)**
   - 임시 `git worktree`에서 안전하게 실행
   - 직접 수집 3회 재시도 + `check_snapshot.py` 검증 후에만 publish
   - 개인 작업 repo를 hard reset 하지 않음
2. **2순위: GitHub Actions backup/rescue**
   - 먼저 배포된 `/api/snapshot`의 `snapshot_date`를 확인
   - 이미 오늘 데이터면 종료
   - stale 상태일 때만 rescue crawl 시도
3. **제외: live-snapshot 의존 설계**
   - 현재 서버리스 환경에서 안정성이 낮아 primary path로 부적합

요약: 현재 기준 가장 현실적인 안정화 구조는 **호스트 직접 수집 primary + GitHub Actions rescue backup** 조합입니다.
