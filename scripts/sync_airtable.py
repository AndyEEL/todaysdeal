#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = REPO_ROOT / "data"
DEFAULT_ENV_PATH = REPO_ROOT / ".env"
AIRTABLE_API_ROOT = "https://api.airtable.com/v0"
BATCH_SIZE = 10
REQUEST_INTERVAL_SECONDS = 0.25

STATUS_LABELS = {
    "entering": "신규 진입",
    "price_changed": "가격 변동",
    "active": "유지",
    "exited": "이탈",
}

AIRTABLE_SCHEMA: dict[str, dict[str, Any]] = {
    "Daily Deals": {
        "merge_field": "Deal Record Key",
        "fields": [
            ("Deal Record Key", "single line text"),
            ("Is Latest Snapshot", "checkbox"),
            ("Snapshot Date", "single line text"),
            ("Product ID", "single line text"),
            ("Product Name", "single line text"),
            ("Product URL", "url"),
            ("Image URL", "url"),
            ("Deal Type", "single line text"),
            ("Store ID", "single line text"),
            ("Store Name", "single line text"),
            ("Brand Name", "single line text"),
            ("Category", "single line text"),
            ("Rank", "number"),
            ("Original Price", "number"),
            ("Sale Price", "number"),
            ("Discount Rate", "number"),
            ("Review Score", "number"),
            ("Review Count", "number"),
            ("Status Today", "single line text"),
            ("New Today", "checkbox"),
            ("Price Changed", "checkbox"),
            ("Days Seen Total", "number"),
            ("Fetched At", "single line text"),
            ("Source URL", "url"),
        ],
    },
    "Products": {
        "merge_field": "Product ID",
        "fields": [
            ("Product ID", "single line text"),
            ("Latest Product Name", "single line text"),
            ("Brand Name", "single line text"),
            ("Category", "single line text"),
            ("First Seen Date", "single line text"),
            ("Last Seen Date", "single line text"),
            ("Active Days", "number"),
            ("Current Status", "single line text"),
            ("Appeared Today", "checkbox"),
            ("Disappeared Today", "checkbox"),
            ("Latest Sale Price", "number"),
            ("Latest Original Price", "number"),
            ("Latest Discount Rate", "number"),
            ("Latest Rank", "number"),
            ("Product URL", "url"),
            ("Latest Image URL", "url"),
            ("Price Change Count", "number"),
            ("Image Change Count", "number"),
            ("Deal Cycles", "number"),
            ("Average Discount Rate", "number"),
            ("Max Discount Rate", "number"),
        ],
    },
    "Runs": {
        "merge_field": "Run Key",
        "fields": [
            ("Run Key", "single line text"),
            ("Snapshot Date", "single line text"),
            ("Run At", "single line text"),
            ("Job Status", "single line text"),
            ("Product Count", "number"),
            ("New Count", "number"),
            ("Removed Count", "number"),
            ("Price Changed Count", "number"),
            ("Source", "single line text"),
            ("Notes", "long text"),
        ],
    },
}


@dataclass
class Config:
    enabled: bool
    api_key: str | None
    base_id: str | None
    daily_deals_table: str
    products_table: str
    runs_table: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync today'sdeal data into Airtable tables.")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help="Path to the data directory. Defaults to repo-root/data.",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=DEFAULT_ENV_PATH,
        help="Optional .env path for Airtable credentials/config.",
    )
    parser.add_argument(
        "--snapshot-date",
        help="Snapshot date to sync (YYYY-MM-DD). Defaults to latest derived snapshot.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build records and print summary without calling Airtable API.",
    )
    parser.add_argument(
        "--print-schema",
        action="store_true",
        help="Print the required Airtable tables/fields as JSON and exit.",
    )
    return parser.parse_args()


def load_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if value.startswith(("\"", "'")) and value.endswith(("\"", "'")) and len(value) >= 2:
            value = value[1:-1]
        values[key] = value
    return values


def resolve_env(name: str, dotenv: dict[str, str], default: str | None = None) -> str | None:
    return os.environ.get(name) or dotenv.get(name) or default


def normalize_airtable_base_id(value: str | None) -> str | None:
    if not value:
        return value
    candidate = value.strip()
    match = re.search(r"\bapp[a-zA-Z0-9]+\b", candidate)
    if match:
        return match.group(0)
    return candidate


