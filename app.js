const numberFormatter = new Intl.NumberFormat("ko-KR");
const dateTimeFormatter = new Intl.DateTimeFormat("ko-KR", {
  timeZone: "Asia/Seoul",
  month: "long",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

let selectedSnapshot = null;
let requestToken = 0;
let currentNewIdSet = new Set();

function getTodayKstString() {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}

function getPreviousDateString(dateString) {
  const [year, month, day] = dateString.split("-").map(Number);
  const utcDate = new Date(Date.UTC(year, month - 1, day));
  utcDate.setUTCDate(utcDate.getUTCDate() - 1);
  return utcDate.toISOString().slice(0, 10);
}

function formatWon(value) {
  if (value == null) return "-";
  return `${numberFormatter.format(value)}원`;
}

function formatReview(score, count) {
  if (!count) return "리뷰 없음";
  return `${score ?? "-"} / ${numberFormatter.format(count)}개`;
}

function normalizeApiError(status, message) {
  if (status === 404) {
    return "선택한 날짜의 스냅샷 파일이 없습니다.";
  }
  return message || `API 요청 실패 (${status})`;
}

async function fetchSnapshot(dateString, allowNotFound = false) {
  const params = new URLSearchParams();
  if (dateString) params.set("date", dateString);
  const url = params.size ? `/api/snapshot?${params.toString()}` : "/api/snapshot";

  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    if (allowNotFound && response.status === 404) {
      return null;
    }
    let apiMessage = "";
    try {
      const payload = await response.json();
      apiMessage = payload.error || "";
    } catch {
      apiMessage = "";
    }
    throw new Error(normalizeApiError(response.status, apiMessage));
  }
  return response.json();
}

function productKey(product) {
  return String(product.product_id || product.name);
}

function diffProducts(currentSnapshot, previousSnapshot) {
  if (!previousSnapshot) {
    return { added: [], removed: [], countDiff: null };
  }

  const currentMap = new Map(currentSnapshot.products.map((product) => [productKey(product), product]));
  const previousMap = new Map(previousSnapshot.products.map((product) => [productKey(product), product]));

  const added = currentSnapshot.products.filter((product) => !previousMap.has(productKey(product)));
  const removed = previousSnapshot.products.filter((product) => !currentMap.has(productKey(product)));

  return {
    added,
    removed,
    countDiff: currentSnapshot.product_count - previousSnapshot.product_count,
  };
}

function renderHero(snapshot, dateString) {
  document.getElementById("stat-date").textContent = dateString;
  document.getElementById("stat-count").textContent = `${snapshot.product_count}개`;
  document.getElementById("stat-updated").textContent = dateTimeFormatter.format(new Date(snapshot.fetched_at));
  document.getElementById("sale-window").textContent =
    `${snapshot.sale_window.start.slice(5, 16).replace("T", " ")} ~ ` +
    `${snapshot.sale_window.end.slice(5, 16).replace("T", " ")}`;
}

function renderCompare(currentSnapshot, previousSnapshot, diff) {
  currentNewIdSet = new Set(diff.added.map((product) => productKey(product)));
  const compareGrid = document.getElementById("compare-grid");
  compareGrid.innerHTML = "";

  const compareItems = [
    {
      title: "상품 수 변화",
      value:
        diff.countDiff == null
          ? "비교 데이터 없음"
          : `${diff.countDiff > 0 ? "+" : ""}${diff.countDiff}개`,
      tone: diff.countDiff == null ? "neutral" : diff.countDiff >= 0 ? "up" : "down",
    },
    {
      title: "신규 추가",
      value: `${diff.added.length}개`,
      tone: "up",
    },
    {
      title: "사라진 상품",
      value: `${diff.removed.length}개`,
      tone: "down",
    },
  ];

  for (const item of compareItems) {
    const card = document.createElement("article");
    card.className = `summary-card tone-${item.tone}`;
    card.innerHTML = `<p>${item.title}</p><strong>${item.value}</strong>`;
    compareGrid.appendChild(card);
  }

  document.getElementById("compare-note").textContent = previousSnapshot
    ? `비교 기준: ${previousSnapshot.snapshot_date} 대비`
    : "전일 스냅샷이 없어 비교 요약만 제한적으로 표시됩니다.";

  renderDeltaList("added-list", diff.added, "NEW");
  renderDeltaList("removed-list", diff.removed, "REMOVED");
}

function renderDeltaList(targetId, products, type) {
  const list = document.getElementById(targetId);
  list.innerHTML = "";

  if (!products.length) {
    const emptyItem = document.createElement("li");
    emptyItem.textContent = "없음";
    list.appendChild(emptyItem);
    return;
  }

  for (const product of products.slice(0, 8)) {
    const item = document.createElement("li");
    item.innerHTML = `
      <span>${product.name}</span>
      <span class="change-badge ${type === "NEW" ? "badge-new" : "badge-removed"}">${type}</span>
    `;
    list.appendChild(item);
  }
}

function createDealCard(product) {
  const template = document.getElementById("deal-card-template");
  const fragment = template.content.cloneNode(true);

  fragment.querySelector(".card-rank").textContent = `#${product.rank}`;
  fragment.querySelector(".card-label").textContent = product.label;
  fragment.querySelector(".card-title").textContent = product.name;
  fragment.querySelector(".card-price").textContent = formatWon(product.discounted_price);
  fragment.querySelector(".card-discount").textContent = `${product.discounted_ratio ?? 0}% off`;
  fragment.querySelector(".card-reviews").textContent = formatReview(
    product.review_score,
    product.review_count
  );
  fragment.querySelector(".card-sale-price").textContent = formatWon(product.sale_price);

  const link = fragment.querySelector(".card-link");
  link.href = product.landing_url;

  return fragment;
}

function renderDeals(products, query = "") {
  const normalizedQuery = query.trim().toLowerCase();
  const filtered = products.filter((product) =>
    product.name.toLowerCase().includes(normalizedQuery)
  );

  const grid = document.getElementById("deal-grid");
  grid.innerHTML = "";
  for (const product of filtered) {
    const node = createDealCard(product);
    if (currentNewIdSet.has(productKey(product))) {
      const label = node.querySelector(".card-label");
      const newBadge = document.createElement("span");
      newBadge.className = "change-badge badge-new";
      newBadge.textContent = "NEW";
      label.parentElement.appendChild(newBadge);
    }
    grid.appendChild(node);
  }
  document.getElementById("list-meta").textContent = `${filtered.length}개 표시 중`;
}

function setLoading(isLoading) {
  document.getElementById("date-input").disabled = isLoading;
  document.getElementById("today-button").disabled = isLoading;
}

function renderError(message) {
  const grid = document.getElementById("deal-grid");
  grid.innerHTML = `
    <article class="panel error-panel">
      <p class="panel-kicker">Load Error</p>
      <h2>데이터를 불러오지 못했습니다.</h2>
      <p>${message}</p>
    </article>
  `;
}

async function loadDashboard(dateString) {
  const currentToken = ++requestToken;
  setLoading(true);

  try {
    const currentSnapshot = await fetchSnapshot(dateString);
    const previousSnapshot = await fetchSnapshot(getPreviousDateString(dateString), true);

    if (currentToken !== requestToken) return;

    selectedSnapshot = currentSnapshot;
    renderHero(currentSnapshot, dateString);
    renderCompare(currentSnapshot, previousSnapshot, diffProducts(currentSnapshot, previousSnapshot));
    renderDeals(currentSnapshot.products, document.getElementById("search-input").value);
  } catch (error) {
    if (currentToken !== requestToken) return;
    selectedSnapshot = null;
    renderError(error instanceof Error ? error.message : "알 수 없는 오류");
  } finally {
    if (currentToken === requestToken) {
      setLoading(false);
    }
  }
}

function bindEvents() {
  const dateInput = document.getElementById("date-input");
  const searchInput = document.getElementById("search-input");
  const todayButton = document.getElementById("today-button");

  dateInput.addEventListener("change", () => {
    if (!dateInput.value) return;
    loadDashboard(dateInput.value);
  });

  todayButton.addEventListener("click", () => {
    const today = getTodayKstString();
    dateInput.value = today;
    loadDashboard(today);
  });

  searchInput.addEventListener("input", () => {
    if (!selectedSnapshot) return;
    renderDeals(selectedSnapshot.products, searchInput.value);
  });
}

function main() {
  const today = getTodayKstString();
  const dateInput = document.getElementById("date-input");
  dateInput.value = today;
  bindEvents();
  loadDashboard(today);
}

main();
