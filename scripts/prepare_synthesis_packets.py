#!/usr/bin/env python3
"""Prepare deterministic synthesis readiness packets from event clusters."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from stock_trading import storage  # noqa: E402


HIGH_IMPACT_TYPES = {
    "earnings_guidance",
    "filing_disclosure",
    "product_launch",
    "ai_platform_update",
    "infrastructure_capacity",
    "security_risk",
    "analyst_target",
}
READY_LABELS = {"primary_plus_confirmed", "independent_confirmed", "multi_source_confirmed"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare evidence review queue and synthesis packets.")
    parser.add_argument("--rebuild", action="store_true", help="Replace stored readiness and review rows.")
    parser.add_argument("--output-dir", default=str(storage.REPORTS_DIR), help="Directory for synthesis packet JSON.")
    parser.add_argument("--report-date", default=datetime.utcnow().date().isoformat(), help="Report date for packet filename.")
    parser.add_argument("--limit-per-symbol", type=int, default=12, help="Maximum events per symbol packet.")
    return parser.parse_args()


def clean(value: object) -> str:
    return str(value or "").strip()


def review_status(row: sqlite3.Row) -> tuple[str, str, str]:
    label = clean(row["corroboration_label"])
    confidence = clean(row["confidence"])
    event_type = clean(row["event_type"])
    source_count = int(row["source_count"] or 0)
    primary_count = int(row["primary_source_count"] or 0)
    opinion_count = int(row["opinion_source_count"] or 0)

    if label in READY_LABELS and confidence in {"high", "medium_high", "medium"}:
        return (
            "ready_for_synthesis",
            "Corroborated event has enough source breadth for deterministic synthesis input.",
            "Use in synthesis packet.",
        )
    if primary_count > 0 and event_type in HIGH_IMPACT_TYPES:
        return (
            "ready_for_synthesis",
            "High-impact primary-source event deserves synthesis even before independent confirmation.",
            "Use with primary-source framing.",
        )
    if label == "company_only":
        return (
            "needs_corroboration",
            "Company-framed event should be checked against independent coverage before strong synthesis claims.",
            "Look for independent confirmation.",
        )
    if label == "single_source" and event_type in HIGH_IMPACT_TYPES:
        return (
            "needs_review",
            "High-impact event has only one source; review before synthesis emphasis.",
            "Verify with another source or primary document.",
        )
    if opinion_count > 0 and source_count <= 1:
        return (
            "ignore_for_now",
            "Opinion/context-only event has weak corroboration.",
            "Keep visible but exclude from synthesis packet.",
        )
    return (
        "needs_review",
        "Event needs review before future AI synthesis.",
        "Inspect source members and corroboration.",
    )


def priority(status: str, row: sqlite3.Row) -> int:
    base = {
        "ready_for_synthesis": 100,
        "needs_corroboration": 200,
        "needs_review": 300,
        "ignore_for_now": 700,
    }.get(status, 500)
    impact_bonus = -25 if clean(row["event_type"]) in HIGH_IMPACT_TYPES else 0
    evidence_bonus = -min(30, int(row["evidence_count"] or 0) * 3)
    return max(1, base + impact_bonus + evidence_bonus)


def load_clusters() -> list[sqlite3.Row]:
    conn = storage.init_db()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT id, event_date, symbol, event_key, event_type, headline, summary,
               corroboration_label, source_count, evidence_count,
               independent_source_count, primary_source_count, company_source_count,
               opinion_source_count, latest_evidence_at, confidence, notes
        FROM evidence_event_clusters
        ORDER BY latest_evidence_at DESC, evidence_count DESC
        """
    ).fetchall()
    conn.close()
    return rows


