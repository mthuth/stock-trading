#!/usr/bin/env python3
"""Cluster related evidence rows into corroborated event groups."""

from __future__ import annotations

import argparse
import hashlib
import re
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from stock_trading import storage  # noqa: E402


LOCAL_SOURCES = {
    "Local deterministic tagger",
    "Local ingestion planner",
    "Local source quality scorer",
}
STOPWORDS = {
    "about",
    "after",
    "and",
    "are",
    "from",
    "into",
    "latest",
    "more",
    "news",
    "official",
    "report",
    "says",
    "source",
    "that",
    "the",
    "this",
    "with",
}
EVENT_KEYWORDS = {
    "earnings_guidance": ("earnings", "guidance", "outlook", "results", "quarter"),
    "filing_disclosure": ("10-k", "10-q", "8-k", "filing", "annual report"),
    "product_launch": ("launch", "introduce", "unveil", "available", "release"),
    "ai_platform_update": ("ai", "model", "agent", "copilot", "gemini", "bedrock", "cuda", "blackwell"),
    "infrastructure_capacity": ("data center", "cloud", "gpu", "accelerator", "chip", "capacity"),
    "security_risk": ("security", "threat", "vulnerability", "incident", "breach"),
    "analyst_target": ("analyst", "rating", "target", "upgrade", "downgrade"),
    "market_sentiment": ("sentiment", "shares", "stock", "market"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cluster research evidence into source-backed events.")
    parser.add_argument("--rebuild", action="store_true", help="Replace existing evidence event clusters.")
    parser.add_argument("--symbols", default="", help="Optional comma-separated symbols.")
    parser.add_argument("--days", type=int, default=45, help="Evidence lookback window.")
    parser.add_argument("--min-evidence", type=int, default=1, help="Minimum evidence rows per cluster.")
    return parser.parse_args()


def clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def parse_time(value: object) -> datetime | None:
    text = clean(value)
    if not text:
        return None
    for candidate in (text, text.replace("Z", "+00:00"), text[:19]):
        try:
            parsed = datetime.fromisoformat(candidate)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            pass
    try:
        return datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def evidence_date(row: sqlite3.Row) -> datetime:
    return (
        parse_time(row["source_timestamp"])
        or parse_time(row["fetched_at"])
        or parse_time(row["created_at"])
        or datetime.now(timezone.utc)
    )


def date_bucket(value: datetime) -> str:
    bucket_start = value.date() - timedelta(days=value.toordinal() % 3)
    return bucket_start.isoformat()


def classify_event(row: sqlite3.Row) -> str:
    text = f"{row['evidence_type']} {row['title']} {row['summary']}".lower()
    for label, terms in EVENT_KEYWORDS.items():
        if any(term in text for term in terms):
            return label
    if "sec_" in clean(row["evidence_type"]):
        return "filing_disclosure"
    if "ir_" in clean(row["evidence_type"]):
        return "earnings_guidance"
    return "general_context"


def source_family(row: sqlite3.Row) -> str:
    source_name = clean(row["source_name"]).lower()
    source_type = clean(row["source_type"]).lower()
    evidence_type = clean(row["evidence_type"]).lower()
    if "sec" in source_name or evidence_type.startswith("sec_"):
        return "primary"
    if "investor relations" in source_name or "official_ir" in evidence_type:
        return "primary"
    if "official" in source_name or "company_blog" in source_type or "company_newsroom" in source_type:
        return "company"
    if "press_wire" in source_type or "business wire" in source_name or "globenewswire" in source_name:
        return "company"
    if source_type in {"newsletter", "podcast"} or "newsletter" in source_name or "podcast" in source_name:
        return "opinion"
    if source_type in {"tech_news", "ai_research", "semiconductor_news"}:
        return "independent"
    if source_name.startswith("local source depth"):
        return "primary"
    return "independent"


def topic_terms(row: sqlite3.Row, event_type: str) -> list[str]:
    text = f"{row['title']} {row['summary']}".lower()
    tokens = [
        token
        for token in re.findall(r"[a-z0-9][a-z0-9.+-]{2,}", text)
        if token not in STOPWORDS and not token.isdigit()
    ]
    preferred = [
        token
        for token in tokens
        if token in {
            "ai",
            "azure",
            "bedrock",
            "blackwell",
            "cloud",
            "copilot",
            "cuda",
            "datacenter",
            "earnings",
            "gemini",
            "gpu",
            "guidance",
            "hbm",
            "llama",
            "revenue",
            "security",
            "trainium",
        }
    ]
    terms = preferred or tokens[:8] or [event_type]
    return list(dict.fromkeys(terms[:5]))


def cluster_key(symbol: str, row: sqlite3.Row, event_type: str, bucket: str) -> tuple[str, str]:
    terms = topic_terms(row, event_type)
    topic = "-".join(terms[:3])
    digest = hashlib.sha1(topic.encode("utf-8")).hexdigest()[:8]
    event_key = f"{symbol}:{event_type}:{bucket}:{digest}"
    return event_key, topic


def symbol_rows(conn: sqlite3.Connection, symbols: set[str], days: int) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    symbol_filter = ""
    params: list[object] = [f"-{max(1, days)} days"]
    if symbols:
        placeholders = ",".join("?" for _ in symbols)
        symbol_filter = f" AND symbol IN ({placeholders})"
        params.extend(sorted(symbols))
    rows = conn.execute(
        f"""
        SELECT id, created_at, symbol, evidence_type, source_name, source_type,
               source_url, provider_id, source_timestamp, fetched_at, title,
               summary, confidence, corroboration_status
        FROM research_evidence
        WHERE source_name NOT IN ({",".join("?" for _ in LOCAL_SOURCES)})
          AND datetime(COALESCE(source_timestamp, fetched_at, created_at)) >= datetime('now', ?)
          {symbol_filter}
        """,
        [*LOCAL_SOURCES, *params],
    ).fetchall()

    tag_params: list[object] = [f"-{max(1, days)} days"]
    tag_filter = ""
    if symbols:
        placeholders = ",".join("?" for _ in symbols)
        tag_filter = f" AND t.symbol IN ({placeholders})"
        tag_params.extend(sorted(symbols))
    tagged = conn.execute(
        f"""
        SELECT e.id, e.created_at, t.symbol, e.evidence_type, e.source_name,
               e.source_type, e.source_url, e.provider_id, e.source_timestamp,
               e.fetched_at, e.title, e.summary, e.confidence,
               e.corroboration_status, t.match_reason, t.confidence_bucket
        FROM evidence_symbol_tags t
        JOIN research_evidence e ON e.id = t.evidence_id
        WHERE e.source_name NOT IN ({",".join("?" for _ in LOCAL_SOURCES)})
          AND t.confidence_bucket IN ('high', 'medium')
          AND datetime(COALESCE(e.source_timestamp, e.fetched_at, e.created_at)) >= datetime('now', ?)
          {tag_filter}
        """,
        [*LOCAL_SOURCES, *tag_params],
    ).fetchall()
    seen = {(int(row["id"]), clean(row["symbol"])) for row in rows}
    merged = list(rows)
    for row in tagged:
        key = (int(row["id"]), clean(row["symbol"]))
        if key not in seen:
            merged.append(row)
            seen.add(key)
    return merged


def corroboration_label(families: set[str], source_count: int) -> str:
    if "primary" in families and ("independent" in families or source_count >= 2):
        return "primary_plus_confirmed"
    if "independent" in families and source_count >= 2:
        return "independent_confirmed"
    if source_count >= 3 and len(families) >= 2:
        return "multi_source_confirmed"
    if families <= {"company"}:
        return "company_only"
    if source_count <= 1:
        return "single_source"
    return "multi_source_unconfirmed"


def cluster_confidence(label: str, evidence_count: int) -> str:
    if label in {"primary_plus_confirmed", "independent_confirmed"}:
        return "high"
    if label == "multi_source_confirmed" or evidence_count >= 3:
        return "medium_high"
    if label in {"company_only", "multi_source_unconfirmed"}:
        return "medium"
    return "low"


def build_clusters(symbols: set[str], days: int, min_evidence: int) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    conn = storage.init_db()
    rows = symbol_rows(conn, symbols, days)
    conn.close()
    grouped: dict[str, list[sqlite3.Row]] = defaultdict(list)
    topics: dict[str, str] = {}
    event_types: dict[str, str] = {}
    buckets: dict[str, str] = {}
    for row in rows:
        symbol = clean(row["symbol"]).upper()
        if not symbol or symbol == "MARKET":
            continue
        event_type = classify_event(row)
        bucket = date_bucket(evidence_date(row))
        event_key, topic = cluster_key(symbol, row, event_type, bucket)
        grouped[event_key].append(row)
        topics[event_key] = topic
        event_types[event_key] = event_type
        buckets[event_key] = bucket

    clusters: list[dict[str, Any]] = []
    members: dict[str, list[dict[str, Any]]] = {}
    for event_key, items in grouped.items():
        if len(items) < min_evidence:
            continue
        symbol = clean(items[0]["symbol"]).upper()
        families = {source_family(row) for row in items}
        source_names = {clean(row["source_name"]) for row in items}
        latest = max(evidence_date(row) for row in items)
        event_type = event_types[event_key]
        headline = best_headline(items, symbol, event_type, topics[event_key])
        label = corroboration_label(families, len(source_names))
        clusters.append(
            {
                "event_date": buckets[event_key],
                "symbol": symbol,
                "event_key": event_key,
                "event_type": event_type,
                "headline": headline,
                "summary": event_summary(items, families, source_names),
                "corroboration_label": label,
                "source_count": len(source_names),
                "evidence_count": len(items),
                "independent_source_count": sum(1 for source in source_names if source_family_for_name(source, items) == "independent"),
                "primary_source_count": sum(1 for source in source_names if source_family_for_name(source, items) == "primary"),
                "company_source_count": sum(1 for source in source_names if source_family_for_name(source, items) == "company"),
                "opinion_source_count": sum(1 for source in source_names if source_family_for_name(source, items) == "opinion"),
                "latest_evidence_at": latest.isoformat(timespec="seconds"),
                "confidence": cluster_confidence(label, len(items)),
                "notes": "Explanatory event cluster only; no score/action impact.",
            }
        )
        members[event_key] = [
            {
                "evidence_id": int(row["id"]),
                "source_name": clean(row["source_name"]),
                "source_family": source_family(row),
                "match_reason": clean(row["match_reason"]) if "match_reason" in row.keys() else "",
                "confidence_bucket": clean(row["confidence_bucket"]) if "confidence_bucket" in row.keys() else "",
            }
            for row in items
        ]

    clusters.sort(
        key=lambda row: (
            -int(row["evidence_count"]),
            -int(row["source_count"]),
            str(row["symbol"]),
            str(row["event_key"]),
        )
    )
    return clusters, members


def source_family_for_name(source_name: str, rows: list[sqlite3.Row]) -> str:
    for row in rows:
        if clean(row["source_name"]) == source_name:
            return source_family(row)
    return "independent"


def best_headline(rows: list[sqlite3.Row], symbol: str, event_type: str, topic: str) -> str:
    sorted_rows = sorted(rows, key=lambda row: (source_family(row) != "primary", -len(clean(row["title"]))))
    title = clean(sorted_rows[0]["title"]) if sorted_rows else ""
    if title:
        return title[:180]
    return f"{symbol} {event_type.replace('_', ' ')} event: {topic}"


def event_summary(rows: list[sqlite3.Row], families: set[str], source_names: set[str]) -> str:
    samples = [clean(row["title"]) for row in rows if clean(row["title"])]
    sample_text = "; ".join(samples[:3])
    return (
        f"{len(rows)} evidence item(s) from {len(source_names)} source(s); "
        f"families: {', '.join(sorted(families))}. "
        f"Representative titles: {sample_text or 'n/a'}."
    )


def main() -> int:
    args = parse_args()
    symbols = {clean(part).upper() for part in args.symbols.split(",") if clean(part)}
    clusters, members = build_clusters(symbols, args.days, args.min_evidence)
    inserted = storage.record_evidence_event_clusters(clusters, members, rebuild=args.rebuild)
    storage.record_provider_payload(
        "Local evidence event clusterer",
        "evidence_event_clusters",
        ",".join(sorted(symbols)) if symbols else "ALL",
        "ok",
        f"clusters={len(clusters)} inserted={inserted}",
        payload_json={"clusters": len(clusters), "symbols": sorted(symbols), "days": args.days},
    )
    print(f"Evidence event clustering complete: clusters={len(clusters)} inserted={inserted}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
