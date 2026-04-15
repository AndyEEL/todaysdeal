const numberFormatter = new Intl.NumberFormat("ko-KR");
const dateFormatter = new Intl.DateTimeFormat("ko-KR", {
  timeZone: "Asia/Seoul",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

const state = {
  selectedDate: null,
  availableDates: [],
  dailyInsight: null,
  productSummaryMap: new Map(),
  productDetailCache: new Map(),
  filteredProducts: [],
  filters: {
    q: "",
    status: "all",
    brand: "all",
    category: "all",
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

function formatWon(value) {
  if (value == null) return "-";
  return `${numberFormatter.format(value)}원`;
}

function formatRatio(value) {
  if (value == null) return "-";
  return `${(value * 100).toFixed(1)}%`;
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

function statusLabel(status) {
  if (status === "entering") return "NEW";
  if (status === "price_changed") return "PRICE CHANGED";
  return "ACTIVE";
}

function applyFiltersAndSort(products) {
  const { q, status, brand, category, sort } = state.filters;
  const keyword = q.trim().toLowerCase();

  let filtered = products.filter((product) => {
    if (status !== "all" && product.status !== status) return false;
    if (brand !== "all" && product.brand !== brand) return false;
    if (category !== "all" && product.category !== category) return false;
    if (!keyword) return true;
    return (
      product.product_name.toLowerCase().includes(keyword) ||
      product.brand.toLowerCase().includes(keyword)
    );
  });

  filtered = [...filtered];
  if (sort === "discount") {
    filtered.sort((a, b) => (b.discount_rate || 0) - (a.discount_rate || 0));
  } else if (sort === "active_days") {
    filtered.sort((a, b) => (b.active_days || 0) - (a.active_days || 0));
  } else if (sort === "price_changes") {
    filtered.sort((a, b) => {
      const aChanges = state.productSummaryMap.get(a.product_id)?.price_change_count || 0;
      const bChanges = state.productSummaryMap.get(b.product_id)?.price_change_count || 0;
      return bChanges - aChanges;
    });
  } else {
    filtered.sort((a, b) => (a.rank_or_position || 9999) - (b.rank_or_position || 9999));
  }

  state.filteredProducts = filtered;
  return filtered;
}

function renderKpis(insight) {
  document.getElementById("kpi-product-count").textContent = `${insight.product_count}개`;
  document.getElementById("kpi-new-count").textContent = `${insight.new_count}개`;
  document.getElementById("kpi-removed-count").textContent = `${insight.removed_count}개`;
  document.getElementById("kpi-price-changed-count").textContent = `${insight.price_changed_count}개`;

  const previousDate = insight.previous_date ? formatDate(insight.previous_date) : "비교 데이터 없음";
  const diff =
    insight.product_count_diff == null
      ? "-"
      : `${insight.product_count_diff > 0 ? "+" : ""}${insight.product_count_diff}`;
  document.getElementById("summary-note").textContent = `${previousDate} 대비 상품 수 ${diff}`;
}

function renderBrandSummary(insight) {
  const entering = insight.top_entering_brand;
  const exiting = insight.top_exiting_brand;
  document.getElementById("top-entering-brand").textContent = entering
    ? `${entering[0]} (${entering[1]}개)`
    : "-";
  document.getElementById("top-exiting-brand").textContent = exiting
    ? `${exiting[0]} (${exiting[1]}개)`
    : "-";
  document.getElementById("post-exit-ratio").textContent =
    insight.price_reverted_after_exit_ratio == null
      ? "관측 데이터 부족"
      : `복귀 ${formatRatio(insight.price_reverted_after_exit_ratio)} / 유지 ${formatRatio(
          insight.price_held_after_exit_ratio
        )}`;
}

function renderDeltaList(targetId, products, tagLabel, tagClass) {
  const list = document.getElementById(targetId);
  list.innerHTML = "";
  if (!products || !products.length) {
    list.innerHTML = "<li>없음</li>";
    return;
  }

  for (const product of products.slice(0, 12)) {
    const item = document.createElement("li");
    item.innerHTML = `
      <span>${escapeHtml(product.product_name)}</span>
      <span class="tag ${tagClass}">${tagLabel}</span>
    `;
    list.appendChild(item);
  }
}

function renderFilterOptions(products) {
  const brandSelect = document.getElementById("brand-filter");
  const categorySelect = document.getElementById("category-filter");
  const currentBrand = state.filters.brand;
  const currentCategory = state.filters.category;

  const brands = [...new Set(products.map((product) => product.brand))].sort((a, b) =>
    a.localeCompare(b, "ko")
  );
  const categories = [...new Set(products.map((product) => product.category))].sort((a, b) =>
    a.localeCompare(b, "ko")
  );

  brandSelect.innerHTML = `<option value="all">전체</option>${brands
    .map((brand) => `<option value="${escapeHtml(brand)}">${escapeHtml(brand)}</option>`)
    .join("")}`;
  categorySelect.innerHTML = `<option value="all">전체</option>${categories
    .map((category) => `<option value="${escapeHtml(category)}">${escapeHtml(category)}</option>`)
    .join("")}`;

  if (brands.includes(currentBrand)) {
    brandSelect.value = currentBrand;
  } else {
    brandSelect.value = "all";
    state.filters.brand = "all";
  }

  if (categories.includes(currentCategory)) {
    categorySelect.value = currentCategory;
  } else {
    categorySelect.value = "all";
    state.filters.category = "all";
  }
}

function createDealCard(product) {
  const template = document.getElementById("deal-card-template");
  const fragment = template.content.cloneNode(true);
  const summary = state.productSummaryMap.get(product.product_id);

  const thumb = fragment.querySelector(".card-thumb");
  thumb.src =
    product.image_url ||
    "https://placehold.co/640x640/f3f4f6/9ca3af?text=No+Image";
  thumb.alt = product.product_name;

  const statusNode = fragment.querySelector(".card-status");
  statusNode.textContent = statusLabel(product.status);
  statusNode.classList.add(`status-${product.status}`);

  fragment.querySelector(".card-rank").textContent = `#${product.rank_or_position || "-"}`;
  fragment.querySelector(".card-title").textContent = product.product_name;
  fragment.querySelector(".card-subtitle").textContent = `${product.brand} · ${product.category} · 누적 ${
    summary?.active_days || product.active_days || 1
  }일`;
  fragment.querySelector(".card-price").textContent = formatWon(product.sale_price);
  fragment.querySelector(".card-discount").textContent = `${product.discount_rate ?? 0}% off`;
  fragment.querySelector(".card-original-price").textContent = `정가 ${formatWon(
    product.original_price
  )}`;

  const link = fragment.querySelector(".card-link");
  link.href = product.product_url || "#";

  const button = fragment.querySelector(".timeline-button");
  button.addEventListener("click", () => loadProductDetail(product.product_id));

  return fragment;
}

function renderProductGrid(products) {
  const grid = document.getElementById("deal-grid");
  grid.innerHTML = "";
  for (const product of products) {
    grid.appendChild(createDealCard(product));
  }
  document.getElementById("list-meta").textContent = `${products.length}개 표시 (기준일 ${state.selectedDate})`;
}

function renderProductDetail(payload) {
  const container = document.getElementById("product-detail");
  const events = payload.lifecycle_events || [];
  const timeline = payload.price_timeline || [];

  const timelineRows = timeline
    .slice(-10)
    .reverse()
    .map(
      (item) => `
      <tr>
        <td>${escapeHtml(item.date)}</td>
        <td>${formatWon(item.sale_price)}</td>
        <td>${formatWon(item.original_price)}</td>
        <td>${item.discount_rate ?? "-"}%</td>
      </tr>
    `
    )
    .join("");

  const eventRows = events
    .slice(-12)
    .reverse()
    .map(
      (event) => `
      <li>
        <span class="event-date">${escapeHtml(event.date)}</span>
        <span class="event-type">${escapeHtml(event.type)}</span>
        <p>${escapeHtml(event.summary || "")}</p>
      </li>
    `
    )
    .join("");

  container.innerHTML = `
    <div class="detail-head">
      <img src="${escapeHtml(
        payload.latest_image_url ||
          "https://placehold.co/300x300/f3f4f6/9ca3af?text=No+Image"
      )}" alt="${escapeHtml(payload.product_name)}" />
      <div>
        <h3>${escapeHtml(payload.product_name)}</h3>
        <p>${escapeHtml(payload.brand)} · ${escapeHtml(payload.category)}</p>
        <p>노출 기간: ${formatDate(payload.first_seen_date)} ~ ${formatDate(payload.last_seen_date)} (${payload.active_days}일)</p>
        <a href="${escapeHtml(payload.product_url || "#")}" target="_blank" rel="noreferrer noopener">상품 페이지 열기</a>
      </div>
    </div>
    <div class="detail-section">
      <h4>가격 타임라인</h4>
      <table class="timeline-table">
        <thead>
          <tr><th>날짜</th><th>판매가</th><th>정가</th><th>할인율</th></tr>
        </thead>
        <tbody>${timelineRows || '<tr><td colspan="4">기록 없음</td></tr>'}</tbody>
      </table>
    </div>
    <div class="detail-section">
      <h4>Lifecycle 이벤트</h4>
      <ul class="event-list">${eventRows || "<li>이벤트 기록 없음</li>"}</ul>
    </div>
  `;
}

async function loadProductDetail(productId) {
  if (!productId) return;
  const cached = state.productDetailCache.get(productId);
  if (cached) {
    renderProductDetail(cached);
    return;
  }

  const container = document.getElementById("product-detail");
  container.innerHTML = `<p class="meta-text">타임라인 로딩 중...</p>`;
  try {
    const payload = await fetchJson(`/api/products?productId=${encodeURIComponent(productId)}`);
    state.productDetailCache.set(productId, payload);
    renderProductDetail(payload);
  } catch (error) {
    container.innerHTML = `<p class="meta-text">${escapeHtml(error.message)}</p>`;
  }
}

function renderError(message) {
  const grid = document.getElementById("deal-grid");
  grid.innerHTML = `
    <article class="error-panel">
      <h3>데이터를 불러오지 못했습니다.</h3>
      <p>${escapeHtml(message)}</p>
    </article>
  `;
}

function setControlsDisabled(disabled) {
  const ids = [
    "date-input",
    "today-button",
    "reload-button",
    "search-input",
    "status-filter",
    "brand-filter",
    "category-filter",
    "sort-filter",
  ];
  for (const id of ids) {
    const node = document.getElementById(id);
    if (node) node.disabled = disabled;
  }
}

async function loadDashboard(dateString) {
  state.selectedDate = dateString;
  setControlsDisabled(true);
  try {
    await ensureProductSummaryMap();
    const insight = await fetchJson(`/api/insights/daily?date=${encodeURIComponent(dateString)}`);
    state.dailyInsight = insight;

    renderKpis(insight);
    renderBrandSummary(insight);
    renderDeltaList("added-list", insight.new_products, "NEW", "tag-new");
    renderDeltaList("removed-list", insight.removed_products, "REMOVED", "tag-removed");
    renderFilterOptions(insight.products || []);

    const visibleProducts = applyFiltersAndSort(insight.products || []);
    renderProductGrid(visibleProducts);
  } catch (error) {
    renderError(error instanceof Error ? error.message : "알 수 없는 오류");
  } finally {
    setControlsDisabled(false);
  }
}

function rerenderByFilters() {
  const insight = state.dailyInsight;
  if (!insight) return;
  const visibleProducts = applyFiltersAndSort(insight.products || []);
  renderProductGrid(visibleProducts);
}

function bindEvents() {
  const dateInput = document.getElementById("date-input");
  const todayButton = document.getElementById("today-button");
  const reloadButton = document.getElementById("reload-button");
  const searchInput = document.getElementById("search-input");
  const statusFilter = document.getElementById("status-filter");
  const brandFilter = document.getElementById("brand-filter");
  const categoryFilter = document.getElementById("category-filter");
  const sortFilter = document.getElementById("sort-filter");

  dateInput.addEventListener("change", () => {
    if (!dateInput.value) return;
    loadDashboard(dateInput.value);
  });

  todayButton.addEventListener("click", () => {
    const today = getTodayKstString();
    const next = state.availableDates.includes(today)
      ? today
      : state.availableDates[state.availableDates.length - 1] || today;
    dateInput.value = next;
    loadDashboard(next);
  });

  reloadButton.addEventListener("click", () => {
    if (!state.selectedDate) return;
    loadDashboard(state.selectedDate);
  });

  searchInput.addEventListener("input", (event) => {
    state.filters.q = event.target.value || "";
    rerenderByFilters();
  });

  statusFilter.addEventListener("change", (event) => {
    state.filters.status = event.target.value;
    rerenderByFilters();
  });

  brandFilter.addEventListener("change", (event) => {
    state.filters.brand = event.target.value;
    rerenderByFilters();
  });

  categoryFilter.addEventListener("change", (event) => {
    state.filters.category = event.target.value;
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
  await loadDashboard(defaultDate);
}

init();
