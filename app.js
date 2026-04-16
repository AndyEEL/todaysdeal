const numberFormatter = new Intl.NumberFormat("ko-KR");
const dateFormatter = new Intl.DateTimeFormat("ko-KR", {
  timeZone: "Asia/Seoul",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

const V1_CATEGORY_LABELS = [
  "식품·신선식품",
  "생활용품·뷰티",
  "디지털·가전",
  "리빙·주방·레저",
  "홈·문구·취미",
  "패션·잡화",
];

const CATEGORY_KEYWORD_RULES = [
  {
    label: "식품·신선식품",
    keywords: [
      "쌀",
      "김치",
      "국밥",
      "냉면",
      "고기",
      "삼겹",
      "목살",
      "한우",
      "오리",
      "닭",
      "명란",
      "생수",
      "토마토",
      "키위",
      "채소",
      "샐러드",
      "인절미",
      "커피",
      "음료",
      "우유",
      "효소",
      "영양식",
      "프로바이오틱스",
      "식품",
      "밀키트",
      "반찬",
      "올리브오일",
    ],
  },
  {
    label: "생활용품·뷰티",
    keywords: [
      "물티슈",
      "주방세제",
      "세제",
      "리필봉투",
      "샴푸",
      "트리트먼트",
      "헤어",
      "클렌징",
      "선크림",
      "로션",
      "크림",
      "비누",
      "마스크팩",
      "탈모",
      "뷰티",
      "미용",
      "청소",
      "세탁",
      "헬스",
      "찜질팩",
      "홈쎄라",
      "리프팅",
    ],
  },
  {
    label: "디지털·가전",
    keywords: [
      "노트북",
      "모니터",
      "이어폰",
      "헤드폰",
      "키보드",
      "마우스",
      "충전기",
      "스피커",
      "태블릿",
      "스마트폰",
      "가전",
      "디지털",
      "블루투스",
      "웨어러블",
    ],
  },
  {
    label: "리빙·주방·레저",
    keywords: [
      "주방",
      "냄비",
      "프라이팬",
      "도마",
      "수납",
      "침구",
      "매트",
      "오븐",
      "에어프라이어",
      "스텝퍼",
      "운동",
      "레저",
      "캠핑",
      "가구",
      "소파",
      "의자",
      "테이블",
      "멀티탭",
    ],
  },
  {
    label: "홈·문구·취미",
    keywords: [
      "문구",
      "노트",
      "다이어리",
      "취미",
      "diy",
      "인테리어",
      "반려",
      "고양이",
      "강아지",
      "모래",
      "유아",
      "완구",
      "장난감",
      "학용",
      "홈",
    ],
  },
  {
    label: "패션·잡화",
    keywords: [
      "원피스",
      "셔츠",
      "티셔츠",
      "팬츠",
      "바지",
      "자켓",
      "신발",
      "가방",
      "의류",
      "양말",
      "모자",
      "잡화",
      "패션",
      "악세사리",
      "액세서리",
    ],
  },
];

const STATUS_LABELS = {
  entering: "신규",
  price_changed: "가격 변동",
  active: "운영 중",
  removed: "이탈",
};

const state = {
  selectedDate: null,
  availableDates: [],
  dailyInsight: null,
  productSummaryMap: new Map(),
  productDetailCache: new Map(),
  storeByProductId: new Map(),
  enrichedProductMap: new Map(),
  enrichedProducts: [],
  filteredProducts: [],
  filters: {
    category: "all",
    store: "all",
    dealType: "all",
    brand: "all",
    q: "",
    sort: "rank",
  },
};

function getTodayKstString() {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function collapseWhitespace(value) {
  return String(value ?? "")
    .replace(/\s+/g, " ")
    .trim();
}

function extractBracketBrand(productName) {
  const match = /^\[([^\]]+)\]/.exec(collapseWhitespace(productName));
  if (!match) return "";
  return collapseWhitespace(match[1]);
}

function isChannelBrand(value) {
  return /^채널\d+$/.test(collapseWhitespace(value));
}

function extractProductIdFromUrl(url) {
  const value = collapseWhitespace(url);
  const match = /\/products\/(\d+)/.exec(value);
  return match ? match[1] : "";
}

function formatWon(value) {
  if (value == null || Number.isNaN(Number(value))) return "-";
  return `${numberFormatter.format(Number(value))}원`;
}

function formatPercent(value) {
  if (value == null || Number.isNaN(Number(value))) return "-";
  return `${Number(value).toFixed(1)}%`;
}

function formatDate(value) {
  if (!value) return "-";
  return dateFormatter.format(new Date(`${value}T00:00:00+09:00`));
}

function normalizeApiError(status, payload) {
  if (status === 404) return payload?.error || "요청한 날짜 데이터가 없습니다.";
  return payload?.error || `API 요청 실패 (${status})`;
}

async function fetchJson(url, allowNotFound = false) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    let payload = null;
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }
    if (allowNotFound && response.status === 404) {
      return null;
    }
    throw new Error(normalizeApiError(response.status, payload));
  }
  return response.json();
}

