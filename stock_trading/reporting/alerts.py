"""Presentation helpers for review-only alert and review-trigger context."""

from __future__ import annotations

from typing import Any


DISPLAY_NOTE = (
    "Review-only alert prompts for manual attention; official recommendations stay unchanged "
    "and no live notifications are sent."
)


def as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def text(value: object, default: str = "") -> str:
    if value is None or value == "":
        return default
    return str(value)


def titleize(value: object) -> str:
    return text(value, "unknown").replace("_", " ").title()


def count_rows(counts: dict[str, Any]) -> list[dict[str, object]]:
    return [
        {
            "label": titleize(label),
            "count": count,
        }
        for label, count in sorted(counts.items())
    ]


def build_alerts_review_view(context: dict[str, object]) -> dict[str, object]:
    review = as_dict(context.get("alerts_review"))
    summary = as_dict(review.get("active_alerts_summary"))
    top_alerts = as_list(review.get("top_priority_alerts"))
    lifecycle = as_dict(review.get("alert_lifecycle_metadata"))
    active_count = int(summary.get("active_alerts") or 0)
    total_count = int(summary.get("total_alerts") or 0)
    return {
        "review_only": review.get("review_only", True),
        "recommendation_only": review.get("recommendation_only", True),
        "no_live_notifications": review.get("no_live_notifications", True),
        "note": text(review.get("note"), DISPLAY_NOTE),
        "cards": [
            {
                "label": "Active alerts",
                "value": active_count,
                "detail": "Manual review prompts currently visible.",
            },
            {
                "label": "Total alerts",
                "value": total_count,
                "detail": "Includes acknowledged, deferred, dismissed, and resolved prompts.",
            },
            {
                "label": "Top priority",
                "value": len(top_alerts),
                "detail": "Highest-priority manual attention items.",
            },
            {
                "label": "Review-only",
                "value": str(review.get("review_only", True)),
                "detail": "Alerts do not override official recommendations.",
            },
            {
                "label": "Live notifications",
                "value": "Off",
                "detail": "No external delivery is configured.",
            },
        ],
        "top_priority_alerts": top_alerts,
        "alerts_by_review_area": count_rows(as_dict(review.get("alerts_by_review_area"))),
        "alerts_by_severity": count_rows(as_dict(review.get("alerts_by_severity"))),
        "alerts_by_status": count_rows(as_dict(review.get("alerts_by_status"))),
        "lifecycle_metadata": [
            {"label": "Dismissed", "value": lifecycle.get("dismissed_count", 0)},
            {"label": "Resolved", "value": lifecycle.get("resolved_count", 0)},
            {"label": "Deferred/stale", "value": lifecycle.get("stale_deferred_alerts", 0)},
            {"label": "Local metadata only", "value": lifecycle.get("local_review_metadata_only", True)},
        ],
        "empty_state": text(review.get("empty_state"), "No active review alerts. Existing recommendations remain unchanged."),
    }
