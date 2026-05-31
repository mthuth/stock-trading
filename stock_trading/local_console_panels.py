"""Panel summaries for the static local decision console."""

from __future__ import annotations

from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


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


def count_rows(section: object) -> int:
    value = as_dict(section)
    return len(as_list(value.get("rows")))


def learning_count(section: dict[str, Any], *keys: str) -> int:
    for key in keys:
        value = section.get(key)
        if isinstance(value, (int, float)):
            return int(value)
    rows = as_list(section.get("rows")) or as_list(section.get("entries")) or as_list(section.get("top_outcomes"))
    return len(rows)


def build_latest_recommendation_panel(context: dict[str, object]) -> dict[str, object]:
    summary = as_dict(context.get("summary"))
    gate = as_dict(summary.get("decision_gate")) or as_dict(context.get("decision_safety"))
    return {
        "title": "Latest Recommendation",
        "status": text(summary.get("recommendation_label"), "No recommendation context found"),
        "items": [
            {"label": "Symbol", "value": text(summary.get("top_symbol"), "n/a")},
            {"label": "Action", "value": text(summary.get("top_action"), "n/a")},
            {"label": "Score", "value": text(summary.get("top_score"), "n/a")},
            {"label": "Decision safety", "value": text(gate.get("status"), "n/a")},
            {"label": "Target confidence", "value": text(summary.get("confidence"), "n/a")},
            {"label": "Suggested amount", "value": text(summary.get("suggested_amount_text"), "n/a")},
        ],
        "note": text(summary.get("top_notes"), "No latest recommendation context is available yet."),
    }


def build_capital_deployment_panel(context: dict[str, object]) -> dict[str, object]:
    deployment = as_dict(context.get("long_term_capital_deployment"))
    primary = as_dict(deployment.get("primary_candidate"))
    fallback = as_dict(deployment.get("fallback_candidate"))
    capital = as_dict(deployment.get("capital_availability"))
    return {
        "title": "Long-Term Capital Deployment",
        "status": text(deployment.get("status"), "Not available"),
        "items": [
            {"label": "Primary candidate", "value": f"{text(primary.get('symbol'), 'n/a')} {text(primary.get('action'))}".strip()},
            {"label": "Decision safety", "value": text(primary.get("decision_gate_status"), "n/a")},
            {"label": "Target confidence", "value": text(primary.get("target_confidence"), "n/a")},
            {"label": "Deployable amount", "value": text(capital.get("deployable_amount_text"), text(primary.get("suggested_amount_text"), "n/a"))},
            {"label": "Capital source", "value": text(capital.get("source"), text(capital.get("status"), "n/a"))},
            {"label": "Fallback", "value": text(fallback.get("symbol"), text(deployment.get("hold_capacity_message"), "None shown"))},
        ],
        "note": text(deployment.get("note"), "Review-only capital deployment context is not available yet."),
    }


def build_earnings_panel(context: dict[str, object]) -> dict[str, object]:
    earnings = as_dict(context.get("earnings_review"))
    upcoming = as_dict(earnings.get("upcoming_earnings_queue"))
    recent = as_dict(earnings.get("recent_earnings_queue"))
    pre = as_dict(earnings.get("pre_earnings_setup_review"))
    post = as_dict(earnings.get("post_earnings_reaction_review"))
    gaps = as_dict(earnings.get("provider_data_gaps"))
    signals = as_dict(earnings.get("earnings_signal_summary"))
    return {
        "title": "Earnings Review",
        "status": text(signals.get("overall_direction"), "Not available"),
        "items": [
            {"label": "Upcoming queue", "value": count_rows(upcoming)},
            {"label": "Recent queue", "value": count_rows(recent)},
            {"label": "Pre-earnings setup", "value": count_rows(pre)},
            {"label": "Post-earnings reaction", "value": count_rows(post)},
            {"label": "Provider/data gaps", "value": count_rows(gaps) + len(as_list(gaps.get("event_rows")))},
            {"label": "Review-only", "value": text(earnings.get("review_only"), "true")},
        ],
        "note": text(earnings.get("note"), "No earnings review context is available yet."),
    }