async function loadDateIndex() {
  const payload = await fetchJson("/api/insights/dates", true);
  if (!payload || !Array.isArray(payload.dates)) {
    return {
      dates: [getTodayKstString()],
      latestDate: getTodayKstString(),
    };
  }
  return {
    dates: payload.dates,
    latestDate: payload.latest_date || payload.dates[payload.dates.length - 1],
  };
}

async function ensureProductSummaryMap() {
  if (state.productSummaryMap.size > 0) return;
  const payload = await fetchJson("/api/insights/products?limit=1000", true);
  if (!payload || !Array.isArray(payload.items)) return;
  for (const item of payload.items) {
    state.productSummaryMap.set(item.product_id, item);
  }
}

async function loadStoreMapForDate(dateString) {
  state.storeByProductId.clear();
  try {
    const payload = await fetchJson(`/data/daily/${encodeURIComponent(dateString)}.json`, true);
    if (!payload || !Array.isArray(payload.products)) return;

    for (const rawProduct of payload.products) {
      const productId = collapseWhitespace(
        rawProduct.product_id || extractProductIdFromUrl(rawProduct.landing_url)
      );
      if (!productId) continue;

      const channelNo = collapseWhitespace(rawProduct.channel_no);
      if (channelNo) {
        state.storeByProductId.set(productId, `채널${channelNo}`);
        continue;
      }

      const storeFromUrl = inferStoreFromUrl(rawProduct.landing_url);
      if (storeFromUrl) {
        state.storeByProductId.set(productId, storeFromUrl);
      }
    }
  } catch (error) {
    console.warn("스토어 매핑 스냅샷 로드 실패, fallback 추론으로 계속 진행합니다.", error);
  }
}

function inferStoreFromUrl(url) {
  const value = collapseWhitespace(url);
  if (!value) return "";

  try {
    const parsed = new URL(value);
    if (parsed.hostname.includes("smartstore.naver.com")) {
      const firstSegment = parsed.pathname.split("/").filter(Boolean)[0] || "";
      if (firstSegment && firstSegment !== "main") {
        return `스토어:${firstSegment}`;
      }
      if (firstSegment === "main") {
        return "스마트스토어 main";
      }
    }
    return parsed.hostname;
  } catch {
    return "";
  }
}

function inferBrandLabel(product) {
  const rawBrand = collapseWhitespace(product.brand);
  if (rawBrand && !isChannelBrand(rawBrand)) {
    return rawBrand;
  }

  const bracketBrand = extractBracketBrand(product.product_name);
  if (bracketBrand && !isChannelBrand(bracketBrand)) {
    return bracketBrand;
  }

  const strippedName = collapseWhitespace(product.product_name).replace(/^\[[^\]]+\]\s*/, "");
  const firstToken = collapseWhitespace(strippedName).split(" ")[0];
  if (firstToken && firstToken.length <= 20) {
    return firstToken;
  }

  if (rawBrand) return rawBrand;
  return "브랜드 미확인";
}

function inferStoreLabel(product) {
  const byProductMap = state.storeByProductId.get(product.product_id);
  if (byProductMap) return byProductMap;

  const rawBrand = collapseWhitespace(product.brand);
  if (isChannelBrand(rawBrand)) return rawBrand;

  const storeFromUrl = inferStoreFromUrl(product.product_url || product.mobile_product_url);
  if (storeFromUrl) return storeFromUrl;

  if (rawBrand) return `${rawBrand} 운영`;
  return "스토어 미확인";
}

