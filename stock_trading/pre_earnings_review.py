"""Review-only pre-earnings setup review helpers."""

from __future__ import annotations

import copy
from datetime import date, datetime
from typing import Iterable, Mapping


SETUP_LABELS = {
    "attractive_pre_earnings_review",
    "wait_for_earnings",
    "avoid_pre_earnings_add",
    "data_insufficient",
    "not_in_pre_earnings_window",
}
REVIEW_ACTIONS = {
    "consider_small_review_only_add",
    "wait_until_after_report",
    "hold_buy_capacity",
    "verify_data_first",
    "ignore_for_now",
}
RECOMMENDATION_ONLY_NOTE = (
    "Recommendation-only pre-earnings setup review. This helper does not place trades, "
    "preview orders, write to brokers, change official recommendation actions, change scores, "
    "change targets, change target confidence, change decision-safety rules, change allocation, "
    "or tune the model."
)
LOW_CONFIDENCE = {"low", "needs review", "needs_review", "weak"}
HIGH_CONFIDENCE = {"high", "medium"}
BLOCKING_GAP_SEVERITIES = {"blocker", "critical", "high"}
BLOCKING_GAP_STATUSES = {
    "blocked",
    "rate_limited",
    "missing",
    "stale",
    "parser_gap",
    "not_implemented",
    "needs_refresh",
    "needs review",
}
WEAK_SOURCE_LABELS = {"noisy", "stale_or_blocked", "needs_more_history", "not_enough_data"}


