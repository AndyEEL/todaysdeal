#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

SEOUL = ZoneInfo("Asia/Seoul")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a today's deal snapshot JSON file.")
    parser.add_argument(
        "--snapshot-file",
        type=Path,
        required=True,
        help="Path to snapshot JSON file (for example data/latest.json).",
    )
    parser.add_argument(
        "--expect-date",
        help="Expected snapshot_date (YYYY-MM-DD). Defaults to today in Asia/Seoul.",
    )
    parser.add_argument(
        "--min-product-count",
        type=int,
        default=1,
        help="Minimum required product_count.",
    )
    parser.add_argument(
        "--require-selected-tab",
        default="스페셜딜",
        help="Expected selected_tab value. Empty string disables this check.",
    )
    return parser.parse_args()


def load_snapshot(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Snapshot file not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Snapshot payload must be a JSON object.")
    return payload


def resolve_expected_date(raw_value: str | None) -> str:
    if raw_value:
        return raw_value
    return datetime.now(tz=SEOUL).date().isoformat()


def main() -> int:
    args = parse_args()
    expected_date = resolve_expected_date(args.expect_date)

    try:
        snapshot = load_snapshot(args.snapshot_file)
        snapshot_date = str(snapshot.get("snapshot_date") or "").strip()
        fetched_at = str(snapshot.get("fetched_at") or "").strip()
        product_count = snapshot.get("product_count")
        products = snapshot.get("products") or []
        selected_tab = str(snapshot.get("selected_tab") or "").strip()

        if snapshot_date != expected_date:
            raise ValueError(
                f"snapshot_date mismatch: expected {expected_date}, got {snapshot_date or '<empty>'}"
            )

        if not isinstance(product_count, int):
            raise ValueError(f"product_count must be an integer, got {type(product_count).__name__}")

        if product_count < args.min_product_count:
            raise ValueError(
                f"product_count too small: expected >= {args.min_product_count}, got {product_count}"
            )

        if len(products) != product_count:
            raise ValueError(
                f"products length mismatch: product_count={product_count}, len(products)={len(products)}"
            )

        if args.require_selected_tab and selected_tab != args.require_selected_tab:
            raise ValueError(
                f"selected_tab mismatch: expected {args.require_selected_tab}, got {selected_tab or '<empty>'}"
            )

        summary = {
            "snapshot_date": snapshot_date,
            "fetched_at": fetched_at,
            "selected_tab": selected_tab,
            "product_count": product_count,
            "source_url": snapshot.get("source_url"),
        }
        print(json.dumps(summary, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
