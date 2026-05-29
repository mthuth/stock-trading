#!/usr/bin/env python3
"""Refresh market data in config/research_inputs.csv.

Provider strategy:
- Use Financial Modeling Prep for quotes and analyst target consensus when available.
- Use Alpha Vantage as fallback/enrichment for quote, fundamentals, estimates, news sentiment.
- Record missing/blocked fields by symbol so paid-provider decisions are evidence-based.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Dict, Iterable, Mapping
from urllib.parse import urlencode


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from engine_common import (  # noqa: E402
    RESEARCH_FILE,
    load_env,
    read_csv,
    record_provider_payload,
    record_provider_run,
    write_csv_atomic,
)
from provider_client import fetch_json_url  # noqa: E402


FMP_BASE = "https://financialmodelingprep.com/stable"
ALPHA_VANTAGE_BASE = "https://www.alphavantage.co/query"


def get_json(url: str, provider: str, endpoint: str, symbol: str) -> object:
    result = fetch_json_url(url, timeout=30, retries=2)
    message = result.message
    if result.error_class:
        message = f"{message}; error_class={result.error_class}; attempts={result.attempts}".strip("; ")
    elif result.attempts > 1:
        message = f"{message}; attempts={result.attempts}".strip("; ")
    record_provider_payload(
        provider,
        endpoint,
        symbol,
        result.status,
        message,
        payload_json=result.payload if result.status in {"ok", "blocked"} else None,
    )
    if result.status != "ok":
        raise RuntimeError(message or result.status)
    return result.payload


def first_object(payload: object) -> Mapping[str, object]:
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        return payload[0]
    if isinstance(payload, dict):
        return payload
    return {}


def first_number(source: Mapping[str, object], keys: Iterable[str]) -> float:
    for key in keys:
        value = source.get(key)
        if value in (None, ""):
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0


def fmp_get(path: str, params: Mapping[str, object], api_key: str) -> object:
    query = urlencode({**params, "apikey": api_key})
    symbol = str(params.get("symbol") or "")
    return get_json(f"{FMP_BASE}/{path}?{query}", "Financial Modeling Prep", path, symbol)


def alpha_vantage_get(params: Mapping[str, object], api_key: str) -> object:
    query = urlencode({**params, "apikey": api_key})
    endpoint = str(params.get("function") or "query")
    symbol = str(params.get("symbol") or params.get("tickers") or "")
    return get_json(f"{ALPHA_VANTAGE_BASE}?{query}", "Alpha Vantage", endpoint, symbol)


def fetch_fmp_symbol(symbol: str, api_key: str) -> Dict[str, object]:
    result: Dict[str, object] = {
        "provider": "Financial Modeling Prep",
        "current_price": 0.0,
        "target_price": 0.0,
        "messages": [],
    }
    try:
        quote = first_object(fmp_get("quote", {"symbol": symbol}, api_key))
        result["current_price"] = first_number(
            quote,
            ["price", "lastPrice", "regularMarketPrice", "previousClose"],
        )
    except Exception as exc:  # noqa: BLE001 - record by symbol and continue.
        result["messages"].append(f"FMP quote failed: {exc}")

    time.sleep(0.12)
    try:
        target = first_object(fmp_get("price-target-consensus", {"symbol": symbol}, api_key))
        result["target_price"] = first_number(
            target,
            [
                "targetConsensus",
                "consensus",
                "targetMeanPrice",
                "priceTargetAverage",
                "targetMedian",
            ],
        )
    except Exception as exc:  # noqa: BLE001
        result["messages"].append(f"FMP target failed: {exc}")
    return result


def fetch_alpha_vantage_symbol(symbol: str, api_key: str) -> Dict[str, object]:
    result: Dict[str, object] = {
        "provider": "Alpha Vantage",
        "current_price": 0.0,
        "target_price": 0.0,
        "revenue_estimate": "",
        "eps_estimate": "",
        "news_sentiment": "",
        "messages": [],
    }
    try:
        quote = first_object(
            alpha_vantage_get({"function": "GLOBAL_QUOTE", "symbol": symbol}, api_key)
        ).get("Global Quote", {})
        if isinstance(quote, dict):
            result["current_price"] = first_number(quote, ["05. price", "08. previous close"])
    except Exception as exc:  # noqa: BLE001
        result["messages"].append(f"Alpha Vantage quote failed: {exc}")

    time.sleep(0.12)
    try:
        estimates = first_object(
            alpha_vantage_get({"function": "EARNINGS_ESTIMATES", "symbol": symbol}, api_key)
        )
        annual = estimates.get("annualEarningsEstimates", [])
        if isinstance(annual, list) and annual:
            first = annual[0]
            if isinstance(first, dict):
                result["eps_estimate"] = first.get("epsAvg", "") or first.get("estimate", "")
                result["revenue_estimate"] = first.get("revenueAvg", "")
    except Exception as exc:  # noqa: BLE001
        result["messages"].append(f"Alpha Vantage estimates failed: {exc}")

    time.sleep(0.12)
    try:
        sentiment = first_object(
            alpha_vantage_get(
                {
                    "function": "NEWS_SENTIMENT",
                    "tickers": symbol,
                    "limit": 20,
                    "sort": "LATEST",
                },
                api_key,
            )
        )
        feed = sentiment.get("feed", [])
        if isinstance(feed, list) and feed:
            scores = []
            for item in feed:
                if not isinstance(item, dict):
                    continue
                for ticker_sentiment in item.get("ticker_sentiment", []):
                    if not isinstance(ticker_sentiment, dict):
                        continue
                    if ticker_sentiment.get("ticker") == symbol:
                        try:
                            scores.append(float(ticker_sentiment.get("ticker_sentiment_score", 0)))
                        except (TypeError, ValueError):
                            pass
            if scores:
                avg = sum(scores) / len(scores)
                result["news_sentiment"] = f"{avg:.3f}"
    except Exception as exc:  # noqa: BLE001
        result["messages"].append(f"Alpha Vantage news sentiment failed: {exc}")
    return result


def ensure_fields(fieldnames: list[str]) -> list[str]:
    for field in [
        "price_source",
        "target_source",
        "estimate_source",
        "sentiment_source",
        "eps_estimate",
        "revenue_estimate",
        "news_sentiment",
        "provider_notes",
    ]:
        if field not in fieldnames:
            fieldnames.append(field)
    return fieldnames


def refresh() -> int:
    load_env()
    fmp_key = os.environ.get("FMP_API_KEY")
    alpha_key = os.environ.get("ALPHA_VANTAGE_API_KEY")
    if not fmp_key and not alpha_key:
        print("Missing provider key. Add FMP_API_KEY or ALPHA_VANTAGE_API_KEY to .env.")
        return 1

    rows, fieldnames = read_csv(RESEARCH_FILE)
    fieldnames = ensure_fields(fieldnames)
    refreshed = 0
    field_status = []

    for row in rows:
        symbol = row["symbol"].strip().upper()
        messages = []

        fmp_data: Dict[str, object] = {}
        if fmp_key:
            fmp_data = fetch_fmp_symbol(symbol, fmp_key)
            messages.extend(fmp_data.get("messages", []))

        av_data: Dict[str, object] = {}
        if alpha_key:
            av_data = fetch_alpha_vantage_symbol(symbol, alpha_key)
            messages.extend(av_data.get("messages", []))

        current_price = float(fmp_data.get("current_price") or 0)
        price_source = "FMP" if current_price else ""
        if not current_price:
            current_price = float(av_data.get("current_price") or 0)
            price_source = "Alpha Vantage" if current_price else ""

        target_price = float(fmp_data.get("target_price") or 0)
        target_source = "FMP" if target_price else ""

        if current_price > 0:
            row["current_price"] = f"{current_price:.4f}"
            row["price_source"] = price_source
            field_status.append(
                {
                    "symbol": symbol,
                    "field_name": "current_price",
                    "provider": price_source,
                    "status": "ok",
                    "message": "",
                }
            )
        else:
            row["price_source"] = row.get("price_source", "")
            existing_price = first_number(row, ["current_price"])
            status = "stale" if existing_price > 0 else "missing"
            message = (
                "No fresh price returned; retained prior price"
                if status == "stale"
                else "No price returned"
            )
            field_status.append(
                {
                    "symbol": symbol,
                    "field_name": "current_price",
                    "provider": "FMP/Alpha Vantage",
                    "status": status,
                    "message": "; ".join(messages) or message,
                }
            )

        if target_price > 0:
            row["target_price"] = f"{target_price:.4f}"
            row["target_source"] = target_source
            field_status.append(
                {
                    "symbol": symbol,
                    "field_name": "target_price",
                    "provider": target_source,
                    "status": "ok",
                    "message": "",
                }
            )
        else:
            row["target_source"] = row.get("target_source") or "Needs paid target provider"
            field_status.append(
                {
                    "symbol": symbol,
                    "field_name": "target_price",
                    "provider": "FMP",
                    "status": "missing",
                    "message": "; ".join(messages) or "No target returned",
                }
            )

        if av_data.get("eps_estimate"):
            row["eps_estimate"] = str(av_data["eps_estimate"])
            row["estimate_source"] = "Alpha Vantage"
        if av_data.get("revenue_estimate"):
            row["revenue_estimate"] = str(av_data["revenue_estimate"])
            row["estimate_source"] = "Alpha Vantage"
        if av_data.get("news_sentiment"):
            row["news_sentiment"] = str(av_data["news_sentiment"])
            row["sentiment_source"] = "Alpha Vantage"

        row["provider_notes"] = " | ".join(messages)
        refreshed += 1
        print(
            f"{symbol}: price={row.get('current_price', '0')} "
            f"target={row.get('target_price', '0')} "
            f"price_source={row.get('price_source', '')} "
            f"target_source={row.get('target_source', '')}"
        )
        time.sleep(0.12)

    write_csv_atomic(RESEARCH_FILE, rows, fieldnames)
    gap_count = sum(1 for row in field_status if row["status"] != "ok")
    run_id = record_provider_run(
        "multi-provider",
        "ok" if refreshed else "failed",
        f"refreshed={refreshed}; gaps={gap_count}",
        field_status,
    )
    print(f"\nRefreshed {refreshed} symbols in {RESEARCH_FILE}")
    print(f"Recorded provider status run {run_id} with {gap_count} gaps")
    return 0 if refreshed else 1


def main() -> int:
    return refresh()


if __name__ == "__main__":
    sys.exit(main())
