const DATA_URL = "./data/naver_special_deals/latest.json";
const numberFormatter = new Intl.NumberFormat("ko-KR");
const dateFormatter = new Intl.DateTimeFormat("ko-KR", {
  timeZone: "Asia/Seoul",
  month: "long",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

async function loadDeals() {
  const response = await fetch(DATA_URL, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to load data: ${response.status}`);
  }
  return response.json();
}

function formatWon(value) {
  if (value == null) return "-";
  return `${numberFormatter.format(value)}원`;
}

function formatReview(score, count) {
  if (!count) return "리뷰 없음";
  return `${score ?? "-"} / ${numberFormatter.format(count)}개`;
}

function buildSummaries(products) {
  const discounts = products
    .map((product) => product.discounted_ratio ?? 0)
    .filter((value) => typeof value === "number");
  const prices = products
    .map((product) => product.discounted_price ?? 0)
    .filter((value) => typeof value === "number");

  return [
    {
      label: "최대 할인",
      value: `${Math.max(...discounts, 0)}%`,
      tone: "warm",
    },
    {
      label: "최저가",
      value: formatWon(Math.min(...prices)),
      tone: "mint",
    },
    {
      label: "10%+ 할인 상품",
      value: `${products.filter((product) => (product.discounted_ratio ?? 0) >= 10).length}개`,
      tone: "ink",
    },
  ];
}

function renderSummaryGrid(products) {
  const container = document.getElementById("summary-grid");
  container.innerHTML = "";

  for (const summary of buildSummaries(products)) {
    const article = document.createElement("article");
    article.className = `summary-card tone-${summary.tone}`;
    article.innerHTML = `
      <p>${summary.label}</p>
      <strong>${summary.value}</strong>
    `;
    container.appendChild(article);
  }
}

function renderHero(snapshot) {
  document.getElementById("stat-updated").textContent = dateFormatter.format(
    new Date(snapshot.fetched_at)
  );
  document.getElementById("stat-count").textContent = `${snapshot.product_count}개`;
  document.getElementById("stat-window").textContent =
    `${snapshot.sale_window.start.slice(5, 16).replace("T", " ")} ~ ` +
    `${snapshot.sale_window.end.slice(5, 16).replace("T", " ")}`;
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
    grid.appendChild(createDealCard(product));
  }

  document.getElementById("list-meta").textContent = `${filtered.length}개 표시 중`;
}

async function main() {
  try {
    const snapshot = await loadDeals();
    renderHero(snapshot);
    renderSummaryGrid(snapshot.products);
    renderDeals(snapshot.products);

    const input = document.getElementById("search-input");
    input.addEventListener("input", () => {
      renderDeals(snapshot.products, input.value);
    });
  } catch (error) {
    const grid = document.getElementById("deal-grid");
    grid.innerHTML = `
      <article class="panel error-panel">
        <p class="panel-kicker">Load Error</p>
        <h2>데이터를 불러오지 못했습니다.</h2>
        <p>${error instanceof Error ? error.message : "알 수 없는 오류"}</p>
      </article>
    `;
  }
}

main();
