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
from stock_trading.ai_synthesis_readiness import (  # noqa: E402
    HIGH_IMPACT_TYPES,
    classify_event_review,
    evaluate_synthesis_readiness,
)
from stock_trading.ai_prompt_packets import build_prompt_packet_context  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare evidence review queue and synthesis packets.")
    parser.add_argument("--rebuild", action="store_true", help="Replace stored readiness and review rows.")
    parser.add_argument("--output-dir", default=str(storage.REPORTS_DIR), help="Directory for synthesis packet JSON.")
    parser.add_argument("--report-date", default=datetime.utcnow().date().isoformat(), help="Report date for packet filename.")
    parser.add_argument("--limit-per-symbol", type=int, default=12, help="Maximum events per symbol packet.")
    parser.add_argument("--prompt-context", help="Optional report-context JSON used to export AI prompt packets.")
    parser.add_argument("--prompt-output", help="Optional path for AI prompt packet JSON output.")
    return parser.parse_args()


def clean(value: object) -> str:
    return str(value or "").strip()


def review_status(row: sqlite3.Row) -> tuple[str, str, str]:
    review = classify_event_review(row)
    return review.status, review.reason, review.action


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


def load_provider_gaps() -> list[dict[str, object]]:
    return [dict(row) for row in storage.latest_provider_gaps()]


def load_verification_queue_rows() -> list[dict[str, object]]:
    return [dict(row) for row in storage.latest_verification_queue(limit=100)]


def load_latest_recommendation_facts() -> dict[str, dict[str, object]]:
    if not storage.DB_FILE.exists():
        return {}
    conn = storage.init_db()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT s.symbol, s.action, s.target_confidence, s.data_status
        FROM recommendation_scores s
        JOIN (
            SELECT symbol, MAX(run_id) AS latest_run_id
            FROM recommendation_scores
            GROUP BY symbol
        ) latest
          ON latest.symbol = s.symbol
         AND latest.latest_run_id = s.run_id
        """
    ).fetchall()
    conn.close()
    return {clean(row["symbol"]).upper(): dict(row) for row in rows}


def load_source_health_by_symbol() -> dict[str, list[dict[str, object]]]:
    if not storage.DB_FILE.exists():
        return {}
    conn = storage.init_db()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT c.symbol, q.source_name, q.quality_label, q.latest_issue, q.latest_evidence_at
        FROM evidence_event_clusters c
        JOIN evidence_event_members m
          ON m.cluster_id = c.id
        JOIN source_quality_metrics q
          ON q.source_name = m.source_name
        JOIN (
            SELECT source_name, MAX(metric_date) AS latest_metric_date
            FROM source_quality_metrics
            GROUP BY source_name
        ) latest
          ON latest.source_name = q.source_name
         AND latest.latest_metric_date = q.metric_date
        """
    ).fetchall()
    conn.close()
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    seen: set[tuple[str, str]] = set()
    for row in rows:
        symbol = clean(row["symbol"]).upper()
        source_name = clean(row["source_name"])
        key = (symbol, source_name)
        if not symbol or not source_name or key in seen:
            continue
        grouped[symbol].append(dict(row))
        seen.add(key)
    return grouped


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
    """Backward-compatible coarse readiness fallback for older call sites."""
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


def rows_by_symbol(rows: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        symbol = clean(row.get("symbol") or row.get("Symbol")).upper()
        if symbol:
            grouped[symbol].append(row)
    return grouped


def build_packets(
    clusters: list[sqlite3.Row],
    review_rows: list[dict[str, Any]],
    report_date: str,
    output_dir: Path,
    limit_per_symbol: int,
    provider_gaps: list[dict[str, object]] | None = None,
    recommendation_facts: dict[str, dict[str, object]] | None = None,
    verification_queue: list[dict[str, object]] | None = None,
    source_health_by_symbol: dict[str, list[dict[str, object]]] | None = None,
    decision_safety_by_symbol: dict[str, dict[str, object]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any], Path]:
    review_by_key = {row["event_key"]: row for row in review_rows}
    provider_gaps_by_symbol = rows_by_symbol(provider_gaps or [])
    verification_by_symbol = rows_by_symbol(verification_queue or [])
    recommendation_facts = recommendation_facts or {}
    source_health_by_symbol = source_health_by_symbol or {}
    decision_safety_by_symbol = decision_safety_by_symbol or {}
    grouped: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for cluster in clusters:
        grouped[clean(cluster["symbol"]).upper()].append(cluster)

    packets: dict[str, Any] = {
        "metadata": {
            "report_date": report_date,
            "generated_at": datetime.utcnow().isoformat(timespec="seconds"),
            "llm_generated": False,
            "purpose": "deterministic_synthesis_packets",
            "readiness_statuses": [
                "ready_for_ai_synthesis",
                "partially_ready",
                "needs_review",
                "needs_corroboration",
                "not_enough_data",
                "blocked_by_provider_gap",
                "ignore_for_now",
            ],
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
        facts = recommendation_facts.get(symbol, {})
        readiness_context = {
            "provider_gaps": provider_gaps_by_symbol.get(symbol, []),
            "verification_queue": verification_by_symbol.get(symbol, []),
            "source_health": source_health_by_symbol.get(symbol, []),
            "target_confidence": facts.get("target_confidence", ""),
            "decision_safety": decision_safety_by_symbol.get(symbol, {}),
        }
        readiness = evaluate_synthesis_readiness(
            symbol,
            symbol_clusters,
            review_counts,
            readiness_context,
            report_date=report_date,
        )
        packets["symbols"][symbol] = {
            "readiness_status": readiness.status,
            "readiness_score": readiness.score,
            "eligible_for_ai_synthesis": readiness.eligible_for_ai_synthesis,
            "reason_codes": readiness.reason_codes,
            "notes": readiness.summary,
            "events": usable_events,
            "review_counts": dict(review_counts),
        }
        readiness_rows.append(
            {
                "symbol": symbol,
                "readiness_status": readiness.status,
                "readiness_score": readiness.score,
                "ready_events": int(review_counts.get("ready_for_synthesis", 0)),
                "needs_review_events": int(review_counts.get("needs_review", 0)),
                "needs_corroboration_events": int(review_counts.get("needs_corroboration", 0)),
                "ignored_events": int(review_counts.get("ignore_for_now", 0)),
                "primary_events": primary_events,
                "independent_confirmed_events": independent_confirmed_events,
                "latest_event_at": latest_event,
                "packet_ref": packet_path.name,
                "notes": readiness.summary,
            }
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    packet_path.write_text(json.dumps(packets, indent=2))
    return readiness_rows, packets, packet_path


def export_prompt_packets(report_context_path: Path, output_path: Path, limit: int) -> dict[str, Any]:
    context = json.loads(report_context_path.read_text())
    packets = build_prompt_packet_context(context, limit=limit)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(packets, indent=2, sort_keys=True))
    return packets


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
        provider_gaps=load_provider_gaps(),
        recommendation_facts=load_latest_recommendation_facts(),
        verification_queue=load_verification_queue_rows(),
        source_health_by_symbol=load_source_health_by_symbol(),
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
    prompt_path = None
    if args.prompt_context:
        prompt_path = Path(args.prompt_output) if args.prompt_output else output_dir / f"ai-prompt-packets-{args.report_date}.json"
        export_prompt_packets(Path(args.prompt_context), prompt_path, args.limit_per_symbol)
    print(
        "Synthesis readiness complete: "
        f"review={len(review_rows)} readiness={len(readiness_rows)} packet={packet_path}"
        + (f" prompt_packet={prompt_path}" if prompt_path else "")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