def build_review_rows(clusters: list[sqlite3.Row]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for cluster in clusters:
        status, reason, action = review_status(cluster)
        rows.append(
            {
                "cluster_id": int(cluster["id"]),
                "symbol": clean(cluster["symbol"]).upper(),
                "event_key": clean(cluster["event_key"]),
                "event_type": clean(cluster["event_type"]),
                "review_status": status,
                "priority_rank": priority(status, cluster),
                "review_reason": reason,
                "recommended_action": action,
                "corroboration_label": clean(cluster["corroboration_label"]),
                "confidence": clean(cluster["confidence"]),
                "source_count": int(cluster["source_count"] or 0),
                "evidence_count": int(cluster["evidence_count"] or 0),
                "latest_evidence_at": clean(cluster["latest_evidence_at"]),
            }
        )
    rows.sort(key=lambda row: (int(row["priority_rank"]), row["symbol"], row["event_key"]))
    for index, row in enumerate(rows, start=1):
        row["priority_rank"] = index
    return rows


def readiness_status(counts: dict[str, int]) -> tuple[str, float, str]:
    ready = counts.get("ready_for_synthesis", 0)
    needs_review = counts.get("needs_review", 0)
    needs_corroboration = counts.get("needs_corroboration", 0)
    ignored = counts.get("ignore_for_now", 0)
    total = ready + needs_review + needs_corroboration + ignored
    score = round(((ready * 2.0) - (needs_review * 0.4) - (needs_corroboration * 0.2)) / max(1, total), 3)
    if ready >= 3 and needs_review <= ready:
        return "ready_for_ai_synthesis", score, "Multiple usable events with manageable review load."
    if ready >= 1:
        return "partially_ready", score, "At least one event is synthesis-ready, but review/corroboration remains."
    if needs_corroboration or needs_review:
        return "needs_review", score, "No synthesis-ready events yet; review or corroborate event clusters first."
    return "not_enough_data", score, "No meaningful event clusters are available."


def build_packets(
    clusters: list[sqlite3.Row],
    review_rows: list[dict[str, Any]],
    report_date: str,
    output_dir: Path,
    limit_per_symbol: int,
) -> tuple[list[dict[str, Any]], dict[str, Any], Path]:
    review_by_key = {row["event_key"]: row for row in review_rows}
    grouped: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for cluster in clusters:
        grouped[clean(cluster["symbol"]).upper()].append(cluster)

    packets: dict[str, Any] = {
        "metadata": {
            "report_date": report_date,
            "generated_at": datetime.utcnow().isoformat(timespec="seconds"),
            "llm_generated": False,
            "purpose": "deterministic_synthesis_packets",
        },
        "symbols": {},
    }
    readiness_rows: list[dict[str, Any]] = []
    packet_path = output_dir / f"synthesis-packets-{report_date}.json"
    for symbol, symbol_clusters in sorted(grouped.items()):
        usable_events: list[dict[str, Any]] = []
        review_counts: dict[str, int] = defaultdict(int)
        primary_events = 0
        independent_confirmed_events = 0
        latest_event = ""
        for cluster in symbol_clusters[: max(limit_per_symbol * 2, limit_per_symbol)]:
            review = review_by_key.get(clean(cluster["event_key"]), {})
            status = clean(review.get("review_status"))
            review_counts[status] += 1
            if int(cluster["primary_source_count"] or 0) > 0:
                primary_events += 1
            if clean(cluster["corroboration_label"]) in {"independent_confirmed", "primary_plus_confirmed"}:
                independent_confirmed_events += 1
            latest_event = max(latest_event, clean(cluster["latest_evidence_at"]))
            if status == "ignore_for_now":
                continue
            usable_events.append(
                {
                    "event_date": clean(cluster["event_date"]),
                    "event_type": clean(cluster["event_type"]),
                    "headline": clean(cluster["headline"]),
                    "summary": clean(cluster["summary"]),
                    "corroboration_label": clean(cluster["corroboration_label"]),
                    "source_count": int(cluster["source_count"] or 0),
                    "evidence_count": int(cluster["evidence_count"] or 0),
                    "source_mix": {
                        "primary": int(cluster["primary_source_count"] or 0),
                        "company": int(cluster["company_source_count"] or 0),
                        "independent": int(cluster["independent_source_count"] or 0),
                        "opinion": int(cluster["opinion_source_count"] or 0),
                    },
                    "confidence": clean(cluster["confidence"]),
                    "review_status": status,
                    "review_reason": clean(review.get("review_reason")),
                }
            )
            if len(usable_events) >= limit_per_symbol:
                break
        status, score, notes = readiness_status(review_counts)
        packets["symbols"][symbol] = {
            "readiness_status": status,
            "readiness_score": score,
            "notes": notes,
            "events": usable_events,
            "review_counts": dict(review_counts),
        }
        readiness_rows.append(
            {
                "symbol": symbol,
                "readiness_status": status,
                "readiness_score": score,
                "ready_events": int(review_counts.get("ready_for_synthesis", 0)),
                "needs_review_events": int(review_counts.get("needs_review", 0)),
                "needs_corroboration_events": int(review_counts.get("needs_corroboration", 0)),
                "ignored_events": int(review_counts.get("ignore_for_now", 0)),
                "primary_events": primary_events,
                "independent_confirmed_events": independent_confirmed_events,
                "latest_event_at": latest_event,
                "packet_ref": packet_path.name,
                "notes": notes,
            }
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    packet_path.write_text(json.dumps(packets, indent=2))
    return readiness_rows, packets, packet_path


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    clusters = load_clusters()
    review_rows = build_review_rows(clusters)
    readiness_rows, packets, packet_path = build_packets(
        clusters,
        review_rows,
        args.report_date,
        output_dir,
        args.limit_per_symbol,
    )
    stored_review = storage.record_evidence_review_queue(review_rows, rebuild=args.rebuild)
    stored_readiness = storage.record_synthesis_readiness(readiness_rows, rebuild=args.rebuild)
    storage.record_provider_payload(
        "Local synthesis readiness preparer",
        "synthesis_packets",
        "ALL",
        "ok",
        f"review={len(review_rows)} readiness={len(readiness_rows)} stored_review={stored_review} stored_readiness={stored_readiness}",
        payload_json={
            "review_rows": len(review_rows),
            "readiness_rows": len(readiness_rows),
            "packet_ref": packet_path.name,
            "symbols": sorted(packets.get("symbols", {}).keys()),
        },
    )
    print(
        "Synthesis readiness complete: "
        f"review={len(review_rows)} readiness={len(readiness_rows)} packet={packet_path}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