function inferV1Category(product) {
  const name = collapseWhitespace(product.product_name).toLowerCase();
  const sourceCategory = collapseWhitespace(product.category).toLowerCase();

  for (const rule of CATEGORY_KEYWORD_RULES) {
    if (rule.keywords.some((keyword) => name.includes(keyword.toLowerCase()))) {
      return rule.label;
    }
  }

  if (sourceCategory.includes("식품") || sourceCategory.includes("음료") || sourceCategory.includes("신선")) {
    return "식품·신선식품";
  }
  if (sourceCategory.includes("뷰티") || sourceCategory.includes("헬스") || sourceCategory.includes("생활")) {
    return "생활용품·뷰티";
  }
  if (sourceCategory.includes("디지털") || sourceCategory.includes("가전")) {
    return "디지털·가전";
  }
  if (sourceCategory.includes("주방") || sourceCategory.includes("리빙") || sourceCategory.includes("레저")) {
    return "리빙·주방·레저";
  }
  if (
    sourceCategory.includes("홈") ||
    sourceCategory.includes("문구") ||
    sourceCategory.includes("취미") ||
    sourceCategory.includes("육아") ||
    sourceCategory.includes("반려")
  ) {
    return "홈·문구·취미";
  }
  if (sourceCategory.includes("패션") || sourceCategory.includes("잡화") || sourceCategory.includes("의류")) {
    return "패션·잡화";
  }

  return "홈·문구·취미";
}

function statusLabel(status) {
  return STATUS_LABELS[status] || "운영 중";
}

function enrichProducts(products) {
  state.enrichedProductMap.clear();

  const enriched = products.map((product) => {
    const summary = state.productSummaryMap.get(product.product_id);

    const enrichedProduct = {
      ...product,
      category_v1: inferV1Category(product),
      brand_label: inferBrandLabel(product),
      store_label: inferStoreLabel(product),
      deal_type_label: collapseWhitespace(product.deal_type) || "스페셜딜",
      active_days: summary?.active_days || product.active_days || 1,
      price_change_count: summary?.price_change_count || 0,
    };

    state.enrichedProductMap.set(enrichedProduct.product_id, enrichedProduct);
    return enrichedProduct;
  });

  state.enrichedProducts = enriched;
  return enriched;
}

function applyFiltersAndSort(products) {
  const { category, store, dealType, brand, q, sort } = state.filters;
  const keyword = q.trim().toLowerCase();

  let filtered = products.filter((product) => {
    if (category !== "all" && product.category_v1 !== category) return false;
    if (store !== "all" && product.store_label !== store) return false;
    if (dealType !== "all" && product.deal_type_label !== dealType) return false;
    if (brand !== "all" && product.brand_label !== brand) return false;

    if (!keyword) return true;

    return (
      collapseWhitespace(product.product_name).toLowerCase().includes(keyword) ||
      collapseWhitespace(product.brand_label).toLowerCase().includes(keyword) ||
      collapseWhitespace(product.store_label).toLowerCase().includes(keyword)
    );
  });

  filtered = [...filtered];

  if (sort === "discount") {
    filtered.sort((a, b) => (b.discount_rate || 0) - (a.discount_rate || 0));
  } else if (sort === "sale_price_low") {
    filtered.sort((a, b) => (a.sale_price || Number.MAX_SAFE_INTEGER) - (b.sale_price || Number.MAX_SAFE_INTEGER));
  } else if (sort === "active_days") {
    filtered.sort((a, b) => (b.active_days || 0) - (a.active_days || 0));
  } else if (sort === "price_changes") {
    filtered.sort((a, b) => (b.price_change_count || 0) - (a.price_change_count || 0));
  } else {
    filtered.sort((a, b) => (a.rank_or_position || 9999) - (b.rank_or_position || 9999));
  }

  state.filteredProducts = filtered;
  return filtered;
}

function renderKpis(products, insight) {
  const totalProducts = products.length;
  const enteringProducts = products.filter((item) => item.status === "entering").length;
  const priceChangedProducts = products.filter((item) => item.status === "price_changed").length;
  const storeCount = new Set(products.map((item) => item.store_label)).size;

  document.getElementById("kpi-total-products").textContent = `${numberFormatter.format(totalProducts)}개`;
  document.getElementById("kpi-entering-products").textContent = `${numberFormatter.format(enteringProducts)}개`;
  document.getElementById("kpi-price-change-products").textContent = `${numberFormatter.format(priceChangedProducts)}개`;
  document.getElementById("kpi-store-count").textContent = `${numberFormatter.format(storeCount)}곳`;

  if (!insight) {
    document.getElementById("summary-note").textContent = "-";
    return;
  }

  const previousDate = insight.previous_date ? formatDate(insight.previous_date) : "비교 데이터 없음";
  const countDiff = insight.product_count_diff;
  const diffText =
    countDiff == null ? "-" : `${countDiff > 0 ? "+" : ""}${numberFormatter.format(countDiff)}개`;

  document.getElementById("summary-note").textContent = `기준일 ${formatDate(
    state.selectedDate
  )} · 전일(${previousDate}) 대비 전체 ${diffText} · 현재 필터 ${numberFormatter.format(
    totalProducts
  )}개`;
}

