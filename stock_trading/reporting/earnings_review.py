"""Presentation helpers for review-only earnings event review context."""

from __future__ import annotations

from typing import Any


def as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: object) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def text(value: object, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def review_label(value: object) -> str:
    raw = text(value)
    labels = {
        "review_pre_earnings": "Review before earnings",
        "review_post_earnings": "Review after earnings",
        "wait_for_date_confirmation": "Wait for earnings date",
        "data_gap_review": "Review earnings data gap",
        "monitor_after_report": "Review after earnings",
        "ignore_for_now": "Not applicable now",
        "consider_small_review_only_add": "Review before earnings",
        "wait_until_after_report": "Wait for earnings",
        "hold_buy_capacity": "Hold capacity",
        "verify_data_first": "Verify earnings data first",
        "review_for_add_after_earnings": "Review after earnings",
        "review_thesis_risk": "Review thesis risk",
        "wait_for_call_or_filing": "Wait for call or filing",
        "monitor_reaction": "Monitor reaction",
    }
    return labels.get(raw, raw.replace("_", " ").title() if raw else "Not available")


def event_row(row: dict[str, Any]) -> list[object]:
    days = row.get("days_until_earnings")
    if days is None:
        days = row.get("days_since_earnings")
    return [
        row.get("symbol", ""),
        row.get("company", ""),
        row.get("earnings_date", "") or "Missing date",
        days if days is not None else "n/a",
        review_label(row.get("recommended_review_action")),
        row.get("source_status", ""),
        row.get("provider_gap_status", ""),
    ]


def pre_review_row(row: dict[str, Any]) -> list[object]:
    return [
        row.get("symbol", ""),
        row.get("earnings_date", "") or "Missing date",
        row.get("days_until_earnings") if row.get("days_until_earnings") is not None else "n/a",
        review_label(row.get("recommended_review_action")),
        row.get("setup_label", ""),
        "; ".join(text(item) for item in as_list(row.get("blockers"))[:2]) or "None listed",
    ]


def post_review_row(row: dict[str, Any]) -> list[object]:
    reaction = row.get("price_reaction_pct")
    reaction_text = f"{float(reaction):+.1f}%" if isinstance(reaction, (int, float)) else "Missing"
    return [
        row.get("symbol", ""),
        row.get("earnings_date", "") or "Missing date",
        row.get("days_since_earnings") if row.get("days_since_earnings") is not None else "n/a",
        review_label(row.get("recommended_review_action")),
        row.get("reaction_label", ""),
        reaction_text,
        row.get("thesis_impact", ""),
    ]


def gap_row(row: dict[str, Any]) -> list[object]:
    return [
        row.get("symbol", ""),
        row.get("provider", "") or row.get("source", ""),
        row.get("field", "") or row.get("source_status", ""),
        row.get("status", "") or row.get("provider_gap_status", ""),
        row.get("latest_issue", "") or row.get("recommended_review_action", ""),
    ]


def table(headers: list[str], rows: list[list[object]], empty_state: str) -> dict[str, object]:
    return {
        "headers": headers,
        "rows": rows,
        "empty_state": empty_state,
    }


def build_earnings_review_view(context: dict[str, object]) -> dict[str, object]:
    section = as_dict(context.get("earnings_review"))
    if not section:
        return {
            "available": False,
            "note": "Recommendation-only earnings review; official recommendation outputs are unchanged.",
            "cards": [
                {
                    "label": "Earnings review",
                    "value": "Not available",
                    "detail": "No earnings review context is available yet.",
                }
            ],
            "upcoming": table(["Symbol", "Company", "Date", "Days", "Review", "Source", "Gap"], [], "No upcoming earnings dates are available."),
            "recent": table(["Symbol", "Company", "Date", "Days", "Review", "Source", "Gap"], [], "No recent earnings events are available."),
            "pre": table(["Symbol", "Date", "Days", "Review", "Setup", "Blockers"], [], "No pre-earnings setup review rows are available."),
            "post": table(["Symbol", "Date", "Days Since", "Review", "Reaction", "Price Move", "Thesis"], [], "No post-earnings reaction review rows are available."),
            "gaps": table(["Symbol", "Provider", "Field", "Status", "Issue"], [], "No earnings-specific provider/data gaps are visible."),
            "signals": {},
        }

    upcoming_section = as_dict(section.get("upcoming_earnings_queue"))
    recent_section = as_dict(section.get("recent_earnings_queue"))
    pre_section = as_dict(section.get("pre_earnings_setup_review"))
    post_section = as_dict(section.get("post_earnings_reaction_review"))
    gaps_section = as_dict(section.get("provider_data_gaps"))
    signal_section = as_dict(section.get("earnings_signal_summary"))
    upcoming_rows = [event_row(as_dict(row)) for row in as_list(upcoming_section.get("rows"))]
    recent_rows = [event_row(as_dict(row)) for row in as_list(recent_section.get("rows"))]
    pre_rows = [pre_review_row(as_dict(row)) for row in as_list(pre_section.get("rows"))]
    post_rows = [post_review_row(as_dict(row)) for row in as_list(post_section.get("rows"))]
    gap_rows = [gap_row(as_dict(row)) for row in as_list(gaps_section.get("rows"))]
    if not gap_rows:
        gap_rows = [gap_row(as_dict(row)) for row in as_list(gaps_section.get("event_rows"))]
    categories = as_dict(signal_section.get("categories"))
    cards = [
        {
            "label": "Upcoming earnings",
            "value": str(len(upcoming_rows)),
            "detail": "Pre-earnings opportunities and wait-for-earnings reviews.",
        },
        {
            "label": "Recent earnings",
            "value": str(len(recent_rows)),
            "detail": "Post-earnings reaction and thesis review opportunities.",
        },
        {
            "label": "Pre-earnings setup",
            "value": str(len(pre_rows)),
            "detail": "Review-only timing setup; it does not override the current decision.",
        },
        {
            "label": "Post-earnings reaction",
            "value": str(len(post_rows)),
            "detail": "Review after earnings when evidence or price reaction is available.",
        },
        {
            "label": "Earnings signals",
            "value": text(signal_section.get("overall_direction"), "missing"),
            "detail": f"{signal_section.get('signal_count', 0)} signal row(s); guidance {categories.get('guidance', 'missing')}.",
        },
    ]
    return {
        "available": True,
        "note": text(section.get("note"), "Recommendation-only earnings review; official recommendation outputs are unchanged."),
        "cards": cards,
        "upcoming": table(["Symbol", "Company", "Date", "Days", "Review", "Source", "Gap"], upcoming_rows, text(upcoming_section.get("empty_state"), "No upcoming earnings dates are available.")),
        "recent": table(["Symbol", "Company", "Date", "Days", "Review", "Source", "Gap"], recent_rows, text(recent_section.get("empty_state"), "No recent earnings events are available.")),
        "pre": table(["Symbol", "Date", "Days", "Review", "Setup", "Blockers"], pre_rows, text(pre_section.get("empty_state"), "No pre-earnings setup review rows are available.")),
        "post": table(["Symbol", "Date", "Days Since", "Review", "Reaction", "Price Move", "Thesis"], post_rows, text(post_section.get("empty_state"), "No post-earnings reaction review rows are available.")),
        "gaps": table(["Symbol", "Provider", "Field", "Status", "Issue"], gap_rows, text(gaps_section.get("empty_state"), "No earnings-specific provider/data gaps are visible.")),
        "signals": {
            "overall_direction": text(signal_section.get("overall_direction"), "missing"),
            "signal_count": signal_section.get("signal_count", 0),
            "categories": categories,
        },
    }


__all__ = ["build_earnings_review_view", "review_label"]
