#!/usr/bin/env python3
"""Deterministic source-health rollup labels and notes."""

from __future__ import annotations

from typing import Any


CONTEXT_CATEGORIES = {
    "ai_research",
    "newsletter",
    "podcast",
    "semiconductor_news",
    "tech_news",
}
LOCAL_DERIVED_SOURCES = {
    "Local deterministic tagger",
    "Local evidence event clusterer",
    "Local ingestion planner",
    "Local synthesis readiness preparer",
    "Local source depth curator",
    "Local source quality scorer",
}
QUALITY_LABEL_ORDER = {
    "blocked_source": 0,
    "parser_gap": 1,
    "stale_source": 2,
    "noisy_source": 3,
    "not_enough_data": 4,
    "useful_context": 5,
    "useful_source": 6,
}


def is_local_derived_source(source_name: object) -> bool:
    return str(source_name or "").strip() in LOCAL_DERIVED_SOURCES


def classify_source_health(
    state: dict[str, Any],
    *,
    total_evidence: int,
    tag_rate: float,
    avg_confidence: float | None,
    days_since_success: float | None,
) -> str:
    """Classify source quality for review only; labels do not affect scoring."""

    category = str(state.get("source_category") or "")
    blocked_count = int(state.get("blocked_runs") or 0)
    parser_gap_count = int(state.get("parser_gap_count") or 0)
    latest_status = str(state.get("latest_status") or "")
    low_confidence = int(state.get("low_confidence_matches") or 0)

    if latest_status == "blocked" or (blocked_count >= 1 and not state.get("latest_success")):
        return "blocked_source"
    if latest_status == "parser_gap" or (parser_gap_count >= 1 and total_evidence < 3):
        return "parser_gap"
    if days_since_success is not None and days_since_success > 7:
        return "stale_source"
    if total_evidence < 3:
        return "not_enough_data"
    if tag_rate >= 0.50 and (avg_confidence or 0) >= 0.80:
        return "useful_source"
    if total_evidence >= 5 and (
        tag_rate < 0.20
        or (avg_confidence is not None and avg_confidence < 0.70)
        or low_confidence > max(3, int(total_evidence * 0.50))
    ):
        return "noisy_source"
    if category in CONTEXT_CATEGORIES or tag_rate >= 0.20:
        return "useful_context"
    return "not_enough_data"


def notes_for_source_health(
    state: dict[str, Any],
    *,
    label: str,
    total_evidence: int,
    tag_rate: float,
    avg_confidence: float | None,
    days_since_success: float | None,
) -> str:
    notes: list[str] = []
    if state.get("latest_issue"):
        notes.append(f"latest issue: {state['latest_issue']}")
    if label == "useful_source":
        notes.append("high symbol-specific evidence coverage")
    elif label == "useful_context":
        notes.append("useful contextual evidence; corroboration still required")
    elif label == "noisy_source":
        notes.append("low symbol-specific signal or low confidence matches")
    elif label == "blocked_source":
        notes.append("provider access or quota is blocking refresh")
    elif label == "parser_gap":
        notes.append("source fetched but parser produced too little usable evidence")
    elif label == "not_enough_data":
        notes.append("not enough evidence to judge source usefulness")
    if tag_rate < 0.20 and total_evidence >= 5:
        notes.append("low symbol-match coverage")
    if avg_confidence is not None and avg_confidence < 0.70:
        notes.append("low average match confidence")
    if days_since_success is not None and days_since_success > 7:
        notes.append(f"last success {days_since_success:.1f}d ago")
    if not notes:
        notes.append("measurement only; no score impact")
    return "; ".join(dict.fromkeys(notes))[:500]


def quality_sort(label: object) -> int:
    return QUALITY_LABEL_ORDER.get(str(label), 9)
