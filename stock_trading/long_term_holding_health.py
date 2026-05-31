"""Review-only long-term holding health checks.

The helper in this module is a non-trading review surface for long-term/core
holdings. It can flag a holding for thesis, valuation, risk, or data review,
but it must not change recommendations, scores, targets, allocation, broker
behavior, or trading.
"""

from __future__ import annotations

from collections.abc import Iterable
from copy import deepcopy
from typing import Mapping


HEALTH_LABELS = {
    "healthy",
    "needs_review",
    "thesis_weakening",
    "valuation_stretched",
    "risk_rising",
    "data_insufficient",
}

REVIEW_ONLY_NOTE = (
    "Review-only long-term holding health. This is not an official action "
    "change and does not alter scores, targets, target confidence, decision "
    "safety, allocation, source weights, broker behavior, or trading."
)

NO_SELL_INSTRUCTION = (
    "No liquidation, position-reduction, short-side, broker-write, preview, or "
    "execution instruction is produced."
)

BUY_OR_HOLD_ACTIONS = {"Strong Buy", "Buy", "Add", "Hold"}
WEAKENING_ACTIONS = {"Watch", "Avoid"}
RISK_ACTIONS = {"Avoid"}
STRETCHED_ACTIONS = {"Trim"}
LOW_CONFIDENCE = {"low", "needs review", "needs_review", "missing", "unknown"}
BAD_OUTCOMES = {"negative_follow_through", "drawdown_warning"}
GOOD_OUTCOMES = {"positive_follow_through", "target_progress"}
BAD_CATALYST_LABELS = {"likely_noisy"}
GOOD_CATALYST_LABELS = {"likely_useful"}
POOR_SOURCE_LABELS = {"noisy", "stale_or_blocked", "needs_more_history"}
AI_GAP_STATUSES = {"not_enough_data", "blocked", "flagged", "rejected", "needs_review"}


def text(value: object, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def to_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def as_mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def as_list(value: object) -> list[object]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, Iterable):
        return list(value)
    return []


def symbol_for(row: Mapping[str, object]) -> str:
    return text(row.get("symbol")).upper()


def rows_for_symbol(rows: Iterable[Mapping[str, object]] | None, symbol: str) -> list[dict[str, object]]:
    wanted = symbol.upper()
    return [dict(row) for row in rows or [] if symbol_for(row) == wanted]


def active_provider_gap(row: Mapping[str, object]) -> bool:
    status = text(row.get("status") or row.get("gap_status") or row.get("state")).lower()
    severity = text(row.get("severity") or row.get("priority")).lower()
    root_cause = text(row.get("root_cause") or row.get("gap") or row.get("field_name")).lower()
    if status in {"resolved", "ok", "healthy", "expected", "expected_gap"}:
        return False
    if "expected" in root_cause and "non-operating" in root_cause:
        return False
    return bool(status or severity or root_cause)


def latest_score_delta(score_trend: Iterable[Mapping[str, object]] | None) -> float:
    rows = list(score_trend or [])
    if not rows:
        return 0.0
    latest = rows[-1]
    if "score_delta" in latest:
        return to_float(latest.get("score_delta"))
    if "change" in latest:
        return to_float(latest.get("change"))
    if len(rows) >= 2:
        return to_float(rows[-1].get("score")) - to_float(rows[-2].get("score"))
    return 0.0


def has_review_flag(row: Mapping[str, object], keys: Iterable[str]) -> bool:
    haystack = " ".join(text(row.get(key)).lower() for key in keys)
    return bool(haystack)


def append_once(values: list[str], value: str) -> None:
    if value and value not in values:
        values.append(value)


