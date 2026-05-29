#!/usr/bin/env python3
"""Curate shadow score signals from stored free data sources."""

from __future__ import annotations

import argparse
import math
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, stdev


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from engine_common import (  # noqa: E402
    DB_FILE,
    RESEARCH_FILE,
    init_db,
    read_csv,
    record_provider_payload,
    record_score_signals,
)


TODAY = datetime.now().date().isoformat()


def clamp(value: float, low: float = -5.0, high: float = 5.0) -> float:
    return max(low, min(high, value))


def parse_date(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    patterns = [
        ("%Y-%m-%dT%H:%M:%S", text[:19]),
        ("%Y-%m-%d %H:%M:%S", text[:19]),
        ("%Y-%m-%d", text[:10]),
        ("%Y%m%dT%H%M%S", text[:15]),
    ]
    for pattern, candidate in patterns:
        try:
            parsed = datetime.strptime(candidate, pattern)
            return parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def freshness_days(value: object) -> int | None:
    parsed = parse_date(value)
    if not parsed:
        return None
    return max((datetime.now(timezone.utc) - parsed).days, 0)


def research_symbols() -> list[str]:
    rows, _ = read_csv(RESEARCH_FILE)
    return [str(row.get("symbol") or "").strip().upper() for row in rows if row.get("symbol")]


def latest_price_rows(conn: sqlite3.Connection, symbol: str, limit: int = 260) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT price_date, close, volume, provider, fetched_at
        FROM price_history
        WHERE symbol = ?
        ORDER BY price_date DESC
        LIMIT ?
        """,
        (symbol, limit),
    ).fetchall()


def add_signal(
    rows: list[dict[str, object]],
    symbol: str,
    signal_type: str,
    metric_name: str,
    raw_value: float | None,
    normalized_delta: float,
    confidence: str,
    source_name: str,
    source_type: str,
    source_ref: str = "",
    freshness: int | None = None,
    notes: str = "",
) -> None:
    rows.append(
        {
            "symbol": symbol,
            "signal_date": TODAY,
            "signal_type": signal_type,
            "metric_name": metric_name,
            "raw_value": raw_value,
            "normalized_delta": round(clamp(normalized_delta), 3),
            "confidence": confidence,
            "source_name": source_name,
            "source_type": source_type,
            "source_ref": source_ref,
            "freshness_days": freshness,
            "signal_mode": "shadow",
            "notes": notes,
        }
    )


def technical_signals(conn: sqlite3.Connection, symbol: str) -> list[dict[str, object]]:
    signals: list[dict[str, object]] = []
    rows = latest_price_rows(conn, symbol)
    closes = [float(row["close"] or 0) for row in reversed(rows) if float(row["close"] or 0) > 0]
    if len(closes) < 25:
        return signals
    latest = closes[-1]
    source_ref = f"price_history:{symbol}:{rows[0]['provider'] if rows else ''}"
    if len(closes) >= 21:
        change_20 = ((latest - closes[-21]) / closes[-21]) * 100 if closes[-21] else 0
        add_signal(
            signals,
            symbol,
            "momentum",
            "20d_relative_strength",
            change_20,
            clamp(change_20 / 4, -3, 3),
            "medium",
            "Price history",
            "technical",
            source_ref,
            freshness_days(rows[0]["price_date"]),
            f"Latest close is {change_20:.1f}% versus roughly 20 trading days ago.",
        )
    sma50 = mean(closes[-50:]) if len(closes) >= 50 else mean(closes)
    sma200 = mean(closes[-200:]) if len(closes) >= 200 else None
    trend_delta = 0.0
    notes = [f"Close {latest:.2f}; 50d average {sma50:.2f}."]
    trend_delta += 1.5 if latest >= sma50 else -1.5
    if sma200:
        trend_delta += 1.5 if latest >= sma200 else -1.5
        notes.append(f"200d average {sma200:.2f}.")
    add_signal(
        signals,
        symbol,
        "momentum",
        "moving_average_trend",
        latest / sma50 if sma50 else None,
        trend_delta,
        "medium",
        "Price history",
        "technical",
        source_ref,
        freshness_days(rows[0]["price_date"]),
        " ".join(notes),
    )
    returns = []
    for previous, current in zip(closes[-22:-1], closes[-21:]):
        if previous:
            returns.append((current - previous) / previous)
    if len(returns) >= 10:
        volatility = stdev(returns) * math.sqrt(252) * 100 if len(returns) > 1 else 0
        delta = -2.5 if volatility >= 80 else -1.5 if volatility >= 55 else -0.5 if volatility >= 35 else 1.0
        add_signal(
            signals,
            symbol,
            "risk",
            "20d_annualized_volatility",
            volatility,
            delta,
            "medium",
            "Price history",
            "technical",
            source_ref,
            freshness_days(rows[0]["price_date"]),
            f"20-day annualized volatility estimate is {volatility:.1f}%.",
        )
    high_60 = max(closes[-60:]) if len(closes) >= 60 else max(closes)
    drawdown = ((latest - high_60) / high_60) * 100 if high_60 else 0
    add_signal(
        signals,
        symbol,
        "risk",
        "60d_drawdown_from_high",
        drawdown,
        clamp(drawdown / 6, -3, 0.5),
        "medium",
        "Price history",
        "technical",
        source_ref,
        freshness_days(rows[0]["price_date"]),
        f"Latest close is {abs(drawdown):.1f}% below the recent 60-day high.",
    )
    return signals


def sec_and_ir_signals(conn: sqlite3.Connection, symbol: str) -> list[dict[str, object]]:
    signals: list[dict[str, object]] = []
    rows = conn.execute(
        """
        SELECT id, evidence_type, source_name, source_type, source_timestamp, title, summary, confidence
        FROM research_evidence
        WHERE symbol = ?
          AND source_name IN ('SEC EDGAR submissions API', 'SEC EDGAR companyfacts API', 'Company investor relations')
        ORDER BY source_timestamp DESC, id DESC
        LIMIT 80
        """,
        (symbol,),
    ).fetchall()
    fact_count = sum(1 for row in rows if row["evidence_type"] == "sec_company_fact")
    if fact_count:
        add_signal(
            signals,
            symbol,
            "quality",
            "sec_fact_coverage",
            fact_count,
            clamp(fact_count / 4, 0, 3),
            "high",
            "SEC EDGAR companyfacts API",
            "SEC XBRL facts",
            f"research_evidence:{symbol}:sec_company_fact",
            None,
            f"{fact_count} SEC companyfact evidence rows are available for primary-source fundamental review.",
        )
    filing_count = 0
    recent_filing_count = 0
    for row in rows:
        if row["evidence_type"] != "sec_filing":
            continue
        filing_count += 1
        age = freshness_days(row["source_timestamp"])
        if age is not None and age <= 30:
            recent_filing_count += 1
    if filing_count:
        add_signal(
            signals,
            symbol,
            "catalyst",
            "recent_sec_filing_activity",
            recent_filing_count,
            clamp(recent_filing_count * 0.75, 0, 3),
            "high",
            "SEC EDGAR submissions API",
            "SEC filing",
            f"research_evidence:{symbol}:sec_filing",
            0 if recent_filing_count else None,
            f"{recent_filing_count} recent filing(s) within 30 days; {filing_count} filing rows tracked.",
        )
    ir_keywords = re.compile(r"earnings|results|quarter|annual|presentation|transcript|guidance|event", re.I)
    ir_hits = [
        row
        for row in rows
        if row["source_name"] == "Company investor relations"
        and ir_keywords.search(f"{row['title'] or ''} {row['summary'] or ''}")
    ]
    if ir_hits:
        newest_age = min((freshness_days(row["source_timestamp"]) or 9999) for row in ir_hits)
        add_signal(
            signals,
            symbol,
            "catalyst",
            "official_ir_event_links",
            len(ir_hits),
            clamp(len(ir_hits) * 0.4, 0, 2),
            "medium",
            "Company investor relations",
            "company release",
            f"research_evidence:{symbol}:official_ir",
            newest_age if newest_age != 9999 else None,
            f"{len(ir_hits)} official IR release/event/presentation lead(s) are available for review.",
        )
    return signals


def target_confidence_signals(conn: sqlite3.Connection, symbol: str) -> list[dict[str, object]]:
    rows = conn.execute(
        """
        SELECT target_type, source_name, confidence, created_at
        FROM target_sources
        WHERE symbol = ?
        ORDER BY id DESC
        LIMIT 12
        """,
        (symbol,),
    ).fetchall()
    if not rows:
        return []
    source_names = {str(row["source_name"] or "") for row in rows}
    target_types = {str(row["target_type"] or "") for row in rows}
    breadth = len(source_names | target_types)
    delta = 2.5 if {"analyst", "fundamental", "technical"}.issubset(target_types) else 1.2 if breadth >= 2 else -1.0
    signals: list[dict[str, object]] = []
    add_signal(
        signals,
        symbol,
        "confidence",
        "target_source_breadth",
        breadth,
        delta,
        "medium" if breadth >= 2 else "low",
        "Target source storage",
        "target blend",
        f"target_sources:{symbol}",
        freshness_days(rows[0]["created_at"]),
        f"{len(rows)} recent target rows from {len(source_names)} source(s) and {len(target_types)} target type(s).",
    )
    return signals


def news_signal_rows(conn: sqlite3.Connection, symbol: str) -> list[dict[str, object]]:
    rows = conn.execute(
        """
        SELECT id, evidence_type, source_name, source_type, source_timestamp, title, summary, confidence
        FROM research_evidence
        WHERE symbol = ?
          AND evidence_type IN ('news_sentiment', 'stock_news')
        ORDER BY source_timestamp DESC, id DESC
        LIMIT 20
        """,
        (symbol,),
    ).fetchall()
    signals: list[dict[str, object]] = []
    sentiments: list[float] = []
    for row in rows:
        match = re.search(r"Ticker sentiment [A-Za-z-]+ \((-?\d+(?:\.\d+)?)\)", str(row["summary"] or ""))
        if match:
            sentiments.append(float(match.group(1)))
    if sentiments:
        avg_sentiment = mean(sentiments)
        add_signal(
            signals,
            symbol,
            "catalyst",
            "avg_news_sentiment",
            avg_sentiment,
            clamp(avg_sentiment * 2.0, -1.5, 1.5),
            "low",
            "Alpha Vantage news sentiment",
            "news sentiment",
            f"research_evidence:{symbol}:news_sentiment",
            freshness_days(rows[0]["source_timestamp"]) if rows else None,
            f"Average Alpha Vantage ticker sentiment from {len(sentiments)} recent item(s).",
        )
    return signals


def curate(symbols: list[str], rebuild: bool) -> int:
    if not DB_FILE.exists():
        print("No SQLite database found yet.")
        return 0
    conn = init_db()
    conn.row_factory = sqlite3.Row
    signals: list[dict[str, object]] = []
    for symbol in symbols:
        signals.extend(technical_signals(conn, symbol))
        signals.extend(sec_and_ir_signals(conn, symbol))
        signals.extend(target_confidence_signals(conn, symbol))
        signals.extend(news_signal_rows(conn, symbol))
    conn.close()
    inserted = record_score_signals(signals, rebuild=rebuild)
    record_provider_payload(
        provider="Local score signal curator",
        endpoint="score_signals",
        symbol="MARKET",
        status="ok",
        message=f"symbols={len(symbols)}; signals={len(signals)}; inserted={inserted}; shadow_mode=true",
        payload_json={
            "symbols": symbols,
            "signals": len(signals),
            "shadow_mode": True,
            "signal_date": TODAY,
        },
    )
    print(f"Score signal curation complete: symbols={len(symbols)} signals={len(signals)} inserted={inserted}")
    return inserted


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Curate shadow score signals from stored data.")
    parser.add_argument("--symbols", help="Comma-separated symbols. Defaults to V1 universe.")
    parser.add_argument("--rebuild", action="store_true", help="Rebuild all shadow score signals.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    symbols = (
        [symbol.strip().upper() for symbol in args.symbols.split(",") if symbol.strip()]
        if args.symbols
        else research_symbols()
    )
    curate(symbols, rebuild=args.rebuild)
    return 0


if __name__ == "__main__":
    sys.exit(main())
