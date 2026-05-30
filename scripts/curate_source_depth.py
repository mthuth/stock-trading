#!/usr/bin/env python3
"""Curate normalized source-depth evidence from stored primary/source rows."""

from __future__ import annotations

import argparse
import hashlib
import re
import sqlite3
import sys
from datetime import date
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from stock_trading import storage  # noqa: E402


CURATOR_SOURCE = "Local source depth curator"
CURATOR_ENDPOINT = "source_depth_curator"
SEC_FACT_RE = re.compile(
    r"^(?P<label>[^:]+):\s*(?P<value>.*?)\s+for period ending\s+"
    r"(?P<period>\d{4}-\d{2}-\d{2})\s+from\s+(?P<form>[^.]+)",
    flags=re.IGNORECASE,
)
SEC_FILING_RE = re.compile(
    r"^(?P<form>[0-9A-Z/-]+)\s+filing\s+for report date\s+"
    r"(?P<period>[^.]+)",
    flags=re.IGNORECASE,
)
IR_KEYWORDS = {
    "earnings_release": ("earnings", "results", "quarterly results", "financial results"),
    "earnings_presentation": ("presentation", "slides", "investor presentation"),
    "annual_report": ("annual report", "10-k", "form 10-k"),
    "transcript": ("transcript", "call transcript"),
    "guidance": ("guidance", "outlook"),
    "investor_event": ("conference", "event", "webcast", "investor day"),
}
OFFICIAL_EVENT_KEYWORDS = {
    "product_launch": ("launch", "introduce", "announces", "unveils", "available now"),
    "ai_platform_update": ("ai", "model", "agent", "copilot", "gemini", "bedrock", "cuda", "blackwell"),
    "infrastructure_update": ("cloud", "data center", "accelerator", "gpu", "chip", "semiconductor"),
    "customer_partner": ("customer", "partner", "collaboration", "alliance"),
    "security_research": ("security", "threat", "vulnerability", "incident"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Curate source-depth evidence from stored rows.")
    parser.add_argument("--rebuild", action="store_true", help="Replace existing source-depth rows.")
    parser.add_argument("--symbols", default="", help="Optional comma-separated symbol filter.")
    parser.add_argument("--limit-per-symbol", type=int, default=24, help="Maximum rows per symbol per depth family.")
    return parser.parse_args()


def clean_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def snake(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or "unknown"


def stable_provider_id(*parts: object) -> str:
    raw = "|".join(clean_text(part) for part in parts)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"source-depth:{digest}"


def source_timestamp(row: sqlite3.Row) -> str:
    return clean_text(row["source_timestamp"]) or clean_text(row["fetched_at"]) or date.today().isoformat()


def evidence_row(
    symbol: str,
    evidence_type: str,
    title: str,
    summary: str,
    source_url: str,
    provider_id: str,
    source_timestamp_value: str,
    confidence: str = "high",
    corroboration: str = "curated_from_primary_source",
) -> dict[str, object]:
    return {
        "run_id": None,
        "symbol": symbol,
        "evidence_type": evidence_type,
        "source_name": CURATOR_SOURCE,
        "source_type": "curated_source_depth",
        "source_url": source_url or f"local://{provider_id}",
        "provider_endpoint": CURATOR_ENDPOINT,
        "provider_id": provider_id,
        "source_timestamp": source_timestamp_value,
        "title": title,
        "summary": summary,
        "raw_text_ref": "",
        "confidence": confidence,
        "corroboration_status": corroboration,
        "user_feedback": "",
    }


def load_direct_symbol_sources() -> dict[str, str]:
    path = storage.CONFIG_DIR / "symbol_aliases.csv"
    if not path.exists():
        return {}
    rows, _ = storage.read_csv(path)
    sources: dict[str, str] = {}
    for row in rows:
        if clean_text(row.get("match_type")) != "direct_symbol":
            continue
        source_name = clean_text(row.get("source_name"))
        symbol = clean_text(row.get("symbol")).upper()
        if source_name and symbol:
            sources[source_name] = symbol
    return sources


def load_product_aliases() -> dict[str, list[str]]:
    path = storage.CONFIG_DIR / "symbol_aliases.csv"
    if not path.exists():
        return {}
    rows, _ = storage.read_csv(path)
    aliases: dict[str, list[str]] = {}
    for row in rows:
        if clean_text(row.get("match_type")) != "product_alias":
            continue
        symbol = clean_text(row.get("symbol")).upper()
        alias = clean_text(row.get("alias")).lower()
        if symbol and alias:
            aliases.setdefault(symbol, []).append(alias)
    return aliases


def symbol_filter_clause(symbols: set[str]) -> tuple[str, tuple[str, ...]]:
    if not symbols:
        return "", ()
    placeholders = ",".join("?" for _ in symbols)
    return f" AND symbol IN ({placeholders})", tuple(sorted(symbols))


def classify_sec_metric(label: str, title: str) -> str:
    text = f"{label} {title}".lower()
    mapping = [
        ("revenue_growth_input", ("revenue",)),
        ("eps_trend_input", ("earnings per share", "eps")),
        ("operating_margin_input", ("operating income", "operating margin")),
        ("free_cash_flow_input", ("cash flow", "operating cash")),
        ("balance_sheet_input", ("assets", "liabilities", "equity")),
        ("dilution_input", ("shares", "share count", "diluted shares")),
        ("profitability_input", ("net income",)),
    ]
    for metric, terms in mapping:
        if any(term in text for term in terms):
            return metric
    return snake(label)


def curate_sec_facts(conn: sqlite3.Connection, symbols: set[str], limit_per_symbol: int) -> list[dict[str, object]]:
    clause, params = symbol_filter_clause(symbols)
    rows = conn.execute(
        f"""
        SELECT id, symbol, title, summary, source_url, provider_id, source_timestamp, fetched_at
        FROM research_evidence
        WHERE evidence_type = 'sec_company_fact'
          AND source_name != ?
          {clause}
        ORDER BY symbol, source_timestamp DESC, id DESC
        """,
        (CURATOR_SOURCE, *params),
    ).fetchall()
    counts: dict[str, int] = {}
    curated: list[dict[str, object]] = []
    for row in rows:
        symbol = clean_text(row["symbol"]).upper()
        if counts.get(symbol, 0) >= limit_per_symbol:
            continue
        match = SEC_FACT_RE.search(clean_text(row["summary"]))
        label = clean_text(match.group("label")) if match else clean_text(row["title"]).replace(symbol, "").strip()
        value = clean_text(match.group("value")) if match else ""
        period = clean_text(match.group("period")) if match else source_timestamp(row)
        form = clean_text(match.group("form")) if match else "SEC filing"
        metric = classify_sec_metric(label, clean_text(row["title"]))
        title = f"{symbol} SEC depth: {metric.replace('_', ' ')}"
        summary = (
            f"{label or metric} from {form} for period ending {period}. "
            f"Latest stored value: {value or 'available in source row'}. "
            "Primary-source fundamental input for future quality/risk validation; no current score impact."
        )
        curated.append(
            evidence_row(
                symbol,
                "sec_fundamental_depth_signal",
                title,
                summary,
                clean_text(row["source_url"]),
                stable_provider_id(symbol, "sec_fact", metric, period, row["provider_id"] or row["id"]),
                period,
                confidence="high",
                corroboration="curated_from_sec_companyfacts",
            )
        )
        counts[symbol] = counts.get(symbol, 0) + 1
    return curated


def classify_filing(form: str) -> str:
    normalized = form.upper()
    if "10-K" in normalized or "20-F" in normalized:
        return "annual_report"
    if "10-Q" in normalized:
        return "quarterly_report"
    if "8-K" in normalized or "6-K" in normalized:
        return "current_report"
    return "filing_event"


def curate_sec_filings(conn: sqlite3.Connection, symbols: set[str], limit_per_symbol: int) -> list[dict[str, object]]:
    clause, params = symbol_filter_clause(symbols)
    rows = conn.execute(
        f"""
        SELECT id, symbol, title, summary, source_url, provider_id, source_timestamp, fetched_at
        FROM research_evidence
        WHERE evidence_type = 'sec_filing'
          AND source_name != ?
          {clause}
        ORDER BY symbol, source_timestamp DESC, id DESC
        """,
        (CURATOR_SOURCE, *params),
    ).fetchall()
    counts: dict[str, int] = {}
    curated: list[dict[str, object]] = []
    for row in rows:
        symbol = clean_text(row["symbol"]).upper()
        if counts.get(symbol, 0) >= max(6, limit_per_symbol // 2):
            continue
        match = SEC_FILING_RE.search(clean_text(row["summary"]))
        form = clean_text(match.group("form")) if match else clean_text(row["title"]).split()[0]
        period = clean_text(match.group("period")) if match else source_timestamp(row)
        filing_type = classify_filing(form)
        curated.append(
            evidence_row(
                symbol,
                "sec_filing_depth_signal",
                f"{symbol} SEC depth: {filing_type.replace('_', ' ')}",
                (
                    f"{form} filing tracked for {period}. "
                    "Primary-source filing timeline item for catalyst/risk review; no current score impact."
                ),
                clean_text(row["source_url"]),
                stable_provider_id(symbol, "sec_filing", filing_type, row["provider_id"] or row["id"]),
                source_timestamp(row),
                confidence="high",
                corroboration="curated_from_sec_submissions",
            )
        )
        counts[symbol] = counts.get(symbol, 0) + 1
    return curated


def classify_by_keywords(text: str, keyword_map: dict[str, tuple[str, ...]], fallback: str) -> str:
    lowered = text.lower()
    for label, terms in keyword_map.items():
        if any(term in lowered for term in terms):
            return label
    return fallback


def curate_ir_depth(conn: sqlite3.Connection, symbols: set[str], limit_per_symbol: int) -> list[dict[str, object]]:
    clause, params = symbol_filter_clause(symbols)
    rows = conn.execute(
        f"""
        SELECT id, symbol, title, summary, source_url, provider_id, source_timestamp, fetched_at
        FROM research_evidence
        WHERE evidence_type IN ('official_ir_link', 'official_ir_page_snapshot')
          AND source_name != ?
          {clause}
        ORDER BY symbol, source_timestamp DESC, id DESC
        """,
        (CURATOR_SOURCE, *params),
    ).fetchall()
    counts: dict[str, int] = {}
    curated: list[dict[str, object]] = []
    for row in rows:
        symbol = clean_text(row["symbol"]).upper()
        if counts.get(symbol, 0) >= limit_per_symbol:
            continue
        combined = f"{row['title']} {row['summary']} {row['source_url']}"
        depth_type = classify_by_keywords(combined, IR_KEYWORDS, "investor_relations_update")
        curated.append(
            evidence_row(
                symbol,
                "official_ir_depth_signal",
                f"{symbol} IR depth: {depth_type.replace('_', ' ')}",
                (
                    f"Official IR item classified as {depth_type.replace('_', ' ')}. "
                    f"Source title: {clean_text(row['title']) or 'IR page snapshot'}. "
                    "Company-framed primary-source context; no current score impact."
                ),
                clean_text(row["source_url"]),
                stable_provider_id(symbol, "ir", depth_type, row["provider_id"] or row["id"]),
                source_timestamp(row),
                confidence="medium_high",
                corroboration="curated_from_official_ir",
            )
        )
        counts[symbol] = counts.get(symbol, 0) + 1
    return curated


def curate_official_company_depth(
    conn: sqlite3.Connection,
    symbols: set[str],
    limit_per_symbol: int,
    direct_sources: dict[str, str],
    product_aliases: dict[str, list[str]],
) -> list[dict[str, object]]:
    if not direct_sources:
        return []
    source_names = sorted(direct_sources)
    placeholders = ",".join("?" for _ in source_names)
    clause, params = symbol_filter_clause(symbols)
    rows = conn.execute(
        f"""
        SELECT id, symbol, source_name, evidence_type, title, summary, source_url,
               provider_id, source_timestamp, fetched_at
        FROM research_evidence
        WHERE source_name IN ({placeholders})
          AND source_name != ?
          AND evidence_type NOT LIKE 'sec_%'
          AND evidence_type NOT LIKE 'official_ir_%'
          {clause}
        ORDER BY source_name, source_timestamp DESC, id DESC
        """,
        (*source_names, CURATOR_SOURCE, *params),
    ).fetchall()
    counts: dict[str, int] = {}
    curated: list[dict[str, object]] = []
    for row in rows:
        source_name = clean_text(row["source_name"])
        symbol = direct_sources.get(source_name, clean_text(row["symbol"]).upper())
        if symbols and symbol not in symbols:
            continue
        if counts.get(symbol, 0) >= limit_per_symbol:
            continue
        combined = f"{row['title']} {row['summary']}".lower()
        depth_type = classify_by_keywords(combined, OFFICIAL_EVENT_KEYWORDS, "official_company_update")
        matched_products = [
            alias
            for alias in product_aliases.get(symbol, [])
            if alias and re.search(rf"(?<![A-Za-z0-9]){re.escape(alias)}(?![A-Za-z0-9])", combined)
        ][:4]
        product_note = (
            f" Matched product terms: {', '.join(matched_products)}."
            if matched_products
            else " No product alias matched; source maps directly to the company."
        )
        curated.append(
            evidence_row(
                symbol,
                "official_source_depth_signal",
                f"{symbol} official source depth: {depth_type.replace('_', ' ')}",
                (
                    f"{source_name} item classified as {depth_type.replace('_', ' ')}. "
                    f"Source title: {clean_text(row['title']) or 'untitled item'}.{product_note} "
                    "Company-framed official context; no current score impact."
                ),
                clean_text(row["source_url"]),
                stable_provider_id(symbol, "official_source", depth_type, row["provider_id"] or row["id"]),
                source_timestamp(row),
                confidence="medium_high",
                corroboration="curated_from_official_company_source",
            )
        )
        counts[symbol] = counts.get(symbol, 0) + 1
    return curated


def delete_existing(symbols: set[str]) -> int:
    conn = storage.init_db()
    clause, params = symbol_filter_clause(symbols)
    with conn:
        cursor = conn.execute(
            f"DELETE FROM research_evidence WHERE source_name = ? {clause}",
            (CURATOR_SOURCE, *params),
        )
        deleted = int(cursor.rowcount)
    conn.close()
    return deleted


def curate(symbols: Iterable[str] = (), limit_per_symbol: int = 24, rebuild: bool = False) -> tuple[int, int]:
    symbol_set = {clean_text(symbol).upper() for symbol in symbols if clean_text(symbol)}
    if rebuild:
        delete_existing(symbol_set)
    conn = storage.init_db()
    conn.row_factory = sqlite3.Row
    direct_sources = load_direct_symbol_sources()
    product_aliases = load_product_aliases()
    rows: list[dict[str, object]] = []
    rows.extend(curate_sec_facts(conn, symbol_set, limit_per_symbol))
    rows.extend(curate_sec_filings(conn, symbol_set, limit_per_symbol))
    rows.extend(curate_ir_depth(conn, symbol_set, limit_per_symbol))
    rows.extend(
        curate_official_company_depth(
            conn,
            symbol_set,
            limit_per_symbol,
            direct_sources,
            product_aliases,
        )
    )
    conn.close()
    inserted = storage.record_research_evidence(rows)
    storage.record_provider_payload(
        CURATOR_SOURCE,
        CURATOR_ENDPOINT,
        ",".join(sorted(symbol_set)) if symbol_set else "ALL",
        "ok",
        f"seen={len(rows)} inserted={inserted}",
        payload_json={
            "seen": len(rows),
            "inserted": inserted,
            "symbols": sorted(symbol_set),
            "source_families": [
                "sec_companyfacts",
                "sec_submissions",
                "official_ir",
                "official_company_sources",
            ],
        },
    )
    return len(rows), inserted


def main() -> int:
    args = parse_args()
    symbols = [part.strip() for part in args.symbols.split(",") if part.strip()]
    seen, inserted = curate(symbols, limit_per_symbol=args.limit_per_symbol, rebuild=args.rebuild)
    print(f"Source-depth curation complete: seen={seen} inserted={inserted}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
