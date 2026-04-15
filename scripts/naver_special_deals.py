#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

SOURCE_URL = "https://shopping.naver.com/promotion"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/135.0.0.0 Safari/537.36"
)
NEXT_DATA_PATTERN = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
    re.DOTALL,
)
SEOUL = ZoneInfo("Asia/Seoul")
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "naver_special_deals"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Crawl Naver Shopping promotion special deals and save JSON snapshots."
    )
    parser.add_argument("--source-url", default=SOURCE_URL, help="Promotion URL to crawl.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory where daily/history JSON files will be written.",
    )
    parser.add_argument(
        "--html-file",
        type=Path,
        help="Read HTML from a local file instead of fetching the live page.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Network timeout in seconds when fetching the live page.",
    )
    parser.add_argument(
        "--skip-history",
        action="store_true",
        help="Only update the daily/latest JSON files.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Reduce log output to warnings and errors only.",
    )
    return parser.parse_args()


def configure_logging(quiet: bool) -> None:
    level = logging.WARNING if quiet else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(message)s")


def fetch_html(url: str, timeout: float) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def load_next_data(html: str) -> dict[str, Any]:
    match = NEXT_DATA_PATTERN.search(html)
    if not match:
        raise ValueError("Could not find __NEXT_DATA__ in the response HTML.")
    return json.loads(match.group(1))


def collapse_whitespace(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def normalize_label(value: str | None) -> str:
    return re.sub(r"\s+", "", value or "")


def get_available_tabs(page_props: dict[str, Any]) -> list[str]:
    queries = page_props.get("dehydratedState", {}).get("queries", [])
    for query in queries:
        query_key = query.get("queryKey", [])
        if query_key and query_key[0] == "getPromotionTabList":
            data = query.get("state", {}).get("data", [])
            return [collapse_whitespace(item.get("title")) for item in data if item.get("title")]
    return []


def extract_special_deals(next_data: dict[str, Any], source_url: str) -> dict[str, Any]:
    page_props = next_data["props"]["pageProps"]
    waffle_data = page_props["waffleData"]
    page_data = waffle_data["pageData"]
    page_meta = waffle_data["pageLayout"]["meta"]
    selected_tab = page_props.get("selectedTab", {})

    if collapse_whitespace(selected_tab.get("title")) != "스페셜딜":
        logging.warning(
            "Selected tab is %r instead of '스페셜딜'. Continuing with label-based filtering.",
            selected_tab.get("title"),
        )

    products: list[dict[str, Any]] = []
    sale_starts: set[str] = set()
    sale_ends: set[str] = set()
    seen_keys: set[str] = set()

    for layer in page_data.get("layers", []):
        for block in layer.get("blocks", []):
            for item in block.get("items", []):
                item_start = item.get("startDate")
                item_end = item.get("endDate")
                for content in item.get("contents", []):
                    if not isinstance(content, dict):
                        continue

                    name = collapse_whitespace(content.get("name"))
                    if not name:
                        continue

                    label = collapse_whitespace(content.get("labelText"))
                    if not normalize_label(label).startswith("스페셜"):
                        continue

                    unique_key = (
                        str(content.get("productId") or "")
                        or collapse_whitespace(content.get("landingUrl"))
                        or name
                    )
                    if unique_key in seen_keys:
                        continue
                    seen_keys.add(unique_key)

                    if item_start:
                        sale_starts.add(item_start)
                    if item_end:
                        sale_ends.add(item_end)

                    products.append(
                        {
                            "product_id": content.get("productId"),
                            "name": name,
                            "label": label,
                            "sale_price": content.get("salePrice"),
                            "discounted_price": content.get("discountedPrice"),
                            "discounted_ratio": content.get("discountedRatio"),
                            "review_score": content.get("averageReviewScore"),
                            "review_count": content.get("totalReviewCount"),
                            "sale_end_date": content.get("saleEndDate"),
                            "landing_url": content.get("landingUrl"),
                            "mobile_landing_url": content.get("mobileLandingUrl"),
                            "image_url": content.get("imageUrl"),
                            "channel_no": content.get("channelNo"),
                            "order": content.get("order"),
                        }
                    )

    if not products:
        raise ValueError("No special deal products were found. The page structure may have changed.")

    for rank, product in enumerate(products, start=1):
        product["rank"] = rank

    fetched_at = datetime.now(tz=SEOUL)
    snapshot_date = fetched_at.date().isoformat()

    return {
        "snapshot_date": snapshot_date,
        "fetched_at": fetched_at.isoformat(),
        "source_url": source_url,
        "page": next_data.get("page"),
        "page_query": next_data.get("query"),
        "page_meta": {
            "title": page_meta.get("title"),
            "description": page_meta.get("description"),
            "type": page_meta.get("type"),
            "start_date": page_meta.get("startDate"),
            "end_date": page_meta.get("endDate"),
        },
        "selected_tab": collapse_whitespace(selected_tab.get("title")),
        "available_tabs": get_available_tabs(page_props),
        "sale_window": {
            "start": min(sale_starts) if sale_starts else page_data.get("startDate"),
            "end": max(sale_ends) if sale_ends else page_data.get("endDate"),
        },
        "product_count": len(products),
        "products": products,
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def save_snapshot(snapshot: dict[str, Any], output_dir: Path, keep_history: bool) -> tuple[Path, Path, Path | None]:
    snapshot_date = snapshot["snapshot_date"]
    fetched_at = datetime.fromisoformat(snapshot["fetched_at"])

    daily_path = output_dir / "daily" / f"{snapshot_date}.json"
    latest_path = output_dir / "latest.json"
    history_path = (
        output_dir
        / "history"
        / snapshot_date
        / f"{fetched_at.strftime('%H%M%S')}.json"
    )

    write_json(daily_path, snapshot)
    write_json(latest_path, snapshot)

    if keep_history:
        write_json(history_path, snapshot)
        return daily_path, latest_path, history_path

    return daily_path, latest_path, None


def main() -> int:
    args = parse_args()
    configure_logging(args.quiet)

    try:
        if args.html_file:
            logging.info("Loading HTML from %s", args.html_file)
            html = args.html_file.read_text(encoding="utf-8")
        else:
            logging.info("Fetching %s", args.source_url)
            html = fetch_html(args.source_url, args.timeout)

        next_data = load_next_data(html)
        snapshot = extract_special_deals(next_data, args.source_url)
        daily_path, latest_path, history_path = save_snapshot(
            snapshot=snapshot,
            output_dir=args.output_dir,
            keep_history=not args.skip_history,
        )

        logging.info(
            "Saved %s products to %s",
            snapshot["product_count"],
            daily_path,
        )
        logging.info("Updated latest snapshot at %s", latest_path)
        if history_path:
            logging.info("Saved history snapshot at %s", history_path)
        return 0
    except FileNotFoundError as exc:
        logging.error("Input HTML file not found: %s", exc)
    except (HTTPError, URLError) as exc:
        logging.error("Failed to fetch live page: %s", exc)
    except (KeyError, ValueError, json.JSONDecodeError) as exc:
        logging.error("Failed to parse promotion page: %s", exc)

    return 1


if __name__ == "__main__":
    sys.exit(main())
