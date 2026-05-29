#!/usr/bin/env python3
"""Deterministically tag broad research evidence to V1 stock symbols."""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from engine_common import (  # noqa: E402
    DB_FILE,
    RESEARCH_FILE,
    init_db,
    read_csv,
    record_evidence_symbol_tags,
    record_provider_payload,
)


STOP_COMPANY_TOKENS = {
    "ai",
    "and",
    "co",
    "company",
    "corp",
    "corporation",
    "etf",
    "fund",
    "holdings",
    "inc",
    "ltd",
    "plc",
    "systems",
    "technology",
    "technologies",
}


SPECIAL_ALIASES: dict[str, list[tuple[str, str, float]]] = {
    "NVDA": [
        ("nvidia", "company_alias", 0.95),
        ("blackwell", "product_alias", 0.85),
        ("rubin", "product_alias", 0.80),
        ("cuda", "product_alias", 0.85),
        ("h100", "product_alias", 0.85),
        ("h200", "product_alias", 0.85),
        ("b200", "product_alias", 0.85),
        ("gb200", "product_alias", 0.85),
    ],
    "MSFT": [
        ("microsoft", "company_alias", 0.95),
        ("azure", "product_alias", 0.85),
        ("microsoft copilot", "product_alias", 0.90),
    ],
    "GOOGL": [
        ("alphabet", "company_alias", 0.95),
        ("google", "company_alias", 0.95),
        ("google cloud", "product_alias", 0.90),
        ("gemini", "product_alias", 0.80),
        ("deepmind", "product_alias", 0.80),
        ("sundar pichai", "person_alias", 0.85),
    ],
    "AMZN": [
        ("amazon", "company_alias", 0.95),
        ("aws", "product_alias", 0.90),
        ("amazon web services", "product_alias", 0.95),
        ("trainium", "product_alias", 0.80),
        ("inferentia", "product_alias", 0.80),
    ],
    "META": [
        ("meta platforms", "company_alias", 0.95),
        ("facebook", "company_alias", 0.85),
        ("instagram", "product_alias", 0.80),
        ("llama", "product_alias", 0.80),
    ],
    "AVGO": [
        ("broadcom", "company_alias", 0.95),
        ("vmware", "product_alias", 0.75),
    ],
    "AMD": [
        ("advanced micro devices", "company_alias", 0.95),
        ("amd instinct", "product_alias", 0.90),
        ("mi300", "product_alias", 0.85),
    ],
    "ARM": [
        ("arm holdings", "company_alias", 0.95),
    ],
    "MU": [
        ("micron", "company_alias", 0.95),
        ("hbm", "product_alias", 0.75),
    ],
    "TSM": [
        ("taiwan semiconductor", "company_alias", 0.95),
        ("tsmc", "company_alias", 0.95),
    ],
    "ASML": [
        ("asml", "company_alias", 0.95),
        ("euv lithography", "product_alias", 0.85),
    ],
    "CRWD": [
        ("crowdstrike", "company_alias", 0.95),
    ],
    "PANW": [
        ("palo alto networks", "company_alias", 0.95),
        ("palo alto", "company_alias", 0.80),
    ],
    "NET": [
        ("cloudflare", "company_alias", 0.95),
    ],
    "DDOG": [
        ("datadog", "company_alias", 0.95),
    ],
    "SNOW": [
        ("snowflake", "company_alias", 0.95),
    ],
    "MDB": [
        ("mongodb", "company_alias", 0.95),
    ],
    "SOUN": [
        ("soundhound", "company_alias", 0.95),
        ("soundhound ai", "company_alias", 0.95),
    ],
    "AEHR": [
        ("aehr", "company_alias", 0.90),
        ("aehr test systems", "company_alias", 0.95),
    ],
    "BBAI": [
        ("bigbear.ai", "company_alias", 0.95),
        ("bigbear", "company_alias", 0.85),
    ],
    "ALAB": [
        ("astera labs", "company_alias", 0.95),
    ],
    "PLAB": [
        ("photronics", "company_alias", 0.95),
    ],
    "QQQM": [
        ("nasdaq 100", "fund_alias", 0.70),
        ("invesco nasdaq 100", "fund_alias", 0.85),
    ],
    "VGT": [
        ("vanguard information technology", "fund_alias", 0.85),
    ],
    "SMH": [
        ("vaneck semiconductor", "fund_alias", 0.85),
    ],
}


@dataclass(frozen=True)
class AliasRule:
    symbol: str
    alias: str
    match_type: str
    confidence: float
    pattern: re.Pattern[str]


def phrase_pattern(phrase: str) -> re.Pattern[str]:
    escaped = re.escape(phrase).replace(r"\ ", r"\s+")
    return re.compile(rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])", re.IGNORECASE)


def ticker_pattern(symbol: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![A-Z0-9])\$?{re.escape(symbol)}(?![A-Z0-9])")