def is_truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def resolve_config(env_file: Path) -> Config:
    dotenv = load_dotenv(env_file)
    return Config(
        enabled=is_truthy(resolve_env("TODAYSDEAL_ENABLE_AIRTABLE_SYNC", dotenv, "0")),
        api_key=resolve_env("AIRTABLE_API_KEY", dotenv) or resolve_env("AIRTABLE_PAT", dotenv),
        base_id=normalize_airtable_base_id(resolve_env("AIRTABLE_BASE_ID", dotenv)),
        daily_deals_table=resolve_env("AIRTABLE_DAILY_DEALS_TABLE", dotenv, "Daily Deals") or "Daily Deals",
        products_table=resolve_env("AIRTABLE_PRODUCTS_TABLE", dotenv, "Products") or "Products",
        runs_table=resolve_env("AIRTABLE_RUNS_TABLE", dotenv, "Runs") or "Runs",
    )


def read_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"Required JSON file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_sync_payload(data_dir: Path, snapshot_date: str | None) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    daily_insights_path = (
        data_dir / "derived" / "daily-insights" / f"{snapshot_date}.json"
        if snapshot_date
        else data_dir / "derived" / "daily-insights" / "latest.json"
    )
    daily_insights = read_json(daily_insights_path)

    resolved_snapshot_date = snapshot_date or daily_insights.get("snapshot_date")
    if not resolved_snapshot_date:
        raise ValueError("Could not resolve snapshot_date from daily insights payload.")

    snapshot_path = data_dir / "daily" / f"{resolved_snapshot_date}.json"
    snapshot = read_json(snapshot_path)
    products_summary = read_json(data_dir / "derived" / "products-summary.json")

    if snapshot.get("snapshot_date") != resolved_snapshot_date:
        raise ValueError(
            f"Snapshot date mismatch: expected {resolved_snapshot_date}, got {snapshot.get('snapshot_date')}"
        )
    if daily_insights.get("snapshot_date") != resolved_snapshot_date:
        raise ValueError(
            f"Daily insights date mismatch: expected {resolved_snapshot_date}, got {daily_insights.get('snapshot_date')}"
        )

    return snapshot, daily_insights, products_summary


def safe_number(value: Any) -> int | float | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return value
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else number


def chunked(items: list[dict[str, Any]], size: int) -> Iterable[list[dict[str, Any]]]:
    for index in range(0, len(items), size):
        yield items[index : index + size]


