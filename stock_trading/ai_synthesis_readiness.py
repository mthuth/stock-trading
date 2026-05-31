#!/usr/bin/env python3
"""Deterministic AI synthesis readiness rules.

The functions in this module decide whether existing evidence is ready to be
handed to a future AI-written research brief. They are explanatory only and do
not change recommendation scores, labels, targets, allocation, or gates.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Mapping, Sequence


READINESS_STATUSES = {
    "ready_for_ai_synthesis",
    "partially_ready",
    "needs_review",
    "needs_corroboration",
    "not_enough_data",
    "blocked_by_provider_gap",
    "ignore_for_now",
}

HIGH_IMPACT_TYPES = {
    "earnings_guidance",
    "filing_disclosure",
    "product_launch",
    "ai_platform_update",
    "infrastructure_capacity",
    "security_risk",
    "analyst_target",
}
READY_CORROBORATION_LABELS = {"primary_plus_confirmed", "independent_confirmed", "multi_source_confirmed"}
BLOCKING_PROVIDER_STATUSES = {"blocked", "rate_limited", "parser_gap", "error"}
REVIEW_PROVIDER_STATUSES = {"missing", "stale"}
OPEN_VERIFICATION_STATUSES = {"open", "queued", "pending", "manual", "auto", "needs_review"}
WEAK_TARGET_CONFIDENCE = {"low", "needs review", "needs_review"}
BAD_SOURCE_HEALTH = {"blocked", "stale", "needs_review", "not_enough_data"}
READY_DECISION_STATUSES = {"ready", "passed", "safe", "safe_to_buy", "decision_safe"}


@dataclass(frozen=True)
class EventReview:
    status: str
    reason: str
    action: str


@dataclass(frozen=True)
class SynthesisReadiness:
    symbol: str
    status: str
    score: float
    summary: str
    reason_codes: list[str] = field(default_factory=list)
    eligible_for_ai_synthesis: bool = False


def clean(value: object) -> str:
    return str(value or "").strip()


def normalized_token(value: object) -> str:
    return clean(value).lower().replace("-", "_").replace(" ", "_")


def row_value(row: object, key: str, default: object = "") -> object:
    if isinstance(row, Mapping):
        return row.get(key, default)
    try:
        return row[key]  # type: ignore[index]
    except Exception:
        return getattr(row, key, default)


def row_int(row: object, key: str) -> int:
    try:
        return int(row_value(row, key, 0) or 0)
    except (TypeError, ValueError):
        return 0


def classify_event_review(row: object) -> EventReview:
    label = normalized_token(row_value(row, "corroboration_label"))
    confidence = normalized_token(row_value(row, "confidence"))
    event_type = normalized_token(row_value(row, "event_type"))
    source_count = row_int(row, "source_count")
    primary_count = row_int(row, "primary_source_count")
    company_count = row_int(row, "company_source_count")
    independent_count = row_int(row, "independent_source_count")
    opinion_count = row_int(row, "opinion_source_count")

    if label in READY_CORROBORATION_LABELS and confidence in {"high", "medium_high", "medium"}:
        return EventReview(
            "ready_for_synthesis",
            "Corroborated event has enough source breadth for deterministic synthesis input.",
            "Use in synthesis packet.",
        )
    if primary_count > 0 and event_type in HIGH_IMPACT_TYPES:
        return EventReview(
            "ready_for_synthesis",
            "High-impact primary-source event can support careful synthesis framing.",
            "Use with primary-source framing.",
        )
    if label == "company_only" or (company_count > 0 and independent_count == 0 and primary_count == 0):
        return EventReview(
            "needs_corroboration",
            "Company-framed event should be checked against independent coverage before strong synthesis claims.",
            "Look for independent confirmation.",
        )
    if opinion_count > 0 and source_count <= max(1, opinion_count):
        return EventReview(
            "ignore_for_now",
            "Opinion/context-only event has weak corroboration.",
            "Keep visible but exclude from synthesis packet.",
        )
    if label == "single_source" and event_type in HIGH_IMPACT_TYPES:
        return EventReview(
            "needs_review",
            "High-impact event has only one non-primary source; review before synthesis emphasis.",
            "Verify with another source or primary document.",
        )
    return EventReview(
        "needs_review",
        "Event needs review before future AI synthesis.",
        "Inspect source members and corroboration.",
    )


def review_counts_from_rows(rows: Sequence[Mapping[str, object]]) -> dict[str, int]:
    return dict(Counter(clean(row.get("review_status")) for row in rows if clean(row.get("review_status"))))


def parse_date(value: object) -> date | None:
    text = clean(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None


def latest_event_date(events: Sequence[object]) -> date | None:
    dates = [parsed for parsed in (parse_date(row_value(event, "latest_evidence_at")) for event in events) if parsed]
    return max(dates) if dates else None


def context_list(context: Mapping[str, object], key: str) -> list[Mapping[str, object]]:
    value = context.get(key)
    if isinstance(value, list):
        return [item for item in value if isinstance(item, Mapping)]
    return []


def provider_gap_reason_codes(provider_gaps: Sequence[Mapping[str, object]]) -> tuple[list[str], list[str]]:
    blocking: list[str] = []
    review: list[str] = []
    for gap in provider_gaps:
        status = normalized_token(gap.get("status"))
        provider = clean(gap.get("provider") or "provider")
        field_name = clean(gap.get("field_name") or "data")
        code = f"provider_gap:{status}:{provider}:{field_name}"
        if status in BLOCKING_PROVIDER_STATUSES:
            blocking.append(code)
        elif status in REVIEW_PROVIDER_STATUSES:
            review.append(code)
    return blocking, review


def verification_reason_codes(queue_rows: Sequence[Mapping[str, object]]) -> list[str]:
    reasons: list[str] = []
    for row in queue_rows:
        status = normalized_token(row.get("status"))
        if not status or status in OPEN_VERIFICATION_STATUSES:
            reasons.append(f"verification_open:{clean(row.get('insight_type') or row.get('reason') or 'verification')}")
    return reasons


def source_health_reason_codes(rows: Sequence[Mapping[str, object]]) -> list[str]:
    reasons: list[str] = []
    for row in rows:
        label = normalized_token(row.get("quality_label") or row.get("status"))
        if label in BAD_SOURCE_HEALTH:
            reasons.append(f"source_health:{label}:{clean(row.get('source_name') or row.get('source') or 'source')}")
    return reasons


def target_confidence_reason_code(value: object) -> str:
    confidence = normalized_token(value)
    if confidence in WEAK_TARGET_CONFIDENCE:
        return f"weak_target_confidence:{confidence}"
    return ""


def decision_safety_reason_code(context: Mapping[str, object]) -> str:
    decision = context.get("decision_safety")
    if not isinstance(decision, Mapping):
        status = normalized_token(context.get("decision_safety_status"))
        if status and status not in READY_DECISION_STATUSES:
            return f"decision_safety:{status}"
        return ""
    safe_to_buy = decision.get("safe_to_buy")
    status = normalized_token(decision.get("status"))
    if safe_to_buy is False or (status and status not in READY_DECISION_STATUSES):
        return f"decision_safety:{status or 'blocked'}"
    return ""


def event_metrics(events: Sequence[object]) -> dict[str, int]:
    return {
        "events": len(events),
        "source_count": sum(row_int(event, "source_count") for event in events),
        "evidence_count": sum(row_int(event, "evidence_count") for event in events),
        "independent_events": sum(1 for event in events if row_int(event, "independent_source_count") > 0),
        "primary_events": sum(1 for event in events if row_int(event, "primary_source_count") > 0),
        "company_events": sum(1 for event in events if row_int(event, "company_source_count") > 0),
        "opinion_events": sum(1 for event in events if row_int(event, "opinion_source_count") > 0),
    }


def readiness_score(review_counts: Mapping[str, int], reason_codes: Sequence[str], events: Sequence[object]) -> float:
    total_events = max(1, len(events))
    ready = int(review_counts.get("ready_for_synthesis", 0))
    needs_review = int(review_counts.get("needs_review", 0))
    needs_corroboration = int(review_counts.get("needs_corroboration", 0))
    ignored = int(review_counts.get("ignore_for_now", 0))
    score = ((ready * 2.0) - (needs_review * 0.55) - (needs_corroboration * 0.35) - (ignored * 0.2)) / total_events
    score = max(0.0, min(1.0, score / 2.0))
    if any(code.startswith(tuple(f"provider_gap:{status}:" for status in BLOCKING_PROVIDER_STATUSES)) for code in reason_codes):
        score = min(score, 0.15)
    elif any(code.startswith(("verification_open:", "decision_safety:", "weak_target_confidence:", "stale_evidence")) for code in reason_codes):
        score = min(score, 0.45)
    elif any(code.startswith("source_health:") for code in reason_codes):
        score = min(score, 0.55)
    return round(score, 3)


def evaluate_synthesis_readiness(
    symbol: str,
    events: Sequence[object],
    review_counts: Mapping[str, int],
    context: Mapping[str, object] | None = None,
    *,
    report_date: object = "",
    stale_after_days: int = 45,
) -> SynthesisReadiness:
    context = context or {}
    metrics = event_metrics(events)
    reason_codes: list[str] = []

    blocking_gaps, review_gaps = provider_gap_reason_codes(context_list(context, "provider_gaps"))
    reason_codes.extend(blocking_gaps)
    reason_codes.extend(review_gaps)
    reason_codes.extend(verification_reason_codes(context_list(context, "verification_queue")))
    reason_codes.extend(source_health_reason_codes(context_list(context, "source_health")))
    target_reason = target_confidence_reason_code(context.get("target_confidence"))
    if target_reason:
        reason_codes.append(target_reason)
    decision_reason = decision_safety_reason_code(context)
    if decision_reason:
        reason_codes.append(decision_reason)

    latest = latest_event_date(events)
    as_of = parse_date(report_date)
    if latest and as_of and (as_of - latest).days > stale_after_days:
        reason_codes.append(f"stale_evidence:{(as_of - latest).days}d")

    ready = int(review_counts.get("ready_for_synthesis", 0))
    needs_review = int(review_counts.get("needs_review", 0))
    needs_corroboration = int(review_counts.get("needs_corroboration", 0))
    ignored = int(review_counts.get("ignore_for_now", 0))
    meaningful_events = metrics["events"] - ignored

    if not events or (meaningful_events <= 0 and ignored == 0):
        status = "not_enough_data"
        summary = "No meaningful event clusters are available for AI synthesis."
    elif blocking_gaps:
        status = "blocked_by_provider_gap"
        summary = "Provider gaps block enough evidence collection for a trustworthy AI synthesis."
    elif meaningful_events <= 0 and ignored > 0:
        status = "ignore_for_now"
        summary = "Available evidence is opinion or context only; do not synthesize yet."
    elif needs_corroboration > 0 and metrics["independent_events"] == 0:
        status = "needs_corroboration"
        summary = "Company-framed evidence needs independent corroboration before strong synthesis claims."
    elif metrics["evidence_count"] < 2 or metrics["source_count"] < 2:
        status = "not_enough_data"
        summary = "Evidence volume or source breadth is too thin for AI synthesis."
    elif any(
        code.startswith(
            (
                "provider_gap:missing:",
                "provider_gap:stale:",
                "verification_open:",
                "decision_safety:",
                "weak_target_confidence:",
                "stale_evidence",
                "source_health:",
            )
        )
        for code in reason_codes
    ):
        status = "needs_review"
        summary = "Evidence exists, but review blockers or weak context must be cleared before AI synthesis."
    elif ready >= 2 and metrics["primary_events"] > 0 and metrics["independent_events"] > 0:
        status = "ready_for_ai_synthesis"
        summary = "Primary evidence and independent corroboration are sufficient for AI synthesis."
    elif ready >= 1 or metrics["primary_events"] > 0:
        status = "partially_ready"
        summary = "Some evidence can be synthesized with careful framing, but additional support would improve trust."
    elif needs_corroboration > 0:
        status = "needs_corroboration"
        summary = "Evidence needs corroboration before AI synthesis."
    elif needs_review > 0:
        status = "needs_review"
        summary = "Evidence needs review before AI synthesis."
    else:
        status = "not_enough_data"
        summary = "Evidence is not strong enough for AI synthesis."

    score = readiness_score(review_counts, reason_codes, events)
    eligible = status in {"ready_for_ai_synthesis", "partially_ready"}
    return SynthesisReadiness(
        symbol=clean(symbol).upper(),
        status=status,
        score=score,
        summary=summary,
        reason_codes=reason_codes,
        eligible_for_ai_synthesis=eligible,
    )