def text(value: object, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def as_dict(value: object) -> dict[str, object]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def as_list(value: object) -> list[object]:
    if isinstance(value, list):
        return copy.deepcopy(value)
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        return [value] if value else []
    return []


def number(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def boolish(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return text(value).lower() in {"1", "true", "yes", "ready", "safe", "available"}


def parse_date(value: object) -> date | None:
    raw = text(value)
    if not raw:
        return None
    for candidate in (raw, raw[:10]):
        try:
            return datetime.fromisoformat(candidate).date()
        except ValueError:
            continue
    return None


def first_text(*values: object) -> str:
    for value in values:
        candidate = text(value)
        if candidate:
            return candidate
    return ""


def normalized_confidence(*values: object) -> str:
    for value in values:
        candidate = text(value)
        if candidate:
            return candidate
    return ""


def decision_gate_context(
    decision_safety: Mapping[str, object] | None,
    recommendation: Mapping[str, object],
    long_term_add: Mapping[str, object],
) -> dict[str, object]:
    gate = as_dict(decision_safety)
    if not gate:
        gate = as_dict(recommendation.get("decision_gate") or long_term_add.get("decision_gate"))
    if not gate:
        safe_value = (
            recommendation.get("safe_to_buy")
            if "safe_to_buy" in recommendation
            else long_term_add.get("safe_to_buy")
        )
        status = first_text(
            recommendation.get("decision_gate_status"),
            recommendation.get("decision_safety_status"),
            long_term_add.get("decision_gate_status"),
            long_term_add.get("decision_safety_status"),
        )
        gate = {
            "safe_to_buy": boolish(safe_value) if safe_value is not None else status.lower() == "ready",
            "status": status or ("Ready" if boolish(safe_value) else "Blocked"),
            "reasons": as_list(recommendation.get("blocked_reasons") or long_term_add.get("blocked_reasons")),
        }
    gate.setdefault("reasons", [])
    return gate


def provider_gap_reasons(provider_gaps: Iterable[object] | object | None) -> tuple[list[str], list[str]]:
    gaps = as_list(provider_gaps)
    blockers: list[str] = []
    data_gaps: list[str] = []
    for gap in gaps:
        if isinstance(gap, Mapping):
            severity = text(gap.get("severity") or gap.get("Severity")).lower()
            status = text(gap.get("status") or gap.get("Status")).lower()
            provider = first_text(gap.get("provider"), gap.get("Provider"), gap.get("source"), gap.get("Source"))
            field = first_text(gap.get("field"), gap.get("Field"), gap.get("endpoint"), gap.get("Endpoint"))
            issue = first_text(gap.get("latest_issue"), gap.get("message"), gap.get("Latest Issue"), gap.get("issue"))
            label = " ".join(part for part in (provider, field, issue) if part) or "Provider gap"
        else:
            severity = ""
            status = text(gap).lower()
            label = text(gap)
        if label:
            data_gaps.append(label)
        if severity in BLOCKING_GAP_SEVERITIES or status in BLOCKING_GAP_STATUSES:
            blockers.append(label or "Blocking provider gap")
    return list(dict.fromkeys(blockers)), list(dict.fromkeys(data_gaps))


def volatility_context(summary: Mapping[str, object] | None) -> tuple[list[str], list[str], int]:
    data = as_dict(summary)
    if not data:
        return [], [], 0
    reasons: list[str] = []
    blockers: list[str] = []
    penalty = 0
    status = text(data.get("status")).lower()
    confidence = text(data.get("confidence")).lower()
    daily_move = number(data.get("max_daily_move_pct") or data.get("recent_daily_move_pct"))
    realized = number(data.get("realized_volatility_pct") or data.get("volatility_pct"))
    history_days = number(data.get("history_days") or data.get("price_history_days"))
    if status in {"insufficient", "missing", "thin"} or confidence in {"low", "weak"}:
        blockers.append("Price history is insufficient for earnings-timing review.")
        penalty += 30
    if 0 < history_days < 20:
        blockers.append("Price history is too thin before earnings.")
        penalty += 25
    if daily_move >= 8 or realized >= 45:
        reasons.append("High volatility increases pre-earnings timing risk.")
        penalty += 25
    elif daily_move >= 5 or realized >= 30:
        reasons.append("Elevated volatility argues for smaller or delayed review.")
        penalty += 15
    return reasons, blockers, penalty


def ai_readiness_reason(readiness: Mapping[str, object] | None) -> tuple[list[str], int]:
    data = as_dict(readiness)
    if not data:
        return [], 0
    status = text(data.get("status") or data.get("readiness_status")).lower()
    eligible = data.get("eligible_for_ai_synthesis")
    if eligible is False or status in {"not_enough_data", "blocked_by_provider_gaps"}:
        return ["AI synthesis readiness is weak; use only as explanatory context."], 10
    if status in {"partially_ready", "needs_review"}:
        return ["AI synthesis is only partially ready before earnings."], 5
    return [], 0


def source_usefulness_reason(source_usefulness: Mapping[str, object] | None) -> tuple[list[str], int]:
    data = as_dict(source_usefulness)
    if not data:
        return [], 0
    label = text(data.get("label") or data.get("source_quality_label") or data.get("status")).lower()
    if label in WEAK_SOURCE_LABELS:
        return [f"Source usefulness is weak before earnings: {label}."], 10
    return [], 0


def prior_follow_through_reason(prior_follow_through: Mapping[str, object] | Iterable[object] | None) -> tuple[list[str], int]:
    rows = as_list(prior_follow_through)
    if isinstance(prior_follow_through, Mapping):
        rows = [prior_follow_through]
    reasons: list[str] = []
    penalty = 0
    for row in rows[:3]:
        if not isinstance(row, Mapping):
            continue
        label = text(row.get("outcome_label") or row.get("outcome_status")).lower()
        if label in {"likely_noisy", "negative_follow_through", "drawdown_warning"}:
            reasons.append("Prior earnings/catalyst follow-through was weak or negative.")
            penalty += 10
            break
    return reasons, penalty


def setup_from_score(score: int, blockers: list[str], days_until: int) -> tuple[str, str]:
    if blockers:
        if any("decision" in blocker.lower() or "provider" in blocker.lower() or "price history" in blocker.lower() for blocker in blockers):
            return "data_insufficient", "verify_data_first"
        return "avoid_pre_earnings_add", "hold_buy_capacity"
    if days_until <= 2 and score < 85:
        return "wait_for_earnings", "wait_until_after_report"
    if score >= 75:
        return "attractive_pre_earnings_review", "consider_small_review_only_add"
    if score >= 50:
        return "wait_for_earnings", "wait_until_after_report"
    return "avoid_pre_earnings_add", "hold_buy_capacity"


def review_pre_earnings_setup(
    *,
    earnings_event: Mapping[str, object] | None = None,
    recommendation: Mapping[str, object] | None = None,
    long_term_add: Mapping[str, object] | None = None,
    decision_safety: Mapping[str, object] | None = None,
    target_confidence: str | None = None,
    price_history_summary: Mapping[str, object] | None = None,
    provider_gaps: Iterable[object] | object | None = None,
    source_usefulness: Mapping[str, object] | None = None,
    ai_synthesis_readiness: Mapping[str, object] | None = None,
    prior_follow_through: Mapping[str, object] | Iterable[object] | None = None,
    as_of_date: str | date | None = None,
    pre_earnings_window_days: int = 14,
) -> dict[str, object]:
    """Classify a pre-earnings setup without mutating official recommendation behavior."""

    event = as_dict(earnings_event)
    rec = as_dict(recommendation)
    add = as_dict(long_term_add)
    as_of = as_of_date if isinstance(as_of_date, date) else parse_date(as_of_date)
    as_of = as_of or date.today()
    earnings_date_text = first_text(
        event.get("earnings_date"),
        event.get("event_date"),
        event.get("report_date"),
        rec.get("earnings_date"),
        add.get("earnings_date"),
    )
    earnings_date = parse_date(earnings_date_text)
    symbol = first_text(event.get("symbol"), rec.get("symbol"), add.get("symbol")).upper()
    company = first_text(event.get("company"), rec.get("company"), add.get("company"))
    confidence = normalized_confidence(
        target_confidence,
        rec.get("target_confidence"),
        rec.get("confidence"),
        add.get("target_confidence"),
        add.get("confidence"),
    )
    reasons: list[str] = []
    blockers: list[str] = []
    data_gaps: list[str] = []
    setup_score = 100

    if not earnings_date:
        return {
            "symbol": symbol,
            "company": company,
            "earnings_date": "",
            "days_until_earnings": None,
            "setup_label": "data_insufficient",
            "setup_score": 0,
            "recommended_review_action": "verify_data_first",
            "reasons": ["Missing earnings date blocks pre-earnings timing review."],
            "blockers": ["Missing earnings date"],
            "data_gaps": ["earnings_date"],
            "review_only": True,
            "recommendation_only_note": RECOMMENDATION_ONLY_NOTE,
        }

    days_until = (earnings_date - as_of).days
    if days_until < 0 or days_until > max(0, pre_earnings_window_days):
        return {
            "symbol": symbol,
            "company": company,
            "earnings_date": earnings_date.isoformat(),
            "days_until_earnings": days_until,
            "setup_label": "not_in_pre_earnings_window",
            "setup_score": 0,
            "recommended_review_action": "ignore_for_now",
            "reasons": [f"Earnings are outside the {pre_earnings_window_days}-day pre-earnings review window."],
            "blockers": [],
            "data_gaps": [],
            "review_only": True,
            "recommendation_only_note": RECOMMENDATION_ONLY_NOTE,
        }

    gate = decision_gate_context(decision_safety, rec, add)
    if not boolish(gate.get("safe_to_buy")):
        gate_reasons = [text(reason) for reason in as_list(gate.get("reasons")) if text(reason)]
        blockers.append("Decision safety is not ready before earnings.")
        blockers.extend(gate_reasons)
        setup_score -= 45

    confidence_lower = confidence.lower()
    if confidence_lower in LOW_CONFIDENCE:
        blockers.append(f"Target confidence is {confidence or 'low'} before earnings.")
        setup_score -= 30
    elif confidence_lower not in HIGH_CONFIDENCE:
        reasons.append("Target confidence is not clearly high or medium before earnings.")
        setup_score -= 10
    else:
        reasons.append(f"Target confidence is {confidence}.")

    gap_blockers, gaps = provider_gap_reasons(provider_gaps)
    if gap_blockers:
        blockers.extend(f"Provider gap blocks confidence: {gap}" for gap in gap_blockers)
        setup_score -= 30
    data_gaps.extend(gaps)

    volatility_reasons, volatility_blockers, volatility_penalty = volatility_context(price_history_summary)
    reasons.extend(volatility_reasons)
    blockers.extend(volatility_blockers)
    setup_score -= volatility_penalty

    ai_reasons, ai_penalty = ai_readiness_reason(ai_synthesis_readiness)
    reasons.extend(ai_reasons)
    setup_score -= ai_penalty

    source_reasons, source_penalty = source_usefulness_reason(source_usefulness)
    reasons.extend(source_reasons)
    setup_score -= source_penalty

    follow_reasons, follow_penalty = prior_follow_through_reason(prior_follow_through)
    reasons.extend(follow_reasons)
    setup_score -= follow_penalty

    if not reasons and not blockers:
        reasons.append("Long-term candidate is in the pre-earnings window with no blocking setup issue provided.")
    if days_until <= 2:
        reasons.append("Earnings are very near; size and timing need extra manual review.")
        setup_score -= 5

    setup_score = max(0, min(100, int(round(setup_score))))
    setup_label, review_action = setup_from_score(setup_score, blockers, days_until)
    if blockers and not gap_blockers and not volatility_blockers and any("decision safety" in blocker.lower() for blocker in blockers):
        setup_label = "avoid_pre_earnings_add"
        review_action = "hold_buy_capacity"
    if confidence_lower in LOW_CONFIDENCE and not gap_blockers and not volatility_blockers and boolish(gate.get("safe_to_buy")):
        setup_label = "wait_for_earnings"
        review_action = "wait_until_after_report"

    return {
        "symbol": symbol,
        "company": company,
        "earnings_date": earnings_date.isoformat(),
        "days_until_earnings": days_until,
        "setup_label": setup_label,
        "setup_score": setup_score,
        "recommended_review_action": review_action,
        "reasons": list(dict.fromkeys(reason for reason in reasons if reason)),
        "blockers": list(dict.fromkeys(blocker for blocker in blockers if blocker)),
        "data_gaps": list(dict.fromkeys(gap for gap in data_gaps if gap)),
        "review_only": True,
        "recommendation_only_note": RECOMMENDATION_ONLY_NOTE,
    }


def review_pre_earnings_setups(
    earnings_events: Iterable[Mapping[str, object]],
    *,
    recommendations_by_symbol: Mapping[str, Mapping[str, object]] | None = None,
    as_of_date: str | date | None = None,
    pre_earnings_window_days: int = 14,
) -> dict[str, object]:
    """Build a deterministic batch review from earnings rows and optional recommendations."""

    recs = {text(symbol).upper(): as_dict(row) for symbol, row in dict(recommendations_by_symbol or {}).items()}
    rows = [
        review_pre_earnings_setup(
            earnings_event=event,
            recommendation=recs.get(text(event.get("symbol")).upper(), {}),
            as_of_date=as_of_date,
            pre_earnings_window_days=pre_earnings_window_days,
        )
        for event in earnings_events
    ]
    rows.sort(key=lambda row: (row.get("days_until_earnings") is None, row.get("days_until_earnings") or 9999, text(row.get("symbol"))))
    return {
        "review_only": True,
        "recommendation_only": True,
        "row_count": len(rows),
        "rows": rows,
        "note": RECOMMENDATION_ONLY_NOTE,
    }


__all__ = [
    "RECOMMENDATION_ONLY_NOTE",
    "REVIEW_ACTIONS",
    "SETUP_LABELS",
    "review_pre_earnings_setup",
    "review_pre_earnings_setups",
]