def build_tactical_panel(context: dict[str, object]) -> dict[str, object]:
    tactical = as_dict(context.get("tactical_review"))
    queue = as_dict(tactical.get("tactical_watchlist_queue"))
    risks = as_dict(tactical.get("risk_zones"))
    gaps = as_dict(tactical.get("provider_data_gaps"))
    events = as_dict(tactical.get("earnings_event_context"))
    outcomes = as_dict(tactical.get("tactical_outcome_history"))
    summary = as_dict(outcomes.get("summary"))
    return {
        "title": "Tactical Review",
        "status": "Review-only" if tactical else "Not available",
        "items": [
            {"label": "Tactical queue", "value": count_rows(queue)},
            {"label": "Risk zones", "value": count_rows(risks)},
            {"label": "Provider/data gaps", "value": count_rows(gaps)},
            {"label": "Earnings/event context", "value": count_rows(events)},
            {"label": "Outcome history", "value": summary.get("outcome_count", count_rows(outcomes))},
            {"label": "Does not override", "value": text(tactical.get("does_not_override_long_term"), "true")},
        ],
        "note": "Recommendation-only tactical review; it does not override long-term capital deployment or official recommendations.",
    }


def build_reliability_panel(context: dict[str, object]) -> dict[str, object]:
    reliability = as_dict(context.get("reliability"))
    source_health = as_dict(as_dict(context.get("source_health")).get("summary"))
    provider_gap_review = as_dict(context.get("provider_gap_review"))
    gap_summary = as_dict(provider_gap_review.get("summary"))
    return {
        "title": "Provider/Data Reliability",
        "status": text(reliability.get("mode"), "Not available"),
        "items": [
            {"label": "Fresh prices", "value": as_dict(reliability.get("price_counts")).get("fresh", "n/a")},
            {"label": "Missing prices", "value": as_dict(reliability.get("price_counts")).get("missing", "n/a")},
            {"label": "Source needs attention", "value": source_health.get("needs_attention", "n/a")},
            {"label": "Provider gaps", "value": gap_summary.get("total_gaps", gap_summary.get("open_gaps", "n/a"))},
        ],
        "note": text(provider_gap_review.get("note"), "Provider gaps and source-health context remain visible for review."),
    }


def build_ai_panel(artifacts: dict[str, object]) -> dict[str, object]:
    latest = as_dict(artifacts.get("latest"))
    ai_files = [
        latest.get("ai_briefs_markdown"),
        latest.get("ai_briefs_json"),
        latest.get("ai_briefs_html"),
        latest.get("ai_analysis_context"),
        latest.get("synthesis_packets"),
    ]
    available = [as_dict(item) for item in ai_files if isinstance(item, dict)]
    return {
        "title": "AI Brief Status",
        "status": "Available" if available else "Not available",
        "items": [
            {"label": "AI brief artifacts", "value": len(available)},
            {"label": "Latest brief", "value": text(as_dict(latest.get("ai_briefs_markdown")).get("file_name"), "n/a")},
            {"label": "Analysis context", "value": text(as_dict(latest.get("ai_analysis_context")).get("file_name"), "n/a")},
            {"label": "Synthesis packets", "value": text(as_dict(latest.get("synthesis_packets")).get("file_name"), "n/a")},
        ],
        "note": "AI briefs are explanatory and do not change official recommendations.",
    }


def build_learning_panel(context: dict[str, object]) -> dict[str, object]:
    learning = as_dict(context.get("learning_review"))
    manual = as_dict(learning.get("manual_trade_journal"))
    outcomes = as_dict(learning.get("recommendation_outcomes"))
    catalyst = as_dict(learning.get("catalyst_follow_through"))
    source_usefulness = as_dict(learning.get("source_usefulness"))
    safety = as_dict(learning.get("decision_safety_effectiveness"))
    return {
        "title": "Learning Review",
        "status": "Review-only",
        "items": [
            {"label": "Manual journal", "value": learning_count(manual, "entry_count", "count")},
            {"label": "Recommendation outcomes", "value": learning_count(outcomes, "outcome_count", "count")},
            {"label": "Catalyst follow-through", "value": learning_count(catalyst, "row_count", "count")},
            {"label": "Source usefulness", "value": learning_count(source_usefulness, "row_count", "count")},
            {"label": "Decision safety outcomes", "value": learning_count(safety, "row_count", "count")},
        ],
        "note": text(learning.get("note"), "Learning outputs are review-only and do not tune the model automatically."),
    }


