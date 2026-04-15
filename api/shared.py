from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"


def parse_query(path: str) -> dict[str, str]:
    parsed = urlparse(path)
    raw_query = parse_qs(parsed.query)
    return {key: values[0] for key, values in raw_query.items() if values}


def validate_date(value: str) -> bool:
    if not DATE_PATTERN.match(value):
        return False
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False


def send_bytes(
    handler: BaseHTTPRequestHandler,
    status_code: int,
    payload: bytes,
    send_body: bool,
    content_type: str = "application/json; charset=utf-8",
    cache_control: str = "no-store, max-age=0",
) -> None:
    handler.send_response(status_code)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Cache-Control", cache_control)
    handler.send_header("Content-Length", str(len(payload)))
    handler.end_headers()
    if send_body:
        handler.wfile.write(payload)


def send_json(
    handler: BaseHTTPRequestHandler,
    status_code: int,
    payload: dict[str, object],
    send_body: bool,
) -> None:
    encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    send_bytes(handler, status_code, encoded, send_body)


def send_json_file(
    handler: BaseHTTPRequestHandler,
    path: Path,
    send_body: bool,
    cache_control: str = "no-store, max-age=0",
) -> None:
    payload = path.read_bytes()
    send_bytes(
        handler=handler,
        status_code=200,
        payload=payload,
        send_body=send_body,
        cache_control=cache_control,
    )


def resolve_first_existing(candidates: list[Path]) -> Path | None:
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def normalize_name_token(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


def slugify_name(value: str, prefix: str = "item") -> str:
    reduced = normalize_name_token(value)
    reduced = re.sub(r"[^0-9a-z]+", "-", reduced).strip("-")
    if reduced:
        return reduced
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]
    return f"{prefix}-{digest}"
