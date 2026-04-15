from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler

from api.shared import DATA_DIR, parse_query, send_json

DERIVED_DIR = DATA_DIR / "derived"
PRODUCTS_SUMMARY_PATH = DERIVED_DIR / "products-summary.json"


def to_int(value: str | None, default: int, minimum: int, maximum: int) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return max(minimum, min(maximum, parsed))


def apply_filters(items: list[dict], query: dict[str, str]) -> list[dict]:
    status = query.get("status", "all").lower()
    brand = query.get("brand", "").strip().lower()
    category = query.get("category", "").strip().lower()
    keyword = query.get("q", "").strip().lower()

    filtered = items
    if status and status != "all":
        filtered = [item for item in filtered if item.get("current_status", "").lower() == status]
    if brand:
        filtered = [item for item in filtered if str(item.get("brand", "")).lower() == brand]
    if category:
        filtered = [item for item in filtered if str(item.get("category", "")).lower() == category]
    if keyword:
        filtered = [
            item
            for item in filtered
            if keyword in str(item.get("product_name", "")).lower()
            or keyword in str(item.get("brand", "")).lower()
        ]
    return filtered


def apply_sorting(items: list[dict], sort_key: str) -> list[dict]:
    if sort_key == "active_days":
        return sorted(items, key=lambda item: (-(item.get("active_days") or 0), item.get("product_name", "")))
    if sort_key == "price_changes":
        return sorted(items, key=lambda item: (-(item.get("price_change_count") or 0), item.get("product_name", "")))
    if sort_key == "discount":
        return sorted(items, key=lambda item: (-(item.get("latest_discount_rate") or 0), item.get("product_name", "")))
    if sort_key == "latest_seen":
        return sorted(
            items,
            key=lambda item: (item.get("last_seen_date", ""), -(item.get("latest_rank") or 10_000)),
            reverse=True,
        )

    return sorted(items, key=lambda item: ((item.get("latest_rank") or 10_000), item.get("product_name", "")))


class handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # pragma: no cover - Vercel runtime path
        self._handle(send_body=True)

    def do_HEAD(self) -> None:  # pragma: no cover - Vercel runtime path
        self._handle(send_body=False)

    def _handle(self, send_body: bool) -> None:
        if not PRODUCTS_SUMMARY_PATH.exists():
            send_json(self, 404, {"error": "Products summary file not found."}, send_body)
            return

        query = parse_query(self.path)
        payload = json.loads(PRODUCTS_SUMMARY_PATH.read_text(encoding="utf-8"))
        items = payload.get("items", [])

        filtered = apply_filters(items, query)
        sort_key = query.get("sort", "rank")
        ordered = apply_sorting(filtered, sort_key)
        limit = to_int(query.get("limit"), default=200, minimum=1, maximum=1000)
        selected = ordered[:limit]

        response_payload = {
            "generated_at": payload.get("generated_at"),
            "snapshot_date": payload.get("snapshot_date"),
            "total_count": payload.get("total_count", len(items)),
            "filtered_count": len(filtered),
            "returned_count": len(selected),
            "items": selected,
        }
        send_json(self, 200, response_payload, send_body)
