#!/usr/bin/env python3
"""Ingest Finnhub free-key endpoint data into SQLite evidence tables."""

from __future__ import annotations

import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable, Mapping
from urllib.parse import urlencode


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from engine_common import (  # noqa: E402
    load_env,
    read_csv,
    record_provider_payload,
    record_provider_run,
    record_research_evidence,
    RESEARCH_FILE,
)
from provider_client import fetch_json_url, sanitize_provider_message  # noqa: E402


FINNHUB_BASE = "https://finnhub.io/api/v1"
NEWS_LIMIT_PER_SYMBOL = 8
REQUEST_TIMEOUT_SECONDS = 12


def get_json(path: str, params: Mapping[str, object], api_key: str) -> object:
    query = urlencode({**params, "token": api_key})
    result = fetch_json_url(
        f"{FINNHUB_BASE}/{path}?{query}",
        timeout=REQUEST_TIMEOUT_SECONDS,
        retries=2,
    )
    if result.status != "ok":
        raise RuntimeError(result.message or result.status)
    return result.payload


def fetch_endpoint(
    path: str,
    params: Mapping[str, object],
    api_key: str,
) -> tuple[str, object, str]:
    query = urlencode({**params, "token": api_key})
    result = fetch_json_url(
        f"{FINNHUB_BASE}/{path}?{query}",
        timeout=REQUEST_TIMEOUT_SECONDS,
        retries=2,
    )
    message = result.message
    if result.error_class:
        message = f"{message}; error_class={result.error_class}; attempts={result.attempts}".strip("; ")
    elif result.attempts > 1:
        message = f"{message}; attempts={result.attempts}".strip("; ")
    return result.status, result.payload, sanitize_provider_message(message)


def symbols_from_research() -> list[str]:
    rows, _ = read_csv(RESEARCH_FILE)
    return [row["symbol"].strip().upper() for row in rows if row.get("symbol")]


def from_unix(value: object) -> str:
    try:
        return datetime.fromtimestamp(int(value)).isoformat(timespec="seconds")
    except (TypeError, ValueError, OSError):
        return ""


def news_evidence(symbol: str, payload: object) -> list[dict[str, object]]:
    rows = []
    if not isinstance(payload, list):
        return rows
    for item in payload[:NEWS_LIMIT_PER_SYMBOL]:
        if not isinstance(item, dict):
            continue
        provider_id = str(item.get("id") or item.get("url") or "")
        title = str(item.get("headline") or "").strip()
        summary = str(item.get("summary") or "").strip()
        if not title and not summary:
            continue
        rows.append(
            {
                "run_id": None,
                "symbol": symbol,
                "evidence_type": "company_news",
                "source_name": "Finnhub company news",
                "source_type": "news",
                "source_url": item.get("url", ""),
                "provider_endpoint": "company-news",
                "provider_id": provider_id,
                "source_timestamp": from_unix(item.get("datetime")),
                "title": title,
                "summary": summary[:700],
                "raw_text_ref": "",
                "confidence": "medium",
                "corroboration_status": "needs_corroboration",
                "user_feedback": "",
            }
        )
    return rows


def recommendation_evidence(symbol: str, payload: object) -> list[dict[str, object]]:
    if not isinstance(payload, list) or not payload:
        return []
    latest = payload[0]
    if not isinstance(latest, dict):
        return []
    period = str(latest.get("period", "") or "")
    summary = (
        f"Recommendation trend for {period}: "
        f"strongBuy={latest.get('strongBuy', 0)}, buy={latest.get('buy', 0)}, "
        f"hold={latest.get('hold', 0)}, sell={latest.get('sell', 0)}, "
        f"strongSell={latest.get('strongSell', 0)}."
    )
    return [
        {
            "run_id": None,
            "symbol": symbol,
            "evidence_type": "recommendation_trend",
            "source_name": "Finnhub recommendation trends",
            "source_type": "analyst",
            "source_url": "",
            "provider_endpoint": "stock/recommendation",
            "provider_id": f"{symbol}-{period}",
            "source_timestamp": period,
            "title": f"{symbol} analyst recommendation trend",
            "summary": summary,
            "raw_text_ref": "",
            "confidence": "medium",
            "corroboration_status": "provider_aggregate",
            "user_feedback": "",
        }
    ]


