#!/usr/bin/env python3
"""Roll up ingestion quality and source-to-symbol relevance metrics."""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from engine_common import (  # noqa: E402
    CONFIG_DIR,
    DB_FILE,
    init_db,
    read_csv,
    record_provider_payload,
    record_source_quality_metrics,
)


CONTEXT_CATEGORIES = {
    "ai_research",
    "newsletter",
    "podcast",
    "semiconductor_news",
    "tech_news",
}
EXCLUDED_SOURCES = {
    "Local deterministic tagger",
    "Local evidence event clusterer",
    "Local ingestion planner",
    "Local synthesis readiness preparer",
    "Local source depth curator",
    "Local source quality scorer",
}
BLOCKED_TERMS = ("blocked", "forbidden", "unauthorized", "payment required", "rate limit", "quota")
ERROR_STATUSES = {"error", "failed", "missing", "parser_gap"}
OK_STATUSES = {"ok", "rss_ok", "page_links_ok"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Score ingestion quality and source relevance.")
    parser.add_argument("--rebuild", action="store_true", help="Replace existing source-quality rows.")
    parser.add_argument("--source", default="", help="Limit scoring to one source name.")
    parser.add_argument("--days", type=int, default=30, help="Recent provider payload window for run counts.")
    return parser.parse_args()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_time(value: object) -> datetime | None:
    text = str(value or "").strip()
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


def age_days(value: object, now: datetime | None = None) -> float | None:
    parsed = parse_time(value)
    if not parsed:
        return None
    return round(((now or utc_now()) - parsed).total_seconds() / 86_400, 2)


def source_configs() -> dict[str, dict[str, str]]:
    sources: dict[str, dict[str, str]] = {}
    for path in (CONFIG_DIR / "research_sources.csv", CONFIG_DIR / "research_source_integrations.csv"):
        if not path.exists():
            continue
        rows, _ = read_csv(path)
        for row in rows:
            name = str(row.get("source_name") or "").strip()
            if not name:
                continue
            current = sources.setdefault(name, {"source_name": name})
            current.update({key: str(value or "") for key, value in row.items()})
    return sources


def normalize_status(status: object, message: object = "") -> str:
    raw_status = str(status or "").strip().lower()
    raw_message = str(message or "").strip().lower()
    if raw_status in OK_STATUSES:
        return "ok"
    if raw_status == "blocked" or any(term in raw_message for term in BLOCKED_TERMS):
        return "blocked"
    if raw_status in ERROR_STATUSES or raw_status:
        return "error"
    return ""


def parsed_record_counts(message: object) -> tuple[int, int]:
    text = str(message or "")
    seen = 0
    inserted = 0
    patterns = {
        "seen": r"(?:seen|scanned|matched|record_count|records?)=(\d+)",
        "inserted": r"inserted=(\d+)",
    }
    for key, pattern in patterns.items():
        matches = [int(match) for match in re.findall(pattern, text, flags=re.IGNORECASE)]
        if matches and key == "seen":
            seen = max(matches)
        elif matches:
            inserted = max(matches)
    return seen, inserted


def confidence_bucket(confidence: float, match_reason: str = "") -> str:
    if match_reason == "sector_context":
        return "needs_review"
    if confidence >= 0.85:
        return "high"
    if confidence >= 0.70:
        return "medium"
    if confidence >= 0.50:
        return "low"
    return "needs_review"


def empty_state(source_name: str, category: str = "") -> dict[str, Any]:
    return {
        "source_name": source_name,
        "source_category": category,
        "records_seen": 0,
        "records_inserted": 0,
        "duplicate_records": 0,
        "raw_payloads": 0,
        "ok_runs": 0,
        "error_runs": 0,
        "blocked_runs": 0,
        "total_evidence": 0,
        "tagged_evidence": 0,
        "tag_count": 0,
        "tagged_evidence_ids": set(),
        "matched_symbols": set(),
        "tag_confidence_sum": 0.0,
        "top_terms": Counter(),
        "match_reasons": Counter(),
        "confidence_buckets": Counter(),
        "low_confidence_matches": 0,
        "latest_success": "",
        "latest_status": "",
        "latest_status_at": "",
        "latest_issue": "",
        "latest_evidence_at": "",
        "feedback_delta": 0.0,
    }


def update_latest(state: dict[str, Any], key: str, value: object) -> None:
    new_time = parse_time(value)
    if not new_time:
        return
    old_time = parse_time(state.get(key))
    if not old_time or new_time > old_time:
        state[key] = str(value)


def update_latest_status(state: dict[str, Any], status: str, at_value: object) -> None:
    new_time = parse_time(at_value)
    if not new_time:
        return
    old_time = parse_time(state.get("latest_status_at"))
    if not old_time or new_time > old_time:
        state["latest_status_at"] = str(at_value)
        state["latest_status"] = status


def state_for(states: dict[str, dict[str, Any]], source_name: str, configs: dict[str, dict[str, str]]) -> dict[str, Any]:
    config = configs.get(source_name, {})
    category = config.get("source_category") or config.get("source_type") or ""
    return states.setdefault(source_name, empty_state(source_name, category))


def load_metrics(source_filter: str = "", days: int = 30) -> list[dict[str, Any]]:
    if not DB_FILE.exists():
        return []
    configs = source_configs()
    states: dict[str, dict[str, Any]] = {
        name: empty_state(
            name,
            config.get("source_category") or config.get("source_type") or "",
        )
        for name, config in configs.items()
        if name not in EXCLUDED_SOURCES and (not source_filter or name == source_filter)
    }

    conn = init_db()
    conn.row_factory = sqlite3.Row

    for row in conn.execute(
        """
        SELECT source_name, COUNT(*) AS count, MAX(fetched_at) AS latest_fetched,
               MAX(source_timestamp) AS latest_source
        FROM research_evidence
        GROUP BY source_name
        """
    ):
        name = str(row["source_name"] or "")
        if name in EXCLUDED_SOURCES:
            continue
        if source_filter and name != source_filter:
            continue
        state = state_for(states, name, configs)
        count = int(row["count"] or 0)
        state["total_evidence"] += count
        state["records_inserted"] += count
        update_latest(state, "latest_evidence_at", row["latest_source"] or row["latest_fetched"])
        update_latest(state, "latest_success", row["latest_fetched"])

    for row in conn.execute(
        """
        SELECT e.source_name, COUNT(DISTINCT t.symbol) AS symbol_count
        FROM evidence_symbol_tags t
        JOIN research_evidence e ON e.id = t.evidence_id
        GROUP BY e.source_name
        """
    ):
        name = str(row["source_name"] or "")
        if name in EXCLUDED_SOURCES:
            continue
        if source_filter and name != source_filter:
            continue
        state = state_for(states, name, configs)
        state["matched_symbol_count"] = int(row["symbol_count"] or 0)

    for row in conn.execute(
        """
        SELECT e.source_name, t.evidence_id, t.symbol, t.match_type, t.matched_text,
               t.confidence, t.confidence_bucket, t.match_reason
        FROM evidence_symbol_tags t
        JOIN research_evidence e ON e.id = t.evidence_id
        """
    ):
        name = str(row["source_name"] or "")
        if name in EXCLUDED_SOURCES:
            continue
        if source_filter and name != source_filter:
            continue
        state = state_for(states, name, configs)
        state["matched_symbols"].add(str(row["symbol"] or ""))
        match_reason = str(row["match_reason"] or row["match_type"] or "unknown")
        confidence_value = float(row["confidence"] or 0)
        bucket = str(row["confidence_bucket"] or confidence_bucket(confidence_value, match_reason))
        if bucket == "low" and confidence_value >= 0.85 and match_reason != "sector_context":
            bucket = "high"
        state["match_reasons"][match_reason] += 1
        state["confidence_buckets"][bucket] += 1
        is_stock_specific = bucket in {"high", "medium"} and match_reason != "sector_context"
        if is_stock_specific:
            state["tagged_evidence_ids"].add(int(row["evidence_id"] or 0))
            state["tag_count"] += 1
            state["tag_confidence_sum"] += float(row["confidence"] or 0)
        else:
            state["low_confidence_matches"] += 1
        matched_text = str(row["matched_text"] or "").strip()
        if matched_text:
            state["top_terms"][matched_text.lower()] += 1

    for row in conn.execute(
        """
        SELECT source_name, symbol, COUNT(*) AS count
        FROM research_evidence
        WHERE COALESCE(symbol, '') NOT IN ('', 'MARKET')
        GROUP BY source_name, symbol
        """
    ):
        name = str(row["source_name"] or "")
        if name in EXCLUDED_SOURCES:
            continue
        if source_filter and name != source_filter:
            continue
        state = state_for(states, name, configs)
        count = int(row["count"] or 0)
        symbol = str(row["symbol"] or "").upper()
        state["tagged_evidence"] += count
        state["tag_count"] += count
        state["tag_confidence_sum"] += count
        state["matched_symbols"].add(symbol)
        state["match_reasons"]["direct_symbol"] += count
        state["confidence_buckets"]["high"] += count
        state["top_terms"][symbol] += count

    for row in conn.execute(
        """
        SELECT provider, endpoint, status, message, created_at
        FROM provider_payloads
        WHERE created_at >= datetime('now', ?)
        """,
        (f"-{max(1, int(days))} days",),
    ):
        name = str(row["provider"] or "")
        if name in EXCLUDED_SOURCES:
            continue
        if source_filter and name != source_filter:
            continue
        state = state_for(states, name, configs)
        status = normalize_status(row["status"], row["message"])
        if status == "ok":
            state["ok_runs"] += 1
            update_latest(state, "latest_success", row["created_at"])
            update_latest_status(state, "ok", row["created_at"])
        elif status == "blocked":
            state["blocked_runs"] += 1
            update_latest_status(state, "blocked", row["created_at"])
            state["latest_issue"] = str(row["message"] or row["status"] or "")
        elif status == "error":
            state["error_runs"] += 1
            update_latest_status(state, "error", row["created_at"])
            state["latest_issue"] = str(row["message"] or row["status"] or "")
        seen, inserted = parsed_record_counts(row["message"])
        if seen:
            state["records_seen"] += seen
        if inserted:
            state["duplicate_records"] += max(0, seen - inserted)

    for row in conn.execute(
        """
        SELECT provider, status, message, COUNT(*) AS count, MAX(created_at) AS latest
        FROM raw_ingestion_payloads
        GROUP BY provider, status, message
        """
    ):
        name = str(row["provider"] or "")
        if name in EXCLUDED_SOURCES:
            continue
        if source_filter and name != source_filter:
            continue
        state = state_for(states, name, configs)
        count = int(row["count"] or 0)
        state["raw_payloads"] += count
        status = normalize_status(row["status"], row["message"])
        if status == "ok":
            update_latest(state, "latest_success", row["latest"])
            update_latest_status(state, "ok", row["latest"])
        elif status == "blocked":
            state["blocked_runs"] += count
            update_latest_status(state, "blocked", row["latest"])
            state["latest_issue"] = str(row["message"] or row["status"] or "")
        elif status == "error":
            state["error_runs"] += count
            update_latest_status(state, "error", row["latest"])
            state["latest_issue"] = str(row["message"] or row["status"] or "")

    for row in conn.execute(
        """
        SELECT source_name, SUM(rating_delta) AS feedback_delta
        FROM source_feedback
        GROUP BY source_name
        """
    ):
        name = str(row["source_name"] or "")
        if name in EXCLUDED_SOURCES:
            continue
        if source_filter and name != source_filter:
            continue
        state = state_for(states, name, configs)
        state["feedback_delta"] = float(row["feedback_delta"] or 0)

    conn.close()

    rows: list[dict[str, Any]] = []
    metric_date = utc_now().date().isoformat()
    for state in states.values():
        total_evidence = int(state.get("total_evidence") or 0)
        tagged_evidence = int(state.get("tagged_evidence") or 0) + len(state.get("tagged_evidence_ids") or [])
        tag_count = int(state.get("tag_count") or 0)
        if not state.get("records_seen"):
            state["records_seen"] = total_evidence + int(state.get("duplicate_records") or 0)
        avg_confidence = (
            round(float(state["tag_confidence_sum"]) / tag_count, 3)
            if tag_count
            else None
        )
        tag_rate = round(tagged_evidence / total_evidence, 3) if total_evidence else 0.0
        days_since = age_days(state.get("latest_success"))
        quality_label = label_for_state(
            state,
            total_evidence=total_evidence,
            tag_rate=tag_rate,
            avg_confidence=avg_confidence,
            days_since_success=days_since,
        )
        rows.append(
            {
                "metric_date": metric_date,
                "source_name": state["source_name"],
                "source_category": state.get("source_category") or "",
                "records_seen": int(state.get("records_seen") or 0),
                "records_inserted": int(state.get("records_inserted") or 0),
                "duplicate_records": int(state.get("duplicate_records") or 0),
                "raw_payloads": int(state.get("raw_payloads") or 0),
                "ok_runs": int(state.get("ok_runs") or 0),
                "error_runs": int(state.get("error_runs") or 0),
                "blocked_runs": int(state.get("blocked_runs") or 0),
                "total_evidence": total_evidence,
                "tagged_evidence": tagged_evidence,
                "tag_count": tag_count,
                "matched_symbol_count": len(state.get("matched_symbols") or []),
                "avg_tag_confidence": avg_confidence,
                "tag_rate": tag_rate,
                "latest_success": state.get("latest_success") or "",
                "latest_issue": state.get("latest_issue") or "",
                "latest_evidence_at": state.get("latest_evidence_at") or "",
                "days_since_success": days_since,
                "top_matched_terms": ", ".join(
                    f"{term} ({count})" for term, count in state["top_terms"].most_common(5)
                ),
                "match_reason_summary": ", ".join(
                    f"{reason}: {count}" for reason, count in state["match_reasons"].most_common()
                ),
                "confidence_bucket_summary": ", ".join(
                    f"{bucket}: {count}" for bucket, count in state["confidence_buckets"].most_common()
                ),
                "low_confidence_matches": int(state.get("low_confidence_matches") or 0),
                "feedback_delta": round(float(state.get("feedback_delta") or 0), 3),
                "quality_label": quality_label,
                "notes": notes_for_state(state, total_evidence, tag_rate, avg_confidence, days_since),
            }
        )
    return sorted(rows, key=lambda row: (quality_sort(row["quality_label"]), str(row["source_name"])))


def label_for_state(
    state: dict[str, Any],
    total_evidence: int,
    tag_rate: float,
    avg_confidence: float | None,
    days_since_success: float | None,
) -> str:
    category = str(state.get("source_category") or "")
    latest_status_blocked = str(state.get("latest_status") or "") == "blocked"
    if latest_status_blocked or (
        int(state.get("blocked_runs") or 0) + int(state.get("error_runs") or 0) >= 3
        and not state.get("latest_success")
    ):
        return "blocked"
    if days_since_success is not None and days_since_success > 7:
        return "stale"
    if total_evidence < 3:
        return "not_enough_data"
    if tag_rate >= 0.50 and (avg_confidence or 0) >= 0.80 and (days_since_success is None or days_since_success <= 7):
        return "high_signal"
    if total_evidence >= 5 and (tag_rate < 0.20 or (avg_confidence is not None and avg_confidence < 0.70)):
        return "needs_review"
    if total_evidence >= 3 and (tag_rate >= 0.20 or category in CONTEXT_CATEGORIES):
        return "useful_context"
    return "needs_review"


def notes_for_state(
    state: dict[str, Any],
    total_evidence: int,
    tag_rate: float,
    avg_confidence: float | None,
    days_since_success: float | None,
) -> str:
    notes: list[str] = []
    if state.get("latest_issue"):
        notes.append(f"latest issue: {state['latest_issue']}")
    if tag_rate < 0.20 and total_evidence >= 5:
        notes.append("low symbol-match coverage")
    if avg_confidence is not None and avg_confidence < 0.70:
        notes.append("low average match confidence")
    if days_since_success is not None and days_since_success > 7:
        notes.append(f"last success {days_since_success:.1f}d ago")
    if not notes:
        notes.append("measurement only; no score impact")
    return "; ".join(notes)[:500]


def quality_sort(label: object) -> int:
    order = {
        "blocked": 0,
        "needs_review": 1,
        "stale": 2,
        "not_enough_data": 3,
        "useful_context": 4,
        "high_signal": 5,
    }
    return order.get(str(label), 9)


def main() -> int:
    args = parse_args()
    init_db()
    rows = load_metrics(source_filter=args.source.strip(), days=args.days)
    inserted = record_source_quality_metrics(rows, rebuild=args.rebuild and not args.source)
    label_counts = Counter(str(row["quality_label"]) for row in rows)
    record_provider_payload(
        provider="Local source quality scorer",
        endpoint="source_quality_metrics",
        symbol=args.source.strip() or "ALL",
        status="ok",
        message=f"sources={len(rows)} inserted={inserted} labels={dict(label_counts)}",
        payload_json={"source_count": len(rows), "labels": dict(label_counts)},
    )
    print(f"Source quality scoring complete: sources={len(rows)} inserted={inserted} labels={dict(label_counts)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
