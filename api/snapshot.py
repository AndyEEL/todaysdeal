from __future__ import annotations

import re
from datetime import date
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
REPO_ROOT = Path(__file__).resolve().parents[1]
PRIMARY_DATA_DIR = REPO_ROOT / "data"
LEGACY_DATA_DIR = REPO_ROOT / "data" / "naver_special_deals"


def resolve_snapshot_path(selected_date: str | None) -> Path | None:
    if selected_date:
        filename = f"{selected_date}.json"
        candidates = [
            PRIMARY_DATA_DIR / "daily" / filename,
            LEGACY_DATA_DIR / "daily" / filename,
        ]
    else:
        candidates = [
            PRIMARY_DATA_DIR / "latest.json",
            LEGACY_DATA_DIR / "latest.json",
        ]

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def validate_date(value: str) -> bool:
    if not DATE_PATTERN.match(value):
        return False
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False


class handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # pragma: no cover - Vercel runtime path
        self._handle(send_body=True)

    def do_HEAD(self) -> None:  # pragma: no cover - Vercel runtime path
        self._handle(send_body=False)

    def _handle(self, send_body: bool) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        selected_date = query.get("date", [None])[0]

        if selected_date and not validate_date(selected_date):
            payload = b'{"error":"Invalid date format. Use YYYY-MM-DD."}'
            self.send_response(400)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store, max-age=0")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            if send_body:
                self.wfile.write(payload)
            return

        snapshot_path = resolve_snapshot_path(selected_date)
        if snapshot_path is None:
            payload = b'{"error":"Snapshot file not found."}'
            self.send_response(404)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store, max-age=0")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            if send_body:
                self.wfile.write(payload)
            return

        payload = snapshot_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if send_body:
            self.wfile.write(payload)
