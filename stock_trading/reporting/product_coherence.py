#!/usr/bin/env python3
"""Presentation-only product-coherence summaries for report context artifacts."""

from __future__ import annotations

from typing import Any


def _as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: object, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _table_rows(section: object) -> list[Any]:
    section_dict = _as_dict(section)
    return _as_list(section_dict.get("rows"))


def _availability(section: object, visible_label: str = "Visible") -> str:
    if _table_rows(section):
        return visible_label
    if _as_dict(section):
        return "Configured"
    return "Planned"


def build_review_path(context: dict[str, object]) -> dict[str, object]:
    """Build a compact hierarchy guide without changing report decisions."""
    summary = _as_dict(context.get("summary"))
    reliability = _as_dict(context.get("reliability"))
    decision_gate = _as_dict(summary.get("decision_gate"))
    top_symbol = _text(summary.get("top_symbol"), "Top candidate")
    top_action = _text(decision_gate.get("candidate_action") or summary.get("top_action"), "Review")
    confidence = _text(summary.get("confidence"), "n/a")
    data_status = _text(summary.get("data_status"), "n/a")
    return {
        "cards": [
            {
                "label": "1. Current buy/add decision",
                "value": f"{top_symbol} - {top_action}",
                "detail": "The current recommendation surface stays first and remains recommendation-only.",
            },
            {
                "label": "2. Safety and target confidence",
                "value": _text(decision_gate.get("status"), "Ready"),
                "detail": f"Decision safety and {confidence} target confidence stay next to the candidate.",
            },
            {
                "label": "3. Provider and data reliability",
                "value": _text(reliability.get("mode"), data_status),
                "detail": "Missing, stale, blocked, and source-health signals are visible before audit tabs.",
            },
            {
                "label": "4. AI synthesis explanatory",
                "value": "No recommendation impact",
                "detail": "Briefs and synthesis readiness explain evidence; they do not change scores or actions.",
            },
            {
                "label": "5. Learning and Wave 7 prep",
                "value": "Review-only",
                "detail": "Learning loops and capital deployment prep are surfaced without broker writes or order previews.",
            },
        ],
    }


def build_learning_review(context: dict[str, object]) -> dict[str, object]:
    """Summarize learning surfaces as review-only product context."""
    source_quality = _as_dict(context.get("source_quality"))
    source_quality_table = _as_dict(source_quality.get("table"))
    recommendation_outcomes = context.get("recommendation_outcomes")
    decision_safety_outcomes = context.get("decision_safety_outcomes")
    catalyst_outcomes = context.get("catalyst_outcomes")
    manual_journal = context.get("manual_trade_journal")
    source_usefulness = context.get("source_usefulness") or source_quality_table
    rows = [
        [
            "Manual journal",
            _availability(manual_journal),
            "Review-only; no broker writes.",
            "Capture manual decision notes and keep them auditable outside recommendation behavior.",
        ],
        [
            "Recommendation outcomes",
            _availability(recommendation_outcomes),
            "Review-only; no score or action changes.",
            "Compare later outcomes against recommendations before any future model-impact proposal.",
        ],
        [
            "Decision-safety effectiveness",
            _availability(decision_safety_outcomes),
            "Review-only; no gate changes.",
            "Review blocked buys, avoided risk, and missed upside without changing decision-safety rules.",
        ],
        [
            "Catalyst follow-through",
            _availability(catalyst_outcomes),
            "Review-only; no catalyst weighting changes.",
            "Check whether tracked catalysts actually followed through before Wave 7 model design.",
        ],
        [
            "Source usefulness",
            _availability(source_usefulness, "Visible via source quality"),
            "Review-only; no source weighting changes.",
            "Use source-quality/noise rows to decide which integrations deserve cleanup or paid-provider review.",
        ],
    ]
    return {
        "cards": [
            {
                "label": "Review-only learning",
                "value": "No model impact",
                "detail": "Learning review does not change scores, targets, actions, gates, allocation, or broker behavior.",
            },
            {
                "label": "Outcome loops",
                "value": _availability(recommendation_outcomes),
                "detail": "Recommendation and decision-safety outcomes remain audit inputs for future requirements.",
            },
            {
                "label": "Catalyst review",
                "value": _availability(catalyst_outcomes),
                "detail": "Catalyst follow-through stays explanatory until an explicit model-impact decision.",
            },
            {
                "label": "Source usefulness",
                "value": _availability(source_usefulness, "Visible"),
                "detail": "Provider/source usefulness is visible for review without changing current recommendations.",
            },
        ],
        "table": {
            "headers": ["Learning surface", "Status", "Decision impact", "Next review action"],
            "rows": rows,
        },
    }


def build_capital_deployment_prep(context: dict[str, object]) -> dict[str, object]:
    """Summarize Wave 7 capital-deployment readiness without broker behavior."""
    summary = _as_dict(context.get("summary"))
    holdings = _as_dict(context.get("holdings"))
    holding_rows = _as_list(holdings.get("rows"))
    suggested_amount = _text(summary.get("suggested_amount_text") or summary.get("suggested_amount"), "n/a")
    amount_label = _text(summary.get("amount_label"), "Buy capacity")
    decision_gate = _as_dict(summary.get("decision_gate"))
    return {
        "cards": [
            {
                "label": "Wave 7 readiness",
                "value": "Prep only",
                "detail": "Capital deployment context is visible before any future broker expansion.",
            },
            {
                "label": amount_label,
                "value": suggested_amount,
                "detail": "No broker orders or previews; decision-support amount only.",
            },
            {
                "label": "Holdings context",
                "value": f"{len(holding_rows)} row(s)",
                "detail": "Allocation and 10% cap context remain tied to the current recommendation view.",
            },
            {
                "label": "Decision gate",
                "value": _text(decision_gate.get("status"), "Ready"),
                "detail": "Capital prep must continue to respect decision-safety status before any manual buy review.",
            },
        ],
        "table": {
            "headers": ["Capital surface", "Current status", "Next Wave 7 action"],
            "rows": [
                [
                    "Manual/configured cash",
                    "Not explicit in current report context",
                    "Add a manual or config-backed cash amount with an as-of date before broker expansion.",
                ],
                [
                    "Monthly buy capacity",
                    "Represented only by the current suggested amount label when available",
                    "Separate recurring buy capacity from per-symbol suggested amount.",
                ],
                [
                    "Holdings and allocation cap",
                    f"{len(holding_rows)} holding row(s) available",
                    "Keep allocation checks visible next to the current decision and future capital plan.",
                ],
                [
                    "Broker posture",
                    "Read-only/manual review",
                    "Do not add broker writes, order previews, or automated trading in Wave 7 prep.",
                ],
            ],
        },
    }
