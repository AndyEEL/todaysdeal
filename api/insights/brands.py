from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler

from api.shared import DATA_DIR, parse_query, send_json

DERIVED_DIR = DATA_DIR / "derived"
BRANDS_SUMMARY_PATH = DERIVED_DIR / "brands-summary.json"


def to_int(value: str | None, default: int, minimum: int, maximum: int) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return max(minimum, min(maximum, parsed))


def apply_filters(items: list[dict], query: dict[str, str]) -> list[dict]:
    keyword = query.get("q", "").strip().lower()
    if not keyword:
        return items
    return [item for item in items if keyword in str(item.get("brand", "")).lower()]


def apply_sorting(items: list[dict], sort_key: str) -> list[dict]:
    if sort_key == "exited_7d":
        return sorted(items, key=lambda item: (-(item.get("exited_last_7d") or 0), item.get("brand", "")))
    if sort_key == "avg_active_days":
        return sorted(items, key=lambda item: (-(item.get("avg_active_days") or 0), item.get("brand", "")))
    if sort_key == "avg_discount":
        return sorted(items, key=lambda item: (-(item.get("avg_discount_rate") or 0), item.get("brand", "")))
    return sorted(items, key=lambda item: (-(item.get("entered_last_7d") or 0), item.get("brand", "")))


class handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # pragma: no cover - Vercel runtime path
        self._handle(send_body=True)

    def do_HEAD(self) -> None:  # pragma: no cover - Vercel runtime path
        self._handle(send_body=False)

    def _handle(self, send_body: bool) -> None:
        if not BRANDS_SUMMARY_PATH.exists():
            send_json(self, 404, {"error": "Brands summary file not found."}, send_body)
            return

        query = parse_query(self.path)
        payload = json.loads(BRANDS_SUMMARY_PATH.read_text(encoding="utf-8"))
        items = payload.get("items", [])

        filtered = apply_filters(items, query)
        ordered = apply_sorting(filtered, query.get("sort", "entered_7d"))
        limit = to_int(query.get("limit"), default=200, minimum=1, maximum=1000)
        selected = ordered[:limit]

        response_payload = {
            "generated_at": payload.get("generated_at"),
            "snapshot_date": payload.get("snapshot_date"),
            "window_days": payload.get("window_days"),
            "total_brands": payload.get("total_brands", len(items)),
            "filtered_count": len(filtered),
            "returned_count": len(selected),
            "items": selected,
        }
        send_json(self, 200, response_payload, send_body)
