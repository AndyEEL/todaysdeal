from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from api.shared import DATA_DIR, normalize_name_token, parse_query, send_json, send_json_file, slugify_name

DERIVED_DIR = DATA_DIR / "derived"
BRANDS_INDEX_PATH = DERIVED_DIR / "brands-index.json"
BRANDS_DIR = DERIVED_DIR / "brands"


def resolve_brand_slug(brand_query: str) -> tuple[str | None, str | None]:
    if not BRANDS_INDEX_PATH.exists():
        return None, "Brands index file not found."

    payload = json.loads(BRANDS_INDEX_PATH.read_text(encoding="utf-8"))
    items = payload.get("items", [])

    normalized = normalize_name_token(brand_query)
    slug_guess = slugify_name(brand_query, prefix="brand")

    for item in items:
        if item.get("slug") == brand_query:
            return item.get("slug"), None
        if normalize_name_token(str(item.get("brand", ""))) == normalized:
            return item.get("slug"), None
        if item.get("slug") == slug_guess:
            return item.get("slug"), None

    return None, "Brand detail not found."


def resolve_brand_path(brand_query: str) -> tuple[Path | None, str | None]:
    slug, error = resolve_brand_slug(brand_query)
    if error:
        return None, error
    target = BRANDS_DIR / f"{slug}.json"
    if not target.exists():
        return None, "Brand detail file missing."
    return target, None


class handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # pragma: no cover - Vercel runtime path
        self._handle(send_body=True)

    def do_HEAD(self) -> None:  # pragma: no cover - Vercel runtime path
        self._handle(send_body=False)

    def _handle(self, send_body: bool) -> None:
        query = parse_query(self.path)
        brand = query.get("brand")
        if not brand:
            send_json(
                self,
                400,
                {"error": "brand query parameter is required. Example: /api/brands?brand=네스프레소"},
                send_body,
            )
            return

        resolved_path, error = resolve_brand_path(brand)
        if error:
            status_code = 404 if "not found" in error.lower() or "missing" in error.lower() else 500
            send_json(self, status_code, {"error": error}, send_body)
            return

        send_json_file(self, resolved_path, send_body)
