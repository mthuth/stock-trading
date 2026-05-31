#!/usr/bin/env python3
"""Display helpers for decision-safety review output."""

from __future__ import annotations

from typing import Any


BUY_ACTIONS = {"Strong Buy", "Buy", "Add"}


def as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def text(value: object, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def money(value: object) -> str:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return "n/a"
    return f"${amount:,.2f}"


def decision_safety_object(summary: dict[str, Any]) -> dict[str, object]:
    """Return the normalized decision-safety object for the top candidate."""
    gate = dict(as_dict(summary.get("decision_gate") or summary.get("decision_safety")))
    candidate_action = text(gate.get("candidate_action") or summary.get("top_action")).replace(" blocked", "")
    safe_to_buy = bool(gate.get("safe_to_buy", candidate_action in BUY_ACTIONS and text(gate.get("status"), "Ready") != "Blocked"))
    status = text(gate.get("status"), "Ready" if safe_to_buy else "Blocked")
    reasons = [text(reason) for reason in as_list(gate.get("reasons")) if text(reason)]
    summary_text = text(gate.get("summary")) or ("Decision-safe buy candidate." if safe_to_buy else "; ".join(reasons))
    return {
        "safe_to_buy": safe_to_buy,
        "status": status,
        "candidate_action": candidate_action,
        "reasons": reasons,
        "summary": summary_text or "Passed",
    }


def decision_safety_review(summary: dict[str, Any]) -> dict[str, object]:
    """Return display-only labels that distinguish candidate rank from buy safety."""
    safety = decision_safety_object(summary)
    candidate_action = text(safety.get("candidate_action"))
    safe_to_buy = bool(safety.get("safe_to_buy"))
    if safe_to_buy and candidate_action in BUY_ACTIONS:
        review_label = "Decision-safe next buy"
    elif not safe_to_buy and candidate_action in BUY_ACTIONS:
        review_label = "Blocked buy candidate"
    else:
        review_label = "Top-ranked candidate"

    suggested_amount_text = text(summary.get("suggested_amount_text"))
    if not suggested_amount_text:
        suggested_amount_text = money(summary.get("suggested_amount"))
    if not safe_to_buy:
        suggested_amount_text = "$0.00"

    return {
        **safety,
        "review_label": review_label,
        "symbol": text(summary.get("top_symbol")),
        "company": text(summary.get("top_company")),
        "score": text(summary.get("top_score")),
        "suggested_amount_text": suggested_amount_text,
    }


def reasons_text(review: dict[str, object]) -> str:
    reasons = [text(reason) for reason in as_list(review.get("reasons")) if text(reason)]
    return "; ".join(reasons) if reasons else "None"
