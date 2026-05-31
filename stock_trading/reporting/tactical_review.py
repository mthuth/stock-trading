"""Presentation helpers for review-only tactical review context."""

from __future__ import annotations

from typing import Any


DISPLAY_NOTE = (
    "Recommendation-only tactical review; it is separate from and does not override "
    "long-term capital deployment or official recommendations."
)


def as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: object) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def text(value: object, default: str = "") -> str:
    if value is None or value == "":
        return default
    return str(value)


def display_label(value: object) -> str:
    labels = {
        "breakout": "Breakout",
        "breakout_review": "Breakout",
        "pullback": "Pullback",
        "pullback_review": "Pullback",
        "momentum": "Momentum",
        "momentum_review": "Momentum",
        "reversal": "Reversal",
        "reversal_review": "Reversal",
        "post_earnings_reaction": "Post-earnings reaction",
        "post_earnings_reaction_review": "Post-earnings reaction",
        "pre_earnings_setup": "Pre-earnings setup",
        "pre_earnings_setup_review": "Pre-earnings setup",
        "news_catalyst": "News catalyst",
        "news_catalyst_review": "News catalyst",
        "data_insufficient": "Data insufficient",
        "no_setup": "No setup",
        "no_tactical_setup": "No setup",
        "tactical_buy_review": "Buy setup review",
        "tactical_sell_review": "Sell setup review",
        "wait_for_confirmation": "Wait for confirmation",
        "watch_intraday": "Watch same day",
        "avoid_for_now": "Avoid for now",
        "hold_existing": "Hold existing",
        "data_gap_review": "Data gap review",
        "same_day": "Same day",
        "same_week": "1 to 5 days",
        "same_month": "5 to 20 days",
        "1_day": "Same day",
        "5_trading_days": "1 to 5 days",
        "20_trading_days": "5 to 20 days",
        "1_to_5_days": "1 to 5 days",
        "5_to_20_days": "5 to 20 days",
        "20_to_60_days": "20 to 60 days",
        "unknown": "Unknown",
        "none": "None",
    }
    raw = text(value)
    return labels.get(raw, raw.replace("_", " ").title() if raw else "Not available")


def pct(value: object) -> str:
    try:
        return f"{float(value):+.1f}%"
    except (TypeError, ValueError):
        return "n/a"


def price(value: object) -> str:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return "n/a"
    return f"${amount:,.2f}"


def table(headers: list[str], rows: list[list[object]], empty_state: str) -> dict[str, object]:
    return {"headers": headers, "rows": rows, "empty_state": empty_state}


def queue_row(row: dict[str, Any]) -> list[object]:
    return [
        row.get("symbol", ""),
        display_label(row.get("setup_label")),
        display_label(row.get("tactical_horizon")),
        display_label(row.get("review_action")),
        display_label(row.get("risk_zone_label")),
        row.get("priority_rank", ""),
        text(row.get("invalidation_condition"), "No invalidation condition available."),
    ]


def risk_row(row: dict[str, Any]) -> list[object]:
    return [
        row.get("symbol", ""),
        display_label(row.get("setup_label")),
        display_label(row.get("tactical_horizon")),
        display_label(row.get("risk_zone_label")),
        price(row.get("support_reference")),
        price(row.get("resistance_reference")),
        text(row.get("invalidation_condition"), "No invalidation condition available."),
    ]


def gap_row(row: dict[str, Any]) -> list[object]:
    return [
        row.get("symbol", ""),
        row.get("provider", "") or row.get("source", ""),
        row.get("field", "") or row.get("endpoint", ""),
        row.get("status", ""),
        row.get("latest_issue", "") or row.get("message", ""),
    ]


def event_row(row: dict[str, Any]) -> list[object]:
    return [
        row.get("symbol", ""),
        display_label(row.get("event_type")),
        row.get("earnings_date", "") or row.get("event_date", "") or "n/a",
        display_label(row.get("recommended_review_action")),
    ]


def outcome_row(row: dict[str, Any]) -> list[object]:
    return [
        row.get("symbol", ""),
        display_label(row.get("setup_label")),
        display_label(row.get("tactical_horizon")),
        display_label(row.get("review_action")),
        row.get("window_trading_days", ""),
        display_label(row.get("outcome_status")),
        pct(row.get("directional_return_pct")),
    ]


