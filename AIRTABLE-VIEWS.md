# Airtable Views Setup for today'sdeal

Airtable Web API 기준으로는 테이블/필드/레코드 동기화는 자동화했지만,
저장된 View 생성/구성은 현재 운영 흐름에서 수동 1회 세팅이 더 안전합니다.

아래 6개 View만 만들면 v1 운영은 충분합니다.

---

## 1) Daily Deals / 오늘 전체 딜
- Table: `Daily Deals`
- View name: `오늘 전체 딜`
- Filter:
  - `Is Latest Snapshot` is checked
- Sort:
  - `Rank` ascending
- Visible fields 추천:
  - `Rank`
  - `Category`
  - `Store Name`
  - `Brand Name`
  - `Product Name`
  - `Deal Type`
  - `Sale Price`
  - `Discount Rate`
  - `Status Today`
  - `Product URL`

---

## 2) Daily Deals / 오늘 신규 진입
- Table: `Daily Deals`
- View name: `오늘 신규 진입`
- Filter:
  - `New Today` is checked
- Sort:
  - `Rank` ascending
- Visible fields 추천:
  - `Rank`
  - `Store Name`
  - `Brand Name`
  - `Product Name`
  - `Sale Price`
  - `Discount Rate`
  - `Review Score`
  - `Review Count`

---

## 3) Daily Deals / 오늘 가격 변동
- Table: `Daily Deals`
- View name: `오늘 가격 변동`
- Filter:
  - `Price Changed` is checked
- Sort:
  - `Discount Rate` descending
  - `Rank` ascending
- Visible fields 추천:
  - `Rank`
  - `Store Name`
  - `Brand Name`
  - `Product Name`
  - `Original Price`
  - `Sale Price`
  - `Discount Rate`
  - `Days Seen Total`

---

## 4) Daily Deals / 카테고리별 워치
- Table: `Daily Deals`
- View name: `카테고리별 워치`
- Filter:
  - `Is Latest Snapshot` is checked
- Group:
  - `Category`
- Sort:
  - `Rank` ascending
- Visible fields 추천:
  - `Category`
  - `Rank`
  - `Store Name`
  - `Brand Name`
  - `Product Name`
  - `Sale Price`
  - `Discount Rate`
  - `Status Today`

---

## 5) Products / 활성 상품
- Table: `Products`
- View name: `활성 상품`
- Filter:
  - `Current Status` is not `이탈`
- Sort:
  - `Latest Rank` ascending
- Visible fields 추천:
  - `Latest Rank`
  - `Brand Name`
  - `Latest Product Name`
  - `Category`
  - `Current Status`
  - `Active Days`
  - `Latest Sale Price`
  - `Latest Discount Rate`
  - `Price Change Count`
  - `Product URL`

---

## 6) Runs / 실행 로그
- Table: `Runs`
- View name: `실행 로그`
- Sort:
  - `Run At` descending
- Visible fields 추천:
  - `Run At`
  - `Snapshot Date`
  - `Job Status`
  - `Product Count`
  - `New Count`
  - `Removed Count`
  - `Price Changed Count`
  - `Source`
  - `Notes`

---

## 운영 팁
- `z_unused_default` 는 비워둔 보관용 기본 테이블입니다. 그냥 무시해도 됩니다.
- `Daily Deals`는 `Is Latest Snapshot` 필드로 최신 데이터만 바로 필터링하세요.
- v1에서는 View를 많이 만들지 말고 위 6개만 먼저 운영하세요.
