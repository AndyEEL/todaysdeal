#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = REPO_ROOT / "data"
PRIMARY_DAILY_DIR = "daily"
LEGACY_DAILY_DIR = "naver_special_deals/daily"
ISO_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SAFE_FILENAME_PATTERN = re.compile(r"[^0-9A-Za-z._-]+")
BRACKETED_BRAND_PATTERN = re.compile(r"^\[([^\]]+)\]")
PRODUCT_ID_IN_URL_PATTERN = re.compile(r"/products/(\d+)")

CATEGORY_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("식품/음료", ("김치", "생수", "먹는샘물", "커피", "음료", "빵", "과자", "삼겹", "라면", "닭", "쌀")),
    ("생활/주방", ("핸드워시", "세제", "베개", "커버", "비누", "청소", "물티슈", "키친", "휴지", "타월")),
    ("뷰티/헬스", ("로션", "크림", "영양제", "비타민", "선크림", "마스크팩", "클렌징", "샴푸", "헬스")),
    ("패션", ("원피스", "셔츠", "팬츠", "신발", "가방", "자켓", "하객룩", "의류", "양말")),
    ("디지털/가전", ("노트북", "모니터", "이어폰", "헤드폰", "키보드", "마우스", "충전", "가전", "스피커")),
    ("육아/반려", ("기저귀", "유아", "반려", "강아지", "고양이", "펫")),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build derived analytics JSON from daily snapshots.")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help="Root data directory that contains daily snapshots.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Reduce log output to warnings only.",
    )
    return parser.parse_args()


def configure_logging(quiet: bool) -> None:
    level = logging.WARNING if quiet else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(message)s")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def collapse_whitespace(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def safe_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def to_iso_date(value: str) -> str | None:
    if not ISO_DATE_PATTERN.match(value):
        return None
    try:
        date.fromisoformat(value)
    except ValueError:
        return None
    return value


def collect_daily_snapshot_files(data_dir: Path) -> dict[str, Path]:
    sources = [
        data_dir / PRIMARY_DAILY_DIR,
        data_dir / LEGACY_DAILY_DIR,
    ]
    resolved: dict[str, Path] = {}

    for source in sources:
        if not source.exists():
            continue
        for path in sorted(source.glob("*.json")):
            snapshot_date = to_iso_date(path.stem)
            if not snapshot_date:
                continue
            if snapshot_date not in resolved:
                resolved[snapshot_date] = path.resolve()
    return dict(sorted(resolved.items(), key=lambda item: item[0]))


def slugify_text(value: str, prefix: str) -> str:
    cleaned = collapse_whitespace(value).lower()
    cleaned = re.sub(r"[^0-9a-z]+", "-", cleaned).strip("-")
    if cleaned:
        return cleaned
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]
    return f"{prefix}-{digest}"


def to_safe_filename(value: str, fallback_prefix: str) -> str:
    cleaned = SAFE_FILENAME_PATTERN.sub("_", value).strip("._")
    if cleaned:
        return cleaned
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]
    return f"{fallback_prefix}_{digest}"


def extract_product_id(raw_product: dict[str, Any]) -> str:
    direct_id = collapse_whitespace(str(raw_product.get("product_id") or ""))
    if direct_id:
        return direct_id

    landing_url = collapse_whitespace(raw_product.get("landing_url"))
    if landing_url:
        match = PRODUCT_ID_IN_URL_PATTERN.search(landing_url)
        if match:
            return match.group(1)

    seed = f"{collapse_whitespace(raw_product.get('name'))}|{landing_url}"
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]
    return f"anon_{digest}"


def infer_brand(product_name: str, raw_product: dict[str, Any]) -> str:
    match = BRACKETED_BRAND_PATTERN.match(product_name)
    if match:
        candidate = collapse_whitespace(match.group(1))
        if 1 <= len(candidate) <= 24:
            return candidate

    channel_no = collapse_whitespace(str(raw_product.get("channel_no") or ""))
    if channel_no:
        return f"채널{channel_no}"

    first_token = collapse_whitespace(product_name).split(" ")[0]
    if 1 <= len(first_token) <= 20:
        return first_token
    return "미분류"


def infer_category(product_name: str) -> str:
    lowered = product_name.lower()
    for category, keywords in CATEGORY_RULES:
        for keyword in keywords:
            if keyword.lower() in lowered:
                return category
    return "기타"


