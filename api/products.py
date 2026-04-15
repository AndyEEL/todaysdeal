from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from api.shared import DATA_DIR, parse_query, resolve_first_existing, send_json, send_json_file

DERIVED_DIR = DATA_DIR / "derived"
PRODUCTS_INDEX_PATH = DERIVED_DIR / "products-index.json"
PRODUCTS_DIR = DATA_DIR / "products"


def resolve_product_path(product_id: str) -> tuple[Path | None, str | None]:
    if not PRODUCTS_INDEX_PATH.exists():
        return None, "Products index file not found."

    payload = json.loads(PRODUCTS_INDEX_PATH.read_text(encoding="utf-8"))
    items = payload.get("items", [])
    mapping = {item.get("product_id"): item.get("file_name") for item in items}
    filename = mapping.get(product_id)
    if not filename:
        return None, "Product timeline not found."

    resolved = resolve_first_existing([PRODUCTS_DIR / filename])
    if resolved is None:
        return None, "Product timeline file missing."
    return resolved, None


class handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # pragma: no cover - Vercel runtime path
        self._handle(send_body=True)

    def do_HEAD(self) -> None:  # pragma: no cover - Vercel runtime path
        self._handle(send_body=False)

    def _handle(self, send_body: bool) -> None:
        query = parse_query(self.path)
        product_id = query.get("productId") or query.get("id")
        if not product_id:
            send_json(
                self,
                400,
                {"error": "productId query parameter is required. Example: /api/products?productId=123"},
                send_body,
            )
            return

        resolved_path, error = resolve_product_path(product_id)
        if error:
            status_code = 404 if "not found" in error.lower() or "missing" in error.lower() else 500
            send_json(self, status_code, {"error": error}, send_body)
            return

        send_json_file(self, resolved_path, send_body)
