#!/usr/bin/env python3
"""Ingest V1.4 research-depth evidence from current/free providers."""

from __future__ import annotations

import argparse
import os
import re
import sqlite3
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Mapping
from urllib.parse import urlencode


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from engine_common import (  # noqa: E402
    RESEARCH_FILE,
    load_env,
    load_targets,
    read_csv,
    record_provider_payload,
    record_provider_run,
    record_research_evidence,
    DB_FILE,
    init_db,
)
from provider_client import fetch_json_url, sanitize_provider_message  # noqa: E402


ALPHA_VANTAGE_BASE = "https://www.alphavantage.co/query"
FMP_STABLE_BASE = "https://financialmodelingprep.com/stable"
REQUEST_TIMEOUT_SECONDS = 20


def get_json(url: str) -> object:
    result = fetch_json_url(
        url,
        headers={"User-Agent": "StockTradingResearch/0.1"},
        timeout=REQUEST_TIMEOUT_SECONDS,
        retries=2,
    )
    if result.status != "ok":
        raise RuntimeError(result.message or result.status)
    return result.payload


def fetch_json(provider: str, endpoint: str, url: str, symbol: str) -> tuple[str, object, str]:
    result = fetch_json_url(
        url,
        headers={"User-Agent": "StockTradingResearch/0.1"},
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


def evidence_limits() -> dict[str, int]:
    targets = load_targets()
    defaults = {
        "max_news_per_symbol": 5,
        "max_transcripts_per_symbol": 2,
        "fresh_evidence_days": 14,
        "alpha_vantage_daily_symbol_budget": 8,
        "alpha_vantage_min_refresh_hours": 72,
    }
    config = targets.get("research_depth", {})
    if not isinstance(config, dict):
        return defaults
    limits = config.get("evidence_limits", {})
    if not isinstance(limits, dict):
        return defaults
    return {key: int(limits.get(key, value) or value) for key, value in defaults.items()}


def parse_db_time(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        try:
            return datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except ValueError:
            return None


def alpha_last_success_by_symbol() -> dict[str, datetime]:
    if not DB_FILE.exists():
        return {}
    conn = init_db()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT symbol, MAX(created_at) AS last_success
        FROM provider_payloads
        WHERE provider = 'Alpha Vantage'
          AND endpoint = 'NEWS_SENTIMENT'
          AND status = 'ok'
        GROUP BY symbol
        """
    ).fetchall()
    conn.close()
    updates: dict[str, datetime] = {}
    for row in rows:
        parsed = parse_db_time(row["last_success"])
        if parsed:
            updates[str(row["symbol"]).upper()] = parsed
    return updates


def alpha_symbols_for_run(symbols: list[str], limits: dict[str, int]) -> set[str]:
    budget = max(0, int(limits.get("alpha_vantage_daily_symbol_budget", 0) or 0))
    if budget <= 0:
        return set()
    last_success = alpha_last_success_by_symbol()
    min_hours = max(0, int(limits.get("alpha_vantage_min_refresh_hours", 0) or 0))
    now = datetime.now(timezone.utc)

    def sort_key(symbol: str) -> tuple[int, float, str]:
        last = last_success.get(symbol)
        if last is None:
            return (0, 0.0, symbol)
        age_hours = (now - last).total_seconds() / 3600
        stale_rank = 0 if age_hours >= min_hours else 1
        return (stale_rank, -age_hours, symbol)

    ordered = sorted([symbol.upper() for symbol in symbols], key=sort_key)
    return set(ordered[: min(budget, len(ordered))])


def alpha_vantage_news_url(symbol: str, api_key: str, limit: int) -> str:
    return (
        f"{ALPHA_VANTAGE_BASE}?"
        + urlencode(
            {
                "function": "NEWS_SENTIMENT",
                "tickers": symbol,
                "sort": "LATEST",
                "limit": limit,
                "apikey": api_key,
            }
        )
    )


def fmp_stock_news_url(symbol: str, api_key: str, limit: int) -> str:
    return (
        f"{FMP_STABLE_BASE}/news/stock-latest?"
        + urlencode({"symbols": symbol, "page": 0, "limit": limit, "apikey": api_key})
    )


def fmp_transcript_url(symbol: str, api_key: str, year: int, quarter: int) -> str:
    return (
        f"{FMP_STABLE_BASE}/earning-call-transcript?"
        + urlencode({"symbol": symbol, "year": year, "quarter": quarter, "apikey": api_key})
    )


def fmp_transcript_dates_url(symbol: str, api_key: str) -> str:
    return (
        f"{FMP_STABLE_BASE}/earning-call-transcript-dates?"
        + urlencode({"symbol": symbol, "apikey": api_key})
    )


def fmp_latest_transcripts_url(api_key: str, limit: int) -> str:
    return (
        f"{FMP_STABLE_BASE}/earning-call-transcript-latest?"
        + urlencode({"page": 0, "limit": limit, "apikey": api_key})
    )


def alpha_vantage_news_evidence(
    symbol: str,
    payload: object,
    limit: int,
) -> list[dict[str, object]]:
    if not isinstance(payload, dict):
        return []
    feed = payload.get("feed", [])
    if not isinstance(feed, list):
        return []
    rows = []
    for item in feed[:limit]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        summary = str(item.get("summary") or "").strip()
        url = str(item.get("url") or "").strip()
        ticker_sentiment = ""
        ticker_relevance = 0.0
        for sentiment in item.get("ticker_sentiment", []):
            if isinstance(sentiment, dict) and sentiment.get("ticker") == symbol:
                ticker_relevance = to_float(sentiment.get("relevance_score"))
                ticker_sentiment = (
                    f"Ticker sentiment {sentiment.get('ticker_sentiment_label', '')} "
                    f"({sentiment.get('ticker_sentiment_score', '')}); "
                    f"relevance {sentiment.get('relevance_score', '')}."
                ).strip()
                break
        if not ticker_sentiment or ticker_relevance < 0.15:
            continue
        if not title and not summary:
            continue
        rows.append(
            {
                "run_id": None,
                "symbol": symbol,
                "evidence_type": "news_sentiment",
                "source_name": "Alpha Vantage news sentiment",
                "source_type": "news sentiment",
                "source_url": url,
                "provider_endpoint": "NEWS_SENTIMENT",
                "provider_id": str(item.get("url") or item.get("time_published") or title),
                "source_timestamp": str(item.get("time_published") or ""),
                "title": title,
                "summary": f"{summary[:650]} {ticker_sentiment}".strip(),
                "raw_text_ref": "",
                "confidence": "medium",
                "corroboration_status": "needs_corroboration",
                "user_feedback": "",
            }
        )
    return rows


def to_float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def fmp_news_evidence(symbol: str, payload: object, limit: int) -> list[dict[str, object]]:
    if not isinstance(payload, list):
        return []
    rows = []
    for item in payload[:limit]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        summary = str(item.get("text") or item.get("summary") or "").strip()
        if not title and not summary:
            continue
        url = str(item.get("url") or "").strip()
        published = str(item.get("publishedDate") or item.get("date") or "")
        rows.append(
            {
                "run_id": None,
                "symbol": symbol,
                "evidence_type": "stock_news",
                "source_name": "FMP stock news",
                "source_type": "news",
                "source_url": url,
                "provider_endpoint": "stock_news",
                "provider_id": str(url or f"{symbol}-{published}-{title}"),
                "source_timestamp": published,
                "title": title,
                "summary": summary[:700],
                "raw_text_ref": "",
                "confidence": "medium",
                "corroboration_status": "needs_corroboration",
                "user_feedback": "",
            }
        )
    return rows


def fmp_transcript_evidence(symbol: str, payload: object, limit: int) -> list[dict[str, object]]:
    if isinstance(payload, dict):
        items = [payload]
    elif isinstance(payload, list):
        items = [item for item in payload if isinstance(item, dict)]
    else:
        return []
    rows = []
    for item in items[:limit]:
        content = str(item.get("content") or item.get("transcript") or "").strip()
        if not content:
            continue
        quarter = str(item.get("quarter") or "")
        year = str(item.get("year") or "")
        date_text = str(item.get("date") or item.get("publishedDate") or "")
        rows.append(
            {
                "run_id": None,
                "symbol": symbol,
                "evidence_type": "earnings_transcript",
                "source_name": "FMP earnings transcripts",
                "source_type": "earnings transcript",
                "source_url": "",
                "provider_endpoint": "earning-call-transcript",
                "provider_id": f"{symbol}-{year}-Q{quarter}-{date_text}",
                "source_timestamp": date_text or f"{year} Q{quarter}".strip(),
                "title": f"{symbol} earnings call transcript {year} Q{quarter}".strip(),
                "summary": content[:900],
                "raw_text_ref": "",
                "confidence": "medium",
                "corroboration_status": "management_commentary",
                "user_feedback": "",
            }
        )
    return rows


def fmp_transcript_periods(payload: object, limit: int) -> list[tuple[int, int]]:
    if not isinstance(payload, list):
        return []
    periods: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    for item in payload:
        year = None
        quarter = None
        if isinstance(item, dict):
            year = item.get("year")
            quarter = item.get("quarter")
            if quarter is None:
                quarter = item.get("fiscalQuarter")
        elif isinstance(item, str):
            text = item.upper()
            year_match = re.search(r"(20\d{2})", text)
            quarter_match = re.search(r"Q([1-4])", text)
            if year_match:
                year = year_match.group(1)
            if quarter_match:
                quarter = quarter_match.group(1)
        try:
            period = (int(year), int(str(quarter).replace("Q", "").strip()))
        except (TypeError, ValueError):
            continue
        if period[1] not in {1, 2, 3, 4} or period in seen:
            continue
        seen.add(period)
        periods.append(period)
        if len(periods) >= limit:
            break
    return periods


def transcript_quarters(today: date, count: int) -> list[tuple[int, int]]:
    year = today.year
    quarter = ((today.month - 1) // 3) + 1
    quarters = []
    for _ in range(count + 2):
        quarters.append((year, quarter))
        quarter -= 1
        if quarter == 0:
            year -= 1
            quarter = 4
    return quarters


def ingest_symbol(
    symbol: str,
    alpha_key: str,
    fmp_key: str,
    limits: dict[str, int],
    allow_alpha: bool = True,
) -> tuple[int, list[dict[str, object]]]:
    evidence: list[dict[str, object]] = []
    statuses: list[dict[str, object]] = []
    max_news = limits["max_news_per_symbol"]
    max_transcripts = limits["max_transcripts_per_symbol"]

    if alpha_key and allow_alpha:
        endpoint = "NEWS_SENTIMENT"
        status, payload, message = fetch_json(
            "Alpha Vantage",
            endpoint,
            alpha_vantage_news_url(symbol, alpha_key, max_news),
            symbol,
        )
        record_provider_payload(
            "Alpha Vantage",
            endpoint,
            symbol,
            status,
            message,
            payload_json=payload if status == "ok" else None,
        )
        if status == "ok":
            evidence.extend(alpha_vantage_news_evidence(symbol, payload, max_news))
        statuses.append(
            {
                "symbol": symbol,
                "provider": "Alpha Vantage",
                "field_name": "news_sentiment",
                "status": status,
                "message": message,
            }
        )
    if fmp_key:
        endpoint = "stock_news"
        status, payload, message = fetch_json(
            "FMP",
            endpoint,
            fmp_stock_news_url(symbol, fmp_key, max_news),
            symbol,
        )
        record_provider_payload(
            "FMP",
            endpoint,
            symbol,
            status,
            message,
            payload_json=payload if status == "ok" else None,
        )
        if status == "ok":
            evidence.extend(fmp_news_evidence(symbol, payload, max_news))
        statuses.append(
            {
                "symbol": symbol,
                "provider": "FMP",
                "field_name": "stock_news",
                "status": status,
                "message": message,
            }
        )

        transcript_rows = []
        transcript_status = "missing"
        transcript_message = "No transcript returned from FMP transcript endpoints"
        status, payload, message = fetch_json(
            "FMP",
            "earning-call-transcript-dates",
            fmp_transcript_dates_url(symbol, fmp_key),
            symbol,
        )
        record_provider_payload(
            "FMP",
            "earning-call-transcript-dates",
            symbol,
            status,
            message,
            payload_json=payload if status == "ok" else None,
        )
        if status != "ok":
            transcript_status = status
            transcript_message = f"Transcript dates endpoint failed: {message}"
        else:
            transcript_periods = fmp_transcript_periods(payload, max_transcripts)
            if not transcript_periods:
                transcript_status = "missing"
                transcript_message = "FMP transcript dates endpoint returned no usable year/quarter values"
            else:
                transcript_status = "ok"
                transcript_message = ""

        for year, quarter in (transcript_periods if transcript_status == "ok" else []):
            status, payload, message = fetch_json(
                "FMP",
                "earning-call-transcript",
                fmp_transcript_url(symbol, fmp_key, year, quarter),
                symbol,
            )
            record_provider_payload(
                "FMP",
                "earning-call-transcript",
                symbol,
                status,
                message,
                payload_json=payload if status == "ok" else None,
            )
            if status != "ok":
                transcript_status = status
                transcript_message = message
                break
            rows = fmp_transcript_evidence(symbol, payload, max_transcripts)
            transcript_rows.extend(rows)
            if len(transcript_rows) >= max_transcripts:
                transcript_status = "ok"
                transcript_message = ""
                break
            time.sleep(0.1)
        evidence.extend(transcript_rows[:max_transcripts])
        statuses.append(
            {
                "symbol": symbol,
                "provider": "FMP",
                "field_name": "earnings_transcripts",
                "status": transcript_status if transcript_rows else transcript_status,
                "message": "" if transcript_rows else transcript_message,
            }
        )

    inserted = record_research_evidence(evidence)
    return inserted, statuses


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest V1.4 research-depth evidence.")
    parser.add_argument("--symbols", help="Comma-separated symbols. Defaults to V1 universe.")
    parser.add_argument("--delay", type=float, default=0.25, help="Delay between symbols.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_env()
    alpha_key = os.environ.get("ALPHA_VANTAGE_API_KEY", "").strip()
    fmp_key = os.environ.get("FMP_API_KEY", "").strip()
    if not alpha_key and not fmp_key:
        print("Missing ALPHA_VANTAGE_API_KEY or FMP_API_KEY in .env.")
        return 1

    symbols = (
        [symbol.strip().upper() for symbol in args.symbols.split(",") if symbol.strip()]
        if args.symbols
        else symbols_from_research()
    )
    limits = evidence_limits()
    alpha_symbols = alpha_symbols_for_run(symbols, limits) if alpha_key else set()
    if alpha_key:
        print(
            "Alpha Vantage NEWS_SENTIMENT budget: "
            f"{len(alpha_symbols)}/{len(symbols)} symbols this run; "
            f"selected={','.join(sorted(alpha_symbols))}",
            flush=True,
        )
    all_statuses: list[dict[str, object]] = []
    total_inserted = 0

    for index, symbol in enumerate(symbols, start=1):
        inserted, statuses = ingest_symbol(
            symbol,
            alpha_key,
            fmp_key,
            limits,
            allow_alpha=(symbol in alpha_symbols if alpha_key else False),
        )
        total_inserted += inserted
        all_statuses.extend(statuses)
        print(f"{symbol}: inserted_research_depth={inserted}", flush=True)
        if index < len(symbols) and args.delay > 0:
            time.sleep(args.delay)

    gaps = sum(1 for row in all_statuses if row.get("status") != "ok")
    run_id = record_provider_run(
        "V1.4 research depth",
        "ok" if all_statuses else "failed",
        f"symbols={len(symbols)}; inserted_evidence={total_inserted}; gaps={gaps}",
        all_statuses,
    )
    print(f"Recorded V1.4 research-depth provider run {run_id} with {gaps} gaps")
    return 0 if all_statuses else 1


if __name__ == "__main__":
    sys.exit(main())
