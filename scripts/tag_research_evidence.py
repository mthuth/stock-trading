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
    SYMBOL_ALIASES_FILE,
    CONFIG_DIR,
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


MATCH_REASON_LABELS = {
    "ticker",
    "direct_symbol",
    "company_alias",
    "product_alias",
    "person_alias",
    "fund_alias",
    "sector_context",
}
STOCK_SPECIFIC_MATCH_TYPES = {
    "ticker",
    "direct_symbol",
    "company_alias",
    "product_alias",
    "person_alias",
}
HEADLINE_ONLY_CATEGORIES = {
    "ai_research",
    "newsletter",
    "podcast",
    "press_wire",
    "semiconductor_news",
    "tech_news",
}


@dataclass(frozen=True)
class AliasRule:
    symbol: str
    alias: str
    match_type: str
    confidence: float
    pattern: re.Pattern[str]
    source_name: str = ""


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


def confidence_bucket(confidence: float, match_type: str = "") -> str:
    if match_type == "sector_context":
        return "needs_review"
    if confidence >= 0.85:
        return "high"
    if confidence >= 0.70:
        return "medium"
    if confidence >= 0.50:
        return "low"
    return "needs_review"


def source_categories() -> dict[str, str]:
    path = CONFIG_DIR / "research_source_integrations.csv"
    if not path.exists():
        return {}
    rows, _ = read_csv(path)
    return {
        str(row.get("source_name") or "").strip(): str(row.get("source_category") or "").strip()
        for row in rows
        if str(row.get("source_name") or "").strip()
    }


def configured_alias_rows() -> list[dict[str, str]]:
    if not SYMBOL_ALIASES_FILE.exists():
        return []
    rows, _ = read_csv(SYMBOL_ALIASES_FILE)
    return rows


def alias_rules() -> list[AliasRule]:
    rows, _ = read_csv(RESEARCH_FILE)
    rules: list[AliasRule] = []
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        symbol = str(row.get("symbol") or "").strip().upper()
        company = str(row.get("company") or "").strip()
        if not symbol:
            continue
        ticker_key = (symbol, f"${symbol}", "")
        if ticker_key not in seen:
            seen.add(ticker_key)
            rules.append(
                AliasRule(symbol, f"${symbol}", "ticker", 0.90, ticker_pattern(symbol))
            )
        for alias in company_aliases(company):
            if not alias or alias.lower() in STOP_COMPANY_TOKENS:
                continue
            key = (symbol, alias.lower(), "")
            if key not in seen:
                seen.add(key)
                rules.append(
                    AliasRule(symbol, alias, "company_alias", 0.90, phrase_pattern(alias))
                )
    for row in configured_alias_rows():
        symbol = str(row.get("symbol") or "").strip().upper()
        alias = str(row.get("alias") or "").strip()
        source_name = str(row.get("source_name") or "").strip()
        match_type = str(row.get("match_type") or "").strip() or "company_alias"
        if not symbol or match_type not in MATCH_REASON_LABELS:
            continue
        try:
            confidence = float(row.get("confidence") or 0)
        except (TypeError, ValueError):
            confidence = 0.0
        key = (symbol, alias.lower(), source_name)
        if key in seen:
            continue
        seen.add(key)
        pattern = ticker_pattern(symbol) if match_type == "ticker" else phrase_pattern(alias) if alias else phrase_pattern(source_name or symbol)
        rules.append(AliasRule(symbol, alias, match_type, confidence, pattern, source_name))
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


def source_default_rules(rules: list[AliasRule]) -> dict[str, AliasRule]:
    return {
        rule.source_name: rule
        for rule in rules
        if rule.source_name and not rule.alias and rule.match_type == "direct_symbol"
    }


def is_allowed_match(category: str, rule: AliasRule) -> bool:
    if rule.match_type == "sector_context":
        return False
    if category == "press_wire":
        return rule.match_type in STOCK_SPECIFIC_MATCH_TYPES
    if category in HEADLINE_ONLY_CATEGORIES:
        return rule.match_type in STOCK_SPECIFIC_MATCH_TYPES or rule.match_type == "fund_alias"
    return True


def match_text_for_rule(row: sqlite3.Row, rule: AliasRule, category: str) -> str:
    headline_text = " ".join(str(row[field] or "") for field in ("title", "source_url"))
    body_text = " ".join(str(row[field] or "") for field in ("title", "summary", "source_url"))
    if category in HEADLINE_ONLY_CATEGORIES and rule.match_type != "ticker":
        return headline_text
    return body_text if rule.match_type == "ticker" else headline_text


def tag_rows(rows: list[sqlite3.Row], rules: list[AliasRule]) -> list[dict[str, object]]:
    tags: list[dict[str, object]] = []
    emitted: set[tuple[int, str, str]] = set()
    categories = source_categories()
    default_rules = source_default_rules(rules)
    for row in rows:
        source_name = str(row["source_name"] or "")
        category = categories.get(source_name, "")
        if source_name in default_rules:
            rule = default_rules[source_name]
            key = (int(row["id"]), rule.symbol, source_name.lower())
            if key not in emitted:
                emitted.add(key)
                tags.append(
                    {
                        "evidence_id": int(row["id"]),
                        "symbol": rule.symbol,
                        "match_type": rule.match_type,
                        "matched_text": source_name,
                        "confidence": rule.confidence,
                        "confidence_bucket": confidence_bucket(rule.confidence, rule.match_type),
                        "match_reason": rule.match_type,
                    }
                )
        row_text = " ".join(str(row[field] or "") for field in ("title", "summary", "source_url"))
        if not row_text.strip():
            continue
        for rule in rules:
            if rule.source_name and rule.source_name != source_name:
                continue
            if not rule.alias or not is_allowed_match(category, rule):
                continue
            match_text = match_text_for_rule(row, rule, category)
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
                    "confidence_bucket": confidence_bucket(rule.confidence, rule.match_type),
                    "match_reason": rule.match_type,
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