def company_aliases(company: str) -> list[str]:
    company = company.strip()
    aliases = [company]
    tokens = [
        token
        for token in re.split(r"[^A-Za-z0-9.]+", company.lower())
        if len(token) >= 4 and token not in STOP_COMPANY_TOKENS
    ]
    if len(tokens) == 1:
        aliases.append(tokens[0])
    return aliases


def alias_rules() -> list[AliasRule]:
    rows, _ = read_csv(RESEARCH_FILE)
    rules: list[AliasRule] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        symbol = str(row.get("symbol") or "").strip().upper()
        company = str(row.get("company") or "").strip()
        if not symbol:
            continue
        ticker_key = (symbol, f"${symbol}")
        if ticker_key not in seen:
            seen.add(ticker_key)
            rules.append(
                AliasRule(symbol, f"${symbol}", "ticker", 0.90, ticker_pattern(symbol))
            )
        for alias in company_aliases(company):
            if not alias or alias.lower() in STOP_COMPANY_TOKENS:
                continue
            key = (symbol, alias.lower())
            if key not in seen:
                seen.add(key)
                rules.append(
                    AliasRule(symbol, alias, "company_alias", 0.90, phrase_pattern(alias))
                )
        for alias, match_type, confidence in SPECIAL_ALIASES.get(symbol, []):
            key = (symbol, alias.lower())
            if key not in seen:
                seen.add(key)
                pattern = ticker_pattern(symbol) if match_type == "ticker" else phrase_pattern(alias)
                rules.append(AliasRule(symbol, alias, match_type, confidence, pattern))
    return sorted(rules, key=lambda rule: len(rule.alias), reverse=True)


def evidence_rows(limit: int | None, only_market: bool) -> list[sqlite3.Row]:
    if not DB_FILE.exists():
        return []
    conn = init_db()
    conn.row_factory = sqlite3.Row
    where = "WHERE symbol = 'MARKET'" if only_market else ""
    limit_clause = "LIMIT ?" if limit else ""
    params: tuple[int, ...] = (limit,) if limit else ()
    rows = conn.execute(
        f"""
        SELECT id, symbol, source_name, evidence_type, title, summary, source_url
        FROM research_evidence
        {where}
        ORDER BY id DESC
        {limit_clause}
        """,
        params,
    ).fetchall()
    conn.close()
    return rows


def tag_rows(rows: list[sqlite3.Row], rules: list[AliasRule]) -> list[dict[str, object]]:
    tags: list[dict[str, object]] = []
    emitted: set[tuple[int, str, str]] = set()
    for row in rows:
        headline_text = " ".join(
            str(row[field] or "")
            for field in ("title", "source_url")
        )
        body_text = " ".join(
            str(row[field] or "")
            for field in ("title", "summary", "source_url")
        )
        if not headline_text.strip() and not body_text.strip():
            continue
        for rule in rules:
            # For broad market sources, titles and canonical URLs are the
            # safest relevance signal. Summaries often mention competitors.
            match_text = body_text if rule.match_type == "ticker" else headline_text
            match = rule.pattern.search(match_text)
            if not match:
                continue
            matched_text = match.group(0)[:80]
            key = (int(row["id"]), rule.symbol, matched_text.lower())
            if key in emitted:
                continue
            emitted.add(key)
            tags.append(
                {
                    "evidence_id": int(row["id"]),
                    "symbol": rule.symbol,
                    "match_type": rule.match_type,
                    "matched_text": matched_text,
                    "confidence": rule.confidence,
                }
            )
    return tags


def clear_existing_tags() -> int:
    conn = init_db()
    with conn:
        cursor = conn.execute("DELETE FROM evidence_symbol_tags")
        deleted = cursor.rowcount
    conn.close()
    return int(deleted or 0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tag research evidence to stock symbols.")
    parser.add_argument("--limit", type=int, default=0, help="Limit evidence rows scanned.")
    parser.add_argument(
        "--all-symbols",
        action="store_true",
        help="Scan every evidence row instead of only broad MARKET context rows.",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Delete existing evidence-symbol tags before rebuilding.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    init_db()
    deleted = clear_existing_tags() if args.rebuild else 0
    rows = evidence_rows(limit=args.limit or None, only_market=not args.all_symbols)
    rules = alias_rules()
    tags = tag_rows(rows, rules)
    inserted = record_evidence_symbol_tags(tags)
    record_provider_payload(
        provider="Local deterministic tagger",
        endpoint="evidence_symbol_tags",
        symbol="MARKET",
        status="ok",
        message=(
            f"scanned={len(rows)} candidate evidence rows; "
            f"matched={len(tags)} tags; inserted={inserted}; deleted={deleted}"
        ),
    )
    print(
        f"Evidence tagging complete: scanned={len(rows)} matched={len(tags)} "
        f"inserted={inserted} deleted={deleted}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