def clean_fields(fields: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in fields.items():
        if value is None:
            continue
        cleaned[key] = value
    return cleaned


def build_daily_deal_records(
    snapshot: dict[str, Any],
    daily_insights: dict[str, Any],
    products_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    summary_items = {
        str(item["product_id"]): item
        for item in products_summary.get("items", [])
        if item.get("product_id") is not None
    }
    new_ids = {str(item["product_id"]) for item in daily_insights.get("new_products", []) if item.get("product_id")}
    price_changed_ids = {
        str(item["product_id"])
        for item in daily_insights.get("price_changed_products", [])
        if item.get("product_id")
    }

    records: list[dict[str, Any]] = []
    snapshot_date = str(snapshot.get("snapshot_date") or "")
    fetched_at = snapshot.get("fetched_at")
    source_url = snapshot.get("source_url")

    for item in snapshot.get("products", []):
        product_id = str(item.get("product_id") or "").strip()
        if not product_id:
            continue
        summary = summary_items.get(product_id, {})
        store_id = str(item.get("channel_no") or "").strip()
        fields = clean_fields(
            {
                "Deal Record Key": f"{snapshot_date}_{product_id}",
                "Is Latest Snapshot": True,
                "Snapshot Date": snapshot_date,
                "Product ID": product_id,
                "Product Name": item.get("name"),
                "Product URL": item.get("landing_url"),
                "Image URL": item.get("image_url"),
                "Deal Type": item.get("label"),
                "Store ID": store_id,
                "Store Name": f"채널{store_id}" if store_id else None,
                "Brand Name": summary.get("brand"),
                "Category": summary.get("category"),
                "Rank": safe_number(item.get("rank") or item.get("order")),
                "Original Price": safe_number(item.get("sale_price")),
                "Sale Price": safe_number(item.get("discounted_price")),
                "Discount Rate": safe_number(item.get("discounted_ratio")),
                "Review Score": safe_number(item.get("review_score")),
                "Review Count": safe_number(item.get("review_count")),
                "Status Today": STATUS_LABELS.get(str(summary.get("current_status") or ""), "유지"),
                "New Today": product_id in new_ids,
                "Price Changed": product_id in price_changed_ids,
                "Days Seen Total": safe_number(summary.get("active_days")),
                "Fetched At": fetched_at,
                "Source URL": source_url,
            }
        )
        records.append(fields)

    return records


def build_product_records(products_summary: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for item in products_summary.get("items", []):
        product_id = str(item.get("product_id") or "").strip()
        if not product_id:
            continue
        fields = clean_fields(
            {
                "Product ID": product_id,
                "Latest Product Name": item.get("product_name"),
                "Brand Name": item.get("brand"),
                "Category": item.get("category"),
                "First Seen Date": item.get("first_seen_date"),
                "Last Seen Date": item.get("last_seen_date"),
                "Active Days": safe_number(item.get("active_days")),
                "Current Status": STATUS_LABELS.get(str(item.get("current_status") or ""), item.get("current_status")),
                "Appeared Today": bool(item.get("appeared_today")),
                "Disappeared Today": bool(item.get("disappeared_today")),
                "Latest Sale Price": safe_number(item.get("latest_sale_price")),
                "Latest Original Price": safe_number(item.get("latest_original_price")),
                "Latest Discount Rate": safe_number(item.get("latest_discount_rate")),
                "Latest Rank": safe_number(item.get("latest_rank")),
                "Product URL": item.get("product_url"),
                "Latest Image URL": item.get("latest_image_url"),
                "Price Change Count": safe_number(item.get("price_change_count")),
                "Image Change Count": safe_number(item.get("image_change_count")),
                "Deal Cycles": safe_number(item.get("deal_cycles")),
                "Average Discount Rate": safe_number(item.get("average_discount_rate")),
                "Max Discount Rate": safe_number(item.get("max_discount_rate")),
            }
        )
        records.append(fields)
    return records


def build_run_records(snapshot: dict[str, Any], daily_insights: dict[str, Any]) -> list[dict[str, Any]]:
    snapshot_date = str(snapshot.get("snapshot_date") or "")
    generated_at = daily_insights.get("generated_at") or snapshot.get("fetched_at") or snapshot_date
    run_key = f"{snapshot_date}__{generated_at}"
    notes = (
        "Synced by scripts/sync_airtable.py. "
        f"Daily deals={snapshot.get('product_count', 0)}, products summary={len(daily_insights.get('new_products', []))} new."
    )
    return [
        clean_fields(
            {
                "Run Key": run_key,
                "Snapshot Date": snapshot_date,
                "Run At": generated_at,
                "Job Status": "success",
                "Product Count": safe_number(daily_insights.get("product_count")),
                "New Count": safe_number(daily_insights.get("new_count")),
                "Removed Count": safe_number(daily_insights.get("removed_count")),
                "Price Changed Count": safe_number(daily_insights.get("price_changed_count")),
                "Source": "scripts/sync_airtable.py",
                "Notes": notes,
            }
        )
    ]


class AirtableClient:
    def __init__(self, api_key: str, base_id: str) -> None:
        self.api_key = api_key
        self.base_id = base_id

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{AIRTABLE_API_ROOT}/{path.lstrip('/')}"
        data = None
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        request = Request(url=url, data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=60) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Airtable API error ({exc.code}) {body}") from exc
        except URLError as exc:
            raise RuntimeError(f"Airtable API network error: {exc}") from exc

        if not raw:
            return {}
        return json.loads(raw)

    def upsert_records(self, table_name: str, merge_field: str, records: list[dict[str, Any]]) -> int:
        if not records:
            return 0

        total = 0
        encoded_table_name = quote(table_name, safe="")
        path = f"{self.base_id}/{encoded_table_name}"

        for batch in chunked(records, BATCH_SIZE):
            payload = {
                "performUpsert": {
                    "fieldsToMergeOn": [merge_field],
                },
                "typecast": True,
                "records": [{"fields": record} for record in batch],
            }
            response = self._request("PATCH", path, payload)
            total += len(response.get("records", []))
            time.sleep(REQUEST_INTERVAL_SECONDS)
        return total

    def list_records(self, table_name: str, fields: list[str] | None = None) -> list[dict[str, Any]]:
        encoded_table_name = quote(table_name, safe="")
        base_path = f"{self.base_id}/{encoded_table_name}"
        records: list[dict[str, Any]] = []
        offset: str | None = None

        while True:
            query_parts: list[str] = []
            if fields:
                for field_name in fields:
                    query_parts.append(f"fields[]={quote(field_name, safe='')}")
            if offset:
                query_parts.append(f"offset={quote(offset, safe='')}")

            path = base_path if not query_parts else f"{base_path}?{'&'.join(query_parts)}"
            payload = self._request("GET", path)
            records.extend(payload.get("records", []))
            offset = payload.get("offset")
            if not offset:
                break
            time.sleep(REQUEST_INTERVAL_SECONDS)

        return records

    def update_records_by_id(self, table_name: str, records: list[dict[str, Any]]) -> int:
        if not records:
            return 0

        total = 0
        encoded_table_name = quote(table_name, safe="")
        path = f"{self.base_id}/{encoded_table_name}"

        for batch in chunked(records, BATCH_SIZE):
            payload = {
                "typecast": True,
                "records": batch,
            }
            response = self._request("PATCH", path, payload)
            total += len(response.get("records", []))
            time.sleep(REQUEST_INTERVAL_SECONDS)
        return total


def build_stale_latest_flag_updates(
    existing_daily_records: list[dict[str, Any]],
    latest_snapshot_date: str,
) -> list[dict[str, Any]]:
    updates: list[dict[str, Any]] = []
    for record in existing_daily_records:
        fields = record.get("fields", {})
        if not fields.get("Is Latest Snapshot"):
            continue
        if fields.get("Snapshot Date") == latest_snapshot_date:
            continue
        updates.append(
            {
                "id": record["id"],
                "fields": {
                    "Is Latest Snapshot": False,
                },
            }
        )
    return updates


def print_schema() -> None:
    payload = {
        "tables": [
            {
                "name": table_name,
                "merge_field": table_meta["merge_field"],
                "fields": [
                    {"name": field_name, "type": field_type}
                    for field_name, field_type in table_meta["fields"]
                ],
            }
            for table_name, table_meta in AIRTABLE_SCHEMA.items()
        ]
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> int:
    args = parse_args()

    if args.print_schema:
        print_schema()
        return 0

    snapshot, daily_insights, products_summary = load_sync_payload(args.data_dir, args.snapshot_date)
    daily_deals_records = build_daily_deal_records(snapshot, daily_insights, products_summary)
    product_records = build_product_records(products_summary)
    run_records = build_run_records(snapshot, daily_insights)

    config = resolve_config(args.env_file)

    if args.dry_run:
        summary = {
            "snapshot_date": snapshot.get("snapshot_date"),
            "daily_deals_records": len(daily_deals_records),
            "product_records": len(product_records),
            "run_records": len(run_records),
            "enabled": config.enabled,
            "base_id_present": bool(config.base_id),
            "api_key_present": bool(config.api_key),
            "tables": {
                "daily_deals": config.daily_deals_table,
                "products": config.products_table,
                "runs": config.runs_table,
            },
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    if not config.enabled:
        print("Airtable sync skipped: TODAYSDEAL_ENABLE_AIRTABLE_SYNC is not enabled.")
        return 0

    if not config.api_key or not config.base_id:
        print(
            "Airtable sync failed: AIRTABLE_API_KEY(or AIRTABLE_PAT) and AIRTABLE_BASE_ID are required when sync is enabled.",
            file=sys.stderr,
        )
        return 1

    client = AirtableClient(api_key=config.api_key, base_id=config.base_id)

    try:
        synced_daily_deals = client.upsert_records(
            table_name=config.daily_deals_table,
            merge_field=AIRTABLE_SCHEMA["Daily Deals"]["merge_field"],
            records=daily_deals_records,
        )
        stale_flag_updates = build_stale_latest_flag_updates(
            existing_daily_records=client.list_records(
                table_name=config.daily_deals_table,
                fields=["Snapshot Date", "Is Latest Snapshot"],
            ),
            latest_snapshot_date=str(snapshot.get("snapshot_date") or ""),
        )
        stale_latest_flags_cleared = client.update_records_by_id(
            table_name=config.daily_deals_table,
            records=stale_flag_updates,
        )
        synced_products = client.upsert_records(
            table_name=config.products_table,
            merge_field=AIRTABLE_SCHEMA["Products"]["merge_field"],
            records=product_records,
        )
        synced_runs = client.upsert_records(
            table_name=config.runs_table,
            merge_field=AIRTABLE_SCHEMA["Runs"]["merge_field"],
            records=run_records,
        )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    summary = {
        "snapshot_date": snapshot.get("snapshot_date"),
        "daily_deals_synced": synced_daily_deals,
        "stale_latest_flags_cleared": stale_latest_flags_cleared,
        "products_synced": synced_products,
        "runs_synced": synced_runs,
        "tables": {
            "daily_deals": config.daily_deals_table,
            "products": config.products_table,
            "runs": config.runs_table,
        },
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
