from __future__ import annotations

from http.server import BaseHTTPRequestHandler

from api.shared import DATA_DIR, parse_query, resolve_first_existing, send_json, send_json_file, validate_date

DERIVED_DIR = DATA_DIR / "derived"
DAILY_INSIGHTS_DIR = DERIVED_DIR / "daily-insights"


def resolve_daily_insight_path(selected_date: str | None):
    if selected_date:
        return resolve_first_existing(
            [
                DAILY_INSIGHTS_DIR / f"{selected_date}.json",
            ]
        )

    return resolve_first_existing(
        [
            DAILY_INSIGHTS_DIR / "latest.json",
        ]
    )


class handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # pragma: no cover - Vercel runtime path
        self._handle(send_body=True)

    def do_HEAD(self) -> None:  # pragma: no cover - Vercel runtime path
        self._handle(send_body=False)

    def _handle(self, send_body: bool) -> None:
        query = parse_query(self.path)
        selected_date = query.get("date")

        if selected_date and not validate_date(selected_date):
            send_json(self, 400, {"error": "Invalid date format. Use YYYY-MM-DD."}, send_body)
            return

        payload_path = resolve_daily_insight_path(selected_date)
        if payload_path is None:
            send_json(self, 404, {"error": "Daily insight file not found."}, send_body)
            return

        send_json_file(self, payload_path, send_body)