def normalize_product(
    raw_product: dict[str, Any],
    snapshot: dict[str, Any],
    snapshot_date: str,
    rank_fallback: int,
    snapshot_file: Path,
) -> dict[str, Any]:
    product_name = collapse_whitespace(raw_product.get("name"))
    product_id = extract_product_id(raw_product)
    image_url = collapse_whitespace(raw_product.get("image_url"))
    original_price = safe_int(raw_product.get("sale_price"))
    sale_price = safe_int(raw_product.get("discounted_price"))
    if sale_price is None:
        sale_price = original_price

    discount_rate = safe_int(raw_product.get("discounted_ratio"))
    if discount_rate is None and original_price and sale_price is not None and original_price > 0:
        discount_rate = max(0, round((1 - sale_price / original_price) * 100))

    deal_type = collapse_whitespace(raw_product.get("label")) or collapse_whitespace(snapshot.get("selected_tab")) or "스페셜딜"

    try:
        snapshot_file_relative = str(snapshot_file.relative_to(REPO_ROOT))
    except ValueError:
        snapshot_file_relative = str(snapshot_file)

    return {
        "snapshot_date": snapshot_date,
        "deal_type": deal_type,
        "product_id": product_id,
        "product_name": product_name,
        "brand": infer_brand(product_name, raw_product),
        "category": infer_category(product_name),
        "original_price": original_price,
        "sale_price": sale_price,
        "discount_rate": discount_rate,
        "product_url": collapse_whitespace(raw_product.get("landing_url")),
        "mobile_product_url": collapse_whitespace(raw_product.get("mobile_landing_url")),
        "image_url": image_url,
        "image_urls": [image_url] if image_url else [],
        "rank_or_position": safe_int(raw_product.get("rank")) or safe_int(raw_product.get("order")) or rank_fallback,
        "review_score": safe_float(raw_product.get("review_score")),
        "review_count": safe_int(raw_product.get("review_count")),
        "raw_snapshot_source": {
            "snapshot_file": snapshot_file_relative,
            "source_url": snapshot.get("source_url"),
            "selected_tab": snapshot.get("selected_tab"),
            "fetched_at": snapshot.get("fetched_at"),
        },
    }


def price_changed(current: dict[str, Any], previous: dict[str, Any]) -> bool:
    tracked_fields = ("original_price", "sale_price", "discount_rate")
    for field in tracked_fields:
        if current.get(field) != previous.get(field):
            return True
    return False


def image_changed(current: dict[str, Any], previous: dict[str, Any]) -> bool:
    return collapse_whitespace(current.get("image_url")) != collapse_whitespace(previous.get("image_url"))


def build_date_products(snapshot_files: dict[str, Path]) -> dict[str, list[dict[str, Any]]]:
    date_products: dict[str, list[dict[str, Any]]] = {}
    for snapshot_date, snapshot_file in snapshot_files.items():
        snapshot = read_json(snapshot_file)
        products = snapshot.get("products", [])
        deduped: dict[str, dict[str, Any]] = {}
        for rank, raw_product in enumerate(products, start=1):
            normalized = normalize_product(raw_product, snapshot, snapshot_date, rank, snapshot_file)
            deduped.setdefault(normalized["product_id"], normalized)
        ordered = sorted(
            deduped.values(),
            key=lambda item: (item.get("rank_or_position") or 10_000, item["product_name"]),
        )
        date_products[snapshot_date] = ordered
    return date_products