def earnings_calendar_evidence(symbol: str, payload: object) -> list[dict[str, object]]:
    if not isinstance(payload, dict):
        return []
    events = payload.get("earningsCalendar", [])
    if not isinstance(events, list):
        return []
    rows = []
    for event in events[:3]:
        if not isinstance(event, dict):
            continue
        event_date = str(event.get("date") or "")
        if not event_date:
            continue
        rows.append(
            {
                "run_id": None,
                "symbol": symbol,
                "evidence_type": "earnings_calendar",
                "source_name": "Finnhub earnings calendar",
                "source_type": "earnings_calendar",
                "source_url": "",
                "provider_endpoint": "calendar/earnings",
                "provider_id": f"{symbol}-{event_date}",
                "source_timestamp": event_date,
                "title": f"{symbol} earnings calendar: {event_date}",
                "summary": (
                    f"Earnings calendar event on {event_date}; "
                    f"EPS estimate={event.get('epsEstimate', '')}, "
                    f"revenue estimate={event.get('revenueEstimate', '')}."
                ),
                "raw_text_ref": "",
                "confidence": "medium",
                "corroboration_status": "provider_calendar",
                "user_feedback": "",
            }
        )
    return rows


def ingest_symbol(symbol: str, api_key: str, days: int) -> tuple[int, list[dict[str, object]]]:
    today = date.today()
    from_date = today - timedelta(days=days)
    endpoints: list[tuple[str, str, dict[str, object]]] = [
        ("quote", "quote", {"symbol": symbol}),
        ("company_profile", "stock/profile2", {"symbol": symbol}),
        (
            "company_news",
            "company-news",
            {"symbol": symbol, "from": from_date.isoformat(), "to": today.isoformat()},
        ),
        ("recommendation_trends", "stock/recommendation", {"symbol": symbol}),
        ("earnings_calendar", "calendar/earnings", {"symbol": symbol}),
    ]
    evidence: list[dict[str, object]] = []
    field_status: list[dict[str, object]] = []
    for name, path, params in endpoints:
        status, payload, message = fetch_endpoint(path, params, api_key)
        record_provider_payload(
            provider="Finnhub",
            endpoint=path,
            symbol=symbol,
            status=status,
            message=message,
            payload_json=payload if name in {"quote", "company_profile", "recommendation_trends", "earnings_calendar"} else None,
        )
        field_status.append(
            {
                "symbol": symbol,
                "provider": "Finnhub",
                "field_name": name,
                "status": status,
                "message": message,
            }
        )
        if status == "ok":
            if name == "company_news":
                evidence.extend(news_evidence(symbol, payload))
            elif name == "recommendation_trends":
                evidence.extend(recommendation_evidence(symbol, payload))
            elif name == "earnings_calendar":
                evidence.extend(earnings_calendar_evidence(symbol, payload))
        time.sleep(0.12)
    inserted = record_research_evidence(evidence)
    return inserted, field_status


def main() -> int:
    load_env()
    api_key = os.environ.get("FINNHUB_API_KEY", "").strip()
    if not api_key:
        print("Missing FINNHUB_API_KEY in .env")
        return 1

    symbols = sys.argv[1:] if len(sys.argv) > 1 else symbols_from_research()
    symbols = [symbol.upper() for symbol in symbols]
    all_status: list[dict[str, object]] = []
    total_inserted = 0
    for symbol in symbols:
        inserted, status_rows = ingest_symbol(symbol, api_key, days=30)
        total_inserted += inserted
        all_status.extend(status_rows)
        print(f"{symbol}: inserted_evidence={inserted}", flush=True)

    gaps = sum(1 for row in all_status if row["status"] != "ok")
    run_id = record_provider_run(
        "Finnhub",
        "ok" if all_status else "failed",
        f"symbols={len(symbols)}; inserted_evidence={total_inserted}; gaps={gaps}",
        all_status,
    )
    print(f"Recorded Finnhub provider run {run_id} with {gaps} gaps")
    return 0 if all_status else 1


if __name__ == "__main__":
    sys.exit(main())
