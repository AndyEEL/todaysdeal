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

실무 권고:
1. **1순위: OpenClaw cron(권장)**
   - 외부 상시 러너에서 정시 실행 + 재시도/모니터링 구성이 쉬움
   - 현재 파이프라인과 동일하게 `live-snapshot 우선 -> 실패 시 직접 수집 fallback` 전략 적용 권장
2. **2순위: GitHub Actions 스케줄 유지(백업 라인)**
   - 이미 `11:15 KST` 스케줄 + fallback 로직이 구현되어 있어 백업 경로로 적합
3. **3순위: 로컬 push cron은 보조 운용**
   - 로컬 머신 가동 상태/네트워크/로그인 세션 의존성이 큼
   - `scripts/update_and_publish.sh`는 자동화 과정에서 `git reset --hard origin/main`을 수행하므로, 개인 작업 트리와 충돌 가능성이 있어 상시 1차 라인으로는 비권장

요약: 운영 안정성 기준으로는 **OpenClaw cron + GitHub Actions 백업** 조합이 가장 안전하고, 로컬 cron은 장애 대응/수동 복구 용도로 두는 구성이 적합합니다.