def build_daily_diffs(date_products: dict[str, list[dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    dates = sorted(date_products.keys())
    diffs: dict[str, dict[str, Any]] = {}

    for index, snapshot_date in enumerate(dates):
        current_list = date_products[snapshot_date]
        current_map = {item["product_id"]: item for item in current_list}
        previous_date = dates[index - 1] if index > 0 else None
        previous_map = {item["product_id"]: item for item in date_products.get(previous_date, [])} if previous_date else {}

        added_ids = sorted(set(current_map) - set(previous_map))
        removed_ids = sorted(set(previous_map) - set(current_map))
        common_ids = sorted(set(current_map) & set(previous_map))
        changed_ids = [
            product_id
            for product_id in common_ids
            if price_changed(current_map[product_id], previous_map[product_id]) or image_changed(current_map[product_id], previous_map[product_id])
        ]

        diffs[snapshot_date] = {
            "snapshot_date": snapshot_date,
            "previous_date": previous_date,
            "added_ids": added_ids,
            "removed_ids": removed_ids,
            "price_changed_ids": sorted(changed_ids),
            "added_products": [current_map[product_id] for product_id in added_ids],
            "removed_products": [previous_map[product_id] for product_id in removed_ids],
            "price_changed_products": [current_map[product_id] for product_id in changed_ids],
            "product_count": len(current_list),
            "product_count_diff": None if previous_date is None else len(current_list) - len(previous_map),
        }
    return diffs


def tokenize_name(product_name: str) -> set[str]:
    normalized = re.sub(r"[^0-9a-zA-Z가-힣]+", " ", product_name.lower())
    tokens = {token for token in normalized.split() if len(token) >= 2}
    return tokens


def jaccard_similarity(first: set[str], second: set[str]) -> float:
    if not first or not second:
        return 0.0
    union = first | second
    if not union:
        return 0.0
    return len(first & second) / len(union)


def build_replacement_index(daily_diffs: dict[str, dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    replacements: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for diff in daily_diffs.values():
        added = diff["added_products"]
        removed = diff["removed_products"]
        if not added or not removed:
            continue

        for removed_product in removed:
            removed_tokens = tokenize_name(removed_product["product_name"])
            removed_brand = removed_product["brand"]
            best_candidate: dict[str, Any] | None = None
            best_score = 0.0

            for added_product in added:
                if added_product["brand"] != removed_brand:
                    continue
                score = jaccard_similarity(removed_tokens, tokenize_name(added_product["product_name"]))
                if score > best_score:
                    best_score = score
                    best_candidate = added_product

            if best_candidate and best_score >= 0.45:
                replacements[removed_product["product_id"]].append(
                    {
                        "date": diff["snapshot_date"],
                        "replaced_by_product_id": best_candidate["product_id"],
                        "replaced_by_product_name": best_candidate["product_name"],
                        "similarity": round(best_score, 4),
                    }
                )
    return replacements


def date_diff_days(first_date: str, second_date: str) -> int:
    first = date.fromisoformat(first_date)
    second = date.fromisoformat(second_date)
    return (second - first).days


def build_product_outputs(
    date_products: dict[str, list[dict[str, Any]]],
    daily_diffs: dict[str, dict[str, Any]],
    replacements: dict[str, list[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[tuple[str, str], int]]:
    timeline_by_product: dict[str, list[dict[str, Any]]] = defaultdict(list)
    sorted_dates = sorted(date_products.keys())
    latest_date = sorted_dates[-1]
    latest_diff = daily_diffs[latest_date]
    removed_today_ids = set(latest_diff["removed_ids"])

    for snapshot_date in sorted_dates:
        for item in date_products[snapshot_date]:
            timeline_by_product[item["product_id"]].append(item)

    products_summary: list[dict[str, Any]] = []
    products_detail: dict[str, dict[str, Any]] = {}
    active_days_index: dict[tuple[str, str], int] = {}

    for product_id, timeline in timeline_by_product.items():
        timeline = sorted(timeline, key=lambda item: item["snapshot_date"])
        first_item = timeline[0]
        last_item = timeline[-1]
        first_seen = first_item["snapshot_date"]
        last_seen = last_item["snapshot_date"]
        is_active = last_seen == latest_date

        if is_active and first_seen == latest_date:
            current_status = "entering"
        elif is_active and product_id in set(latest_diff["price_changed_ids"]):
            current_status = "price_changed"
        elif is_active:
            current_status = "active"
        else:
            current_status = "exited"

        lifecycle_events: list[dict[str, Any]] = [
            {
                "date": first_seen,
                "type": "entered_deal",
                "summary": "딜에 처음 진입했습니다.",
            }
        ]

        stats = {
            "price_change_count": 0,
            "image_change_count": 0,
            "deal_cycles": 1,
            "post_exit_observed_count": 0,
            "post_exit_reverted_count": 0,
            "post_exit_held_count": 0,
            "replacement_count": 0,
        }

        for index, item in enumerate(timeline):
            active_days_index[(product_id, item["snapshot_date"])] = index + 1
            if index == 0:
                continue

            previous = timeline[index - 1]
            gap_days = date_diff_days(previous["snapshot_date"], item["snapshot_date"])

            if gap_days > 1:
                stats["deal_cycles"] += 1
                lifecycle_events.append(
                    {
                        "date": previous["snapshot_date"],
                        "type": "exited_deal",
                        "summary": f"{gap_days - 1}일 공백 후 이탈로 간주했습니다.",
                    }
                )
                lifecycle_events.append(
                    {
                        "date": item["snapshot_date"],
                        "type": "entered_deal",
                        "summary": "딜에 재진입했습니다.",
                    }
                )

                previous_sale = previous.get("sale_price")
                current_sale = item.get("sale_price")
                if previous_sale is not None and current_sale is not None:
                    stats["post_exit_observed_count"] += 1
                    if current_sale > previous_sale:
                        stats["post_exit_reverted_count"] += 1
                        lifecycle_events.append(
                            {
                                "date": item["snapshot_date"],
                                "type": "price_reverted_after_exit",
                                "summary": "재진입 시 판매가가 이전 대비 상승했습니다.",
                                "from_sale_price": previous_sale,
                                "to_sale_price": current_sale,
                            }
                        )
                    else:
                        stats["post_exit_held_count"] += 1
                        lifecycle_events.append(
                            {
                                "date": item["snapshot_date"],
                                "type": "price_held_after_exit",
                                "summary": "재진입 시 판매가가 이전 수준으로 유지/하락했습니다.",
                                "from_sale_price": previous_sale,
                                "to_sale_price": current_sale,
                            }
                        )
            else:
                lifecycle_events.append(
                    {
                        "date": item["snapshot_date"],
                        "type": "active_in_deal",
                        "summary": "딜 노출이 유지되었습니다.",
                    }
                )

            if price_changed(item, previous):
                stats["price_change_count"] += 1
                lifecycle_events.append(
                    {
                        "date": item["snapshot_date"],
                        "type": "price_changed_in_deal",
                        "summary": "딜 노출 중 가격/할인율이 변경되었습니다.",
                        "from_sale_price": previous.get("sale_price"),
                        "to_sale_price": item.get("sale_price"),
                    }
                )

            if image_changed(item, previous):
                stats["image_change_count"] += 1
                lifecycle_events.append(
                    {
                        "date": item["snapshot_date"],
                        "type": "image_changed",
                        "summary": "상품 대표 이미지가 변경되었습니다.",
                        "from_image_url": previous.get("image_url"),
                        "to_image_url": item.get("image_url"),
                    }
                )

        if not is_active:
            lifecycle_events.append(
                {
                    "date": last_seen,
                    "type": "exited_deal",
                    "summary": "최신 스냅샷 기준 딜에서 이탈했습니다.",
                }
            )

        for replacement in replacements.get(product_id, []):
            stats["replacement_count"] += 1
            lifecycle_events.append(
                {
                    "date": replacement["date"],
                    "type": "replaced_by_other_sku",
                    "summary": "유사 상품으로 SKU 교체 가능성이 감지되었습니다.",
                    "replaced_by_product_id": replacement["replaced_by_product_id"],
                    "replaced_by_product_name": replacement["replaced_by_product_name"],
                    "similarity": replacement["similarity"],
                }
            )

        price_timeline = [
            {
                "date": item["snapshot_date"],
                "original_price": item["original_price"],
                "sale_price": item["sale_price"],
                "discount_rate": item["discount_rate"],
            }
            for item in timeline
        ]
        image_timeline = [
            {
                "date": item["snapshot_date"],
                "image_url": item["image_url"],
            }
            for item in timeline
        ]

        discount_values = [item["discount_rate"] for item in timeline if item.get("discount_rate") is not None]
        average_discount = round(sum(discount_values) / len(discount_values), 2) if discount_values else None
        max_discount = max(discount_values) if discount_values else None

        summary_item = {
            "product_id": product_id,
            "deal_type": last_item["deal_type"],
            "product_name": last_item["product_name"],
            "brand": last_item["brand"],
            "category": last_item["category"],
            "first_seen_date": first_seen,
            "last_seen_date": last_seen,
            "active_days": len(timeline),
            "current_status": current_status,
            "appeared_today": first_seen == latest_date,
            "disappeared_today": product_id in removed_today_ids,
            "latest_sale_price": last_item["sale_price"],
            "latest_original_price": last_item["original_price"],
            "latest_discount_rate": last_item["discount_rate"],
            "latest_image_url": last_item["image_url"],
            "latest_rank": last_item["rank_or_position"],
            "product_url": last_item["product_url"],
            "price_change_count": stats["price_change_count"],
            "image_change_count": stats["image_change_count"],
            "deal_cycles": stats["deal_cycles"],
            "average_discount_rate": average_discount,
            "max_discount_rate": max_discount,
        }

        detail_item = {
            **summary_item,
            "timeline": timeline,
            "price_timeline": price_timeline,
            "image_timeline": image_timeline,
            "lifecycle_events": sorted(
                lifecycle_events,
                key=lambda event: (event["date"], event["type"]),
            ),
            "stats": stats,
        }

        products_summary.append(summary_item)
        products_detail[product_id] = detail_item

    status_priority = {"entering": 0, "price_changed": 1, "active": 2, "exited": 3}
    products_summary.sort(
        key=lambda item: (
            status_priority.get(item["current_status"], 9),
            item.get("latest_rank") or 10_000,
            item["product_name"],
        )
    )
    return products_summary, products_detail, active_days_index


def rolling_window_start(snapshot_date: str, days: int) -> str:
    current = date.fromisoformat(snapshot_date)
    start = current - timedelta(days=days - 1)
    return start.isoformat()


def filter_dates_in_window(all_dates: list[str], end_date: str, days: int) -> list[str]:
    start = rolling_window_start(end_date, days)
    return [value for value in all_dates if start <= value <= end_date]


def strategy_label(avg_active_days: float, avg_discount_rate: float, entered_last_7d: int) -> str:
    if avg_discount_rate >= 40 and avg_active_days <= 3:
        return "고할인 단기 집중형"
    if avg_active_days >= 5:
        return "장기 노출 유지형"
    if entered_last_7d >= 3:
        return "신규 유입 확장형"
    return "균형 운영형"


def build_brand_outputs(
    products_summary: list[dict[str, Any]],
    products_detail: dict[str, dict[str, Any]],
    latest_date: str,
    window_days: int = 7,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in products_summary:
        grouped[item["brand"]].append(item)

    window_start = rolling_window_start(latest_date, window_days)
    brand_details: dict[str, dict[str, Any]] = {}
    brand_summary_items: list[dict[str, Any]] = []

    for brand, items in grouped.items():
        entered_last_window = sum(1 for item in items if item["first_seen_date"] >= window_start)
        exited_last_window = sum(
            1
            for item in items
            if item["current_status"] == "exited" and item["last_seen_date"] >= window_start
        )
        active_products = sum(1 for item in items if item["current_status"] != "exited")
        avg_active_days = round(sum(item["active_days"] for item in items) / len(items), 2)

        discount_values = [item["average_discount_rate"] for item in items if item["average_discount_rate"] is not None]
        avg_discount_rate = round(sum(discount_values) / len(discount_values), 2) if discount_values else 0.0

        post_exit_observed = 0
        post_exit_reverted = 0
        post_exit_held = 0
        for item in items:
            stats = products_detail[item["product_id"]]["stats"]
            post_exit_observed += stats["post_exit_observed_count"]
            post_exit_reverted += stats["post_exit_reverted_count"]
            post_exit_held += stats["post_exit_held_count"]

        reverted_ratio = round(post_exit_reverted / post_exit_observed, 4) if post_exit_observed else None
        held_ratio = round(post_exit_held / post_exit_observed, 4) if post_exit_observed else None

        summary_item = {
            "brand": brand,
            "product_total": len(items),
            "active_products": active_products,
            "entered_last_7d": entered_last_window,
            "exited_last_7d": exited_last_window,
            "avg_active_days": avg_active_days,
            "avg_discount_rate": avg_discount_rate,
            "post_exit_observed_count": post_exit_observed,
            "price_reverted_after_exit_ratio": reverted_ratio,
            "price_held_after_exit_ratio": held_ratio,
            "strategy_pattern": strategy_label(avg_active_days, avg_discount_rate, entered_last_window),
        }
        brand_summary_items.append(summary_item)

        top_products = sorted(
            items,
            key=lambda product: (
                -(product["active_days"] or 0),
                -(product["latest_discount_rate"] or 0),
                product["product_name"],
            ),
        )[:10]

        brand_details[brand] = {
            "brand": brand,
            "snapshot_date": latest_date,
            "window_days": window_days,
            "summary": summary_item,
            "top_products": top_products,
            "products": sorted(
                items,
                key=lambda product: (
                    product["current_status"] == "exited",
                    -(product["active_days"] or 0),
                    product["product_name"],
                ),
            ),
        }

    brand_summary_items.sort(
        key=lambda item: (
            -item["entered_last_7d"],
            -item["active_products"],
            item["brand"],
        )
    )
    return {
        "snapshot_date": latest_date,
        "window_days": window_days,
        "total_brands": len(brand_summary_items),
        "items": brand_summary_items,
    }, brand_details


def build_daily_insights(
    dates: list[str],
    date_products: dict[str, list[dict[str, Any]]],
    daily_diffs: dict[str, dict[str, Any]],
    active_days_index: dict[tuple[str, str], int],
    products_detail: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    insights_by_date: dict[str, dict[str, Any]] = {}

    for snapshot_date in dates:
        diff = daily_diffs[snapshot_date]
        current_products = date_products[snapshot_date]
        added_ids = set(diff["added_ids"])
        changed_ids = set(diff["price_changed_ids"])

        status_products: list[dict[str, Any]] = []
        for product in current_products:
            product_id = product["product_id"]
            if product_id in added_ids:
                status = "entering"
            elif product_id in changed_ids:
                status = "price_changed"
            else:
                status = "active"

            status_products.append(
                {
                    **product,
                    "status": status,
                    "appeared_today": product_id in added_ids,
                    "price_changed_today": product_id in changed_ids,
                    "active_days": active_days_index.get((product_id, snapshot_date), 1),
                }
            )

        removed_products = [{**item, "status": "removed"} for item in diff["removed_products"]]

        entering_brand_counts = Counter(item["brand"] for item in diff["added_products"])
        exiting_brand_counts = Counter(item["brand"] for item in diff["removed_products"])

        reverted_events = 0
        held_events = 0
        for detail in products_detail.values():
            for event in detail["lifecycle_events"]:
                if event["date"] > snapshot_date:
                    continue
                if event["type"] == "price_reverted_after_exit":
                    reverted_events += 1
                if event["type"] == "price_held_after_exit":
                    held_events += 1
        observed_events = reverted_events + held_events

        status_counts = {
            "entering": len(diff["added_ids"]),
            "price_changed": len(diff["price_changed_ids"]),
            "active": max(
                0,
                len(current_products) - len(diff["added_ids"]) - len(diff["price_changed_ids"]),
            ),
            "exited": len(diff["removed_ids"]),
        }

        insights_by_date[snapshot_date] = {
            "snapshot_date": snapshot_date,
            "previous_date": diff["previous_date"],
            "product_count": diff["product_count"],
            "product_count_diff": diff["product_count_diff"],
            "new_count": len(diff["added_ids"]),
            "removed_count": len(diff["removed_ids"]),
            "price_changed_count": len(diff["price_changed_ids"]),
            "status_counts": status_counts,
            "top_entering_brand": entering_brand_counts.most_common(1)[0] if entering_brand_counts else None,
            "top_exiting_brand": exiting_brand_counts.most_common(1)[0] if exiting_brand_counts else None,
            "price_reverted_after_exit_ratio": round(reverted_events / observed_events, 4) if observed_events else None,
            "price_held_after_exit_ratio": round(held_events / observed_events, 4) if observed_events else None,
            "new_products": diff["added_products"],
            "removed_products": removed_products,
            "price_changed_products": diff["price_changed_products"],
            "products": status_products,
        }
    return insights_by_date


def clear_json_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    for json_file in path.glob("*.json"):
        json_file.unlink()


def unique_brand_slugs(brands: list[str]) -> dict[str, str]:
    used_slugs: set[str] = set()
    mapping: dict[str, str] = {}
    for brand in sorted(brands):
        base = slugify_text(brand, "brand")
        slug = base
        suffix = 2
        while slug in used_slugs:
            slug = f"{base}-{suffix}"
            suffix += 1
        used_slugs.add(slug)
        mapping[brand] = slug
    return mapping


def write_outputs(
    data_dir: Path,
    dates: list[str],
    date_products: dict[str, list[dict[str, Any]]],
    daily_diffs: dict[str, dict[str, Any]],
    products_summary: list[dict[str, Any]],
    products_detail: dict[str, dict[str, Any]],
    brands_summary: dict[str, Any],
    brand_details: dict[str, dict[str, Any]],
    insights_by_date: dict[str, dict[str, Any]],
) -> None:
    latest_date = dates[-1]
    generated_at = datetime.now().isoformat()

    products_dir = data_dir / "products"
    derived_dir = data_dir / "derived"
    insights_dir = derived_dir / "daily-insights"
    brands_dir = derived_dir / "brands"

    clear_json_dir(products_dir)
    clear_json_dir(insights_dir)
    clear_json_dir(brands_dir)

    products_index: dict[str, str] = {}
    for product_id, payload in products_detail.items():
        filename = f"{to_safe_filename(product_id, 'product')}.json"
        products_index[product_id] = filename
        write_json(products_dir / filename, payload)

    write_json(
        derived_dir / "products-summary.json",
        {
            "generated_at": generated_at,
            "snapshot_date": latest_date,
            "total_count": len(products_summary),
            "active_count": sum(1 for item in products_summary if item["current_status"] != "exited"),
            "items": products_summary,
        },
    )

    write_json(
        derived_dir / "products-index.json",
        {
            "generated_at": generated_at,
            "snapshot_date": latest_date,
            "items": [{"product_id": product_id, "file_name": file_name} for product_id, file_name in sorted(products_index.items())],
        },
    )

    write_json(
        derived_dir / "brands-summary.json",
        {
            "generated_at": generated_at,
            **brands_summary,
        },
    )

    brand_slugs = unique_brand_slugs(list(brand_details.keys()))
    brand_index_payload: list[dict[str, str]] = []
    for brand, payload in brand_details.items():
        slug = brand_slugs[brand]
        write_json(brands_dir / f"{slug}.json", {**payload, "slug": slug})
        brand_index_payload.append({"brand": brand, "slug": slug})

    write_json(
        derived_dir / "brands-index.json",
        {
            "generated_at": generated_at,
            "snapshot_date": latest_date,
            "items": sorted(brand_index_payload, key=lambda item: item["brand"]),
        },
    )

    for snapshot_date in dates:
        payload = {
            "generated_at": generated_at,
            **insights_by_date[snapshot_date],
        }
        write_json(insights_dir / f"{snapshot_date}.json", payload)

    write_json(insights_dir / "latest.json", {"generated_at": generated_at, **insights_by_date[latest_date]})

    write_json(
        derived_dir / "dates.json",
        {
            "generated_at": generated_at,
            "latest_date": latest_date,
            "dates": dates,
        },
    )

    write_json(
        derived_dir / "lifecycle-summary.json",
        {
            "generated_at": generated_at,
            "snapshot_date": latest_date,
            "status_counts": dict(
                Counter(item["current_status"] for item in products_summary)
            ),
            "total_products_observed": len(products_summary),
            "total_daily_snapshots": len(dates),
            "last_daily_diff": {
                "snapshot_date": latest_date,
                "new_count": len(daily_diffs[latest_date]["added_ids"]),
                "removed_count": len(daily_diffs[latest_date]["removed_ids"]),
                "price_changed_count": len(daily_diffs[latest_date]["price_changed_ids"]),
            },
            "categories": dict(Counter(item["category"] for item in date_products[latest_date])),
        },
    )


def main() -> int:
    args = parse_args()
    configure_logging(args.quiet)

    snapshot_files = collect_daily_snapshot_files(args.data_dir)
    if not snapshot_files:
        logging.error("No daily snapshots found under %s", args.data_dir)
        return 1

    dates = sorted(snapshot_files.keys())
    latest_date = dates[-1]
    logging.info("Found %s daily snapshots. Latest date: %s", len(dates), latest_date)

    try:
        date_products = build_date_products(snapshot_files)
        daily_diffs = build_daily_diffs(date_products)
        replacements = build_replacement_index(daily_diffs)
        products_summary, products_detail, active_days_index = build_product_outputs(
            date_products=date_products,
            daily_diffs=daily_diffs,
            replacements=replacements,
        )
        brands_summary, brand_details = build_brand_outputs(
            products_summary=products_summary,
            products_detail=products_detail,
            latest_date=latest_date,
            window_days=7,
        )
        insights_by_date = build_daily_insights(
            dates=dates,
            date_products=date_products,
            daily_diffs=daily_diffs,
            active_days_index=active_days_index,
            products_detail=products_detail,
        )
        write_outputs(
            data_dir=args.data_dir,
            dates=dates,
            date_products=date_products,
            daily_diffs=daily_diffs,
            products_summary=products_summary,
            products_detail=products_detail,
            brands_summary=brands_summary,
            brand_details=brand_details,
            insights_by_date=insights_by_date,
        )
        logging.info("Derived data build complete. Products tracked: %s", len(products_summary))
        return 0
    except (KeyError, ValueError, json.JSONDecodeError) as exc:
        logging.error("Failed to build derived data: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
