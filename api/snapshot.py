from http.server import BaseHTTPRequestHandler
import json

from scripts.naver_special_deals import SOURCE_URL, extract_special_deals, fetch_candidate_html, load_next_data


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            html, resolved_source_url = fetch_candidate_html(SOURCE_URL, 30.0)
            next_data = load_next_data(html)
            snapshot = extract_special_deals(next_data, resolved_source_url)
            payload = json.dumps(snapshot, ensure_ascii=False).encode("utf-8")

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store, max-age=0")
            self.end_headers()
            self.wfile.write(payload)
        except Exception as exc:  # pragma: no cover - Vercel runtime path
            payload = json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store, max-age=0")
            self.end_headers()
            self.wfile.write(payload)
