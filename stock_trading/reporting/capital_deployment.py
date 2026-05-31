"""Presentation helpers for review-only long-term capital deployment context."""

from __future__ import annotations

from typing import Any


def as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: object) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        return [value] if value else []
    return []


def text(value: object, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def money(value: object) -> str:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return "Needs manual update"
    return f"${amount:,.2f}"


def compact_candidate(value: object, fallback_label: str) -> dict[str, object]:
    candidate = as_dict(value)
    if not candidate:
        return {
            "available": False,
            "label": fallback_label,
            "symbol": "None",
            "company": "",
            "action": "",
            "decision_safety": "Not available",
            "target_confidence": "Not available",
            "suggested_amount": "",
            "rationale": [],
            "blockers": [],
        }
    return {
        "available": True,
        "label": text(candidate.get("candidate_role"), fallback_label).replace("_", " ").title(),
        "symbol": text(candidate.get("symbol"), "None"),
        "company": text(candidate.get("company")),
        "action": text(candidate.get("action")),
        "decision_safety": text(candidate.get("decision_gate_status"), "Not available"),
        "target_confidence": text(candidate.get("target_confidence"), "Not available"),
        "suggested_amount": text(candidate.get("suggested_amount_text")) or money(candidate.get("suggested_amount")),
        "rationale": as_list(candidate.get("key_rationale")),
        "blockers": as_list(candidate.get("key_blockers")),
    }


def build_long_term_capital_deployment_view(context: dict[str, object]) -> dict[str, object]:
    section = as_dict(context.get("long_term_capital_deployment"))
    if not section:
        return {
            "available": False,
            "question": "What should I buy/add today for long-term holdings?",
            "status": "missing",
            "cards": [
                {
                    "label": "Long-term add",
                    "value": "Not available",
                    "detail": "No long-term capital deployment context is available yet.",
                },
                {
                    "label": "Capital availability",
                    "value": "Needs manual update",
                    "detail": "Configure manual or configured capital availability before reviewing deployable amount.",
                },
            ],
            "primary": compact_candidate({}, "Primary Candidate"),
            "fallback": compact_candidate({}, "Fallback Candidate"),
            "hold_capacity_message": "Buy capacity held until long-term capital deployment context is available.",
            "blockers": ["No long-term capital deployment context is available yet."],
            "holding_health": {
                "available": False,
                "message": "No long-term holding health rows are available yet.",
                "summary": {},
                "top_review_rows": [],
            },
            "note": "Review-only and recommendation-only; official recommendations are unchanged.",
        }

    primary = compact_candidate(section.get("primary_candidate"), "Primary Candidate")
    fallback = compact_candidate(section.get("fallback_candidate"), "Fallback Candidate")
    capital = as_dict(section.get("capital_availability"))
    holding_health = as_dict(section.get("long_term_holding_health_summary"))
    deployable_text = text(capital.get("deployable_amount_text")) or money(capital.get("deployable_amount"))
    capital_status = text(capital.get("status") or section.get("status"), "Not available")
    cards = [
        {
            "label": "Primary long-term add",
            "value": f"{primary['symbol']} {primary['action']}".strip(),
            "detail": f"{primary['decision_safety']} decision safety; {primary['target_confidence']} target confidence.",
        },
        {
            "label": "Deployable amount",
            "value": deployable_text,
            "detail": text(capital.get("reason"), "Capital availability is review-only."),
        },
        {
            "label": "Capital availability",
            "value": capital_status,
            "detail": f"Source: {text(capital.get('source'), 'not configured')}; as of {text(capital.get('as_of_date'), 'n/a')}.",
        },
        {
            "label": "Fallback / hold",
            "value": fallback["symbol"] if fallback.get("available") else "Hold capacity",
            "detail": text(section.get("hold_capacity_message")) or "Fallback candidate is only shown when the top add is blocked.",
        },
        {
            "label": "Holding health",
            "value": text(holding_health.get("holding_count"), "0"),
            "detail": text(holding_health.get("message"), "No long-term holding health rows are available yet."),
        },
    ]
    return {
        "available": True,
        "question": text(section.get("question"), "What should I buy/add today for long-term holdings?"),
        "status": text(section.get("status"), "review"),
        "cards": cards,
        "primary": primary,
        "fallback": fallback,
        "hold_capacity_message": text(section.get("hold_capacity_message")),
        "blockers": as_list(section.get("key_blockers")),
        "rationale": as_list(section.get("key_rationale")),
        "capital": capital,
        "holding_health": {
            "available": bool(holding_health.get("available")),
            "message": text(holding_health.get("message"), "No long-term holding health rows are available yet."),
            "summary": as_dict(holding_health.get("summary")),
            "top_review_rows": as_list(holding_health.get("top_review_rows")),
        },
        "ai_synthesis_note": text(section.get("ai_synthesis_note"), "AI synthesis is explanatory only."),
        "note": text(section.get("note"), "Review-only and recommendation-only; official recommendations are unchanged."),
    }


__all__ = ["build_long_term_capital_deployment_view"]