function renderSelectOptions(selectNode, values, currentValue) {
  selectNode.innerHTML = `<option value="all">전체</option>${values
    .map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`)
    .join("")}`;

  if (currentValue !== "all" && values.includes(currentValue)) {
    selectNode.value = currentValue;
  } else {
    selectNode.value = "all";
  }
}

function renderFilterOptions(products) {
  const categorySelect = document.getElementById("category-filter");
  const storeSelect = document.getElementById("store-filter");
  const dealTypeSelect = document.getElementById("deal-type-filter");
  const brandSelect = document.getElementById("brand-filter");

  const current = { ...state.filters };

  renderSelectOptions(categorySelect, V1_CATEGORY_LABELS, current.category);
  const selectedCategory = categorySelect.value;

  const categoryScopedProducts =
    selectedCategory === "all"
      ? products
      : products.filter((product) => product.category_v1 === selectedCategory);

  const stores = [...new Set(categoryScopedProducts.map((product) => product.store_label))].sort((a, b) =>
    a.localeCompare(b, "ko")
  );
  renderSelectOptions(storeSelect, stores, current.store);
  const selectedStore = storeSelect.value;

  const storeScopedProducts =
    selectedStore === "all"
      ? categoryScopedProducts
      : categoryScopedProducts.filter((product) => product.store_label === selectedStore);

  const dealTypes = [...new Set(storeScopedProducts.map((product) => product.deal_type_label))].sort((a, b) =>
    a.localeCompare(b, "ko")
  );
  const brands = [...new Set(storeScopedProducts.map((product) => product.brand_label))].sort((a, b) =>
    a.localeCompare(b, "ko")
  );

  renderSelectOptions(dealTypeSelect, dealTypes, current.dealType);
  renderSelectOptions(brandSelect, brands, current.brand);

  state.filters.category = categorySelect.value;
  state.filters.store = storeSelect.value;
  state.filters.dealType = dealTypeSelect.value;
  state.filters.brand = brandSelect.value;
}

function statusClassName(status) {
  if (status === "entering") return "status-entering";
  if (status === "price_changed") return "status-price-changed";
  if (status === "removed") return "status-removed";
  return "status-active";
}

function renderProductTable(products) {
  const body = document.getElementById("product-table-body");

  if (!products.length) {
    body.innerHTML = `
      <tr>
        <td colspan="12" class="empty-cell">조건에 맞는 상품이 없습니다.</td>
      </tr>
    `;
    document.getElementById("list-meta").textContent = `0개 표시 (기준일 ${state.selectedDate})`;
    return;
  }

  body.innerHTML = products
    .map(
      (product) => `
      <tr>
        <td class="cell-number">${product.rank_or_position ?? "-"}</td>
        <td>${escapeHtml(product.category_v1)}</td>
        <td>${escapeHtml(product.store_label)}</td>
        <td>${escapeHtml(product.brand_label)}</td>
        <td class="cell-product">${escapeHtml(product.product_name)}</td>
        <td>${escapeHtml(product.deal_type_label)}</td>
        <td class="cell-number">${formatWon(product.sale_price)}</td>
        <td class="cell-number">${
          product.discount_rate == null ? "-" : `${product.discount_rate}%`
        }</td>
        <td><span class="status-chip ${statusClassName(product.status)}">${escapeHtml(
        statusLabel(product.status)
      )}</span></td>
        <td class="cell-number">${numberFormatter.format(product.active_days || 1)}일</td>
        <td>
          <a class="line-button" href="${escapeHtml(
            product.product_url || "#"
          )}" target="_blank" rel="noreferrer noopener">열기</a>
        </td>
        <td>
          <button type="button" class="line-button timeline-button" data-product-id="${escapeHtml(
            product.product_id
          )}">타임라인</button>
        </td>
      </tr>
    `
    )
    .join("");

  for (const button of body.querySelectorAll(".timeline-button")) {
    button.addEventListener("click", () => loadProductDetail(button.dataset.productId || ""));
  }

  document.getElementById("list-meta").textContent = `${numberFormatter.format(
    products.length
  )}개 표시 / 전체 ${numberFormatter.format(state.enrichedProducts.length)}개 (기준일 ${state.selectedDate})`;
}

function buildBrandFlowRows(products) {
  const grouped = new Map();

  for (const product of products) {
    const key = product.brand_label || "브랜드 미확인";

    if (!grouped.has(key)) {
      grouped.set(key, {
        brand: key,
        productCount: 0,
        enteringCount: 0,
        changedCount: 0,
        activeCount: 0,
        storeSet: new Set(),
        discountSum: 0,
        discountCount: 0,
        activeDaysSum: 0,
        categoryCounts: new Map(),
      });
    }

    const row = grouped.get(key);
    row.productCount += 1;
    row.storeSet.add(product.store_label);
    row.activeDaysSum += product.active_days || 1;

    if (product.status === "entering") row.enteringCount += 1;
    if (product.status === "price_changed") row.changedCount += 1;
    if (product.status === "active") row.activeCount += 1;

    if (product.discount_rate != null) {
      row.discountSum += Number(product.discount_rate);
      row.discountCount += 1;
    }

    const currentCategoryCount = row.categoryCounts.get(product.category_v1) || 0;
    row.categoryCounts.set(product.category_v1, currentCategoryCount + 1);
  }

  return [...grouped.values()]
    .map((row) => {
      const topCategory = [...row.categoryCounts.entries()].sort((a, b) => {
        if (b[1] !== a[1]) return b[1] - a[1];
        return V1_CATEGORY_LABELS.indexOf(a[0]) - V1_CATEGORY_LABELS.indexOf(b[0]);
      })[0]?.[0];

      return {
        brand: row.brand,
        productCount: row.productCount,
        storeCount: row.storeSet.size,
        enteringCount: row.enteringCount,
        changedCount: row.changedCount,
        activeCount: row.activeCount,
        averageDiscountRate: row.discountCount ? row.discountSum / row.discountCount : null,
        averageActiveDays: row.productCount ? row.activeDaysSum / row.productCount : null,
        topCategory: topCategory || "-",
      };
    })
    .sort((a, b) => {
      if (b.productCount !== a.productCount) return b.productCount - a.productCount;
      if (b.enteringCount !== a.enteringCount) return b.enteringCount - a.enteringCount;
      return a.brand.localeCompare(b.brand, "ko");
    });
}

function renderBrandFlow(rows) {
  const body = document.getElementById("brand-flow-body");

  if (!rows.length) {
    body.innerHTML = `
      <tr>
        <td colspan="9" class="empty-cell">브랜드 플로우를 계산할 데이터가 없습니다.</td>
      </tr>
    `;
    document.getElementById("brand-flow-meta").textContent = "0개 브랜드";
    return;
  }

  body.innerHTML = rows
    .map(
      (row) => `
      <tr>
        <td>${escapeHtml(row.brand)}</td>
        <td class="cell-number">${numberFormatter.format(row.productCount)}개</td>
        <td class="cell-number">${numberFormatter.format(row.storeCount)}곳</td>
        <td class="cell-number">${numberFormatter.format(row.enteringCount)}개</td>
        <td class="cell-number">${numberFormatter.format(row.changedCount)}개</td>
        <td class="cell-number">${numberFormatter.format(row.activeCount)}개</td>
        <td class="cell-number">${formatPercent(row.averageDiscountRate)}</td>
        <td class="cell-number">${row.averageActiveDays == null ? "-" : `${row.averageActiveDays.toFixed(
          1
        )}일`}</td>
        <td>${escapeHtml(row.topCategory)}</td>
      </tr>
    `
    )
    .join("");

  document.getElementById("brand-flow-meta").textContent = `${numberFormatter.format(
    rows.length
  )}개 브랜드 (현재 필터 기준)`;
}

function renderRemovedList(removedProducts) {
  const list = document.getElementById("removed-list");
  list.innerHTML = "";

  if (!removedProducts || !removedProducts.length) {
    list.innerHTML = "<li>오늘 이탈 상품이 없습니다.</li>";
    return;
  }

  for (const product of removedProducts.slice(0, 12)) {
    const item = document.createElement("li");
    const category = inferV1Category(product);
    item.innerHTML = `
      <span>${escapeHtml(product.product_name)}</span>
      <span>${escapeHtml(category)}</span>
    `;
    list.appendChild(item);
  }
}

function renderProductDetail(payload, productMeta) {
  const container = document.getElementById("product-detail");
  const timeline = payload.price_timeline || [];
  const lifecycleEvents = payload.lifecycle_events || [];

  const brandLabel = productMeta?.brand_label || inferBrandLabel(payload);
  const storeLabel = productMeta?.store_label || inferStoreLabel(payload);
  const categoryLabel = productMeta?.category_v1 || inferV1Category(payload);

  const timelineRows = timeline
    .slice(-10)
    .reverse()
    .map(
      (item) => `
      <tr>
        <td>${escapeHtml(item.date)}</td>
        <td>${formatWon(item.sale_price)}</td>
        <td>${formatWon(item.original_price)}</td>
        <td>${item.discount_rate == null ? "-" : `${item.discount_rate}%`}</td>
      </tr>
    `
    )
    .join("");

  const eventRows = lifecycleEvents
    .slice(-12)
    .reverse()
    .map(
      (event) => `
      <li>
        <span class="event-head">${escapeHtml(event.date)} · ${escapeHtml(event.type)}</span>
        <p>${escapeHtml(event.summary || "")}</p>
      </li>
    `
    )
    .join("");

  container.innerHTML = `
    <div class="detail-head">
      <img
        src="${escapeHtml(
          payload.latest_image_url || "https://placehold.co/300x300/e5e7eb/9ca3af?text=No+Image"
        )}"
        alt="${escapeHtml(payload.product_name)}"
      />
      <div>
        <h3>${escapeHtml(payload.product_name)}</h3>
        <p>${escapeHtml(categoryLabel)} · ${escapeHtml(storeLabel)} · ${escapeHtml(brandLabel)}</p>
        <p>노출 기간: ${formatDate(payload.first_seen_date)} ~ ${formatDate(payload.last_seen_date)} (${numberFormatter.format(
    payload.active_days || 0
  )}일)</p>
        <a href="${escapeHtml(payload.product_url || "#")}" target="_blank" rel="noreferrer noopener">상품 페이지 열기</a>
      </div>
    </div>

    <div class="detail-grid">
      <div class="detail-block">
        <h4>가격 타임라인</h4>
        <table class="mini-table">
          <thead>
            <tr><th>날짜</th><th>판매가</th><th>정가</th><th>할인율</th></tr>
          </thead>
          <tbody>${timelineRows || '<tr><td colspan="4">기록 없음</td></tr>'}</tbody>
        </table>
      </div>
      <div class="detail-block">
        <h4>운영 이벤트</h4>
        <ul class="event-list">${eventRows || "<li><p>이벤트 기록 없음</p></li>"}</ul>
      </div>
    </div>
  `;
}

async function loadProductDetail(productId) {
  if (!productId) return;

  const container = document.getElementById("product-detail");
  container.innerHTML = `<p class="meta-text">타임라인을 불러오는 중입니다...</p>`;

  const cached = state.productDetailCache.get(productId);
  const productMeta = state.enrichedProductMap.get(productId);

  if (cached) {
    renderProductDetail(cached, productMeta);
    return;
  }

  try {
    const payload = await fetchJson(`/api/products?productId=${encodeURIComponent(productId)}`);
    state.productDetailCache.set(productId, payload);
    renderProductDetail(payload, productMeta);
  } catch (error) {
    container.innerHTML = `<p class="meta-text">${escapeHtml(error.message)}</p>`;
  }
}

function renderError(message) {
  document.getElementById("product-table-body").innerHTML = `
    <tr>
      <td colspan="12" class="empty-cell error-cell">데이터를 불러오지 못했습니다. ${escapeHtml(message)}</td>
    </tr>
  `;

  document.getElementById("brand-flow-body").innerHTML = `
    <tr>
      <td colspan="9" class="empty-cell error-cell">브랜드 플로우를 계산할 수 없습니다.</td>
    </tr>
  `;

  document.getElementById("removed-list").innerHTML = `<li>${escapeHtml(message)}</li>`;
  document.getElementById("brand-flow-meta").textContent = "-";
  document.getElementById("list-meta").textContent = "-";
  document.getElementById("summary-note").textContent = escapeHtml(message);

  const kpiIds = [
    "kpi-total-products",
    "kpi-entering-products",
    "kpi-price-change-products",
    "kpi-store-count",
  ];

  for (const id of kpiIds) {
    document.getElementById(id).textContent = "-";
  }
}

function setControlsDisabled(disabled) {
  const ids = [
    "date-input",
    "today-button",
    "reload-button",
    "category-filter",
    "store-filter",
    "deal-type-filter",
    "brand-filter",
    "search-input",
    "sort-filter",
  ];

  for (const id of ids) {
    const node = document.getElementById(id);
    if (node) node.disabled = disabled;
  }
}

function rerenderByFilters() {
  const visibleProducts = applyFiltersAndSort(state.enrichedProducts || []);
  renderKpis(visibleProducts, state.dailyInsight);
  renderProductTable(visibleProducts);

  const brandFlowRows = buildBrandFlowRows(visibleProducts);
  renderBrandFlow(brandFlowRows);
}

async function loadWorkbench(dateString) {
  state.selectedDate = dateString;
  setControlsDisabled(true);

  try {
    await ensureProductSummaryMap();
    await loadStoreMapForDate(dateString);

    const insight = await fetchJson(`/api/insights/daily?date=${encodeURIComponent(dateString)}`);
    state.dailyInsight = insight;

    enrichProducts(insight.products || []);
    renderFilterOptions(state.enrichedProducts);
    renderRemovedList(insight.removed_products || []);
    rerenderByFilters();
  } catch (error) {
    renderError(error instanceof Error ? error.message : "알 수 없는 오류");
  } finally {
    setControlsDisabled(false);
  }
}

function bindEvents() {
  const dateInput = document.getElementById("date-input");
  const todayButton = document.getElementById("today-button");
  const reloadButton = document.getElementById("reload-button");

  const categoryFilter = document.getElementById("category-filter");
  const storeFilter = document.getElementById("store-filter");
  const dealTypeFilter = document.getElementById("deal-type-filter");
  const brandFilter = document.getElementById("brand-filter");
  const searchInput = document.getElementById("search-input");
  const sortFilter = document.getElementById("sort-filter");

  dateInput.addEventListener("change", () => {
    if (!dateInput.value) return;
    loadWorkbench(dateInput.value);
  });

  todayButton.addEventListener("click", () => {
    const today = getTodayKstString();
    const next = state.availableDates.includes(today)
      ? today
      : state.availableDates[state.availableDates.length - 1] || today;
    dateInput.value = next;
    loadWorkbench(next);
  });

  reloadButton.addEventListener("click", () => {
    if (!state.selectedDate) return;
    loadWorkbench(state.selectedDate);
  });

  categoryFilter.addEventListener("change", (event) => {
    state.filters.category = event.target.value;
    state.filters.store = "all";
    state.filters.brand = "all";
    renderFilterOptions(state.enrichedProducts);
    rerenderByFilters();
  });

  storeFilter.addEventListener("change", (event) => {
    state.filters.store = event.target.value;
    state.filters.brand = "all";
    renderFilterOptions(state.enrichedProducts);
    rerenderByFilters();
  });

  dealTypeFilter.addEventListener("change", (event) => {
    state.filters.dealType = event.target.value;
    renderFilterOptions(state.enrichedProducts);
    rerenderByFilters();
  });

  brandFilter.addEventListener("change", (event) => {
    state.filters.brand = event.target.value;
    rerenderByFilters();
  });

  searchInput.addEventListener("input", (event) => {
    state.filters.q = event.target.value || "";
    rerenderByFilters();
  });

  sortFilter.addEventListener("change", (event) => {
    state.filters.sort = event.target.value;
    rerenderByFilters();
  });
}

async function init() {
  bindEvents();

  const dateInput = document.getElementById("date-input");
  const dateIndex = await loadDateIndex();

  state.availableDates = dateIndex.dates || [];

  const defaultDate = state.availableDates.includes(getTodayKstString())
    ? getTodayKstString()
    : dateIndex.latestDate || getTodayKstString();

  if (state.availableDates.length) {
    dateInput.min = state.availableDates[0];
    dateInput.max = state.availableDates[state.availableDates.length - 1];
  }

  dateInput.value = defaultDate;
  await loadWorkbench(defaultDate);
}

init();
