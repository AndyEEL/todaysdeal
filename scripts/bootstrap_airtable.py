#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from sync_airtable import AIRTABLE_SCHEMA, Config, resolve_config

AIRTABLE_META_ROOT = "https://api.airtable.com/v0/meta"
REQUEST_INTERVAL_SECONDS = 0.25
DEFAULT_ENV_PATH = Path(__file__).resolve().parents[1] / ".env"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap today'sdeal Airtable tables.")
    parser.add_argument(
        "--env-file",
        type=Path,
        default=DEFAULT_ENV_PATH,
        help="Optional .env path for Airtable credentials/config.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show which tables would be created without writing to Airtable.",
    )
    return parser.parse_args()


class AirtableMetaClient:
    def __init__(self, config: Config) -> None:
        if not config.api_key or not config.base_id:
            raise ValueError("AIRTABLE_API_KEY(or AIRTABLE_PAT) and AIRTABLE_BASE_ID are required.")
        self.api_key = config.api_key
        self.base_id = config.base_id

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{AIRTABLE_META_ROOT}/{path.lstrip('/')}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        request = Request(url=url, headers=headers, data=data, method=method)
        try:
            with urlopen(request, timeout=60) as response:
                body = response.read().decode("utf-8")
        except HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Airtable metadata API error ({exc.code}) {error_body}") from exc
        except URLError as exc:
            raise RuntimeError(f"Airtable metadata API network error: {exc}") from exc

        return json.loads(body) if body else {}

    def list_tables(self) -> list[dict[str, Any]]:
        payload = self._request("GET", f"bases/{self.base_id}/tables")
        return payload.get("tables", [])

    def create_table(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._request("POST", f"bases/{self.base_id}/tables", payload)
        time.sleep(REQUEST_INTERVAL_SECONDS)
        return response

    def create_field(self, table_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._request("POST", f"bases/{self.base_id}/tables/{table_id}/fields", payload)
        time.sleep(REQUEST_INTERVAL_SECONDS)
        return response


def to_field_payload(field_name: str, field_type: str) -> dict[str, Any]:
    if field_type == "single line text":
        return {"name": field_name, "type": "singleLineText"}
    if field_type == "long text":
        return {"name": field_name, "type": "multilineText"}
    if field_type == "url":
        return {"name": field_name, "type": "url"}
    if field_type == "checkbox":
        return {
            "name": field_name,
            "type": "checkbox",
            "options": {
                "icon": "check",
                "color": "greenBright",
            },
        }
    if field_type == "number":
        precision = 2 if field_name in {"Review Score", "Average Discount Rate", "Avg Discount Rate", "Avg Sale Price"} else 0
        return {
            "name": field_name,
            "type": "number",
            "options": {
                "precision": precision,
            },
        }
    raise ValueError(f"Unsupported schema field type: {field_type}")


def build_table_payload(table_name: str, table_meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": table_name,
        "description": f"todaysdeal sync table for {table_name}",
        "fields": [to_field_payload(field_name, field_type) for field_name, field_type in table_meta["fields"]],
    }


def main() -> int:
    args = parse_args()
    config = resolve_config(args.env_file)

    if not config.api_key or not config.base_id:
        print("Airtable bootstrap failed: AIRTABLE_API_KEY(or AIRTABLE_PAT) and AIRTABLE_BASE_ID are required.", file=sys.stderr)
        return 1

    client = AirtableMetaClient(config)

    try:
        existing_tables = client.list_tables()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    existing_by_name = {table.get("name"): table for table in existing_tables}
    missing_table_names = [name for name in AIRTABLE_SCHEMA if name not in existing_by_name]

    summary: dict[str, Any] = {
        "base_id": config.base_id,
        "existing_tables": [table.get("name") for table in existing_tables],
        "missing_tables": missing_table_names,
        "created_tables": [],
        "created_fields": {},
    }

    if args.dry_run:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    try:
        for table_name in missing_table_names:
            payload = build_table_payload(table_name, AIRTABLE_SCHEMA[table_name])
            created = client.create_table(payload)
            summary["created_tables"].append(created.get("name", table_name))

        refreshed_tables = client.list_tables()
        refreshed_by_name = {table.get("name"): table for table in refreshed_tables}

        for table_name, table_meta in AIRTABLE_SCHEMA.items():
            table = refreshed_by_name.get(table_name)
            if not table:
                continue
            existing_field_names = {field.get("name") for field in table.get("fields", [])}
            for field_name, field_type in table_meta["fields"]:
                if field_name in existing_field_names:
                    continue
                payload = to_field_payload(field_name, field_type)
                client.create_field(table["id"], payload)
                summary.setdefault("created_fields", {}).setdefault(table_name, []).append(field_name)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
