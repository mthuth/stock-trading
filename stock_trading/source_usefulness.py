"""Review-only source usefulness history metrics.

This module turns historical source-quality observations, source feedback, and
optional follow-through associations into audit fields. The output is
intentionally explanatory: it must not change scores, source weights,
recommendation labels, target prices, decision safety, allocation, broker
behavior, or trading.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Mapping


USEFULNESS_LABELS = {
    "consistently_useful",
    "useful_but_sparse",
    "useful_context",
    "noisy",
    "stale_or_blocked",
    "needs_more_history",
}

REVIEW_ONLY_NOTE = (
    "Review-only source usefulness. These metrics do not automatically change "
    "scores, source weights, actions, targets, decision safety, allocations, "
    "broker behavior, or trading."
)

POSITIVE_FEEDBACK_TYPES = {"useful_source", "useful_insight", "agree", "helpful"}
NEGATIVE_FEEDBACK_TYPES = {"noisy_source", "unsupported_claim", "weak_source", "disagree", "misleading"}
POSITIVE_OUTCOMES = {"positive_follow_through", "target_progress"}
NEGATIVE_OUTCOMES = {"negative_follow_through", "drawdown_warning"}
STALE_OR_BLOCKED_LABELS = {
    "blocked",
    "blocked_source",
    "parser_gap",
    "stale",
    "stale_source",
    "rate_limited",
}


def text(value: object, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def to_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def to_int(value: object, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def parse_datetime(value: object) -> datetime | None:
    raw = text(value)
    if not raw:
        return None
    for candidate in (raw, raw.replace("Z", "+00:00"), raw[:19]):
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            continue
    return None


def source_name(row: Mapping[str, object]) -> str:
    return text(row.get("source_name") or row.get("source") or row.get("provider"))


def row_date(row: Mapping[str, object]) -> str:
    return text(
        row.get("metric_date")
        or row.get("created_at")
        or row.get("fetched_at")
        or row.get("source_timestamp")
        or row.get("date")
    )


def has_aggregate_fields(row: Mapping[str, object]) -> bool:
    return any(key in row for key in ("total_evidence", "tag_rate", "avg_tag_confidence", "quality_label"))


def row_evidence_count(row: Mapping[str, object]) -> int:
    if "total_evidence" in row:
        return to_int(row.get("total_evidence"))
    if "evidence_count" in row:
        return to_int(row.get("evidence_count"))
    return 1


def row_symbol_match_quality(row: Mapping[str, object]) -> float:
    if "symbol_match_quality" in row:
        return max(0.0, min(1.0, to_float(row.get("symbol_match_quality"))))
    if "tag_rate" in row:
        return max(0.0, min(1.0, to_float(row.get("tag_rate"))))
    symbol = text(row.get("symbol")).upper()
    if symbol and symbol != "MARKET":
        return 1.0
    return 0.0


def row_confidence(row: Mapping[str, object]) -> float:
    if "avg_tag_confidence" in row:
        return max(0.0, min(1.0, to_float(row.get("avg_tag_confidence"))))
    if "average_confidence" in row:
        return max(0.0, min(1.0, to_float(row.get("average_confidence"))))
    raw = row.get("confidence")
    if isinstance(raw, str):
        buckets = {"high": 0.9, "medium": 0.7, "low": 0.45, "needs_review": 0.25}
        return buckets.get(raw.strip().lower(), to_float(raw))
    return max(0.0, min(1.0, to_float(raw)))


def row_status_label(row: Mapping[str, object]) -> str:
    return text(row.get("quality_label") or row.get("status") or row.get("source_status")).lower()


def duplicate_key(row: Mapping[str, object]) -> str:
    explicit = text(row.get("duplicate_key") or row.get("provider_id") or row.get("source_url"))
    if explicit:
        return explicit
    title = text(row.get("title")).lower()
    symbol = text(row.get("symbol")).upper()
    date_value = row_date(row)[:10]
    if title or symbol or date_value:
        return "|".join((symbol, date_value, title))
    return ""


def source_names_from_row(row: Mapping[str, object]) -> set[str]:
    name = source_name(row)
    names = {name} if name else set()
    raw_sources = row.get("sources") or row.get("source_names")
    if isinstance(raw_sources, str):
        names.update(part.strip() for part in raw_sources.split(",") if part.strip())
    elif isinstance(raw_sources, Iterable):
        names.update(text(part) for part in raw_sources if text(part))
    return names


def feedback_delta(row: Mapping[str, object]) -> float:
    if "rating_delta" in row or "delta" in row:
        return to_float(row.get("rating_delta", row.get("delta")))
    feedback_type = text(row.get("feedback_type") or row.get("type")).lower()
    if feedback_type in POSITIVE_FEEDBACK_TYPES:
        return 0.1
    if feedback_type in NEGATIVE_FEEDBACK_TYPES:
        return -0.1
    return 0.0


def empty_state(name: str) -> dict[str, object]:
    return {
        "source_name": name,
        "source_category": "",
        "metric_observations": 0,
        "aggregate_rows": False,
        "evidence_rows": 0,
        "max_evidence_count": 0,
        "total_evidence_count": 0,
        "weighted_match_sum": 0.0,
        "weighted_confidence_sum": 0.0,
        "confidence_weight": 0,
        "low_confidence_matches": 0,
        "duplicate_records": 0,
        "records_seen": 0,
        "blocked_count": 0,
        "parser_gap_count": 0,
        "stale_count": 0,
        "latest_status": "",
        "latest_status_at": "",
        "latest_issue": "",
        "evidence_count_over_time": [],
        "duplicate_keys": set(),
        "seen_duplicate_keys": set(),
        "positive_user_feedback": 0,
        "negative_user_feedback": 0,
        "feedback_delta": 0.0,
        "follow_through_count": 0,
        "positive_follow_through": 0,
        "negative_follow_through": 0,
    }


def update_latest_status(state: dict[str, object], row: Mapping[str, object]) -> None:
    status = row_status_label(row)
    when = row_date(row)
    parsed = parse_datetime(when)
    current = parse_datetime(state.get("latest_status_at"))
    if status and (current is None or parsed is None or parsed >= current):
        state["latest_status"] = status
        state["latest_status_at"] = when
        state["latest_issue"] = text(row.get("latest_issue") or row.get("message") or row.get("notes"))


def absorb_quality_or_evidence_row(state: dict[str, object], row: Mapping[str, object]) -> None:
    state["metric_observations"] = to_int(state["metric_observations"]) + 1
    category = text(row.get("source_category") or row.get("source_type"))
    if category and not state.get("source_category"):
        state["source_category"] = category

    count = max(0, row_evidence_count(row))
    weight = max(1, count)
    state["aggregate_rows"] = bool(state["aggregate_rows"]) or has_aggregate_fields(row)
    state["evidence_rows"] = to_int(state["evidence_rows"]) + (0 if has_aggregate_fields(row) else 1)
    state["max_evidence_count"] = max(to_int(state["max_evidence_count"]), count)
    state["total_evidence_count"] = to_int(state["total_evidence_count"]) + count
    state["weighted_match_sum"] = to_float(state["weighted_match_sum"]) + (row_symbol_match_quality(row) * weight)
    confidence = row_confidence(row)
    if confidence > 0:
        state["weighted_confidence_sum"] = to_float(state["weighted_confidence_sum"]) + (confidence * weight)
        state["confidence_weight"] = to_int(state["confidence_weight"]) + weight

    low_confidence = to_int(row.get("low_confidence_matches"))
    if not has_aggregate_fields(row) and 0 < confidence < 0.55:
        low_confidence += 1
    state["low_confidence_matches"] = to_int(state["low_confidence_matches"]) + low_confidence

    seen = to_int(row.get("records_seen")) or count
    duplicate_count = to_int(row.get("duplicate_records"))
    key = duplicate_key(row)
    if key:
        duplicate_keys = state["duplicate_keys"]
        seen_duplicate_keys = state["seen_duplicate_keys"]
        if isinstance(duplicate_keys, set) and isinstance(seen_duplicate_keys, set):
            if key in seen_duplicate_keys:
                duplicate_count += 1
                duplicate_keys.add(key)
            seen_duplicate_keys.add(key)
    state["records_seen"] = to_int(state["records_seen"]) + seen
    state["duplicate_records"] = to_int(state["duplicate_records"]) + duplicate_count

    blocked_count = to_int(row.get("blocked_count") or row.get("blocked_runs"))
    parser_gap_count = to_int(row.get("parser_gap_count"))
    stale_count = to_int(row.get("stale_count"))
    status = row_status_label(row)
    if status in {"blocked", "blocked_source", "rate_limited"}:
        blocked_count += 1 if not blocked_count else 0
    if status == "parser_gap":
        parser_gap_count += 1 if not parser_gap_count else 0
    if status in {"stale", "stale_source"}:
        stale_count += 1 if not stale_count else 0
    state["blocked_count"] = to_int(state["blocked_count"]) + blocked_count
    state["parser_gap_count"] = to_int(state["parser_gap_count"]) + parser_gap_count
    state["stale_count"] = to_int(state["stale_count"]) + stale_count

    state["evidence_count_over_time"].append(
        {
            "date": row_date(row),
            "evidence_count": count,
            "symbol_match_quality": round(row_symbol_match_quality(row), 4),
            "average_confidence": round(confidence, 4),
            "status": status,
        }
    )
    update_latest_status(state, row)


def absorb_feedback_row(states: dict[str, dict[str, object]], row: Mapping[str, object]) -> None:
    name = source_name(row)
    if not name:
        return
    state = states.setdefault(name, empty_state(name))
    delta = feedback_delta(row)
    state["feedback_delta"] = round(to_float(state["feedback_delta"]) + delta, 4)
    if delta > 0:
        state["positive_user_feedback"] = to_int(state["positive_user_feedback"]) + 1
    elif delta < 0:
        state["negative_user_feedback"] = to_int(state["negative_user_feedback"]) + 1


def absorb_follow_through_row(states: dict[str, dict[str, object]], row: Mapping[str, object]) -> None:
    status = text(row.get("outcome_status") or row.get("follow_through_status")).lower()
    for name in source_names_from_row(row):
        state = states.setdefault(name, empty_state(name))
        state["follow_through_count"] = to_int(state["follow_through_count"]) + 1
        if status in POSITIVE_OUTCOMES:
            state["positive_follow_through"] = to_int(state["positive_follow_through"]) + 1
        elif status in NEGATIVE_OUTCOMES:
            state["negative_follow_through"] = to_int(state["negative_follow_through"]) + 1


def usefulness_label(metrics: Mapping[str, object]) -> str:
    evidence_count = to_int(metrics.get("evidence_count"))
    observations = to_int(metrics.get("metric_observations"))
    match_quality = to_float(metrics.get("symbol_match_quality"))
    avg_confidence = to_float(metrics.get("average_confidence"))
    duplicate_rate = to_float(metrics.get("duplicate_rate"))
    low_confidence_rate = to_float(metrics.get("low_confidence_match_rate"))
    positive_feedback = to_int(metrics.get("positive_user_feedback"))
    negative_feedback = to_int(metrics.get("negative_user_feedback"))
    positive_follow = to_int(metrics.get("positive_follow_through"))
    negative_follow = to_int(metrics.get("negative_follow_through"))
    latest_status = text(metrics.get("latest_status")).lower()

    if latest_status in STALE_OR_BLOCKED_LABELS or to_int(metrics.get("blocked_count")) or to_int(metrics.get("parser_gap_count")):
        return "stale_or_blocked"
    sparse_but_strong = evidence_count > 0 and match_quality >= 0.65 and avg_confidence >= 0.70
    if evidence_count < 3 and observations < 2 and positive_feedback == 0 and positive_follow == 0 and not sparse_but_strong:
        return "needs_more_history"
    if (
        negative_feedback > positive_feedback
        or negative_follow > positive_follow
        or (evidence_count >= 3 and match_quality < 0.35)
        or (evidence_count >= 3 and avg_confidence and avg_confidence < 0.55)
        or duplicate_rate >= 0.35
        or low_confidence_rate >= 0.50
    ):
        return "noisy"
    if (
        observations >= 3
        and evidence_count >= 10
        and match_quality >= 0.70
        and avg_confidence >= 0.72
        and duplicate_rate <= 0.25
        and low_confidence_rate <= 0.25
    ):
        return "consistently_useful"
    if positive_feedback > 0 or positive_follow > 0 or (evidence_count < 10 and match_quality >= 0.65 and avg_confidence >= 0.70):
        return "useful_but_sparse"
    if evidence_count > 0:
        return "useful_context"
    return "needs_more_history"


def materialize_state(state: Mapping[str, object]) -> dict[str, object]:
    aggregate_rows = bool(state.get("aggregate_rows"))
    evidence_count = to_int(state.get("max_evidence_count") if aggregate_rows else state.get("total_evidence_count"))
    match_denominator = to_int(state.get("total_evidence_count")) or 1
    confidence_weight = to_int(state.get("confidence_weight")) or 1
    records_seen = to_int(state.get("records_seen")) or evidence_count
    low_confidence_matches = to_int(state.get("low_confidence_matches"))
    metrics = {
        "source_name": text(state.get("source_name")),
        "source_category": text(state.get("source_category")),
        "label": "",
        "evidence_count": evidence_count,
        "metric_observations": to_int(state.get("metric_observations")),
        "symbol_match_quality": round(to_float(state.get("weighted_match_sum")) / match_denominator, 4),
        "average_confidence": round(to_float(state.get("weighted_confidence_sum")) / confidence_weight, 4),
        "blocked_count": to_int(state.get("blocked_count")),
        "parser_gap_count": to_int(state.get("parser_gap_count")),
        "stale_count": to_int(state.get("stale_count")),
        "latest_status": text(state.get("latest_status")),
        "latest_status_at": text(state.get("latest_status_at")),
        "latest_issue": text(state.get("latest_issue")),
        "low_confidence_match_rate": round(low_confidence_matches / max(1, to_int(state.get("total_evidence_count"))), 4),
        "duplicate_rate": round(to_int(state.get("duplicate_records")) / max(1, records_seen), 4),
        "duplicate_records": to_int(state.get("duplicate_records")),
        "records_seen": records_seen,
        "follow_through_count": to_int(state.get("follow_through_count")),
        "positive_follow_through": to_int(state.get("positive_follow_through")),
        "negative_follow_through": to_int(state.get("negative_follow_through")),
        "positive_user_feedback": to_int(state.get("positive_user_feedback")),
        "negative_user_feedback": to_int(state.get("negative_user_feedback")),
        "feedback_delta": round(to_float(state.get("feedback_delta")), 4),
        "evidence_count_over_time": sorted(
            list(state.get("evidence_count_over_time") or []),
            key=lambda item: text(item.get("date")) if isinstance(item, Mapping) else "",
        ),
        "review_only": True,
        "score_impact": "none",
        "source_weight_impact": "none",
        "notes": REVIEW_ONLY_NOTE,
    }
    metrics["label"] = usefulness_label(metrics)
    return metrics


def build_source_usefulness(
    source_rows: Iterable[Mapping[str, object]],
    feedback_rows: Iterable[Mapping[str, object]] | None = None,
    follow_through_rows: Iterable[Mapping[str, object]] | None = None,
) -> list[dict[str, object]]:
    """Build deterministic, review-only source usefulness rows.

    ``source_rows`` may be historical rows from ``source_quality_metrics`` or
    raw evidence-like rows. The function intentionally does not read storage or
    call providers so tests and future dashboard integrations can use fixtures.
    """

    states: dict[str, dict[str, object]] = {}
    for row in source_rows:
        name = source_name(row)
        if not name:
            continue
        state = states.setdefault(name, empty_state(name))
        absorb_quality_or_evidence_row(state, row)

    for row in feedback_rows or []:
        absorb_feedback_row(states, row)

    for row in follow_through_rows or []:
        absorb_follow_through_row(states, row)

    return sorted(
        (materialize_state(state) for state in states.values()),
        key=lambda row: (text(row["label"]), text(row["source_name"])),
    )


def summarize_source_usefulness(rows: Iterable[Mapping[str, object]]) -> dict[str, object]:
    counts = {label: 0 for label in sorted(USEFULNESS_LABELS)}
    source_count = 0
    for row in rows:
        source_count += 1
        label = text(row.get("label"))
        if label in counts:
            counts[label] += 1
    return {
        "review_only": True,
        "source_count": source_count,
        "labels": counts,
        "notes": REVIEW_ONLY_NOTE,
    }


__all__ = [
    "REVIEW_ONLY_NOTE",
    "USEFULNESS_LABELS",
    "build_source_usefulness",
    "summarize_source_usefulness",
    "usefulness_label",
]
