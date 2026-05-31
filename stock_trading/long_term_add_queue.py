"""Deterministic long-term add queue built from existing recommendation output."""

from __future__ import annotations

import copy
from typing import Iterable, Mapping


BUY_ACTIONS = {"Strong Buy", "Buy", "Add"}
LONG_TERM_MODES = {"long_term_buy_add"}
LONG_TERM_SLEEVES = {"long_term", "long_term_core"}
LONG_TERM_TRADE_TYPES = {"long_term", "multi_year", "12_months"}
RECOMMENDATION_ONLY_NOTE = (
    "Recommendation-only long-term add queue. It reads existing recommendation, "
    "decision-safety, target-confidence, allocation, provider-gap, and AI readiness "
    "context but does not change scores, actions, targets, target confidence, "
    "decision gates, suggested amounts, source weights, broker behavior, or trading."
)


def _as_dict(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_list(value: object) -> list[object]:
    return list(value) if isinstance(value, list) else []


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _number(value: object, default: float = 0.0) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def _is_truthy(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1", "ready"}
    return bool(value)


def _normalized_confidence(row: Mapping[str, object]) -> str:
    return _text(row.get("target_confidence") or row.get("confidence") or row.get("target_status"))


def _decision_gate(row: Mapping[str, object]) -> dict[str, object]:
    gate = _as_dict(row.get("decision_gate"))
    if gate:
        return gate
    safe = row.get("safe_to_buy")
    status = _text(row.get("decision_gate_status") or row.get("decision_status"))
    return {
        "safe_to_buy": _is_truthy(safe) if safe is not None else status.lower() == "ready",
        "status": status or ("Ready" if _is_truthy(safe) else "Blocked"),
        "reasons": _as_list(row.get("blocked_reasons")),
        "summary": _text(row.get("decision_gate_summary") or row.get("summary")),
    }


def _is_buy_action(row: Mapping[str, object]) -> bool:
    return _text(row.get("action")) in BUY_ACTIONS


def _is_long_term(row: Mapping[str, object]) -> bool:
    mode = _text(row.get("decision_mode"))
    sleeve = _text(row.get("sleeve"))
    trade_type = _text(row.get("trade_type"))
    return mode in LONG_TERM_MODES or sleeve in LONG_TERM_SLEEVES or trade_type in LONG_TERM_TRADE_TYPES


def _watchlist_blocked(row: Mapping[str, object]) -> bool:
    policy = _as_dict(row.get("watchlist_policy"))
    if policy.get("blocked") is not None:
        return _is_truthy(policy.get("blocked"))
    return _is_truthy(row.get("watchlist_only_blocked"))


def _allocation_notes(row: Mapping[str, object]) -> list[str]:
    allocation = _as_dict(row.get("allocation_safety"))
    notes: list[str] = []
    reason = _text(allocation.get("reason") or row.get("allocation_notes"))
    if reason:
        notes.append(reason)
    applied_limit = _text(allocation.get("applied_limit"))
    suggested = _number(allocation.get("suggested_amount", row.get("suggested_amount")))
    buy_capacity = _number(allocation.get("buy_capacity", row.get("buy_capacity")))
    if applied_limit and applied_limit != "buy_capacity" and buy_capacity > suggested:
        notes.append(f"Allocation limit reduced deployable amount: {applied_limit}.")
    for reason_value in _as_list(allocation.get("reduction_reasons")):
        reason_text = _text(reason_value)
        if reason_text:
            notes.append(reason_text)
    return list(dict.fromkeys(notes))


def _provider_blockers(row: Mapping[str, object]) -> list[str]:
    blockers: list[str] = []
    for key in ("provider_blockers", "provider_gaps", "data_blockers", "key_risks", "blockers"):
        value = row.get(key)
        if isinstance(value, list):
            blockers.extend(_text(item) for item in value if _text(item))
        elif _text(value):
            blockers.append(_text(value))
    data_status = _text(row.get("data_status") or row.get("target_status"))
    if data_status and any(term in data_status.lower() for term in ("missing", "needs", "stale", "gap", "blocked")):
        blockers.append(data_status)
    return list(dict.fromkeys(blockers))


def _blocked_reasons(row: Mapping[str, object], gate: Mapping[str, object]) -> list[str]:
    reasons = [_text(reason) for reason in _as_list(gate.get("reasons")) if _text(reason)]
    if _watchlist_blocked(row):
        reasons.append(_text(_as_dict(row.get("watchlist_policy")).get("reason")) or "Watchlist-only policy blocks buy-readiness.")
    confidence = _normalized_confidence(row)
    if confidence.lower() in {"low", "needs review"}:
        reasons.append(f"Target confidence is {confidence}.")
    reasons.extend(_provider_blockers(row))
    return list(dict.fromkeys(reason for reason in reasons if reason))


def _why(row: Mapping[str, object], gate: Mapping[str, object], suggested_amount: float, blockers: list[str]) -> str:
    action = _text(row.get("action"))
    if _is_truthy(gate.get("safe_to_buy")) and suggested_amount > 0 and not _watchlist_blocked(row):
        return f"Long-term {action} candidate with decision safety and allocation capacity available."
    if _is_truthy(gate.get("safe_to_buy")) and suggested_amount <= 0:
        return f"Long-term {action} candidate, but buy capacity is held by allocation or capital limits."
    if blockers:
        return f"Long-term {action} candidate, but review blockers remain: {'; '.join(blockers)}."
    return f"Long-term {action} candidate kept in queue for review."


def _score_drivers(row: Mapping[str, object]) -> list[str]:
    drivers = row.get("key_score_drivers")
    if isinstance(drivers, list):
        return [_text(driver) for driver in drivers if _text(driver)]
    explanation = _text(row.get("score_breakdown") or row.get("score_explanation") or row.get("why"))
    return [explanation] if explanation else []


def _ai_readiness(row: Mapping[str, object]) -> dict[str, object]:
    readiness = _as_dict(row.get("ai_synthesis_readiness") or row.get("synthesis_readiness"))
    if not readiness:
        return {}
    return {
        **readiness,
        "review_only": True,
        "note": "AI synthesis readiness is explanatory only and does not affect queue eligibility.",
    }


def _queue_row(row: Mapping[str, object], queue_rank: int) -> dict[str, object]:
    gate = _decision_gate(row)
    allocation = _as_dict(row.get("allocation_safety"))
    suggested_amount = _number(row.get("suggested_amount", allocation.get("suggested_amount")))
    blockers = _blocked_reasons(row, gate)
    safe_to_buy = _is_truthy(gate.get("safe_to_buy")) and not _watchlist_blocked(row)
    if blockers and any("watchlist" in blocker.lower() for blocker in blockers):
        safe_to_buy = False
    return {
        "rank": queue_rank,
        "source_rank": row.get("rank"),
        "symbol": _text(row.get("symbol")),
        "company": _text(row.get("company")),
        "action": _text(row.get("action")),
        "score": row.get("score"),
        "decision_mode": _text(row.get("decision_mode") or "long_term_buy_add"),
        "sleeve": _text(row.get("sleeve")),
        "decision_gate_status": _text(gate.get("status") or ("Ready" if safe_to_buy else "Blocked")),
        "safe_to_buy": bool(safe_to_buy),
        "blocked_reasons": blockers,
        "target_confidence": _normalized_confidence(row),
        "target_status": _text(row.get("target_status") or row.get("data_status")),
        "data_status": _text(row.get("data_status") or row.get("target_status")),
        "suggested_amount": suggested_amount,
        "allocation_notes": _allocation_notes(row),
        "key_score_drivers": _score_drivers(row),
        "key_risks_blockers": blockers,
        "provider_data_blockers": _provider_blockers(row),
        "ai_synthesis_readiness": _ai_readiness(row),
        "why_this_is_in_queue": _why(row, gate, suggested_amount, blockers),
        "review_only": True,
        "recommendation_only_note": RECOMMENDATION_ONLY_NOTE,
    }


def _source_rank(row: Mapping[str, object]) -> tuple[int, float]:
    rank = int(_number(row.get("rank") or row.get("source_rank"), 9999))
    return (rank, -_number(row.get("score")))


def build_long_term_add_queue(candidates: Iterable[Mapping[str, object]], *, limit: int = 8) -> dict[str, object]:
    """Build a review-only long-term add queue from already-computed candidates."""

    copied = [copy.deepcopy(dict(row)) for row in candidates]
    eligible = [row for row in copied if _is_buy_action(row) and _is_long_term(row)]
    eligible_ids = {id(row) for row in eligible}
    excluded = [
        {
            "symbol": _text(row.get("symbol")),
            "action": _text(row.get("action")),
            "sleeve": _text(row.get("sleeve")),
            "reason": "Not a long-term Buy/Add candidate for this queue.",
        }
        for row in copied
        if id(row) not in eligible_ids
    ]
    eligible.sort(key=_source_rank)
    rows = [_queue_row(row, index) for index, row in enumerate(eligible[:limit], start=1)]
    decision_safe_rows = [
        row for row in rows if row["safe_to_buy"] and _number(row.get("suggested_amount")) > 0
    ]
    top_candidate = rows[0] if rows else None
    best_safe = decision_safe_rows[0] if decision_safe_rows else None
    backup_safe = decision_safe_rows[1] if len(decision_safe_rows) > 1 else None
    if best_safe is None:
        result = "hold_buy_capacity"
        hold_reason = "Hold buy capacity: no decision-safe long-term Buy/Add candidate with allocation capacity is available."
    else:
        result = "decision_safe_add_available"
        hold_reason = ""
    return {
        "review_only": True,
        "recommendation_only": True,
        "decision_mode": "long_term_buy_add",
        "result": result,
        "should_deploy_buy_capacity": best_safe is not None,
        "hold_buy_capacity_reason": hold_reason,
        "top_candidate_symbol": top_candidate.get("symbol") if top_candidate else "",
        "best_decision_safe_symbol": best_safe.get("symbol") if best_safe else "",
        "backup_decision_safe_symbol": backup_safe.get("symbol") if backup_safe else "",
        "rows": rows,
        "excluded": excluded,
        "note": RECOMMENDATION_ONLY_NOTE,
    }


__all__ = [
    "BUY_ACTIONS",
    "LONG_TERM_MODES",
    "LONG_TERM_SLEEVES",
    "RECOMMENDATION_ONLY_NOTE",
    "build_long_term_add_queue",
]