def build_manual_outcomes_panel(context: dict[str, object]) -> dict[str, object]:
    learning = as_dict(context.get("learning_review"))
    manual = as_dict(learning.get("manual_trade_journal"))
    outcomes = as_dict(learning.get("recommendation_outcomes"))
    return {
        "title": "Manual Journal And Outcomes",
        "status": "Review-only",
        "items": [
            {"label": "Manual entries", "value": learning_count(manual, "entry_count", "count")},
            {"label": "Outcome rows", "value": learning_count(outcomes, "outcome_count", "count")},
            {"label": "Manual empty state", "value": text(manual.get("empty_state"), "n/a")},
            {"label": "Outcome empty state", "value": text(outcomes.get("empty_state"), "n/a")},
        ],
        "note": "Manual actions and outcomes are after-the-fact review records, not run controls.",
    }


def build_artifacts_panel(artifacts: dict[str, object]) -> dict[str, object]:
    items = as_list(artifacts.get("items"))
    latest = as_dict(artifacts.get("latest"))
    return {
        "title": "Artifacts",
        "status": f"{len(items)} indexed" if items else "No artifacts",
        "items": [
            {"label": "Dashboard", "value": text(as_dict(latest.get("dashboard")).get("file_name"), "n/a")},
            {"label": "Report context", "value": text(as_dict(latest.get("report_context")).get("file_name"), "n/a")},
            {"label": "Markdown report", "value": text(as_dict(latest.get("daily_markdown")).get("file_name"), "n/a")},
            {"label": "CSV export", "value": text(as_dict(latest.get("daily_csv")).get("file_name"), "n/a")},
        ],
        "note": text(artifacts.get("empty_state"), "Open generated artifacts manually from the local filesystem."),
    }


def build_run_history_panel(runs: dict[str, object]) -> dict[str, object]:
    workflow = as_list(runs.get("workflow_runs"))
    recommendations = as_list(runs.get("recommendation_runs"))
    latest_workflow = as_dict(workflow[0]) if workflow else {}
    latest_recommendation = as_dict(recommendations[0]) if recommendations else {}
    return {
        "title": "Run History",
        "status": "Available" if workflow or recommendations else "No runs",
        "items": [
            {"label": "Workflow runs", "value": len(workflow)},
            {"label": "Recommendation runs", "value": len(recommendations)},
            {"label": "Latest workflow", "value": text(latest_workflow.get("status"), "n/a")},
            {"label": "Latest report date", "value": text(latest_recommendation.get("report_date"), "n/a")},
        ],
        "note": text(runs.get("empty_state"), "Run history is read-only metadata."),
    }


def build_strategy_links_panel() -> dict[str, object]:
    return {
        "title": "Strategy And Roadmap",
        "status": "Reference links",
        "links": [
            {"label": "Product Strategy", "path": str(ROOT / "docs" / "PRODUCT_STRATEGY.md")},
            {"label": "Roadmap Status", "path": str(ROOT / "docs" / "ROADMAP_STATUS.md")},
            {"label": "Local App Strategy", "path": str(ROOT / "docs" / "LOCAL_APP_STRATEGY.md")},
            {"label": "Decision Modes", "path": str(ROOT / "docs" / "DECISION_MODES.md")},
            {"label": "UX Experience", "path": str(ROOT / "docs" / "UX_EXPERIENCE.md")},
        ],
        "note": "Strategy links are local documentation references only.",
    }


def build_console_panels(
    report_context: dict[str, object],
    artifacts: dict[str, object],
    runs: dict[str, object],
) -> dict[str, object]:
    return {
        "latest_recommendation": build_latest_recommendation_panel(report_context),
        "capital_deployment": build_capital_deployment_panel(report_context),
        "earnings_review": build_earnings_panel(report_context),
        "tactical_review": build_tactical_panel(report_context),
        "provider_reliability": build_reliability_panel(report_context),
        "ai_brief_status": build_ai_panel(artifacts),
        "learning_review": build_learning_panel(report_context),
        "manual_journal_outcomes": build_manual_outcomes_panel(report_context),
        "artifacts": build_artifacts_panel(artifacts),
        "run_history": build_run_history_panel(runs),
        "strategy_roadmap": build_strategy_links_panel(),
    }


__all__ = ["build_console_panels"]
