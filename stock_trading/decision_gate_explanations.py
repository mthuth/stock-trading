"""Plain-English decision-gate explanations.

This helper explains existing decision-safety outputs without changing the
rules that decide whether a candidate is buy-ready.
"""

from __future__ import annotations

import copy
from typing import Iterable, Mapping


BUY_ACTIONS = {"Strong Buy", "Buy", "Add"}
RECOMMENDATION_ONLY_NOTE = (
    "Review-only decision-gate explanation. This text explains existing gate "
    "state and does not change scores, recommendation labels, targets, target "
    "confidence, decision-safety rules, allocation, provider behavior, broker "
    "behavior, or trading."
)


def _text(value: object, default: str = "") -> str:
    if value is None:
        return default
    result = str(value).strip()
    return result if result else default


def _lower(value: object) -> str:
    return _text(value).lower()


def _as_dict(value: object) -> dict[str, object]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _as_list(value: object) -> list[object]:
    if isinstance(value, list):
        return copy.deepcopy(value)
    if isinstance(value, tuple):
        return list(copy.deepcopy(value))
    if isinstance(value, str):
        return [value] if value.strip() else []
    return []


def _boolish(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return _lower(value) in {"1", "true", "yes", "ready", "safe"}


def _number(value: object) -> float | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _reason_texts(values: Iterable[object]) -> list[str]:
    return list(dict.fromkeys(_text(value) for value in values if _text(value)))


def _provider_gap_texts(value: object) -> list[str]:
    gaps: list[str] = []
    for item in _as_list(value):
        if isinstance(item, Mapping):
            provider = _text(item.get("provider") or item.get("source") or "Provider")
            field = _text(item.get("field") or item.get("endpoint") or item.get("data_type") or "data")
            status = _text(item.get("status") or item.get("severity"))
            if provider or field or status:
                gaps.append(f"{provider} {field} {status}".strip())
        else:
            gaps.append(_text(item))
    return _reason_texts(gaps)


def _blocked_reasons(inputs: Mapping[str, object]) -> list[str]:
    gate = _as_dict(inputs.get("decision_gate"))
    reasons = (
        inputs.get("blocked_reasons")
        or inputs.get("reasons")
        or gate.get("reasons")
        or gate.get("blocked_reasons")
        or []
    )
    return _reason_texts(_as_list(reasons))


def _action(inputs: Mapping[str, object]) -> str:
    gate = _as_dict(inputs.get("decision_gate"))
    return _text(
        inputs.get("candidate_action")
        or inputs.get("action")
        or gate.get("candidate_action")
        or inputs.get("top_action")
    ).replace(" blocked", "")


def _watchlist_blocked(inputs: Mapping[str, object], reasons: list[str]) -> bool:
    policy = _as_dict(inputs.get("watchlist_policy") or _as_dict(inputs.get("decision_gate")).get("watchlist_policy"))
    if policy.get("blocked") is not None:
        return _boolish(policy.get("blocked"))
    haystack = " ".join(reasons).lower()
    return "watchlist" in haystack


def _allocation_blocked(inputs: Mapping[str, object], reasons: list[str]) -> bool:
    allocation = _as_dict(inputs.get("allocation_safety") or inputs.get("allocation"))
    status = _lower(inputs.get("allocation_status") or allocation.get("status") or allocation.get("applied_limit"))
    haystack = " ".join([status, *(_lower(reason) for reason in reasons)])
    return any(token in haystack for token in ("allocation", "cap", "buy_capacity", "capacity", "suggested amount"))


def _verification_open(inputs: Mapping[str, object], reasons: list[str]) -> bool:
    verification = _as_dict(inputs.get("verification") or inputs.get("verification_status"))
    status = _lower(verification.get("status") or inputs.get("verification_status"))
    haystack = " ".join([status, *(_lower(reason) for reason in reasons)])
    return "verification" in haystack and any(token in haystack for token in ("open", "needed", "still", "queue", "check"))


def _missing_price(inputs: Mapping[str, object], reasons: list[str]) -> bool:
    current_price = _number(inputs.get("current_price"))
    status = _lower(inputs.get("current_price_status") or inputs.get("price_status") or inputs.get("data_status"))
    haystack = " ".join([status, *(_lower(reason) for reason in reasons)])
    return current_price == 0 or "missing current price" in haystack or "price refresh" in haystack or "quote" in haystack


def _target_confidence_low(inputs: Mapping[str, object], reasons: list[str]) -> bool:
    confidence = _lower(inputs.get("target_confidence") or inputs.get("confidence"))
    haystack = " ".join([confidence, *(_lower(reason) for reason in reasons)])
    return "low target confidence" in haystack or confidence in {"low", "needs review", "needs_review", "unknown"}


def _provider_gap(inputs: Mapping[str, object], reasons: list[str], gaps: list[str]) -> bool:
    data_status = _lower(inputs.get("data_status"))
    haystack = " ".join([data_status, *(_lower(reason) for reason in reasons), *(_lower(gap) for gap in gaps)])
    return bool(gaps) or any(token in haystack for token in ("provider", "data gap", "gap", "blocked source"))


def _reason_contains_not_buy_action(action: str, reasons: list[str]) -> bool:
    haystack = " ".join(_lower(reason) for reason in reasons)
    return action not in BUY_ACTIONS or "not a buy action" in haystack


def _add_group(groups: list[dict[str, object]], key: str, label: str, explanation: str, reasons: list[str]) -> None:
    groups.append(
        {
            "group": key,
            "label": label,
            "explanation": explanation,
            "reasons": reasons,
        }
    )


def explain_decision_gate(inputs: Mapping[str, object]) -> dict[str, object]:
    """Explain a decision gate in plain English without changing gate state."""

    data = _as_dict(inputs)
    gate = _as_dict(data.get("decision_gate"))
    action = _action(data)
    status = _text(data.get("decision_gate_status") or gate.get("status"), "Ready")
    raw_safe = data.get("safe_to_buy") if "safe_to_buy" in data else gate.get("safe_to_buy")
    safe_to_buy = (
        _boolish(raw_safe)
        if raw_safe is not None
        else status.lower() == "ready" and action in BUY_ACTIONS
    )
    reasons = _blocked_reasons(data)
    gaps = _provider_gap_texts(data.get("provider_gaps"))
    groups: list[dict[str, object]] = []
    buy_ready_steps: list[str] = []

    if _reason_contains_not_buy_action(action, reasons):
        _add_group(
            groups,
            "action_not_buy_ready",
            "Current action is not buy-ready",
            f"The current model action is {action or 'not available'}, so this is a review candidate rather than a buy/add candidate.",
            [reason for reason in reasons if "not a buy action" in _lower(reason)] or [action or "No buy/add action"],
        )
        buy_ready_steps.append("The official action would need to upgrade to Add, Buy, or Strong Buy.")

    if _verification_open(data, reasons):
        _add_group(
            groups,
            "verification_open",
            "Verification is still open",
            "A verification check still needs to clear before this can be treated as buy-ready.",
            [reason for reason in reasons if "verification" in _lower(reason)],
        )
        buy_ready_steps.append("The open verification check would need to clear.")

    if _missing_price(data, reasons):
        _add_group(
            groups,
            "missing_price",
            "Price data needs refresh",
            "Current price or quote data is missing or stale, so readiness and sizing are reduced.",
            [reason for reason in reasons if "price" in _lower(reason) or "quote" in _lower(reason)],
        )
        buy_ready_steps.append("Current price data would need to refresh.")

    if _provider_gap(data, reasons, gaps):
        _add_group(
            groups,
            "provider_gap",
            "Provider or source gaps reduce confidence",
            "Provider/source data gaps are reducing trust in the decision, not making the thesis automatically bearish.",
            [reason for reason in reasons if "gap" in _lower(reason) or "provider" in _lower(reason)] or gaps,
        )
        buy_ready_steps.append("Material provider/data gaps would need to resolve.")

    if _target_confidence_low(data, reasons):
        _add_group(
            groups,
            "low_target_confidence",
            "Target confidence is too low",
            "The target or upside estimate is not confident enough for buy-readiness yet.",
            [reason for reason in reasons if "confidence" in _lower(reason)] or [_text(data.get("target_confidence") or data.get("confidence"))],
        )
        buy_ready_steps.append("Target confidence would need to improve to Medium or High.")

    if _watchlist_blocked(data, reasons):
        _add_group(
            groups,
            "watchlist_only",
            "Watchlist-only policy blocks buy-readiness",
            "This name is allowed to stay visible for review, but the watchlist policy blocks a buy/add decision.",
            [reason for reason in reasons if "watchlist" in _lower(reason)],
        )
        buy_ready_steps.append("The watchlist-only policy would need to clear.")

    if _allocation_blocked(data, reasons):
        _add_group(
            groups,
            "allocation_blocked",
            "Allocation or buy-capacity blocks sizing",
            "The idea may be interesting, but allocation limits or buy capacity hold the suggested amount at zero.",
            [reason for reason in reasons if any(token in _lower(reason) for token in ("allocation", "cap", "capacity"))],
        )
        buy_ready_steps.append("Allocation capacity would need to be available under portfolio caps.")

    if not safe_to_buy and not groups:
        _add_group(
            groups,
            "no_decision_safe_buy",
            "No decision-safe buy is available",
            "The gate is blocked, so buy capacity should be held for manual review.",
            reasons or [_text(gate.get("summary")) or "Decision gate is blocked."],
        )
        buy_ready_steps.append("The decision gate would need to move to Ready.")

    missing_data = any(group["group"] in {"missing_price", "provider_gap", "low_target_confidence"} for group in groups)
    missing_data_note = (
        "Data is incomplete, so confidence/readiness is reduced."
        if missing_data
        else ""
    )
    not_bearish_note = (
        "This is a reliability/readiness blocker, not a bearish thesis by itself."
        if missing_data
        else ""
    )

    if safe_to_buy and action in BUY_ACTIONS:
        plain_status = "Decision-safe buy/add candidate"
        plain_summary = "This candidate passed the current decision gate for manual buy/add review."
        buyer_explanation = plain_summary
    elif not safe_to_buy:
        plain_status = "Not buy-ready yet"
        labels = [str(group["label"]) for group in groups[:2]]
        plain_summary = "Blocked for now: " + "; ".join(labels) + "."
        buyer_explanation = (
            f"{action or 'This candidate'} is visible for review, but it is not buy-ready yet. "
            f"{' '.join(str(group['explanation']) for group in groups[:3])}"
        )
    else:
        plain_status = "Review-only candidate"
        plain_summary = "This candidate is worth reviewing, but it is not currently a buy/add action."
        buyer_explanation = plain_summary

    return {
        "plain_status": plain_status,
        "plain_summary": plain_summary,
        "buyer_friendly_explanation": buyer_explanation,
        "blocker_groups": groups,
        "what_would_make_buy_ready": list(dict.fromkeys(buy_ready_steps)),
        "missing_data_note": missing_data_note,
        "not_bearish_note": not_bearish_note,
        "review_only": True,
        "recommendation_only_note": RECOMMENDATION_ONLY_NOTE,
        "raw_status": status,
        "raw_reasons": reasons,
    }


__all__ = [
    "BUY_ACTIONS",
    "RECOMMENDATION_ONLY_NOTE",
    "explain_decision_gate",
]