def evaluate_holding_health(
    holding: Mapping[str, object],
    *,
    recommendation: Mapping[str, object] | None = None,
    score_trend: Iterable[Mapping[str, object]] | None = None,
    provider_gaps: Iterable[Mapping[str, object]] | None = None,
    catalyst_follow_through: Iterable[Mapping[str, object]] | None = None,
    recommendation_outcomes: Iterable[Mapping[str, object]] | None = None,
    source_usefulness: Iterable[Mapping[str, object]] | None = None,
    ai_status: Mapping[str, object] | None = None,
    allocation_context: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Return a deterministic, review-only holding health row."""

    holding_copy = dict(holding)
    recommendation_copy = dict(recommendation or {})
    symbol = text(holding_copy.get("symbol") or recommendation_copy.get("symbol")).upper()
    company = text(holding_copy.get("company") or recommendation_copy.get("company"))
    sleeve = text(holding_copy.get("sleeve") or recommendation_copy.get("sleeve"))
    action = text(recommendation_copy.get("action"))
    target_confidence = text(recommendation_copy.get("target_confidence")).lower()
    data_status = text(recommendation_copy.get("data_status")).lower()
    score = to_float(recommendation_copy.get("score"), -1.0)
    current_price = to_float(recommendation_copy.get("current_price"))
    target_price = to_float(recommendation_copy.get("target_price"))
    upside_pct = to_float(recommendation_copy.get("upside_pct"))
    score_trend_rows = [dict(row) for row in score_trend or []]
    score_delta = latest_score_delta(score_trend_rows)
    gaps = rows_for_symbol(provider_gaps, symbol)
    catalysts = rows_for_symbol(catalyst_follow_through, symbol)
    outcomes = rows_for_symbol(recommendation_outcomes, symbol)
    sources = rows_for_symbol(source_usefulness, symbol)
    ai = as_mapping(ai_status)
    allocation = as_mapping(allocation_context)

    reasons: list[str] = []
    review_actions: list[str] = []
    data_gaps: list[str] = []
    positive_points = 0
    penalty = 0
    thesis_flags = 0
    valuation_flags = 0
    risk_flags = 0
    data_flags = 0

    if not symbol:
        append_once(data_gaps, "Missing holding symbol.")
        data_flags += 2
        penalty += 30
    if not recommendation_copy:
        append_once(data_gaps, "Missing current recommendation context for holding-health review.")
        append_once(review_actions, "Refresh recommendation context before interpreting holding health.")
        data_flags += 2
        penalty += 30
    if sleeve and sleeve not in {"long_term", "long_term_core"}:
        append_once(reasons, f"{sleeve} sleeve is outside the long-term/core holding-health focus.")
        append_once(review_actions, "Confirm this holding belongs in long-term/core review before comparing it with core names.")
        data_flags += 1
        penalty += 8

    if current_price <= 0:
        append_once(data_gaps, "Missing current price.")
        data_flags += 2
        penalty += 20
    if score < 0:
        append_once(data_gaps, "Missing current score.")
        data_flags += 1
        penalty += 15
    if target_confidence in LOW_CONFIDENCE or not target_confidence:
        append_once(data_gaps, f"Target confidence is {target_confidence or 'unknown'}.")
        append_once(review_actions, "Review target-source breadth and freshness.")
        data_flags += 1
        penalty += 12
    if any(term in data_status for term in ("missing", "stale", "needs review", "needs_price")):
        append_once(data_gaps, f"Data status needs review: {data_status}.")
        data_flags += 1
        penalty += 10

    for gap in gaps:
        if active_provider_gap(gap):
            label = text(gap.get("field_name") or gap.get("gap") or gap.get("provider") or "provider/data gap")
            append_once(data_gaps, f"Active provider/data gap: {label}.")
            data_flags += 1
            penalty += 8

    if action in WEAKENING_ACTIONS:
        append_once(reasons, f"Current official action is {action}, so the long-term thesis should be reviewed.")
        append_once(review_actions, "Review whether recent evidence still supports the long-term thesis.")
        thesis_flags += 1
        penalty += 18
    if action in RISK_ACTIONS:
        append_once(reasons, f"Current official action is {action}, indicating elevated risk review.")
        risk_flags += 1
        penalty += 12
    if score_delta <= -8:
        append_once(reasons, f"Score trend weakened by {score_delta:.1f} points.")
        append_once(review_actions, "Compare the latest score drivers with prior runs.")
        thesis_flags += 1
        penalty += 14
    elif score_delta >= 5:
        positive_points += 1

    if target_price > 0 and current_price > 0 and target_price <= current_price:
        append_once(reasons, "Current price is at or above target, so valuation looks stretched for additional capital.")
        append_once(review_actions, "Review target assumptions before adding more long-term capital.")
        valuation_flags += 2
        penalty += 18
    elif upside_pct <= 5 and target_price > 0:
        append_once(reasons, f"Upside is only {upside_pct:.1f}%, so valuation may be stretched.")
        append_once(review_actions, "Review whether target upside still justifies new long-term capital.")
        valuation_flags += 1
        penalty += 12
    if action in STRETCHED_ACTIONS:
        append_once(reasons, f"Current official action is {action}, so valuation or concentration should be reviewed.")
        valuation_flags += 1
        penalty += 12

    position_pct = to_float(
        allocation.get("current_position_pct")
        or allocation.get("position_after_buy_pct")
        or holding_copy.get("portfolio_pct")
    )
    if position_pct >= 9.5:
        append_once(reasons, f"Position is near the single-stock cap at {position_pct:.1f}% of portfolio.")
        append_once(review_actions, "Review concentration before allocating more capital.")
        valuation_flags += 1
        penalty += 8

    for outcome in outcomes:
        outcome_status = text(outcome.get("outcome_status")).lower()
        if outcome_status in BAD_OUTCOMES:
            append_once(reasons, f"Recommendation outcome shows {outcome_status}.")
            append_once(review_actions, "Review whether price follow-through contradicts the long-term thesis.")
            thesis_flags += 1
            penalty += 12
        elif outcome_status in GOOD_OUTCOMES:
            positive_points += 1

    for catalyst in catalysts:
        label = text(catalyst.get("outcome_label")).lower()
        reason_text = " ".join(text(item).lower() for item in as_list(catalyst.get("outcome_reasons")))
        if label in BAD_CATALYST_LABELS or "negative_follow_through" in reason_text:
            append_once(reasons, "Recent catalyst follow-through was weak or negative.")
            append_once(review_actions, "Review whether catalysts are still supporting the holding thesis.")
            thesis_flags += 1
            penalty += 12
        elif label in GOOD_CATALYST_LABELS:
            positive_points += 1

    for source in sources:
        label = text(source.get("label") or source.get("quality_label")).lower()
        if label in POOR_SOURCE_LABELS:
            append_once(data_gaps, f"Source usefulness is {label}.")
            append_once(review_actions, "Review source quality before increasing conviction.")
            data_flags += 1
            penalty += 8
        elif label in {"consistently_useful", "useful_but_sparse", "useful_context"}:
            positive_points += 1

    ai_readiness = text(
        ai.get("readiness_status")
        or ai.get("status")
        or ai.get("review_status")
        or ai.get("guardrail_status")
    ).lower()
    if ai_readiness in AI_GAP_STATUSES:
        append_once(data_gaps, f"AI/synthesis review status is {ai_readiness}.")
        append_once(review_actions, "Review AI brief guardrails and source support before relying on synthesis.")
        data_flags += 1
        penalty += 6
    if has_review_flag(ai, ("risk_or_uncertainty", "bear_case", "guardrail_reason")):
        risk_text = text(ai.get("risk_or_uncertainty") or ai.get("bear_case") or ai.get("guardrail_reason"))
        if any(term in risk_text.lower() for term in ("risk", "uncertain", "unsupported", "stale", "hallucination")):
            append_once(reasons, "AI/source-backed brief highlights risk or uncertainty.")
            risk_flags += 1
            penalty += 8

    if action in BUY_OR_HOLD_ACTIONS and score >= 70 and target_confidence not in LOW_CONFIDENCE and not data_gaps:
        positive_points += 2

    health_score = max(0, min(100, 100 - penalty + min(6, positive_points * 2)))
    if data_flags >= 2 or (not recommendation_copy and data_flags):
        label = "data_insufficient"
    elif risk_flags >= 2:
        label = "risk_rising"
    elif thesis_flags >= 2 or (thesis_flags and score_delta <= -8):
        label = "thesis_weakening"
    elif valuation_flags >= 2:
        label = "valuation_stretched"
    elif risk_flags:
        label = "risk_rising"
    elif thesis_flags:
        label = "thesis_weakening"
    elif valuation_flags:
        label = "valuation_stretched"
    elif data_flags or health_score < 75:
        label = "needs_review"
    else:
        label = "healthy"

    if label == "healthy":
        append_once(reasons, "Long-term holding context is constructive with no active review blockers.")
        append_once(review_actions, "Continue routine long-term thesis monitoring.")
    elif not review_actions:
        append_once(review_actions, "Review the flagged long-term holding-health drivers.")

    return {
        "symbol": symbol,
        "company": company,
        "sleeve": sleeve,
        "health_label": label,
        "health_score": round(float(health_score), 2),
        "confidence": "low" if data_flags >= 2 else "medium" if reasons or data_gaps else "high",
        "current_action": action,
        "target_confidence": target_confidence,
        "score_delta": round(score_delta, 4),
        "reasons": reasons,
        "review_actions": review_actions,
        "data_gaps": data_gaps,
        "inputs_considered": {
            "recommendation": bool(recommendation_copy),
            "score_trend": bool(score_trend_rows),
            "provider_gaps": len(gaps),
            "catalyst_follow_through": len(catalysts),
            "recommendation_outcomes": len(outcomes),
            "source_usefulness": len(sources),
            "ai_status": bool(ai),
            "allocation_context": bool(allocation),
        },
        "review_only": True,
        "recommendation_impact": "none",
        "score_impact": "none",
        "target_impact": "none",
        "decision_safety_impact": "none",
        "allocation_impact": "none",
        "broker_behavior": "none",
        "no_sell_instruction": NO_SELL_INSTRUCTION,
        "notes": REVIEW_ONLY_NOTE,
    }


def build_holding_health_review(
    holdings: Iterable[Mapping[str, object]],
    *,
    recommendations_by_symbol: Mapping[str, Mapping[str, object]] | None = None,
    score_trends_by_symbol: Mapping[str, Iterable[Mapping[str, object]]] | None = None,
    provider_gaps: Iterable[Mapping[str, object]] | None = None,
    catalyst_follow_through: Iterable[Mapping[str, object]] | None = None,
    recommendation_outcomes: Iterable[Mapping[str, object]] | None = None,
    source_usefulness: Iterable[Mapping[str, object]] | None = None,
    ai_status_by_symbol: Mapping[str, Mapping[str, object]] | None = None,
    allocation_by_symbol: Mapping[str, Mapping[str, object]] | None = None,
) -> dict[str, object]:
    """Build a review-only health review for multiple long-term holdings."""

    recommendations_by_symbol = recommendations_by_symbol or {}
    score_trends_by_symbol = score_trends_by_symbol or {}
    ai_status_by_symbol = ai_status_by_symbol or {}
    allocation_by_symbol = allocation_by_symbol or {}
    rows: list[dict[str, object]] = []
    for holding in holdings:
        symbol = text(holding.get("symbol")).upper()
        rows.append(
            evaluate_holding_health(
                deepcopy(holding),
                recommendation=deepcopy(recommendations_by_symbol.get(symbol, {})),
                score_trend=deepcopy(list(score_trends_by_symbol.get(symbol, []))),
                provider_gaps=provider_gaps,
                catalyst_follow_through=catalyst_follow_through,
                recommendation_outcomes=recommendation_outcomes,
                source_usefulness=source_usefulness,
                ai_status=deepcopy(ai_status_by_symbol.get(symbol, {})),
                allocation_context=deepcopy(allocation_by_symbol.get(symbol, {})),
            )
        )
    summary = {label: 0 for label in sorted(HEALTH_LABELS)}
    for row in rows:
        label = text(row.get("health_label"))
        if label in summary:
            summary[label] += 1
    return {
        "metadata": {
            "review_only": True,
            "holding_count": len(rows),
            "notes": f"{REVIEW_ONLY_NOTE} {NO_SELL_INSTRUCTION}",
        },
        "summary": summary,
        "holdings": rows,
    }


__all__ = [
    "HEALTH_LABELS",
    "NO_SELL_INSTRUCTION",
    "REVIEW_ONLY_NOTE",
    "build_holding_health_review",
    "evaluate_holding_health",
]
