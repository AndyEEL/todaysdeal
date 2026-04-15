from __future__ import annotations

from http.server import BaseHTTPRequestHandler

from api.shared import DATA_DIR, send_json, send_json_file

DATES_PATH = DATA_DIR / "derived" / "dates.json"


class handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # pragma: no cover - Vercel runtime path
        self._handle(send_body=True)

    def do_HEAD(self) -> None:  # pragma: no cover - Vercel runtime path
        self._handle(send_body=False)

    def _handle(self, send_body: bool) -> None:
        if not DATES_PATH.exists():
            send_json(self, 404, {"error": "Derived dates file not found."}, send_body)
            return
        send_json_file(self, DATES_PATH, send_body)