def build_tactical_review_view(context: dict[str, object]) -> dict[str, object]:
    section = as_dict(context.get("tactical_review"))
    if not section:
        return {
            "available": False,
            "note": DISPLAY_NOTE,
            "cards": [
                {
                    "label": "Tactical review",
                    "value": "Not available",
                    "detail": "No tactical review context is available yet.",
                }
            ],
            "watchlist": table(["Symbol", "Setup", "Horizon", "Review", "Risk", "Rank", "Invalidation"], [], "No tactical review setups are available yet."),
            "risk_zones": table(["Symbol", "Setup", "Horizon", "Risk", "Support", "Resistance", "Invalidation"], [], "No tactical risk-zone rows are available yet."),
            "gaps": table(["Symbol", "Provider", "Field", "Status", "Issue"], [], "No tactical provider/data gaps are visible."),
            "events": table(["Symbol", "Event", "Date", "Review"], [], "No earnings/event context is attached to tactical review rows."),
            "outcomes": table(["Symbol", "Setup", "Horizon", "Review", "Window", "Outcome", "Move"], [], "No tactical outcome history is available yet."),
        }

    queue = as_dict(section.get("tactical_watchlist_queue"))
    risk_zones = as_dict(section.get("risk_zones"))
    gaps = as_dict(section.get("provider_data_gaps"))
    events = as_dict(section.get("earnings_event_context"))
    outcomes = as_dict(section.get("tactical_outcome_history"))
    summary = as_dict(outcomes.get("summary"))
    queue_rows = [queue_row(as_dict(row)) for row in as_list(queue.get("rows"))]
    risk_rows = [risk_row(as_dict(row)) for row in as_list(risk_zones.get("rows"))]
    gap_rows = [gap_row(as_dict(row)) for row in as_list(gaps.get("rows"))]
    event_rows = [event_row(as_dict(row)) for row in as_list(events.get("rows"))]
    outcome_rows = [outcome_row(as_dict(row)) for row in as_list(outcomes.get("rows"))]
    cards = [
        {
            "label": "Tactical queue",
            "value": str(len(queue_rows)),
            "detail": "Separate review-only setup queue below long-term and earnings context.",
        },
        {
            "label": "Review-only",
            "value": "True" if section.get("review_only", True) else "False",
            "detail": "Official long-term recommendations remain unchanged.",
        },
        {
            "label": "Does not override",
            "value": "True" if section.get("does_not_override_long_term", True) else "False",
            "detail": "Long-term capital deployment remains the first decision surface.",
        },
        {
            "label": "Provider/data gaps",
            "value": str(len(gap_rows)),
            "detail": "Data gaps create review metadata only.",
        },
        {
            "label": "Outcome history",
            "value": str(summary.get("outcome_count", len(outcome_rows))),
            "detail": "After-the-fact tactical outcome review when history is available.",
        },
    ]
    return {
        "available": True,
        "note": DISPLAY_NOTE,
        "cards": cards,
        "watchlist": table(
            ["Symbol", "Setup", "Horizon", "Review", "Risk", "Rank", "Invalidation"],
            queue_rows,
            text(queue.get("empty_state"), "No tactical review setups are available yet."),
        ),
        "risk_zones": table(
            ["Symbol", "Setup", "Horizon", "Risk", "Support", "Resistance", "Invalidation"],
            risk_rows,
            text(risk_zones.get("empty_state"), "No tactical risk-zone rows are available yet."),
        ),
        "gaps": table(
            ["Symbol", "Provider", "Field", "Status", "Issue"],
            gap_rows,
            text(gaps.get("empty_state"), "No tactical provider/data gaps are visible."),
        ),
        "events": table(
            ["Symbol", "Event", "Date", "Review"],
            event_rows,
            text(events.get("empty_state"), "No earnings/event context is attached to tactical review rows."),
        ),
        "outcomes": table(
            ["Symbol", "Setup", "Horizon", "Review", "Window", "Outcome", "Move"],
            outcome_rows,
            text(outcomes.get("empty_state"), "No tactical outcome history is available yet."),
        ),
    }


__all__ = ["DISPLAY_NOTE", "build_tactical_review_view", "display_label"]
