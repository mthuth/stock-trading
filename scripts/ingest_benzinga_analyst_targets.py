#!/usr/bin/env python3
"""Ingest Benzinga analyst target rows into the supplemental target CSV."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Mapping


ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"
RESEARCH_FILE = CONFIG_DIR / "research_inputs.csv"
MANUAL_ANALYST_TARGETS_FILE = CONFIG_DIR / "manual_analyst_targets.csv"
DEFAULT_RATINGS_URL = "https://api.benzinga.com/api/v2.1/calendar/ratings"
TARGET_FIELDS = [
    "symbol",
    "source_name",
    "target_price",
    "target_low",
    "target_high",
    "as_of_date",
    "confidence",
    "provider_endpoint",
    "notes",
]

sys.path.insert(0, str(ROOT / "scripts"))

from engine_common import load_env, read_csv, record_provider_run, write_csv_atomic  # noqa: E402


def to_float(value: object, default: float = 0.0) -> float:
    try:
        return float(str(value).replace("$", "").replace(",", ""))
    except (TypeError, ValueError):
        return default


def first_value(row: Mapping[str, object], keys: Iterable[str]) -> object:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return ""


def research_symbols() -> List[str]:
    rows, _ = read_csv(RESEARCH_FILE)
    return [str(row.get("symbol") or "").strip().upper() for row in rows if row.get("symbol")]


def fetch_ratings(symbols: List[str], api_key: str, days: int, url: str) -> object:
    end_date = date.today()
    start_date = end_date - timedelta(days=days)
    params = {
        "token": api_key,
        "parameters[tickers]": ",".join(symbols),
        "parameters[date_from]": start_date.isoformat(),
        "parameters[date_to]": end_date.isoformat(),
        "pagesize": "1000",
    }
    request_url = f"{url}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(request_url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = response.read().decode("utf-8")
    return json.loads(payload)


def payload_records(payload: object) -> List[Mapping[str, object]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("ratings", "data", "results", "analyst_ratings"):
        value = payload.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
        if isinstance(value, dict):
            nested = payload_records(value)
            if nested:
                return nested
    for value in payload.values():
        if isinstance(value, list) and all(isinstance(row, dict) for row in value):
            return value
    return []


def normalize_rating_rows(records: Iterable[Mapping[str, object]], symbols: List[str]) -> List[Dict[str, object]]:
    allowed = set(symbols)
    rows: List[Dict[str, object]] = []
    for record in records:
        symbol = str(first_value(record, ("ticker", "symbol"))).strip().upper()
        if symbol not in allowed:
            continue
        target_price = to_float(
            first_value(
                record,
                (
                    "pt_current",
                    "price_target",
                    "priceTarget",
                    "target_price",
                    "target",
                    "current_price_target",
                ),
            )
        )
        if target_price <= 0:
            continue
        as_of_date = str(
            first_value(
                record,
                ("date", "rating_date", "updated", "updated_at", "published_date", "created_at"),
            )
        ).strip()
        firm = str(first_value(record, ("firm", "analyst", "analyst_name", "brokerage", "source"))).strip()
        action = str(first_value(record, ("action", "action_company", "action_pt", "change"))).strip()
        rating = str(first_value(record, ("rating", "rating_current", "recommendation"))).strip()
        note_parts = [part for part in (firm, action, rating) if part]
        rows.append(
            {
                "symbol": symbol,
                "source_name": "Benzinga analyst ratings",
                "target_price": f"{target_price:.4f}",
                "target_low": "",
                "target_high": "",
                "as_of_date": as_of_date,
                "confidence": "medium",
                "provider_endpoint": "Benzinga calendar ratings API",
                "notes": "; ".join(note_parts) or "Imported from Benzinga analyst ratings.",
            }
        )
    return rows


def merge_rows(imported_rows: List[Dict[str, object]], symbols: List[str]) -> None:
    existing: List[Dict[str, object]] = []
    if MANUAL_ANALYST_TARGETS_FILE.exists():
        existing, _ = read_csv(MANUAL_ANALYST_TARGETS_FILE)
    symbol_set = set(symbols)
    kept = [
        row
        for row in existing
        if not (
            str(row.get("source_name") or "") == "Benzinga analyst ratings"
            and str(row.get("symbol") or "").upper() in symbol_set
        )
    ]
    write_csv_atomic(MANUAL_ANALYST_TARGETS_FILE, kept + imported_rows, TARGET_FIELDS)


def ingest(symbols: List[str], days: int, dry_run: bool = False) -> int:
    load_env()
    api_key = os.environ.get("BENZINGA_API_KEY", "").strip()
    if not api_key:
        print("Missing BENZINGA_API_KEY. Add it to .env to import Benzinga analyst ratings.")
        return 1
    if not symbols:
        print("No symbols requested.")
        return 1

    url = os.environ.get("BENZINGA_ANALYST_RATINGS_URL", DEFAULT_RATINGS_URL).strip()
    payload = fetch_ratings(symbols, api_key, days, url)
    imported_rows = normalize_rating_rows(payload_records(payload), symbols)
    if not dry_run:
        merge_rows(imported_rows, symbols)

    imported_by_symbol = {symbol: 0 for symbol in symbols}
    for row in imported_rows:
        imported_by_symbol[str(row.get("symbol"))] = imported_by_symbol.get(str(row.get("symbol")), 0) + 1
    field_rows = [
        {
            "symbol": symbol,
            "provider": "Benzinga analyst ratings",
            "field_name": "analyst_target",
            "status": "ok" if imported_by_symbol.get(symbol, 0) else "missing",
            "message": f"imported_targets={imported_by_symbol.get(symbol, 0)}",
        }
        for symbol in symbols
    ]
    record_provider_run(
        "Benzinga analyst ratings",
        "ok" if imported_rows else "missing",
        f"symbols={len(symbols)}; imported_targets={len(imported_rows)}; dry_run={dry_run}",
        field_rows,
    )
    print(f"Imported {len(imported_rows)} Benzinga analyst target rows into {MANUAL_ANALYST_TARGETS_FILE}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import Benzinga analyst targets into config/manual_analyst_targets.csv")
    parser.add_argument("--symbols", nargs="+", help="Symbols to refresh. Defaults to config/research_inputs.csv.")
    parser.add_argument("--days", type=int, default=365, help="Calendar lookback window for rating events.")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and normalize without writing the CSV.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    symbols = [symbol.strip().upper() for symbol in args.symbols] if args.symbols else research_symbols()
    started = time.time()
    try:
        return ingest(symbols, args.days, args.dry_run)
    finally:
        print(f"Elapsed {time.time() - started:.1f}s")


if __name__ == "__main__":
    sys.exit(main())
