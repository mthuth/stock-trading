#!/usr/bin/env python3
"""Ingest daily price history for technical target modeling."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from datetime import date, timedelta
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from engine_common import (  # noqa: E402
    RESEARCH_FILE,
    load_env,
    read_csv,
    record_price_history,
    record_provider_payload,
    record_provider_run,
)
from provider_client import fetch_json_url  # noqa: E402


ALPHA_VANTAGE_BASE = "https://www.alphavantage.co/query"
STOOQ_BASE = "https://stooq.com/q/d/l/"
YAHOO_CHART_BASE = "https://query1.finance.yahoo.com/v8/finance/chart"


def get_json(url: str) -> object:
    result = fetch_json_url(url, timeout=30, retries=2)
    if result.status != "ok":
        raise RuntimeError(result.message or result.status)
    return result.payload


def alpha_vantage_daily(symbol: str, api_key: str, outputsize: str) -> object:
    query = urlencode(
        {
            "function": "TIME_SERIES_DAILY_ADJUSTED",
            "symbol": symbol,
            "outputsize": outputsize,
            "apikey": api_key,
        }
    )
    url = f"{ALPHA_VANTAGE_BASE}?{query}"
    result = fetch_json_url(url, timeout=30, retries=2)
    record_provider_payload(
        "Alpha Vantage",
        "TIME_SERIES_DAILY_ADJUSTED",
        symbol,
        result.status,
        result.message,
        payload_json=result.payload if result.status in {"ok", "blocked"} else None,
    )
    if result.status != "ok":
        raise RuntimeError(result.message or result.status)
    return result.payload


def stooq_symbol(symbol: str) -> str:
    return f"{symbol.lower().replace('-', '.')}.us"


def stooq_daily(symbol: str, max_days: int) -> list[dict[str, object]]:
    end = date.today()
    start = end - timedelta(days=max_days * 2)
    query = urlencode(
        {
            "s": stooq_symbol(symbol),
            "d1": start.strftime("%Y%m%d"),
            "d2": end.strftime("%Y%m%d"),
            "i": "d",
        }
    )
    request = Request(f"{STOOQ_BASE}?{query}", headers={"Accept": "text/csv"})
    with urlopen(request, timeout=30) as response:
        text = response.read().decode()
    reader = csv.DictReader(text.splitlines())
    rows = []
    for row in list(reader)[-max_days:]:
        if not row.get("Date") or row.get("Close") in (None, "", "N/D"):
            continue
        close = to_float(row.get("Close"))
        if close <= 0:
            continue
        rows.append(
            {
                "symbol": symbol,
                "price_date": row["Date"],
                "open": to_float(row.get("Open")),
                "high": to_float(row.get("High")),
                "low": to_float(row.get("Low")),
                "close": close,
                "adjusted_close": close,
                "volume": to_float(row.get("Volume")),
                "provider": "Stooq",
            }
        )
    return rows


def yahoo_daily(symbol: str, max_days: int) -> list[dict[str, object]]:
    range_value = "1y" if max_days <= 260 else "2y"
    url = f"{YAHOO_CHART_BASE}/{symbol}?{urlencode({'range': range_value, 'interval': '1d', 'events': 'history'})}"
    result = fetch_json_url(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 StockTradingResearch/0.1",
        },
        timeout=30,
        retries=2,
    )
    record_provider_payload(
        "Yahoo Finance",
        "chart",
        symbol,
        result.status,
        result.message,
        payload_json=result.payload if result.status in {"ok", "blocked"} else None,
    )
    if result.status != "ok":
        raise RuntimeError(result.message or result.status)
    payload = result.payload
    chart = payload.get("chart", {}) if isinstance(payload, dict) else {}
    result = chart.get("result", [])
    if not result:
        return []
    first = result[0]
    timestamps = first.get("timestamp", [])
    quote = first.get("indicators", {}).get("quote", [{}])[0]
    adjusted = first.get("indicators", {}).get("adjclose", [{}])[0].get("adjclose", [])
    rows = []
    window_timestamps = timestamps[-max_days:]
    start_index = len(timestamps) - len(window_timestamps)
    for offset, timestamp in enumerate(window_timestamps):
        source_index = start_index + offset
        close = to_float((quote.get("close") or [])[source_index])
        if close <= 0:
            continue
        price_date = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")
        rows.append(
            {
                "symbol": symbol,
                "price_date": price_date,
                "open": to_float((quote.get("open") or [])[source_index]),
                "high": to_float((quote.get("high") or [])[source_index]),
                "low": to_float((quote.get("low") or [])[source_index]),
                "close": close,
                "adjusted_close": to_float(adjusted[source_index])
                if adjusted
                else close,
                "volume": to_float((quote.get("volume") or [])[source_index]),
                "provider": "Yahoo Finance",
            }
        )
    return rows


def to_float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def parse_rows(symbol: str, payload: object, max_days: int) -> tuple[list[dict[str, object]], str]:
    if not isinstance(payload, dict):
        return [], "Unexpected non-object response"
    if payload.get("Note"):
        return [], str(payload["Note"])
    if payload.get("Information"):
        return [], str(payload["Information"])
    if payload.get("Error Message"):
        return [], str(payload["Error Message"])

    series = payload.get("Time Series (Daily)")
    if not isinstance(series, dict):
        return [], "No daily time series returned"

    rows = []
    for price_date in sorted(series.keys(), reverse=True)[:max_days]:
        day = series.get(price_date, {})
        if not isinstance(day, dict):
            continue
        close = to_float(day.get("4. close"))
        if close <= 0:
            continue
        rows.append(
            {
                "symbol": symbol,
                "price_date": price_date,
                "open": to_float(day.get("1. open")),
                "high": to_float(day.get("2. high")),
                "low": to_float(day.get("3. low")),
                "close": close,
                "adjusted_close": to_float(day.get("5. adjusted close")),
                "volume": to_float(day.get("6. volume")),
                "provider": "Alpha Vantage",
            }
        )
    return rows, ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest daily price history.")
    parser.add_argument("--symbols", help="Comma-separated symbols. Defaults to the V1 universe.")
    parser.add_argument("--max-days", type=int, default=260, help="Maximum daily bars per symbol.")
    parser.add_argument(
        "--outputsize",
        choices=["compact", "full"],
        default="full",
        help="Alpha Vantage output size. Use full for 200-day technical windows.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Delay between provider calls.",
    )
    parser.add_argument(
        "--provider",
        choices=["yahoo", "stooq", "alpha-vantage"],
        default="yahoo",
        help="Daily price-history provider. Yahoo is the no-key default.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_env()
    api_key = os.environ.get("ALPHA_VANTAGE_API_KEY")
    if args.provider == "alpha-vantage" and not api_key:
        print("Missing ALPHA_VANTAGE_API_KEY in .env.")
        return 1

    if args.symbols:
        symbols = [symbol.strip().upper() for symbol in args.symbols.split(",") if symbol.strip()]
    else:
        research_rows, _ = read_csv(RESEARCH_FILE)
        symbols = [row["symbol"].strip().upper() for row in research_rows if row.get("symbol")]

    field_rows = []
    total_inserted = 0
    for index, symbol in enumerate(symbols, start=1):
        try:
            if args.provider == "alpha-vantage":
                payload = alpha_vantage_daily(symbol, str(api_key), args.outputsize)
                rows, message = parse_rows(symbol, payload, args.max_days)
                provider = "Alpha Vantage"
            elif args.provider == "yahoo":
                rows = yahoo_daily(symbol, args.max_days)
                message = "" if rows else "No daily price history returned from Yahoo Finance"
                provider = "Yahoo Finance"
            else:
                rows = stooq_daily(symbol, args.max_days)
                message = "" if rows else "No daily price history returned from Stooq"
                provider = "Stooq"
            inserted = record_price_history(rows)
            total_inserted += inserted
            status = "ok" if rows else "missing"
            print(f"{symbol}: price_history_rows={len(rows)}")
            field_rows.append(
                {
                    "symbol": symbol,
                    "provider": provider,
                    "field_name": "price_history",
                    "status": status,
                    "message": message,
                }
            )
        except Exception as exc:  # noqa: BLE001 - provider errors become tracked gaps.
            print(f"{symbol}: price_history_error={exc}")
            field_rows.append(
                {
                    "symbol": symbol,
                    "provider": args.provider,
                    "field_name": "price_history",
                    "status": "error",
                    "message": str(exc),
                }
            )
        if index < len(symbols) and args.delay > 0:
            time.sleep(args.delay)

    run_id = record_provider_run(
        f"{args.provider} price history",
        "ok",
        f"symbols={len(symbols)}; rows={total_inserted}",
        field_rows,
    )
    gaps = sum(1 for row in field_rows if row.get("status") != "ok")
    print(f"Recorded {args.provider} price-history provider run {run_id} with {gaps} gaps")
    return 0


if __name__ == "__main__":
    sys.exit(main())
