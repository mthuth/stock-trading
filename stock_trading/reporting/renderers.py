#!/usr/bin/env python3
"""UX presentation renderer for stock-trading report-context data."""

from __future__ import annotations

import csv
import html
import json
import re
from pathlib import Path
from typing import Any

from stock_trading.ai_briefs import write_ai_brief_artifacts
from stock_trading.reporting import decision_safety as safety_review
from stock_trading.reporting.alerts import build_alerts_review_view
from stock_trading.reporting.capital_deployment import build_long_term_capital_deployment_view
from stock_trading.reporting.data_reliability import build_data_reliability_review
from stock_trading.reporting.earnings_review import build_earnings_review_view
from stock_trading.reporting.model_evaluation import build_model_evaluation_view
from stock_trading.reporting.provider_gaps import (
    render_provider_gap_review_html,
    render_provider_gap_review_markdown,
)
from stock_trading.reporting.product_coherence import (
    build_capital_deployment_prep,
    build_review_path,
)
from stock_trading.reporting.tactical_review import build_tactical_review_view


REQUIRED_CONTEXT_SECTIONS = (
    "metadata",
    "summary",
    "reliability",
    "recommendations",
    "holdings",
    "queues",
    "decision_briefs",
    "insight_themes",
    "score_movement",
    "trend_insights",
    "data_gaps",
    "source_health",
    "data_ingestion",
    "research_sources",
    "feedback",
    "learning_review",
    "long_term_capital_deployment",
    "earnings_review",
    "tactical_review",
    "model_evaluation",
    "alerts_review",
    "artifacts",
)
REPORT_SECTION_LABELS = (
    "Long-Term Capital Deployment Review",
    "Earnings Review",
    "Tactical Review",
    "Model Evaluation",
    "Alerts And Review Triggers",
    "Product Review Path",
    "Learning Review",
    "Wave 7 Capital Deployment Prep",
    "Insight Drivers",
    "Score Movement",
    "Trend Insights",
    "Ranked Data Gap Queue",
    "Decision Briefs",
    "Decision Insight",
    "Insight Themes",
    "What To Verify Next",
    "Verification Queue",
    "Provider Blocker Review",
    "Evidence Events",
    "Evidence Review Queue",
    "Synthesis Readiness By Symbol",
    "AI Insight Briefs",
    "Decision Insight History",
    "AI Analysis Context Ready",
)


def load_report_context(path: Path) -> dict[str, object]:
    return json.loads(path.read_text())


def validate_report_context(context: dict[str, object]) -> list[str]:
    return [section for section in REQUIRED_CONTEXT_SECTIONS if section not in context]


def as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def text(value: object, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def plain_text(value: object) -> str:
    """Return display-safe text from values that may contain dashboard HTML snippets."""
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", text(value))).split())


def money(value: object) -> str:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if amount == 0:
        return "$0.00"
    return f"${amount:,.2f}"


def pct(value: object) -> str:
    try:
        return f"{float(value):,.1f}%"
    except (TypeError, ValueError):
        return "n/a"


def slug(value: object) -> str:
    return "".join(char.lower() if char.isalnum() else "-" for char in text(value)).strip("-") or "item"


def context_filename_date(context: dict[str, object]) -> str:
    return text(as_dict(context.get("metadata")).get("report_date") or "context")


def artifact_names(context: dict[str, object]) -> dict[str, str]:
    date_label = context_filename_date(context)
    configured = as_dict(context.get("artifacts"))
    defaults = {
        "dashboard": f"dashboard-{date_label}.html",
        "markdown": f"daily-recommendation-{date_label}.md",
        "csv": f"daily-recommendation-{date_label}.csv",
        "email": f"email-summary-{date_label}.txt",
        "end_of_day": f"end-of-day-{date_label}.md",
        "watchlist": f"next-day-watchlist-{date_label}.md",
        "context": f"report-context-{date_label}.json",
        "ai_briefs_markdown": f"ai-insight-briefs-{date_label}.md",
        "ai_briefs_json": f"ai-insight-briefs-{date_label}.json",
        "ai_briefs_html": f"ai-insight-briefs-{date_label}.html",
    }
    return {key: text(configured.get(key) or default) for key, default in defaults.items()}


def markdown_escape_cell(value: object) -> str:
    return text(value).replace("|", "/").replace("\n", " ")


def markdown_table(headers: list[str], rows: list[list[object]]) -> str:
    if not rows:
        return ""
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        padded = [*row, *[""] * max(0, len(headers) - len(row))]
        lines.append("| " + " | ".join(markdown_escape_cell(value) for value in padded[: len(headers)]) + " |")
    return "\n".join(lines)


def html_table(
    headers: list[str],
    rows: list[list[object]],
    class_name: str = "compact-table",
    raw_columns: set[int] | None = None,
) -> str:
    raw_columns = raw_columns or set()
    if not rows:
        return "<p>No rows available.</p>"
    head = "".join(f"<th>{html.escape(header)}</th>" for header in headers)
    body = []
    for row in rows:
        cells = []
        padded = [*row, *[""] * max(0, len(headers) - len(row))]
        for index, value in enumerate(padded[: len(headers)]):
            rendered = text(value) if index in raw_columns else html.escape(text(value))
            cells.append(f"<td>{rendered}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    return f'<table class="{class_name}"><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table>'


def context_table(context: dict[str, object], section: str, fallback_headers: list[str]) -> tuple[list[str], list[list[object]]]:
    table = as_dict(context.get(section))
    return as_list(table.get("headers")) or fallback_headers, as_list(table.get("rows"))


def recommendations(context: dict[str, object]) -> list[dict[str, Any]]:
    return [as_dict(item) for item in as_list(context.get("recommendations"))]


def queue(context: dict[str, object], name: str) -> dict[str, Any]:
    return as_dict(as_dict(context.get("queues")).get(name))


def queue_table(context: dict[str, object], name: str, class_name: str = "decision-table") -> str:
    section = queue(context, name)
    return html_table(
        as_list(section.get("headers")),
        as_list(section.get("rows")),
        class_name,
        set(as_list(section.get("raw_columns"))),
    )


def column_lookup(headers: list[str]) -> dict[str, int]:
    return {header.lower(): index for index, header in enumerate(headers)}


def row_cell(headers: list[str], row: list[Any], candidates: list[str]) -> object:
    lookup = column_lookup(headers)
    index = next((lookup.get(candidate.lower()) for candidate in candidates if candidate.lower() in lookup), None)
    if index is None or index >= len(row):
        return ""
    return row[index]


def action_pill_html(value: object) -> str:
    raw = text(value)
    match = re.search(r'<span class="pill ([^"]+)">([^<]+)</span>', raw)
    if match:
        class_name = html.escape(match.group(1), quote=True)
        label = html.escape(html.unescape(match.group(2)))
        return f'<span class="pill {class_name}">{label}</span>'
    label = plain_text(raw)
    if not label:
        return ""
    return f'<span class="pill">{html.escape(label)}</span>'


def change_badge_html(value: object) -> str:
    raw = text(value)
    if '<span class="change-badge ' in raw:
        return raw
    label = plain_text(raw) or "No material change"
    return f'<span class="change-badge change-none">{html.escape(label)}</span>'


def normalized_source_health_status(status: object, severity: object) -> str:
    status_text = plain_text(status).lower()
    severity_text = plain_text(severity).lower()
    if "need" in status_text or "attention" in status_text or severity_text == "high":
        return "blocker"
    if "review" in status_text or severity_text in {"medium", "med"}:
        return "review"
    if "info" in status_text or "healthy" in status_text or severity_text == "low":
        return "info"
    return "review" if status_text or severity_text else "info"


def render_source_health_alerts_table(alerts: dict[str, Any]) -> str:
    headers = [text(header) for header in as_list(alerts.get("headers"))]
    rows = as_list(alerts.get("rows"))
    if not headers or not rows:
        return "<p>No rows available.</p>"

    lookup = column_lookup(headers)
    severity_index = lookup.get("severity")
    status_index = lookup.get("status")
    counts = {"all": len(rows), "blocker": 0, "review": 0, "info": 0}
    body = []
    for row in rows:
        values = as_list(row)
        severity = values[severity_index] if severity_index is not None and severity_index < len(values) else ""
        status = values[status_index] if status_index is not None and status_index < len(values) else ""
        category = normalized_source_health_status(status, severity)
        counts[category] = counts.get(category, 0) + 1
        padded = [*values, *[""] * max(0, len(headers) - len(values))]
        cells = "".join(f"<td>{html.escape(text(value))}</td>" for value in padded[: len(headers)])
        body.append(f'<tr data-source-health-filter="{html.escape(category)}">{cells}</tr>')

    buttons = [
        ("all", "All", counts["all"]),
        ("blocker", "Blockers", counts["blocker"]),
        ("review", "Review", counts["review"]),
        ("info", "Info", counts["info"]),
    ]
    controls = "".join(
        '<button class="source-health-filter" type="button" '
        f'data-source-health-filter="{html.escape(key)}" '
        f'aria-pressed="{str(key == "all").lower()}">'
        f'{html.escape(label)} <span>{count}</span></button>'
        for key, label, count in buttons
    )
    head = "".join(f"<th>{html.escape(header)}</th>" for header in headers)
    return (
        '<div class="source-health-filter-bar" aria-label="Source health alert filters">'
        f"{controls}</div>"
        '<div class="source-health-filter-summary" aria-live="polite">Showing all source health alerts.</div>'
        f'<table class="source-health-table"><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table>'
    )


def render_action_queue(context: dict[str, object]) -> str:
    section = queue(context, "action_queue")
    headers = [text(header) for header in as_list(section.get("headers"))]
    rows = as_list(section.get("rows"))
    audit_table = queue_table(context, "action_queue")
    if not headers or not rows:
        return (
            '<section class="action-queue-section">'
            '<div class="section-title"><h2>Action Queue</h2><span class="section-note">Compact decision scan</span></div>'
            "<p>No rows available.</p>"
            '<details class="action-audit-table"><summary>Full Action Queue Audit</summary>'
            f"{audit_table}</details></section>"
        )

    cards: list[str] = []
    for row in rows:
        values = as_list(row)
        rank = plain_text(row_cell(headers, values, ["Rank"]))
        symbol = plain_text(row_cell(headers, values, ["Symbol"]))
        action_html = action_pill_html(row_cell(headers, values, ["Action"]))
        score = plain_text(row_cell(headers, values, ["Score"]))
        change_html = change_badge_html(row_cell(headers, values, ["Change"]))
        current = plain_text(row_cell(headers, values, ["Current", "Today"]))
        target = plain_text(row_cell(headers, values, ["Target"]))
        upside = plain_text(row_cell(headers, values, ["Upside", "1Y Upside"]))
        confidence = plain_text(row_cell(headers, values, ["Confidence"]))
        status = plain_text(row_cell(headers, values, ["Data Status", "Status"]))
        trade_type = plain_text(row_cell(headers, values, ["Type", "Trade Type"]))
        rationale = plain_text(row_cell(headers, values, ["Rationale", "Why"]))
        rank_label = f"#{rank}" if rank else ""
        metric_items = [
            ("Current", current or "n/a"),
            ("Target", target or "n/a"),
            ("Upside", upside or "n/a"),
            ("Confidence", confidence or "n/a"),
            ("Data status", status or "n/a"),
        ]
        metrics_html = "".join(
            '<span>'
            f'<span class="label">{html.escape(label)}</span>'
            f'<strong>{html.escape(value)}</strong>'
            "</span>"
            for label, value in metric_items
        )
        cards.append(
            '<article class="action-card">'
            '<div class="action-card-head">'
            '<div class="action-card-title">'
            f'<span class="action-rank">{html.escape(rank_label)}</span>'
            f'<strong>{html.escape(symbol)}</strong>'
            f"{action_html}"
            "</div>"
            '<div class="action-card-score">'
            '<span class="label">Score</span>'
            f'<strong>{html.escape(score or "n/a")}</strong>'
            f"{change_html}"
            "</div>"
            "</div>"
            f'<div class="action-card-metrics">{metrics_html}</div>'
            f'<p class="action-card-rationale"><strong>{html.escape(trade_type or "Review")}</strong> · {html.escape(rationale or "No rationale available.")}</p>'
            "</article>"
        )

    return (
        '<section class="action-queue-section">'
        '<div class="section-title"><h2>Action Queue</h2><span class="section-note">Compact decision scan; audit table retained below</span></div>'
        f'<div class="action-queue-list">{"".join(cards)}</div>'
        '<details class="action-audit-table"><summary>Full Action Queue Audit</summary>'
        f"{audit_table}</details></section>"
    )


def compact_queue_table(
    section: dict[str, Any],
    column_specs: list[tuple[str, list[str]]],
    limit: int = 8,
    class_name: str = "print-table",
) -> str:
    headers = [text(header) for header in as_list(section.get("headers"))]
    rows = as_list(section.get("rows"))
    if not headers or not rows:
        return "<p>No rows available.</p>"

    lookup = {header.lower(): index for index, header in enumerate(headers)}
    selected_headers: list[str] = []
    selected_indexes: list[int | None] = []
    for display_header, candidates in column_specs:
        selected_headers.append(display_header)
        selected_indexes.append(next((lookup.get(candidate.lower()) for candidate in candidates if candidate.lower() in lookup), None))

    compact_rows: list[list[object]] = []
    for row in rows[:limit]:
        values = as_list(row)
        compact_rows.append(
            [
                plain_text(values[index]) if index is not None and index < len(values) else ""
                for index in selected_indexes
            ]
        )
    return html_table(selected_headers, compact_rows, class_name)


def summary_value(context: dict[str, object], key: str, default: str = "") -> str:
    return text(normalized_summary(context).get(key), default)


BUY_ACTIONS = {"Strong Buy", "Buy", "Add"}


def summary_decision_gate_reasons(context: dict[str, object], summary: dict[str, Any]) -> list[str]:
    action = text(summary.get("top_action")).replace(" blocked", "")
    if action not in BUY_ACTIONS:
        return []

    reasons: list[str] = []
    confidence = text(summary.get("confidence")).lower()
    data_status = text(summary.get("data_status"))
    if confidence and confidence not in {"medium", "high"}:
        reasons.append(f"{confidence.title()} target confidence")
    if data_status.startswith("Needs"):
        reasons.append(data_status)
    elif data_status == "Wide range":
        reasons.append("Wide target range")
    elif data_status == "Partial blend":
        reasons.append("Partial target blend")

    top_symbol = text(summary.get("top_symbol"))
    decision_rows = as_list(as_dict(context.get("decision_briefs")).get("rows"))
    for row in decision_rows:
        values = as_list(row)
        if len(values) >= 2 and text(values[0]) == top_symbol and text(values[1]) in {"Verification Needed", "Data Gap"}:
            reasons.append("Verification check is still open" if text(values[1]) == "Verification Needed" else "Required data gap is still open")
            break

    verification_rows = as_list(queue(context, "verification").get("rows"))
    if any(as_list(row) and text(as_list(row)[1]) == top_symbol for row in verification_rows):
        reasons.append("Verification queue item is still open")

    return list(dict.fromkeys(reason for reason in reasons if reason))


def normalized_summary(context: dict[str, object]) -> dict[str, Any]:
    summary = dict(as_dict(context.get("summary")))
    gate = dict(as_dict(summary.get("decision_gate")))
    if not gate:
        reasons = summary_decision_gate_reasons(context, summary)
        if reasons:
            action = text(summary.get("top_action")).replace(" blocked", "")
            gate = {
                "safe_to_buy": False,
                "status": "Blocked",
                "candidate_action": action,
                "reasons": reasons,
                "summary": "; ".join(reasons),
            }
    if gate:
        summary["decision_gate"] = gate
        if not gate.get("safe_to_buy"):
            action = text(gate.get("candidate_action") or summary.get("top_action")).replace(" blocked", "")
            summary["recommendation_label"] = "No decision-safe buy"
            summary["amount_label"] = "Buy capacity held"
            summary["suggested_amount"] = 0.0
            summary["suggested_amount_text"] = "$0.00"
            if action in BUY_ACTIONS:
                summary["top_action"] = f"{action} blocked"
    return summary


def normalized_report_context(context: dict[str, object]) -> dict[str, object]:
    normalized = dict(context)
    normalized["summary"] = normalized_summary(context)
    normalized["decision_safety"] = safety_review.decision_safety_object(normalized["summary"])
    return normalized


def decision_gate_detail(summary: dict[str, Any]) -> str:
    gate = as_dict(summary.get("decision_gate"))
    reasons = [text(reason) for reason in as_list(gate.get("reasons")) if text(reason)]
    return "; ".join(reasons) if reasons else text(gate.get("summary")) or "Passed"


def render_decision_safety_review(context: dict[str, object]) -> str:
    summary = normalized_summary(context)
    review = safety_review.decision_safety_review(summary)
    reasons = [text(reason) for reason in as_list(review.get("reasons")) if text(reason)]
    reason_items = "".join(f"<li>{html.escape(reason)}</li>" for reason in reasons) or "<li>None</li>"
    summary_text = text(review.get("summary")) or ("Passed the decision-safety gate." if review.get("safe_to_buy") else "Review required.")
    return (
        '<section class="decision-safety-review">'
        '<div class="section-title"><h2>Decision Safety Review</h2><span class="section-note">Top candidate gate</span></div>'
        '<div class="decision-safety-callout">'
        "<div>"
        f'<span class="label">{html.escape(text(review.get("status"), "Ready"))}</span>'
        f'<strong>{html.escape(text(review.get("review_label")))}</strong>'
        f'<p>{html.escape(summary_text)}</p>'
        "</div>"
        '<div class="decision-safety-facts">'
        f'<span><span class="label">Candidate</span><strong>{html.escape(text(review.get("symbol")) or "n/a")}</strong></span>'
        f'<span><span class="label">Action</span><strong>{html.escape(text(review.get("candidate_action")) or "n/a")}</strong></span>'
        f'<span><span class="label">Suggested amount</span><strong>{html.escape(text(review.get("suggested_amount_text")) or "n/a")}</strong></span>'
        "</div>"
        "</div>"
        '<div class="decision-safety-reasons"><span class="label">Blocked reasons</span>'
        f"<ul>{reason_items}</ul></div>"
        "</section>"
    )


def top_recommendation(context: dict[str, object], summary: dict[str, Any]) -> dict[str, Any]:
    top_symbol = text(summary.get("top_symbol"))
    for item in recommendations(context):
        if text(item.get("symbol")) == top_symbol:
            return item
    return recommendations(context)[0] if recommendations(context) else {}


def matching_table_rows(
    table: dict[str, Any],
    symbol: str,
    symbol_headers: list[str] | None = None,
    limit: int = 3,
) -> tuple[list[str], list[list[object]]]:
    headers = [text(header) for header in as_list(table.get("headers"))]
    rows = [as_list(row) for row in as_list(table.get("rows"))]
    if not headers or not rows:
        return headers, []
    candidates = symbol_headers or ["Symbol", "Ticker"]
    lookup = column_lookup(headers)
    symbol_index = next((lookup.get(candidate.lower()) for candidate in candidates if candidate.lower() in lookup), None)
    if symbol_index is None:
        return headers, rows[:limit]
    matched = [row for row in rows if symbol_index < len(row) and plain_text(row[symbol_index]) == symbol]
    return headers, (matched or rows)[:limit]


def first_row_value(headers: list[str], rows: list[list[object]], candidates: list[str], default: str = "") -> str:
    if not rows:
        return default
    return plain_text(row_cell(headers, rows[0], candidates)) or default


def score_review_text(context: dict[str, object], summary: dict[str, Any]) -> str:
    top = top_recommendation(context, summary)
    explanation = as_dict(top.get("score_explanation"))
    drivers = as_list(explanation.get("top_drivers"))
    if drivers:
        labels = []
        for driver in drivers[:3]:
            item = as_dict(driver)
            label = text(item.get("label") or item.get("key"), "Driver")
            points = item.get("points")
            points_text = f" {float(points):+.1f}" if isinstance(points, (int, float)) else ""
            labels.append(f"{label}{points_text}".strip())
        return "; ".join(labels)

    headers, rows = matching_table_rows(as_dict(context.get("score_movement")), text(summary.get("top_symbol")), limit=1)
    top_driver = first_row_value(headers, rows, ["Top Driver"])
    final_score = first_row_value(headers, rows, ["Final"])
    if top_driver:
        return f"{top_driver}" + (f" Final score {final_score}." if final_score else "")
    return text(top.get("score_breakdown") or summary.get("top_notes"), "No score driver detail available.")


def score_detail_html(context: dict[str, object], summary: dict[str, Any]) -> str:
    top = top_recommendation(context, summary)
    explanation = as_dict(top.get("score_explanation"))
    components = as_list(explanation.get("component_details"))
    if components:
        rows = [
            [
                as_dict(component).get("label", ""),
                as_dict(component).get("raw", ""),
                as_dict(component).get("points", ""),
                as_dict(component).get("description", ""),
            ]
            for component in components
        ]
        return html_table(["Component", "Raw", "Points", "Explanation"], rows, "compact-table")
    headers, rows = matching_table_rows(as_dict(context.get("score_movement")), text(summary.get("top_symbol")), limit=3)
    return html_table(headers, rows, "compact-table") if rows else "<p>No score explainability rows available.</p>"


def target_review_text(context: dict[str, object], summary: dict[str, Any]) -> str:
    target_drilldowns = as_dict(context.get("target_drilldowns"))
    top = as_dict(target_drilldowns.get("top_candidate"))
    if top:
        return (
            f"{text(top.get('blend_label'), text(summary.get('data_status'), 'Target review'))}; "
            f"{text(top.get('confidence'), text(summary.get('confidence'), 'n/a'))} confidence; "
            f"{text(top.get('target_price_text'), text(summary.get('target_text'), 'n/a'))}"
        )
    headers, rows = matching_table_rows(queue(context, "source_drilldown"), text(summary.get("top_symbol")), limit=1)
    analyst_targets = first_row_value(headers, rows, ["Analyst Targets"])
    all_targets = first_row_value(headers, rows, ["All Targets"])
    if rows:
        return f"{text(summary.get('confidence'), 'n/a')} confidence; {text(summary.get('data_status'), 'n/a')}; {analyst_targets or '0'} analyst / {all_targets or '0'} total targets"
    return f"{text(summary.get('confidence'), 'n/a')} confidence; {text(summary.get('data_status'), 'n/a')}; {text(summary.get('target_text'), 'n/a')}"


def target_detail_html(context: dict[str, object], summary: dict[str, Any]) -> str:
    target_drilldowns = as_dict(context.get("target_drilldowns"))
    top = as_dict(target_drilldowns.get("top_candidate"))
    source_rows = []
    for row in as_list(top.get("sources")):
        source = as_dict(row)
        source_rows.append(
            [
                source.get("target_type", ""),
                source.get("source_name", ""),
                source.get("source_type", ""),
                source.get("target_price_text", ""),
                source.get("range_text", "n/a"),
                source.get("as_of_date", ""),
                source.get("freshness", ""),
                source.get("confidence", ""),
                source.get("notes", ""),
            ]
        )
    if source_rows:
        return html_table(
            ["Type", "Source", "Source Type", "Target", "Range", "As Of", "Freshness", "Confidence", "Notes"],
            source_rows,
            "compact-table",
        )
    headers, rows = matching_table_rows(queue(context, "source_drilldown"), text(summary.get("top_symbol")), limit=3)
    return html_table(headers, rows, "compact-table") if rows else "<p>No target source drilldown rows available.</p>"


def provider_gap_review_text(context: dict[str, object], summary: dict[str, Any]) -> str:
    provider_gap_review = as_dict(context.get("provider_gap_review") or as_dict(context.get("source_health")).get("provider_gap_review"))
    gap_summary = as_dict(provider_gap_review.get("summary"))
    if gap_summary:
        affected = "affected" if gap_summary.get("top_candidate_affected") else "not directly affected"
        return f"{text(gap_summary.get('total'), '0')} active gap(s); top candidate {affected}."
    headers, rows = matching_table_rows(as_dict(as_dict(context.get("source_health")).get("provider_blockers")), text(summary.get("top_symbol")), limit=1)
    if rows:
        provider = first_row_value(headers, rows, ["Provider"], "Provider")
        cause = first_row_value(headers, rows, ["Likely Cause", "Latest Detail"], "needs review")
        return f"{provider}: {cause}"
    return "No active provider blockers for the top candidate."


def provider_gap_review_count(context: dict[str, object], summary: dict[str, Any]) -> str:
    provider_gap_review = as_dict(context.get("provider_gap_review") or as_dict(context.get("source_health")).get("provider_gap_review"))
    gap_summary = as_dict(provider_gap_review.get("summary"))
    if gap_summary:
        return text(gap_summary.get("total"), "0")
    _, rows = matching_table_rows(as_dict(as_dict(context.get("source_health")).get("provider_blockers")), text(summary.get("top_symbol")), limit=99)
    return text(len(rows), "0")


def provider_gap_detail_html(context: dict[str, object], summary: dict[str, Any]) -> str:
    provider_gap_review = as_dict(context.get("provider_gap_review") or as_dict(context.get("source_health")).get("provider_gap_review"))
    if provider_gap_review:
        return html_table(as_list(provider_gap_review.get("headers")), as_list(provider_gap_review.get("rows")), "compact-table")
    headers, rows = matching_table_rows(as_dict(as_dict(context.get("source_health")).get("provider_blockers")), text(summary.get("top_symbol")), limit=4)
    return html_table(headers, rows, "compact-table") if rows else "<p>No active provider blockers for the top candidate.</p>"


def render_daily_decision_review(context: dict[str, object]) -> str:
    summary = normalized_summary(context)
    gate = as_dict(summary.get("decision_gate"))
    candidate_action = text(gate.get("candidate_action") or summary.get("top_action")).replace(" blocked", "")
    gate_status = text(gate.get("status"), "Ready")
    cards = [
        ("Decision safety", gate_status, decision_gate_detail(summary)),
        ("Score explainability", text(summary.get("top_score"), "n/a"), score_review_text(context, summary)),
        ("Target confidence", text(summary.get("confidence"), "n/a"), target_review_text(context, summary)),
        ("Provider gaps", provider_gap_review_count(context, summary), provider_gap_review_text(context, summary)),
    ]
    card_html = "".join(
        '<div class="daily-review-card">'
        f'<span class="label">{html.escape(label)}</span>'
        f'<strong>{html.escape(value)}</strong>'
        f'<p>{html.escape(detail)}</p>'
        "</div>"
        for label, value, detail in cards
    )
    return (
        '<section class="daily-decision-review">'
        '<div class="section-title"><h2>Daily Decision Review</h2><span class="section-note">Decision first; details on demand</span></div>'
        '<div class="daily-review-lead">'
        f'<div><span class="label">{html.escape(text(summary.get("recommendation_label"), "Top candidate"))}</span>'
        f'<strong>{html.escape(text(summary.get("top_symbol")))} · {html.escape(candidate_action or text(summary.get("top_action")))}</strong>'
        f'<p>{html.escape(text(summary.get("top_company") or summary.get("top_notes")))}</p></div>'
        f'<div><span class="label">{html.escape(text(summary.get("amount_label"), "Buy capacity"))}</span>'
        f'<strong>{html.escape(text(summary.get("suggested_amount_text"), money(summary.get("suggested_amount"))))}</strong>'
        f'<p>{html.escape(text(summary.get("target_text"), money(summary.get("target_price"))))} · {html.escape(text(summary.get("upside_text"), pct(summary.get("upside_pct"))))}</p></div>'
        "</div>"
        f'<div class="daily-review-grid">{card_html}</div>'
        '<div class="daily-review-details">'
        '<details><summary>Score drivers</summary>'
        f"{score_detail_html(context, summary)}</details>"
        '<details><summary>Target source drilldown</summary>'
        f"{target_detail_html(context, summary)}</details>"
        '<details><summary>Provider gap review</summary>'
        f"{provider_gap_detail_html(context, summary)}</details>"
        "</div>"
        "</section>"
    )


def decision_safety_markdown_lines(summary: dict[str, Any]) -> list[str]:
    review = safety_review.decision_safety_review(summary)
    return [
        "## Decision Safety Review",
        "",
        f"- Review state: **{review.get('review_label', '')}**",
        f"- Status: **{review.get('status', 'Ready')}**",
        f"- Candidate action: **{review.get('candidate_action', '') or 'n/a'}**",
        f"- Suggested amount: **{review.get('suggested_amount_text', '') or 'n/a'}**",
        f"- Summary: {review.get('summary', '') or 'Passed'}",
        f"- Blocked reasons: {safety_review.reasons_text(review)}",
        "",
    ]


def daily_decision_review_markdown_lines(context: dict[str, object]) -> list[str]:
    summary = normalized_summary(context)
    gate = as_dict(summary.get("decision_gate"))
    candidate_action = text(gate.get("candidate_action") or summary.get("top_action")).replace(" blocked", "")
    return [
        "## Daily Decision Review",
        "",
        f"- Candidate: **{summary.get('top_symbol', '')} - {summary.get('top_company', '')}**",
        f"- Candidate action: **{candidate_action or summary.get('top_action', '')}**",
        f"- Decision safety: **{gate.get('status', 'Ready')}** - {decision_gate_detail(summary)}",
        f"- Score drivers: **{summary.get('top_score', '')}/100** - {score_review_text(context, summary)}",
        f"- Target confidence: **{summary.get('confidence', '')}** - {target_review_text(context, summary)}",
        f"- Provider gap review: {provider_gap_review_text(context, summary)}",
        "",
    ]


def render_data_reliability_review(context: dict[str, object]) -> str:
    review = build_data_reliability_review(context)
    cards = []
    for card in as_list(review.get("cards")):
        item = as_dict(card)
        cards.append(
            '<div class="data-review-card">'
            f'<span class="label">{html.escape(text(item.get("label")))}</span>'
            f'<strong>{html.escape(text(item.get("value"), "n/a"))}</strong>'
            f'<p>{html.escape(text(item.get("detail")))}</p>'
            "</div>"
        )
    details = [
        ("Provider gap status", "What is missing, blocked, or rate-limited by provider.", as_dict(review.get("provider_gap_status"))),
        ("Source health rollups", "Health counts and source usefulness signals.", as_dict(review.get("source_health_rollups"))),
        ("SEC coverage", "Primary-source filing and companyfacts coverage where available.", as_dict(review.get("sec_coverage"))),
        ("Official IR coverage", "Company investor-relations evidence coverage where available.", as_dict(review.get("official_ir_coverage"))),
        ("Source usefulness/noise", "Useful, low-relevance, noisy, or low-confidence source evidence.", as_dict(review.get("source_usefulness"))),
        ("Refresh plan", "What should refresh next and why.", as_dict(review.get("refresh_plan"))),
        ("Backfill needs", "Historical source windows that still need coverage.", as_dict(review.get("backfill"))),
    ]
    detail_html = "".join(
        "<details>"
        f"<summary>{html.escape(title)}</summary>"
        f'<p class="section-note">{html.escape(note)}</p>'
        f'{html_table(as_list(table.get("headers")), as_list(table.get("rows")), "compact-table")}'
        "</details>"
        for title, note, table in details
    )
    return (
        '<section class="data-reliability-review">'
        '<div class="section-title"><h2>Data Reliability Review</h2><span class="section-note">Missing, stale, blocked, useful, and next-refresh signals</span></div>'
        f'<div class="data-review-grid">{"".join(cards)}</div>'
        f'<div class="data-review-details">{detail_html}</div>'
        "</section>"
    )


def data_reliability_review_markdown_lines(context: dict[str, object]) -> list[str]:
    review = build_data_reliability_review(context)
    lines = [
        "## Data Reliability Review",
        "",
    ]
    for card in as_list(review.get("cards")):
        item = as_dict(card)
        lines.append(f"- {item.get('label', '')}: **{item.get('value', '')}** - {item.get('detail', '')}")
    lines.append("")
    for title, key, empty in (
        ("Provider Gap Status", "provider_gap_status", "No provider gaps currently visible."),
        ("Source Health Rollups", "source_health_rollups", "No source-health rollups available."),
        ("SEC Coverage", "sec_coverage", "No SEC coverage rows available."),
        ("Official IR Coverage", "official_ir_coverage", "No official IR coverage rows available."),
        ("Source Usefulness / Noise", "source_usefulness", "No source usefulness rows available."),
        ("Refresh Plan", "refresh_plan", "No refresh plan rows available."),
        ("Backfill Needs", "backfill", "No backfill rows available."),
    ):
        append_table_section(lines, title, as_dict(review.get(key)), empty)
    return lines


def _coherence_cards_html(cards: object) -> str:
    rendered = []
    for card in as_list(cards):
        item = as_dict(card)
        rendered.append(
            '<div class="coherence-card">'
            f'<span class="label">{html.escape(text(item.get("label")))}</span>'
            f'<strong>{html.escape(text(item.get("value"), "n/a"))}</strong>'
            f'<p>{html.escape(text(item.get("detail")))}</p>'
            "</div>"
        )
    return "".join(rendered)


def product_review_cards(context: dict[str, object]) -> list[dict[str, object]]:
    review_path = build_review_path(context)
    cards: list[dict[str, object]] = []
    for card in as_list(review_path.get("cards")):
        item = dict(as_dict(card))
        label = text(item.get("label"))
        if label.startswith("5. Learning"):
            item["label"] = "5. Learning review"
            item["value"] = "Review-only"
            item["detail"] = "Learning loops remain secondary; Long-Term Capital Deployment Review owns the Wave 7 buy/add context."
        cards.append(item)
    return cards


def render_product_review_path(context: dict[str, object]) -> str:
    return (
        '<section class="product-review-path">'
        '<div class="section-title"><h2>Product Review Path</h2>'
        '<span class="section-note">Current decision first; audit, synthesis, and learning stay non-impacting</span></div>'
        f'<div class="coherence-grid">{_coherence_cards_html(product_review_cards(context))}</div>'
        "</section>"
    )


def product_review_path_markdown_lines(context: dict[str, object]) -> list[str]:
    lines = ["## Product Review Path", ""]
    for card in product_review_cards(context):
        item = as_dict(card)
        lines.append(f"- {item.get('label', '')}: **{item.get('value', '')}** - {item.get('detail', '')}")
    lines.append("")
    return lines


def _candidate_review_html(candidate: dict[str, object], empty: str) -> str:
    if not candidate.get("available"):
        return f"<p>{html.escape(empty)}</p>"
    rationale = as_list(candidate.get("rationale"))
    blockers = as_list(candidate.get("blockers"))
    rationale_html = "".join(f"<li>{html.escape(text(item))}</li>" for item in rationale) or "<li>No rationale available yet.</li>"
    blockers_html = "".join(f"<li>{html.escape(text(item))}</li>" for item in blockers) or "<li>No active blockers listed.</li>"
    return (
        '<div class="action-detail-card">'
        f'<p><strong>{html.escape(text(candidate.get("label")))}:</strong> '
        f'{html.escape(text(candidate.get("symbol")))} · {html.escape(text(candidate.get("action")))} · '
        f'{html.escape(text(candidate.get("decision_safety")))} safety · '
        f'{html.escape(text(candidate.get("target_confidence")))} confidence · '
        f'{html.escape(text(candidate.get("suggested_amount")))} suggested.</p>'
        f"<p><strong>Key rationale:</strong></p><ul>{rationale_html}</ul>"
        f"<p><strong>Key blockers:</strong></p><ul>{blockers_html}</ul>"
        "</div>"
    )


def render_long_term_capital_deployment(context: dict[str, object]) -> str:
    review = build_long_term_capital_deployment_view(context)
    primary = as_dict(review.get("primary"))
    fallback = as_dict(review.get("fallback"))
    holding_health = as_dict(review.get("holding_health"))
    health_summary = as_dict(holding_health.get("summary"))
    health_rows = [
        [
            row.get("symbol", ""),
            row.get("health_label", ""),
            row.get("confidence", ""),
            "; ".join(str(item) for item in as_list(row.get("review_actions"))[:2]),
        ]
        for row in as_list(holding_health.get("top_review_rows"))
        if isinstance(row, dict)
    ]
    health_table = html_table(
        ["Symbol", "Health", "Confidence", "Review Action"],
        health_rows,
        "compact-table",
    ) if health_rows else ""
    blockers = as_list(review.get("blockers"))
    blocker_html = "".join(f"<li>{html.escape(text(item))}</li>" for item in blockers) or "<li>No active blockers listed for the displayed long-term add review.</li>"
    health_counts = ", ".join(f"{key}: {value}" for key, value in health_summary.items() if value) or "No flagged holding-health buckets."
    fallback_empty = text(review.get("hold_capacity_message")) or "No fallback candidate is needed or available yet."
    return (
        '<section class="capital-deployment-review">'
        '<div class="section-title"><h2>Long-Term Capital Deployment Review</h2>'
        '<span class="section-note">Review-only answer to today\'s long-term buy/add question</span></div>'
        f'<p><strong>{html.escape(text(review.get("question")))}</strong></p>'
        f'<p class="section-note">{html.escape(text(review.get("note")))}</p>'
        f'<div class="coherence-grid">{_coherence_cards_html(review.get("cards"))}</div>'
        '<div class="table-pair">'
        f'<section><h3>Primary Add Review</h3>{_candidate_review_html(primary, "No primary long-term add candidate is available yet.")}</section>'
        f'<section><h3>Fallback / Hold Review</h3>{_candidate_review_html(fallback, fallback_empty)}</section>'
        "</div>"
        f'<section><h3>Key Blockers</h3><ul>{blocker_html}</ul></section>'
        f'<section><h3>Long-Term Holding Health</h3><p>{html.escape(text(holding_health.get("message")))}</p><p class="section-note">{html.escape(health_counts)}</p>{health_table}</section>'
        f'<p class="section-note">{html.escape(text(review.get("ai_synthesis_note")))}</p>'
        "</section>"
    )


def long_term_capital_deployment_markdown_lines(context: dict[str, object]) -> list[str]:
    review = build_long_term_capital_deployment_view(context)
    primary = as_dict(review.get("primary"))
    fallback = as_dict(review.get("fallback"))
    holding_health = as_dict(review.get("holding_health"))
    lines = [
        "## Long-Term Capital Deployment Review",
        "",
        f"**{review.get('question', 'What should I buy/add today for long-term holdings?')}**",
        "",
        text(review.get("note"), "Review-only and recommendation-only; official recommendations are unchanged."),
        "",
    ]
    for card in as_list(review.get("cards")):
        item = as_dict(card)
        lines.append(f"- {item.get('label', '')}: **{item.get('value', '')}** - {item.get('detail', '')}")
    lines.extend(["", "### Primary Add Review", ""])
    if primary.get("available"):
        lines.extend(
            [
                f"- Candidate: **{primary.get('symbol', '')} {primary.get('action', '')}**",
                f"- Decision safety: **{primary.get('decision_safety', '')}**",
                f"- Target confidence: **{primary.get('target_confidence', '')}**",
                f"- Suggested/deployable amount: **{primary.get('suggested_amount', '')}**",
            ]
        )
        for item in as_list(primary.get("rationale")):
            lines.append(f"- Rationale: {item}")
    else:
        lines.append("No primary long-term add candidate is available yet.")
    lines.extend(["", "### Fallback / Hold Review", ""])
    if fallback.get("available"):
        lines.extend(
            [
                f"- Fallback candidate: **{fallback.get('symbol', '')} {fallback.get('action', '')}**",
                f"- Decision safety: **{fallback.get('decision_safety', '')}**",
                f"- Target confidence: **{fallback.get('target_confidence', '')}**",
            ]
        )
    else:
        lines.append(text(review.get("hold_capacity_message")) or "No fallback candidate is needed or available yet.")
    blockers = as_list(review.get("blockers"))
    lines.extend(["", "### Key Blockers", ""])
    if blockers:
        lines.extend(f"- {item}" for item in blockers)
    else:
        lines.append("No active blockers listed for the displayed long-term add review.")
    lines.extend(
        [
            "",
            "### Long-Term Holding Health",
            "",
            text(holding_health.get("message"), "No long-term holding health rows are available yet."),
            "",
            text(review.get("ai_synthesis_note"), "AI synthesis is explanatory only."),
            "",
        ]
    )
    return lines


def render_review_table(table: dict[str, object], class_name: str = "compact-table") -> str:
    rows = as_list(table.get("rows"))
    if not rows:
        return f"<p>{html.escape(text(table.get('empty_state'), 'No rows available.'))}</p>"
    return html_table(as_list(table.get("headers")), rows, class_name)


def render_earnings_review(context: dict[str, object]) -> str:
    review = build_earnings_review_view(context)
    signals = as_dict(review.get("signals"))
    categories = as_dict(signals.get("categories"))
    signal_text = ", ".join(f"{key}: {value}" for key, value in categories.items()) or "No earnings signals available yet."
    return (
        '<section class="earnings-review">'
        '<div class="section-title"><h2>Earnings Review</h2>'
        '<span class="section-note">Event-driven review-only opportunities; official recommendations stay unchanged</span></div>'
        f'<p class="section-note">{html.escape(text(review.get("note")))}</p>'
        f'<div class="coherence-grid">{_coherence_cards_html(review.get("cards"))}</div>'
        '<div class="table-pair">'
        f'<section><h3>Upcoming Earnings Queue</h3>{render_review_table(as_dict(review.get("upcoming")))}</section>'
        f'<section><h3>Recent Earnings Queue</h3>{render_review_table(as_dict(review.get("recent")))}</section>'
        "</div>"
        '<div class="table-pair">'
        f'<section><h3>Pre-Earnings Setup Review</h3>{render_review_table(as_dict(review.get("pre")))}</section>'
        f'<section><h3>Post-Earnings Reaction Review</h3>{render_review_table(as_dict(review.get("post")))}</section>'
        "</div>"
        f'<section><h3>Earnings Signal Summary</h3><p class="section-note">{html.escape(signal_text)}</p></section>'
        f'<section><h3>Earnings Provider/Data Gaps</h3>{render_review_table(as_dict(review.get("gaps")))}</section>'
        "</section>"
    )


def earnings_review_markdown_lines(context: dict[str, object]) -> list[str]:
    review = build_earnings_review_view(context)
    signals = as_dict(review.get("signals"))
    categories = as_dict(signals.get("categories"))
    lines = [
        "## Earnings Review",
        "",
        text(review.get("note"), "Recommendation-only earnings review; official recommendation outputs are unchanged."),
        "",
    ]
    for card in as_list(review.get("cards")):
        item = as_dict(card)
        lines.append(f"- {item.get('label', '')}: **{item.get('value', '')}** - {item.get('detail', '')}")
    lines.append("")
    for title, key in (
        ("Upcoming Earnings Queue", "upcoming"),
        ("Recent Earnings Queue", "recent"),
        ("Pre-Earnings Setup Review", "pre"),
        ("Post-Earnings Reaction Review", "post"),
        ("Earnings Provider/Data Gaps", "gaps"),
    ):
        append_table_section(lines, title, as_dict(review.get(key)), text(as_dict(review.get(key)).get("empty_state"), "No rows available."))
    lines.extend(
        [
            "### Earnings Signal Summary",
            "",
            f"- Overall direction: **{signals.get('overall_direction', 'missing')}**",
            f"- Signal rows: **{signals.get('signal_count', 0)}**",
        ]
    )
    for key, value in categories.items():
        lines.append(f"- {key}: **{value}**")
    lines.append("")
    return lines


def render_tactical_review(context: dict[str, object]) -> str:
    review = build_tactical_review_view(context)
    return (
        '<section class="tactical-review">'
        '<div class="section-title"><h2>Tactical Review</h2>'
        '<span class="section-note">Separate review-only setup context; long-term decisions stay first</span></div>'
        f'<p class="section-note">{html.escape(text(review.get("note")))}</p>'
        f'<div class="coherence-grid">{_coherence_cards_html(review.get("cards"))}</div>'
        '<div class="table-pair">'
        f'<section><h3>Tactical Watchlist Queue</h3>{render_review_table(as_dict(review.get("watchlist")))}</section>'
        f'<section><h3>Tactical Risk Zones</h3>{render_review_table(as_dict(review.get("risk_zones")))}</section>'
        "</div>"
        '<div class="table-pair">'
        f'<section><h3>Tactical Provider/Data Gaps</h3>{render_review_table(as_dict(review.get("gaps")))}</section>'
        f'<section><h3>Earnings/Event Context</h3>{render_review_table(as_dict(review.get("events")))}</section>'
        "</div>"
        f'<section><h3>Tactical Outcome History</h3>{render_review_table(as_dict(review.get("outcomes")))}</section>'
        "</section>"
    )


def tactical_review_markdown_lines(context: dict[str, object]) -> list[str]:
    review = build_tactical_review_view(context)
    lines = [
        "## Tactical Review",
        "",
        text(review.get("note"), "Recommendation-only tactical review; official recommendations are unchanged."),
        "",
    ]
    for card in as_list(review.get("cards")):
        item = as_dict(card)
        lines.append(f"- {item.get('label', '')}: **{item.get('value', '')}** - {item.get('detail', '')}")
    lines.append("")
    for title, key in (
        ("Tactical Watchlist Queue", "watchlist"),
        ("Tactical Risk Zones", "risk_zones"),
        ("Tactical Provider/Data Gaps", "gaps"),
        ("Earnings/Event Context", "events"),
        ("Tactical Outcome History", "outcomes"),
    ):
        append_table_section(lines, title, as_dict(review.get(key)), text(as_dict(review.get(key)).get("empty_state"), "No rows available."))
    return lines


def render_model_evaluation(context: dict[str, object]) -> str:
    review = build_model_evaluation_view(context)
    trust = as_dict(review.get("trust"))
    trust_detail = (
        f'{html.escape(text(trust.get("trust_level"), "observe"))} · '
        f'{html.escape(text(trust.get("confidence"), "low"))} confidence · review-only'
        if trust
        else "Trust score not available yet."
    )
    return (
        '<section class="model-evaluation-review">'
        '<div class="section-title"><h2>Model Evaluation</h2>'
        '<span class="section-note">Review-only model learning; official recommendations stay unchanged</span></div>'
        f'<p class="section-note">{html.escape(text(review.get("note")))}</p>'
        f'<div class="coherence-grid">{_coherence_cards_html(review.get("cards"))}</div>'
        f'<section><h3>Model Trust Score V1</h3><p class="section-note">{trust_detail}</p></section>'
        '<div class="table-pair">'
        f'<section><h3>Prediction Records</h3>{render_review_table(as_dict(review.get("predictions")))}</section>'
        f'<section><h3>Model Registry</h3>{render_review_table(as_dict(review.get("registry")))}</section>'
        "</div>"
        '<div class="table-pair">'
        f'<section><h3>Recommendation Backtest</h3>{render_review_table(as_dict(review.get("backtest")))}</section>'
        f'<section><h3>Benchmark Comparison</h3>{render_review_table(as_dict(review.get("benchmark")))}</section>'
        "</div>"
        '<div class="table-pair">'
        f'<section><h3>AI Thesis Evaluation</h3>{render_review_table(as_dict(review.get("ai")))}</section>'
        f'<section><h3>Model Evaluation Warnings</h3>{render_review_table(as_dict(review.get("warnings")))}</section>'
        "</div>"
        "</section>"
    )


def model_evaluation_markdown_lines(context: dict[str, object]) -> list[str]:
    review = build_model_evaluation_view(context)
    trust = as_dict(review.get("trust"))
    lines = [
        "## Model Evaluation",
        "",
        text(review.get("note"), "Recommendation-only model evaluation; official recommendations are unchanged."),
        "",
    ]
    for card in as_list(review.get("cards")):
        item = as_dict(card)
        lines.append(f"- {item.get('label', '')}: **{item.get('value', '')}** - {item.get('detail', '')}")
    lines.extend(
        [
            "",
            "### Model Trust Score V1",
            "",
            f"- Trust score: **{trust.get('trust_score', 'n/a')}**",
            f"- Trust level: **{trust.get('trust_level', 'observe')}**",
            f"- Confidence: **{trust.get('confidence', 'low')}**",
            f"- Review-only: **{trust.get('review_only', True)}**",
            f"- No model promotion: **{trust.get('no_model_promotion', True)}**",
            "",
        ]
    )
    for title, key in (
        ("Prediction Records", "predictions"),
        ("Model Registry", "registry"),
        ("Recommendation Backtest", "backtest"),
        ("Benchmark Comparison", "benchmark"),
        ("AI Thesis Evaluation", "ai"),
        ("Model Evaluation Warnings", "warnings"),
    ):
        append_table_section(lines, title, as_dict(review.get(key)), text(as_dict(review.get(key)).get("empty_state"), "No rows available."))
    return lines


def alert_count_table(rows: object) -> dict[str, object]:
    items = [as_dict(row) for row in as_list(rows)]
    return {
        "headers": ["Group", "Count"],
        "rows": [[item.get("label", ""), item.get("count", 0)] for item in items],
        "empty_state": "No alert counts are available.",
    }


def alert_top_priority_table(rows: object) -> dict[str, object]:
    items = [as_dict(row) for row in as_list(rows)]
    return {
        "headers": ["Priority", "Severity", "Area", "Symbol", "Status", "Why Review", "Review Action"],
        "rows": [
            [
                item.get("priority", ""),
                item.get("display_severity", item.get("severity", "")),
                text(item.get("review_area")).replace("_", " ").title(),
                item.get("symbol", ""),
                item.get("status", ""),
                item.get("why_review", ""),
                item.get("review_action", ""),
            ]
            for item in items
        ],
        "empty_state": "No active review alerts.",
    }


def alert_lifecycle_table(rows: object) -> dict[str, object]:
    items = [as_dict(row) for row in as_list(rows)]
    return {
        "headers": ["Lifecycle Field", "Value"],
        "rows": [[item.get("label", ""), item.get("value", "")] for item in items],
        "empty_state": "No alert lifecycle metadata is available.",
    }


def render_alerts_review(context: dict[str, object]) -> str:
    review = build_alerts_review_view(context)
    return (
        '<section class="alerts-review">'
        '<div class="section-title"><h2>Alerts And Review Triggers</h2>'
        '<span class="section-note">Review-only manual attention summary; official recommendations stay unchanged</span></div>'
        f'<p class="section-note">{html.escape(text(review.get("note")))}</p>'
        f'<div class="coherence-grid">{_coherence_cards_html(review.get("cards"))}</div>'
        '<div class="table-pair">'
        f'<section><h3>Top Priority Alerts</h3>{render_review_table(alert_top_priority_table(review.get("top_priority_alerts")))}</section>'
        f'<section><h3>Alert Lifecycle Metadata</h3>{render_review_table(alert_lifecycle_table(review.get("lifecycle_metadata")))}</section>'
        "</div>"
        '<div class="table-pair">'
        f'<section><h3>Alerts By Review Area</h3>{render_review_table(alert_count_table(review.get("alerts_by_review_area")))}</section>'
        f'<section><h3>Alerts By Severity</h3>{render_review_table(alert_count_table(review.get("alerts_by_severity")))}</section>'
        "</div>"
        f'<section><h3>Alerts By Status</h3>{render_review_table(alert_count_table(review.get("alerts_by_status")))}</section>'
        "</section>"
    )


def alerts_review_markdown_lines(context: dict[str, object]) -> list[str]:
    review = build_alerts_review_view(context)
    lines = [
        "## Alerts And Review Triggers",
        "",
        text(review.get("note"), "Review-only alert prompts; official recommendations stay unchanged."),
        "",
    ]
    for card in as_list(review.get("cards")):
        item = as_dict(card)
        lines.append(f"- {item.get('label', '')}: **{item.get('value', '')}** - {item.get('detail', '')}")
    lines.append("")
    for title, table in (
        ("Top Priority Alerts", alert_top_priority_table(review.get("top_priority_alerts"))),
        ("Alert Lifecycle Metadata", alert_lifecycle_table(review.get("lifecycle_metadata"))),
        ("Alerts By Review Area", alert_count_table(review.get("alerts_by_review_area"))),
        ("Alerts By Severity", alert_count_table(review.get("alerts_by_severity"))),
        ("Alerts By Status", alert_count_table(review.get("alerts_by_status"))),
    ):
        append_table_section(lines, title, table, text(table.get("empty_state"), "No rows available."))
    return lines


def learning_review_summary_value(section: dict[str, Any], *keys: str) -> object:
    summary = as_dict(section.get("summary"))
    for key in keys:
        if key in summary:
            return summary.get(key)
    return 0


def learning_review_card_detail(section: dict[str, Any], count: object, available: str, empty: str) -> str:
    if str(count) not in {"", "0", "0.0", "None"}:
        return available
    return text(section.get("empty_state"), empty)


def compact_learning_rows(rows: list[Any], fields: list[str], limit: int = 5) -> list[list[object]]:
    result: list[list[object]] = []
    for row in rows[:limit]:
        item = as_dict(row)
        result.append([item.get(field, "") for field in fields])
    return result


def render_learning_review_html(context: dict[str, object]) -> str:
    learning = as_dict(context.get("learning_review"))
    note = text(
        learning.get("note"),
        "Review-only learning outputs; these metrics do not change current recommendations, scores, targets, gates, allocation, or broker behavior.",
    )
    manual = as_dict(learning.get("manual_journal"))
    outcomes = as_dict(learning.get("recommendation_outcomes"))
    catalysts = as_dict(learning.get("catalyst_follow_through"))
    sources = as_dict(learning.get("source_usefulness"))
    safety = as_dict(learning.get("decision_safety_effectiveness"))

    manual_count = learning_review_summary_value(manual, "entry_count")
    outcome_count = learning_review_summary_value(outcomes, "outcome_count")
    catalyst_count = learning_review_summary_value(catalysts, "outcome_count")
    source_count = learning_review_summary_value(sources, "source_count")
    safety_count = learning_review_summary_value(safety, "row_count")
    cards = [
        (
            "Review-only learning",
            "No model impact",
            "Learning review stays separate from scores, targets, actions, gates, allocation, and broker behavior.",
        ),
        (
            "Manual actions",
            manual_count,
            learning_review_card_detail(manual, manual_count, "Manual decisions recorded for after-the-fact review.", "No manual journal entries recorded yet."),
        ),
        (
            "Recommendation outcomes",
            outcome_count,
            learning_review_card_detail(outcomes, outcome_count, "Prior recommendations have later outcome rows.", "Not enough recommendation outcome history yet."),
        ),
        (
            "Catalyst follow-through",
            catalyst_count,
            learning_review_card_detail(catalysts, catalyst_count, "Catalyst rows are available for follow-through review.", "No catalyst follow-through rows available yet."),
        ),
        (
            "Source usefulness",
            source_count,
            learning_review_card_detail(sources, source_count, "Source rows are available for usefulness/noise review.", "No source usefulness history available yet."),
        ),
        (
            "Decision safety",
            safety_count,
            learning_review_card_detail(safety, safety_count, "Decision-safety rows compare blocked and ready candidates.", "No decision-safety effectiveness history available yet."),
        ),
    ]
    card_html = "".join(
        '<div class="data-review-card">'
        f'<span class="label">{html.escape(label)}</span>'
        f'<strong>{html.escape(text(value))}</strong>'
        f'<p>{html.escape(detail)}</p>'
        "</div>"
        for label, value, detail in cards
    )
    sections = [
        (
            "What the app recommended",
            ["Symbol", "Report Date", "Action", "Outcome", "Move %"],
            compact_learning_rows(
                as_list(outcomes.get("top_outcomes")),
                ["symbol", "report_date", "original_action", "outcome_status", "percent_change"],
            ),
            "No recommendation outcome rows available yet.",
        ),
        (
            "What the user did manually",
            ["Date", "Symbol", "Action", "Amount", "Notes"],
            compact_learning_rows(
                as_list(manual.get("recent_actions")),
                ["decision_date", "symbol", "action_taken", "amount", "notes"],
            ),
            "No manual journal entries recorded yet.",
        ),
        (
            "What happened afterward",
            ["Symbol", "Window", "Outcome", "Later Price", "Move %"],
            compact_learning_rows(
                as_list(outcomes.get("top_outcomes")),
                ["symbol", "window_trading_days", "outcome_status", "later_price", "percent_change"],
            ),
            "Not enough outcome history yet.",
        ),
        (
            "Catalyst follow-through",
            ["Symbol", "Event", "Headline", "Outcome"],
            compact_learning_rows(
                as_list(catalysts.get("top_outcomes")),
                ["symbol", "event_type", "headline", "outcome_label"],
            ),
            "No catalyst rows available yet.",
        ),
        (
            "Source usefulness / noise",
            ["Source", "Label", "Evidence", "Feedback", "Latest Issue"],
            compact_learning_rows(
                as_list(sources.get("top_sources")),
                ["source_name", "label", "evidence_count", "feedback_delta", "latest_issue"],
            ),
            "No source usefulness history available yet.",
        ),
        (
            "Decision safety effectiveness",
            ["Symbol", "Gate", "Bucket", "Move %", "Assessment"],
            compact_learning_rows(
                as_list(safety.get("top_rows")),
                ["symbol", "decision_gate_status", "review_bucket", "later_price_movement_pct", "assessment"],
            ),
            "No decision-safety effectiveness rows available yet.",
        ),
    ]
    details = "".join(
        "<details>"
        f"<summary>{html.escape(title)}</summary>"
        f'{html_table(headers, rows, "compact-table") if rows else f"<p>{html.escape(empty)}</p>"}'
        "</details>"
        for title, headers, rows, empty in sections
    )
    return (
        '<section class="learning-review">'
        '<div class="section-title"><h2>Learning Review</h2><span class="section-note">Review-only outcomes and follow-through; no recommendation impact</span></div>'
        f'<p class="section-note">{html.escape(note)}</p>'
        f'<div class="data-review-grid">{card_html}</div>'
        f'<div class="data-review-details">{details}</div>'
        "</section>"
    )


def learning_review_markdown_lines(context: dict[str, object]) -> list[str]:
    learning = as_dict(context.get("learning_review"))
    manual = as_dict(learning.get("manual_journal"))
    outcomes = as_dict(learning.get("recommendation_outcomes"))
    catalysts = as_dict(learning.get("catalyst_follow_through"))
    sources = as_dict(learning.get("source_usefulness"))
    safety = as_dict(learning.get("decision_safety_effectiveness"))
    lines = [
        "## Learning Review",
        "",
        text(learning.get("note"), "Review-only learning outputs; these metrics do not change current recommendations, scores, targets, gates, allocation, or broker behavior."),
        "",
        "- Review-only learning: **No model impact** - Learning review stays separate from scores, targets, actions, gates, allocation, and broker behavior.",
        f"- What the app recommended: **{learning_review_summary_value(outcomes, 'outcome_count')}** outcome row(s).",
        f"- What the user did manually: **{learning_review_summary_value(manual, 'entry_count')}** journal entry row(s).",
        f"- Catalyst follow-through: **{learning_review_summary_value(catalysts, 'outcome_count')}** catalyst row(s).",
        f"- Source usefulness/noise: **{learning_review_summary_value(sources, 'source_count')}** source row(s).",
        f"- Decision safety: **{learning_review_summary_value(safety, 'row_count')}** effectiveness row(s).",
        "",
    ]
    append_table_section(
        lines,
        "Recent Manual Actions",
        {
            "headers": ["Date", "Symbol", "Action", "Amount", "Notes"],
            "rows": compact_learning_rows(as_list(manual.get("recent_actions")), ["decision_date", "symbol", "action_taken", "amount", "notes"]),
        },
        text(manual.get("empty_state"), "No manual journal entries recorded yet."),
    )
    append_table_section(
        lines,
        "Top Recommendation Outcomes",
        {
            "headers": ["Symbol", "Report Date", "Action", "Outcome", "Move %"],
            "rows": compact_learning_rows(as_list(outcomes.get("top_outcomes")), ["symbol", "report_date", "original_action", "outcome_status", "percent_change"]),
        },
        text(outcomes.get("empty_state"), "Not enough recommendation outcome history yet."),
    )
    append_table_section(
        lines,
        "Catalyst Follow-Through",
        {
            "headers": ["Symbol", "Event", "Headline", "Outcome"],
            "rows": compact_learning_rows(as_list(catalysts.get("top_outcomes")), ["symbol", "event_type", "headline", "outcome_label"]),
        },
        text(catalysts.get("empty_state"), "No catalyst rows available yet."),
    )
    append_table_section(
        lines,
        "Source Usefulness / Noise",
        {
            "headers": ["Source", "Label", "Evidence", "Feedback", "Latest Issue"],
            "rows": compact_learning_rows(as_list(sources.get("top_sources")), ["source_name", "label", "evidence_count", "feedback_delta", "latest_issue"]),
        },
        text(sources.get("empty_state"), "No source usefulness history available yet."),
    )
    append_table_section(
        lines,
        "Decision Safety Effectiveness",
        {
            "headers": ["Symbol", "Gate", "Bucket", "Move %", "Assessment"],
            "rows": compact_learning_rows(as_list(safety.get("top_rows")), ["symbol", "decision_gate_status", "review_bucket", "later_price_movement_pct", "assessment"]),
        },
        text(safety.get("empty_state"), "No decision-safety effectiveness rows available yet."),
    )
    return lines


def render_capital_deployment_prep(context: dict[str, object]) -> str:
    prep = build_capital_deployment_prep(context)
    table = as_dict(prep.get("table"))
    return (
        '<section class="capital-deployment-prep">'
        '<div class="section-title"><h2>Wave 7 Capital Deployment Prep</h2>'
        '<span class="section-note">Manual capital context before broker expansion; no order previews</span></div>'
        f'<div class="coherence-grid">{_coherence_cards_html(prep.get("cards"))}</div>'
        f'{html_table(as_list(table.get("headers")), as_list(table.get("rows")), "compact-table")}'
        "</section>"
    )


def capital_deployment_prep_markdown_lines(context: dict[str, object]) -> list[str]:
    prep = build_capital_deployment_prep(context)
    lines = [
        "## Wave 7 Capital Deployment Prep",
        "",
        "Manual capital context before broker expansion; no order previews.",
        "",
    ]
    for card in as_list(prep.get("cards")):
        item = as_dict(card)
        lines.append(f"- {item.get('label', '')}: **{item.get('value', '')}** - {item.get('detail', '')}")
    lines.append("")
    append_table_section(
        lines,
        "Capital Deployment Prep Surfaces",
        as_dict(prep.get("table")),
        "No capital deployment prep surfaces available.",
    )
    return lines


def render_dashboard_html(context: dict[str, object]) -> str:
    metadata = as_dict(context.get("metadata"))
    summary = normalized_summary(context)
    reliability = as_dict(context.get("reliability"))
    price_counts = as_dict(reliability.get("price_counts"))
    source_health = as_dict(context.get("source_health"))
    provider_gap_review = as_dict(context.get("provider_gap_review"))
    source_quality = as_dict(context.get("source_quality"))
    source_depth = as_dict(context.get("source_depth"))
    ingestion_run_plan = as_dict(context.get("ingestion_run_plan"))
    ingestion_backfill = as_dict(context.get("ingestion_backfill"))
    evidence_events = as_dict(context.get("evidence_events"))
    evidence_review_queue = as_dict(context.get("evidence_review_queue"))
    synthesis_readiness = as_dict(context.get("synthesis_readiness"))
    source_summary = as_dict(source_health.get("summary") or reliability.get("source_health"))
    holdings = as_dict(context.get("holdings"))
    data_ingestion = as_dict(context.get("data_ingestion"))
    feedback = as_dict(context.get("feedback"))
    artifacts = artifact_names(context)
    decision_gate = as_dict(summary.get("decision_gate"))

    action_queue = queue(context, "action_queue")
    full_universe = queue(context, "full_universe")
    next_day = queue(context, "next_day")
    source_drilldown = queue(context, "source_drilldown")
    data_gaps = queue(context, "data_gaps")
    verification_queue = queue(context, "verification")

    source_health_alerts = as_dict(source_health.get("alerts"))
    source_issue_groups = as_dict(source_health.get("issue_groups"))
    provider_blockers = as_dict(source_health.get("provider_blockers"))
    score_changes = as_dict(context.get("score_changes"))
    score_movement = as_dict(context.get("score_movement"))
    trend_insights = as_dict(context.get("trend_insights"))
    insight_themes = as_dict(context.get("insight_themes"))
    decision_briefs = as_dict(context.get("decision_briefs"))
    decision_history = as_dict(context.get("decision_insight_history"))
    verify_next = as_dict(context.get("verification"))

    source_options = "\n".join(
        f'<option value="{html.escape(text(source))}">{html.escape(text(source))}</option>'
        for source in as_list(feedback.get("source_options"))
    )
    fallback_symbol = summary_value(context, "top_symbol", "SYMBOL")

    dashboard_css = """
    :root { color-scheme: light; --bg:#f6f7f9; --panel:#fff; --text:#18202a; --muted:#5e6a78; --line:#d8dde5; --blue:#1d5fd0; --green:#137a49; --amber:#9a6100; --red:#b42318; }
    * { box-sizing: border-box; }
    body { margin:0; background:var(--bg); color:var(--text); font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; line-height:1.45; }
    header { background:#111827; color:white; padding:18px 24px; }
    main { max-width:1280px; margin:0 auto; padding:16px 20px 24px; }
    h1,h2,h3 { margin:0; } h1 { font-size:24px; } h2 { font-size:17px; margin-bottom:10px; } h3 { font-size:15px; }
    .subtle { color:#cbd5e1; margin-top:6px; }
    .summary { display:grid; grid-template-columns:minmax(300px,1.6fr) repeat(5,minmax(112px,1fr)); gap:10px; margin:14px 0; }
    .metric, section { background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:14px; }
    .metric strong { display:block; font-size:22px; margin-top:4px; }
    .label { color:var(--muted); font-size:12px; font-weight:700; text-transform:uppercase; }
    .thesis, .section-note { color:var(--muted); }
    .tab-nav,.subtab-nav { display:flex; gap:8px; margin:0 0 14px; overflow-x:auto; }
    .tab-button,.subtab-button,.feedback-buttons button,#sortScore { min-height:34px; border:1px solid var(--line); border-radius:6px; background:var(--panel); color:var(--muted); cursor:pointer; font-weight:800; padding:7px 10px; white-space:nowrap; }
    .tab-button[aria-selected="true"],.subtab-button[aria-selected="true"] { background:#eef4ff; border-color:#b7cdf8; color:var(--blue); }
    .tab-panel[hidden],.recommendation-subtab[hidden],[hidden] { display:none !important; }
    section { margin-bottom:14px; overflow-x:auto; }
    .two-column,.table-pair { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:14px; align-items:start; }
    .section-title { display:flex; justify-content:space-between; align-items:baseline; gap:10px; margin-bottom:10px; }
    table { width:100%; border-collapse:collapse; min-width:720px; }
    th,td { border-bottom:1px solid var(--line); padding:8px 7px; text-align:left; white-space:nowrap; font-size:13px; vertical-align:top; }
    th { color:var(--muted); font-size:12px; text-transform:uppercase; }
    .compact-table,.decision-table,.source-status-table,.source-health-table,.source-issue-group-table,.score-trend-table { min-width:0; table-layout:auto; }
    td:last-child,.compact-table td:last-child,.decision-table td:last-child,.source-status-table td:nth-child(8),.source-status-table td:last-child,.source-health-table td:last-child { white-space:normal; color:var(--muted); }
    .pill { display:inline-block; min-width:54px; text-align:center; border-radius:999px; padding:3px 8px; font-weight:700; font-size:12px; }
    .add,.buy,.strong-buy { background:#dff7ea; color:var(--green); } .watch,.hold { background:#fff2cf; color:var(--amber); } .avoid,.trim { background:#fde3df; color:var(--red); }
    .change-badge { display:inline-block; border:1px solid var(--line); border-radius:999px; padding:3px 8px; font-size:12px; font-weight:800; color:var(--muted); background:#f3f5f8; }
    .change-up,.change-new { border-color:#b8e4ca; background:#eaf8ef; color:var(--green); } .change-action { border-color:#f3d08a; background:#fff6df; color:var(--amber); } .change-down { border-color:#f3b7b0; background:#fff0ee; color:var(--red); }
    .daily-review-lead { display:grid; grid-template-columns:minmax(280px,1.5fr) minmax(220px,.8fr); gap:12px; margin-bottom:10px; }
    .daily-review-lead > div,.daily-review-card,.data-review-card,.coherence-card { border:1px solid var(--line); border-radius:8px; background:#fbfcfe; padding:12px; min-width:0; }
    .daily-review-lead strong,.daily-review-card strong,.data-review-card strong,.coherence-card strong { display:block; color:var(--text); font-size:18px; margin-top:2px; overflow-wrap:anywhere; }
    .daily-review-lead p,.daily-review-card p,.data-review-card p,.coherence-card p { margin:6px 0 0; color:var(--muted); font-size:13px; }
    .daily-review-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:10px; }
    .data-review-grid { display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:10px; }
    .coherence-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:10px; margin-bottom:10px; }
    .daily-review-details,.data-review-details { display:grid; gap:8px; margin-top:10px; }
    .daily-review-details details,.data-review-details details { border:1px solid var(--line); border-radius:8px; background:#fbfcfe; padding:8px 10px; }
    .daily-review-details summary,.data-review-details summary { cursor:pointer; color:var(--blue); font-weight:800; }
    .daily-review-details table,.data-review-details table { margin-top:8px; }
    .action-queue-list { display:grid; gap:10px; }
    .action-card { border:1px solid var(--line); border-radius:8px; background:#fbfcfe; padding:12px; }
    .action-card-head { display:flex; justify-content:space-between; align-items:flex-start; gap:12px; }
    .action-card-title,.action-card-score { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
    .action-card-title strong { font-size:18px; }
    .action-rank { color:var(--muted); font-size:12px; font-weight:800; min-width:28px; }
    .action-card-score strong { font-size:19px; line-height:1; }
    .action-card-metrics { display:grid; grid-template-columns:repeat(5,minmax(112px,1fr)); gap:8px; margin-top:10px; }
    .action-card-metrics > span { border:1px solid var(--line); border-radius:6px; background:white; padding:7px 8px; min-width:0; }
    .action-card-metrics strong { display:block; color:var(--text); margin-top:2px; overflow-wrap:anywhere; }
    .action-card-rationale { margin:10px 0 0; color:var(--muted); font-size:13px; white-space:normal; }
    .action-card-rationale strong { color:var(--text); }
    .action-audit-table { margin-top:10px; }
    .action-audit-table summary { cursor:pointer; color:var(--blue); font-weight:800; padding:5px 0; }
    .decision-safety-callout { display:grid; grid-template-columns:minmax(240px,1.2fr) minmax(280px,1fr); gap:12px; align-items:start; border:1px solid var(--line); border-radius:8px; background:#fbfcfe; padding:12px; }
    .decision-safety-callout strong { display:block; font-size:18px; margin-top:2px; }
    .decision-safety-callout p { margin:6px 0 0; color:var(--muted); }
    .decision-safety-facts { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:8px; }
    .decision-safety-facts > span { border:1px solid var(--line); border-radius:6px; background:white; padding:7px 8px; min-width:0; }
    .decision-safety-facts strong { overflow-wrap:anywhere; }
    .decision-safety-reasons { margin-top:10px; color:var(--muted); }
    .decision-safety-reasons ul { margin:6px 0 0; padding-left:18px; }
    .source-health-filter-bar { display:flex; flex-wrap:wrap; gap:8px; margin:0 0 8px; }
    .source-health-filter { min-height:32px; border:1px solid var(--line); border-radius:999px; background:white; color:var(--muted); cursor:pointer; font-weight:800; padding:5px 10px; }
    .source-health-filter span { color:var(--text); margin-left:4px; }
    .source-health-filter[aria-pressed="true"] { background:#eef4ff; border-color:#b7cdf8; color:var(--blue); }
    .source-health-filter-summary { color:var(--muted); font-size:12px; margin-bottom:6px; }
    .provider-gap-counts { display:grid; grid-template-columns:repeat(4,minmax(120px,1fr)); gap:8px; margin:0 0 10px; }
    .provider-gap-count { border:1px solid var(--line); border-radius:8px; background:#fbfcfe; padding:9px 10px; }
    .provider-gap-count span { display:block; color:var(--muted); font-size:12px; font-weight:800; text-transform:uppercase; }
    .provider-gap-count strong { display:block; font-size:20px; margin-top:2px; }
    .provider-gap-count-blocker strong,.provider-gap-severity-blocker td:first-child { color:var(--red); font-weight:800; }
    .provider-gap-count-review-needed strong,.provider-gap-severity-review-needed td:first-child { color:var(--amber); font-weight:800; }
    .provider-gap-count-stale-missing strong,.provider-gap-severity-stale-missing td:first-child { color:#7c3aed; font-weight:800; }
    .provider-gap-count-informational strong,.provider-gap-severity-informational td:first-child { color:var(--muted); font-weight:800; }
    .provider-gap-table { min-width:0; }
    .readiness-grid,.decision-brief-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:10px; }
    .readiness-card,.decision-brief-card { border:1px solid var(--line); border-radius:8px; background:#fbfcfe; padding:12px; }
    .decision-brief-card p,.notes { color:var(--muted); }
    .allocation-row { margin-bottom:12px; } .allocation-label { display:flex; justify-content:space-between; gap:12px; margin-bottom:5px; color:var(--muted); }
    .allocation-label strong { color:var(--text); } .allocation-track { height:10px; background:#edf0f5; border-radius:999px; overflow:hidden; } .allocation-fill { height:100%; border-radius:999px; background:var(--blue); }
    .toolbar,.feedback-buttons { display:flex; flex-wrap:wrap; gap:10px; margin-bottom:12px; align-items:center; }
    .toolbar input,.toolbar select,.feedback-grid input,.feedback-grid select,.feedback-grid textarea { min-height:36px; border:1px solid var(--line); border-radius:6px; padding:6px 8px; background:white; color:var(--text); font:inherit; }
    .feedback-grid { display:grid; grid-template-columns:repeat(2,minmax(180px,1fr)); gap:12px; margin-bottom:12px; }
    .feedback-grid label { display:grid; gap:6px; color:var(--muted); font-size:12px; font-weight:700; text-transform:uppercase; }
    .feedback-grid textarea { grid-column:1/-1; resize:vertical; }
    #feedbackCommand { white-space:pre-wrap; background:#111827; color:#e5e7eb; border-radius:8px; padding:12px; overflow-x:auto; }
    .feedback-status { border:1px solid var(--line); border-radius:8px; background:#fbfcfe; color:var(--muted); padding:10px 12px; margin:0 0 10px; font-size:13px; }
    .feedback-status.saved { border-color:#b8e4ca; background:#eaf8ef; color:var(--green); }
    .feedback-status.fallback { border-color:#f3d08a; background:#fff6df; color:var(--amber); }
    .feedback-status.failed { border-color:#f3b7b0; background:#fff0ee; color:var(--red); }
    .recent-feedback { margin-top:12px; border-top:1px solid var(--line); padding-top:12px; }
    .recent-feedback ul { list-style:none; margin:0; padding:0; display:grid; gap:8px; }
    .recent-feedback li { border:1px solid var(--line); border-radius:8px; background:#fbfcfe; padding:9px 10px; }
    .recent-feedback li span { display:block; color:var(--muted); font-size:12px; margin-top:2px; }
    .recent-feedback li p { margin:5px 0 0; color:var(--muted); font-size:13px; }
    .recent-feedback .empty-feedback { color:var(--muted); }
    .header-content { display:flex; justify-content:space-between; align-items:center; gap:16px; }
    .print-button { min-height:34px; border:1px solid rgba(255,255,255,.35); border-radius:6px; background:#eef4ff; color:var(--blue); cursor:pointer; font-weight:800; padding:7px 10px; white-space:nowrap; }
    .next-day-preview { margin:10px 0 0; border:1px solid var(--line); border-radius:8px; background:#fbfcfe; padding:12px; }
    .next-day-preview-head { display:flex; justify-content:space-between; gap:12px; align-items:center; margin-bottom:8px; }
    .next-day-preview-head strong { display:block; color:var(--text); font-size:16px; margin-top:3px; }
    .next-day-preview-metrics { display:grid; grid-template-columns:repeat(4,minmax(110px,1fr)); gap:8px; color:var(--muted); font-size:12px; }
    .next-day-preview-metrics strong { color:var(--text); margin-left:4px; }
    .next-day-preview p { margin:8px 0 0; color:var(--muted); font-size:13px; }
    .print-review { display:none; }
    .print-summary-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:8px; }
    .print-summary-card { border:1px solid var(--line); border-radius:8px; padding:10px; background:#fbfcfe; }
    .print-summary-card strong { display:block; font-size:15px; margin-top:3px; }
    .print-table { min-width:0; table-layout:auto; }
    @media (max-width:860px) { main { padding:16px; } .summary,.two-column,.table-pair,.feedback-grid,.decision-safety-callout,.daily-review-lead,.daily-review-grid,.data-review-grid,.coherence-grid { grid-template-columns:1fr; } .action-card-head { flex-direction:column; } .action-card-metrics,.decision-safety-facts { grid-template-columns:repeat(2,minmax(0,1fr)); } }
    @media print {
      @page { margin:.45in; }
      :root { --bg:#fff; --panel:#fff; --text:#111827; --muted:#4b5563; --line:#d1d5db; }
      body { background:#fff; color:var(--text); font-size:10pt; line-height:1.25; }
      header,.screen-dashboard,.print-button { display:none !important; }
      main { max-width:none; padding:0; margin:0; }
      .print-review { display:block !important; }
      .print-review h1 { font-size:18pt; margin:0 0 3px; }
      .print-review h2 { font-size:12pt; margin:0 0 6px; }
      .print-review section { border:0; border-top:1px solid var(--line); border-radius:0; padding:8px 0; margin:0 0 8px; overflow:visible; break-inside:avoid; page-break-inside:avoid; }
      .print-review .section-title { margin-bottom:6px; }
      .print-summary-grid,.readiness-grid,.coherence-grid { grid-template-columns:repeat(3,1fr); gap:6px; }
      .print-summary-card,.readiness-card,.coherence-card,.next-day-preview { border:1px solid var(--line); border-radius:4px; padding:7px; background:#fff; }
      .next-day-preview-metrics { grid-template-columns:repeat(4,1fr); gap:4px; }
      .decision-briefs,.tab-nav,.subtab-nav,.feedback-grid,.feedback-buttons,.feedback-status,.recent-feedback,.toolbar,.full-universe,.notes,#feedbackCommand { display:none !important; }
      table,.compact-table,.decision-table,.source-status-table,.source-health-table,.source-issue-group-table,.score-trend-table,.print-table { width:100%; min-width:0 !important; table-layout:auto; border-collapse:collapse; }
      thead { display:table-header-group; }
      tr { break-inside:avoid; page-break-inside:avoid; }
      th,td { white-space:normal; padding:4px 5px; font-size:8pt; border-bottom:1px solid var(--line); }
      th { color:#374151; }
    }
    """

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Stock Trading Dashboard - {html.escape(text(metadata.get("report_date"), context_filename_date(context)))}</title>
  <style>{dashboard_css}</style>
</head>
<body>
  <header>
    <div class="header-content">
      <div>
        <h1>Stock Trading Dashboard</h1>
        <div class="subtle">Report Context · Generated {html.escape(text(metadata.get("generated_at")))} · Recommendation-only · No automated trading</div>
      </div>
      <button class="print-button" type="button" onclick="window.print()">Print Review</button>
    </div>
  </header>
  <main>
    <div class="screen-dashboard">
    <div class="summary">
      <div class="metric">
        <span class="label">{html.escape(text(summary.get("recommendation_label"), "Top Candidate"))}</span>
        <strong>{html.escape(summary_value(context, "top_symbol"))} · {html.escape(summary_value(context, "top_action"))}</strong>
        <div class="thesis">{html.escape(text(summary.get("top_company")))} · {html.escape(text(summary.get("top_notes")))}</div>
      </div>
      <div class="metric"><span class="label">Decision Gate</span><strong>{html.escape(text(decision_gate.get("status"), "Ready"))}</strong><div class="thesis">{html.escape(decision_gate_detail(summary))}</div></div>
      <div class="metric"><span class="label">Score</span><strong>{html.escape(text(summary.get("top_score")))}</strong></div>
      <div class="metric"><span class="label">{html.escape(text(summary.get("amount_label"), "Buy Capacity"))}</span><strong>{html.escape(text(summary.get("suggested_amount_text"), money(summary.get("suggested_amount"))))}</strong></div>
      <div class="metric"><span class="label">Blended Target</span><strong>{html.escape(text(summary.get("target_text"), money(summary.get("target_price"))))}</strong><div class="thesis">{html.escape(text(summary.get("confidence")))} confidence · {html.escape(text(summary.get("target_quality")))}</div></div>
      <div class="metric"><span class="label">1Y Upside</span><strong>{html.escape(text(summary.get("upside_text"), pct(summary.get("upside_pct"))))}</strong><div class="thesis">{html.escape(text(summary.get("data_status")))}</div></div>
      <div class="metric"><span class="label">Reliability</span><strong>{html.escape(text(reliability.get("mode"), "n/a"))}</strong><div class="thesis">Fresh {html.escape(text(price_counts.get("fresh"), "0"))} · fallback {html.escape(text(price_counts.get("fallback"), "0"))} · missing {html.escape(text(price_counts.get("missing"), "0"))}</div></div>
      <div class="metric"><span class="label">Source Health</span><strong>{html.escape(text(source_summary.get("needs_attention"), "0"))}</strong><div class="thesis">{html.escape(text(source_summary.get("healthy"), "0"))} healthy · {html.escape(text(source_summary.get("stale"), "0"))} stale · {html.escape(text(source_summary.get("not_implemented"), "0"))} not implemented</div></div>
    </div>

    {render_daily_decision_review(context)}
    {render_long_term_capital_deployment(context)}
    {render_earnings_review(context)}
    {render_tactical_review(context)}
    {render_product_review_path(context)}
    {render_data_reliability_review(context)}
    {render_model_evaluation(context)}
    {render_alerts_review(context)}

    <nav class="tab-nav" aria-label="Dashboard sections">
      <button class="tab-button" type="button" aria-selected="true" data-tab-target="recommendationsTab">Recommendations</button>
      <button class="tab-button" type="button" aria-selected="false" data-tab-target="holdingsTab">Current Holdings</button>
      <button class="tab-button" type="button" aria-selected="false" data-tab-target="healthTrendsTab">Health & Trends</button>
      <button class="tab-button" type="button" aria-selected="false" data-tab-target="dataIngestionTab">Data Ingestion</button>
      <button class="tab-button" type="button" aria-selected="false" data-tab-target="learningReviewTab">Learning Review</button>
      <button class="tab-button" type="button" aria-selected="false" data-tab-target="researchSourcesTab">Research Sources</button>
      <button class="tab-button" type="button" aria-selected="false" data-tab-target="feedbackTab">Feedback</button>
    </nav>

    <div id="recommendationsTab" class="tab-panel">
      <nav class="subtab-nav" aria-label="Recommendation sections">
        <button class="subtab-button" type="button" aria-selected="true" data-rec-tab-target="actionQueueSubtab">Action Queue</button>
        <button class="subtab-button" type="button" aria-selected="false" data-rec-tab-target="longTermSubtab">Long-Term Queue</button>
        <button class="subtab-button" type="button" aria-selected="false" data-rec-tab-target="shortTermSubtab">Short-Term Queue</button>
        <button class="subtab-button" type="button" aria-selected="false" data-rec-tab-target="nextDaySubtab">Next-Day Watchlist</button>
        <button class="subtab-button" type="button" aria-selected="false" data-rec-tab-target="speculativeSubtab">Speculative AI Watchlist</button>
        <button class="subtab-button" type="button" aria-selected="false" data-rec-tab-target="dataGapsSubtab">Data Gaps</button>
      </nav>
      <div id="actionQueueSubtab" class="recommendation-subtab">
        {render_readiness(as_dict(context.get("readiness")))}
        {render_decision_safety_review(context)}
        {render_decision_cards(as_list(decision_briefs.get("rows")))}
        {render_action_queue(context)}
      </div>
      <div id="longTermSubtab" class="recommendation-subtab" hidden><section><div class="section-title"><h2>Long-Term Queue</h2><span class="section-note">75% sleeve</span></div>{queue_table(context, "long_term")}</section></div>
      <div id="shortTermSubtab" class="recommendation-subtab" hidden><section><div class="section-title"><h2>Short-Term Queue</h2><span class="section-note">Day, week, or 2-4 week trades</span></div>{queue_table(context, "short_term")}</section></div>
      <div id="nextDaySubtab" class="recommendation-subtab" hidden><section><div class="section-title"><h2>Next-Day Watchlist</h2><span class="section-note">{html.escape(text(next_day.get("status", {}).get("label") if isinstance(next_day.get("status"), dict) else ""))}</span></div>{queue_table(context, "next_day")}</section></div>
      <div id="speculativeSubtab" class="recommendation-subtab" hidden><section><div class="section-title"><h2>Speculative AI Watchlist</h2><span class="section-note">Observation only</span></div>{queue_table(context, "speculative")}</section></div>
      <div id="dataGapsSubtab" class="recommendation-subtab" hidden>
        <section><div class="section-title"><h2>Ranked Data Gap Queue</h2><span class="section-note">{html.escape(text(data_gaps.get("note"), "Ranked by expected score and confidence impact"))}</span></div>{queue_table(context, "data_gaps", "compact-table")}</section>
        <section><div class="section-title"><h2>Verification Queue</h2><span class="section-note">Semi-automatic next checks from persisted decision insights</span></div>{html_table(as_list(verification_queue.get("headers")), as_list(verification_queue.get("rows")), "compact-table")}</section>
        <section><div class="section-title"><h2>Source Drilldowns</h2><span class="section-note">Target-source and evidence counts</span></div>{html_table(as_list(source_drilldown.get("headers")), as_list(source_drilldown.get("rows")), "compact-table")}</section>
      </div>
      <details class="full-universe"><summary>Open full ranked V1 universe and filters</summary><div class="toolbar"><input id="tickerFilter" type="search" placeholder="Filter ticker or company"><select id="sleeveFilter"><option value="">All sleeves</option><option value="long_term">Long term</option><option value="short_term">Short term</option><option value="speculative_ai">Speculative AI</option><option value="etf">ETF</option></select><select id="actionFilter"><option value="">All actions</option><option value="Add">Add</option><option value="Watch">Watch</option><option value="Avoid">Avoid</option><option value="Hold">Hold</option></select><button type="button" id="sortScore">Sort by score</button></div>{html_table(as_list(full_universe.get("headers")), as_list(full_universe.get("rows")), "rank-table", set(as_list(full_universe.get("raw_columns"))))}</details>
      <section><h2>Notes</h2><ul class="notes"><li>This dashboard is decision support, not automated trading.</li><li>Low-confidence, wide-range, partial-blend, or verification-blocked candidates stay visible for review but cannot be labeled as the recommended next buy.</li><li>The 10% single-stock cap is applied to any decision-safe suggested purchase amount.</li></ul></section>
    </div>

    <div id="holdingsTab" class="tab-panel" hidden>
      <div class="two-column">
        <section><div class="section-title"><h2>Current Holdings Used</h2><span class="section-note">Latest E*TRADE snapshot or manual fallback</span></div>{html_table(as_list(holdings.get("headers")), as_list(holdings.get("rows")), "compact-table")}</section>
        <section><div class="section-title"><h2>Holdings Allocation</h2><span class="section-note">10% cap check</span></div>{render_allocation(as_list(holdings.get("allocation")))}</section>
      </div>
    </div>

    <div id="healthTrendsTab" class="tab-panel" hidden>
      <section><div class="section-title"><h2>Report Reliability</h2><span class="section-note">Run {html.escape(text(metadata.get("workflow_run_id") or "direct"))} · recommendation run {html.escape(text(metadata.get("recommendation_run_id")))}</span></div><p><strong>Status:</strong> {html.escape(text(reliability.get("mode"), "n/a"))}. <strong>Latest successful provider refresh:</strong> {html.escape(text(reliability.get("latest_provider_refresh"), "n/a"))}.</p>{html_table(["Fresh Prices", "Fallback Prices", "Stale Prices", "Manual Prices", "Missing Prices", "Top Blocker"], [[price_counts.get("fresh", 0), price_counts.get("fallback", 0), price_counts.get("stale", 0), price_counts.get("manual", 0), price_counts.get("missing", 0), source_health.get("top_blocker") or "None"]], "compact-table")}</section>
      {render_provider_gap_review_html(provider_gap_review)}
      <section><div class="section-title"><h2>Source Issue Groups</h2><span class="section-note">Grouped root causes; detailed alerts remain below</span></div>{html_table(as_list(source_issue_groups.get("headers")), as_list(source_issue_groups.get("rows")), "source-issue-group-table")}</section>
      <section><div class="section-title"><h2>Provider Blocker Review</h2><span class="section-note">Field-level blockers and concrete next actions</span></div>{html_table(as_list(provider_blockers.get("headers")), as_list(provider_blockers.get("rows")), "source-issue-group-table")}</section>
      <section><div class="section-title"><h2>Insight Themes</h2><span class="section-note">Common decision patterns across the ranked universe</span></div>{html_table(as_list(insight_themes.get("headers")), as_list(insight_themes.get("rows")), "compact-table")}</section>
      <section><div class="section-title"><h2>Decision Insight History</h2><span class="section-note">Latest decision insight movement by symbol</span></div>{html_table(as_list(decision_history.get("headers")), as_list(decision_history.get("rows")), "compact-table")}</section>
      <div class="table-pair">
        <section><div class="section-title"><h2>Source Health Alerts</h2><span class="section-note">{len(as_list(source_health_alerts.get("rows")))} active alert(s)</span></div>{render_source_health_alerts_table(source_health_alerts)}</section>
        <section><div class="section-title"><h2>Score Changes</h2><span class="section-note">Changes of 1 point or more</span></div>{html_table(as_list(score_changes.get("headers")), as_list(score_changes.get("rows")), "compact-table")}</section>
      </div>
      <section><div class="section-title"><h2>Score Movement</h2><span class="section-note">Base score plus transparent signal overlay</span></div>{html_table(as_list(score_movement.get("headers")), as_list(score_movement.get("rows")), "compact-table")}</section>
      <section><div class="section-title"><h2>Trend Insights</h2><span class="section-note">Score, price trend, and data-gap context</span></div>{html_table(as_list(trend_insights.get("headers")), as_list(trend_insights.get("rows")), "compact-table")}</section>
    </div>

    <div id="dataIngestionTab" class="tab-panel" hidden>
      <section><div class="section-title"><h2>Data Ingestion & Signal Health</h2><span class="section-note">Free-first raw + curated ingestion status</span></div><p class="section-note">Raw payload rows are retained for audit and future synthesis. Curated records are normalized into evidence, targets, prices, and active insight signals.</p>{html_table(as_list(data_ingestion.get("headers")), as_list(data_ingestion.get("rows")), "source-status-table")}</section>
      <section><div class="section-title"><h2>Next Ingestion Runs</h2><span class="section-note">Freshness, cadence, cooldown, and run priority</span></div>{html_table(as_list(ingestion_run_plan.get("headers")), as_list(ingestion_run_plan.get("rows")), "source-status-table")}</section>
      <section><div class="section-title"><h2>Backfill Queue</h2><span class="section-note">Historical source windows that need more records</span></div>{html_table(as_list(ingestion_backfill.get("headers")), as_list(ingestion_backfill.get("rows")), "compact-table")}</section>
      <section><div class="section-title"><h2>Evidence Events</h2><span class="section-note">Related evidence clustered by symbol, topic, source mix, and corroboration</span></div>{html_table(as_list(evidence_events.get("headers")), as_list(evidence_events.get("rows")), "compact-table")}</section>
      <section><div class="section-title"><h2>Evidence Review Queue</h2><span class="section-note">Review queue for future AI synthesis; no score or recommendation impact</span></div>{html_table(as_list(evidence_review_queue.get("headers")), as_list(evidence_review_queue.get("rows")), "compact-table")}</section>
      <section><div class="section-title"><h2>AI Synthesis Readiness By Symbol</h2><span class="section-note">Deterministic packets for future AI summaries; explanatory only, no LLM conclusions yet</span></div>{html_table(as_list(synthesis_readiness.get("headers")), as_list(synthesis_readiness.get("rows")), "compact-table")}</section>
      <section><div class="section-title"><h2>Source Quality</h2><span class="section-note">Reliability and stock-relevance measurement; no score impact yet</span></div>{html_table(as_list(as_dict(source_quality.get("table")).get("headers")), as_list(as_dict(source_quality.get("table")).get("rows")), "source-status-table")}</section>
      <section><div class="section-title"><h2>Source Depth Signals</h2><span class="section-note">Normalized SEC, IR, and official-source extraction; shadow/explanatory only</span></div>{html_table(as_list(source_depth.get("headers")), as_list(source_depth.get("rows")), "compact-table")}</section>
      <section><div class="section-title"><h2>Low Relevance / Noisy Sources</h2><span class="section-note">Sources producing records with weak symbol matches</span></div>{html_table(as_list(as_dict(source_quality.get("low_relevance")).get("headers")), as_list(as_dict(source_quality.get("low_relevance")).get("rows")), "compact-table")}</section>
      <section><div class="section-title"><h2>Low Confidence Matches</h2><span class="section-note">Evidence tags needing review before synthesis or scoring use</span></div>{html_table(as_list(as_dict(source_quality.get("low_confidence_matches")).get("headers")), as_list(as_dict(source_quality.get("low_confidence_matches")).get("rows")), "compact-table")}</section>
      <section><div class="section-title"><h2>Paid Provider Watchlist</h2><span class="section-note">Track cost before buying anything</span></div>{html_table(as_list(as_dict(context.get("paid_providers")).get("headers")), as_list(as_dict(context.get("paid_providers")).get("rows")), "compact-table")}</section>
      <section><div class="section-title"><h2>Insight Signal Health</h2><span class="section-note">Active deterministic scoring overlay</span></div>{html_table(as_list(as_dict(context.get("signal_health")).get("headers")), as_list(as_dict(context.get("signal_health")).get("rows")), "compact-table")}</section>
    </div>

    <div id="learningReviewTab" class="tab-panel" hidden>
      {render_learning_review_html(context)}
    </div>

    <div id="feedbackTab" class="tab-panel" hidden>
      <section><h2>Feedback</h2><div id="feedbackStatus" class="feedback-status">Choose feedback to save locally when the dashboard server is available, or generate a command fallback.</div><div class="feedback-grid"><label>Feedback target<select id="feedbackKind"><option value="recommendation">Recommendation</option><option value="source">Research source</option></select></label><label id="feedbackSymbolWrap">Symbol<input id="feedbackSymbol" type="text" placeholder="{html.escape(fallback_symbol)}"></label><label id="feedbackSourceWrap" hidden>Source<select id="feedbackSource">{source_options}</select></label><label>Details<textarea id="feedbackNotes" rows="4" placeholder="What should the engine learn from your review?"></textarea></label></div><div class="feedback-buttons"><button type="button" data-kind="recommendation" data-feedback="agree">Agree</button><button type="button" data-kind="recommendation" data-feedback="disagree">Disagree</button><button type="button" data-kind="recommendation" data-feedback="too_risky">Too risky</button><button type="button" data-kind="source" data-feedback="useful_source" hidden>Useful source</button><button type="button" data-kind="source" data-feedback="noisy_source" hidden>Noisy source</button></div><pre id="feedbackCommand">Choose feedback to generate a local save command.</pre>{render_recent_feedback(as_list(feedback.get("recent")))}</section>
    </div>

    <div id="researchSourcesTab" class="tab-panel" hidden>
      <section><div class="section-title"><h2>Research Sources</h2><span class="section-note">Implementation, health, and weighting</span></div>{render_research_sources(context)}</section>
    </div>
    </div>
    {render_print_review(context)}
  </main>
  <script>{dashboard_script(fallback_symbol, text(metadata.get("report_date")))}</script>
</body>
</html>
"""


def render_next_day_preview(preview: object) -> str:
    preview_dict = as_dict(preview)
    if not preview_dict:
        preview_text = text(preview)
        return f"<p class=\"section-note\">{html.escape(preview_text)}</p>" if preview_text else ""
    return (
        '<div class="next-day-preview">'
        '<div class="next-day-preview-head">'
        "<div>"
        '<span class="label">Top next-day watch</span>'
        f'<strong>{html.escape(text(preview_dict.get("symbol")))} · {html.escape(text(preview_dict.get("action")))} · {html.escape(text(preview_dict.get("score")))}</strong>'
        "</div>"
        "</div>"
        '<div class="next-day-preview-metrics">'
        f'<span>Current <strong>{html.escape(text(preview_dict.get("current")))}</strong></span>'
        f'<span>Target <strong>{html.escape(text(preview_dict.get("target")))}</strong></span>'
        f'<span>Upside <strong>{html.escape(text(preview_dict.get("upside")))}</strong></span>'
        f'<span>Status <strong>{html.escape(text(preview_dict.get("data_status")))}</strong></span>'
        "</div>"
        f'<p>{html.escape(text(preview_dict.get("rationale")))}</p>'
        "</div>"
    )


def render_readiness(readiness: dict[str, Any]) -> str:
    items = as_list(readiness.get("items"))
    if not items:
        return ""
    cards = []
    for item in items:
        item_dict = as_dict(item)
        cards.append(
            "<div class=\"readiness-card\">"
            f"<div class=\"label\">{html.escape(text(item_dict.get('status'), 'Review'))}</div>"
            f"<strong>{html.escape(text(item_dict.get('label') or item_dict.get('name')))}</strong>"
            f"<p>{html.escape(text(item_dict.get('reason') or item_dict.get('detail') or item_dict.get('message')))}</p>"
            f"<div class=\"section-note\">{html.escape(text(item_dict.get('next_action')))}</div>"
            "</div>"
        )
    preview_html = render_next_day_preview(readiness.get("preview"))
    return f'<section class="readiness-section"><div class="section-title"><h2>Pre-Market Readiness</h2><span class="section-note">Decision-safety gate applied before buy labeling</span></div>{preview_html}<div class="readiness-grid">{"".join(cards)}</div></section>'


def render_recent_feedback(records: list[Any]) -> str:
    items = []
    for record in records[:8]:
        item = as_dict(record)
        subject = text(item.get("subject") or item.get("symbol") or item.get("source") or item.get("source_name"))
        feedback_type = text(item.get("type") or item.get("feedback_type") or item.get("record"))
        created_at = text(item.get("created_at") or item.get("timestamp"))
        notes = text(item.get("notes"))
        items.append(
            "<li>"
            f"<strong>{html.escape(subject)}</strong>"
            f"<span>{html.escape(feedback_type)} · {html.escape(created_at)}</span>"
            f"<p>{html.escape(notes)}</p>"
            "</li>"
        )
    if not items:
        items.append('<li class="empty-feedback">No feedback saved in this session yet.</li>')
    return f'<div class="recent-feedback"><div class="section-title"><h3>Recent Feedback</h3><span class="section-note">Latest local saves</span></div><ul id="recentFeedbackList">{"".join(items)}</ul></div>'


def render_print_summary(context: dict[str, object]) -> str:
    summary = normalized_summary(context)
    reliability = as_dict(context.get("reliability"))
    price_counts = as_dict(reliability.get("price_counts"))
    source_health = as_dict(context.get("source_health"))
    source_summary = as_dict(source_health.get("summary") or reliability.get("source_health"))
    decision_gate = as_dict(summary.get("decision_gate"))
    cards = [
        ("Top candidate", f"{summary_value(context, 'top_symbol')} · {summary_value(context, 'top_action')}", text(summary.get("top_company") or summary.get("top_notes"))),
        ("Decision Gate", text(decision_gate.get("status"), "Ready"), decision_gate_detail(summary)),
        ("Score", text(summary.get("top_score")), ""),
        (text(summary.get("amount_label"), "Buy Capacity"), text(summary.get("suggested_amount_text"), money(summary.get("suggested_amount"))), ""),
        ("Blended Target", text(summary.get("target_text"), money(summary.get("target_price"))), f"{text(summary.get('confidence'))} confidence"),
        ("1Y Upside", text(summary.get("upside_text"), pct(summary.get("upside_pct"))), text(summary.get("data_status"))),
        ("Reliability", text(reliability.get("mode"), "n/a"), f"Fresh {text(price_counts.get('fresh'), '0')} · fallback {text(price_counts.get('fallback'), '0')} · missing {text(price_counts.get('missing'), '0')}"),
        ("Source Health", text(source_summary.get("needs_attention"), "0"), f"{text(source_summary.get('healthy'), '0')} healthy · {text(source_summary.get('stale'), '0')} stale"),
    ]
    rendered = []
    for label, value, detail in cards:
        rendered.append(
            '<div class="print-summary-card">'
            f'<span class="label">{html.escape(label)}</span>'
            f'<strong>{html.escape(value)}</strong>'
            f'<div class="section-note">{html.escape(detail)}</div>'
            "</div>"
        )
    return f'<section><div class="section-title"><h2>Summary Metrics</h2><span class="section-note">Decision snapshot</span></div><div class="print-summary-grid">{"".join(rendered)}</div></section>'


def render_print_review(context: dict[str, object]) -> str:
    metadata = as_dict(context.get("metadata"))
    report_date = text(metadata.get("report_date"), context_filename_date(context))
    generated_at = text(metadata.get("generated_at"))
    action_queue = queue(context, "action_queue")
    data_gaps = queue(context, "data_gaps")
    next_day = queue(context, "next_day")
    action_columns = [
        ("Rank", ["Rank"]),
        ("Symbol", ["Symbol"]),
        ("Action", ["Action"]),
        ("Score", ["Score"]),
        ("Current", ["Current", "Today"]),
        ("Target", ["Target"]),
        ("Upside", ["Upside", "1Y Upside"]),
        ("Data Status", ["Data Status", "Status"]),
        ("Rationale", ["Rationale", "Why"]),
    ]
    gap_columns = [
        ("Rank", ["Rank"]),
        ("Symbol", ["Symbol"]),
        ("Data Gap", ["Data Gap"]),
        ("Impact", ["Impact"]),
        ("Best Pull", ["Best Pull"]),
        ("Next Action", ["Next Action"]),
    ]
    next_day_columns = [
        ("Rank", ["Rank"]),
        ("Symbol", ["Symbol"]),
        ("Action", ["Action"]),
        ("Score", ["Score"]),
        ("Current", ["Current", "Today"]),
        ("Target", ["Target"]),
        ("Upside", ["Upside"]),
        ("Data Status", ["Data Status", "Status"]),
        ("Why", ["Why", "Rationale"]),
    ]
    return f"""
    <article class="print-review" aria-label="Print review">
      <section class="print-title">
        <h1>Pre-Market Review</h1>
        <div class="section-note">Generated {html.escape(generated_at)} · Report {html.escape(report_date)} · Recommendation-only · No automated trading</div>
      </section>
      {render_print_summary(context)}
      {render_daily_decision_review(context)}
      {render_long_term_capital_deployment(context)}
      {render_earnings_review(context)}
      {render_tactical_review(context)}
      {render_model_evaluation(context)}
      {render_alerts_review(context)}
      {render_decision_safety_review(context)}
      {render_readiness(as_dict(context.get("readiness")))}
      <section>
        <div class="section-title"><h2>Action Queue</h2><span class="section-note">Top candidates</span></div>
        {compact_queue_table(action_queue, action_columns, limit=8)}
      </section>
      <section>
        <div class="section-title"><h2>Ranked Data Gaps</h2><span class="section-note">Highest-impact checks</span></div>
        {compact_queue_table(data_gaps, gap_columns, limit=8)}
      </section>
      <section>
        <div class="section-title"><h2>Next-Day Watchlist</h2><span class="section-note">Before next session</span></div>
        {compact_queue_table(next_day, next_day_columns, limit=8)}
      </section>
    </article>
    """


def render_decision_cards(rows: list[Any]) -> str:
    if not rows:
        return (
            '<section class="decision-briefs"><div class="section-title">'
            "<h2>Explanatory Decision Briefs</h2>"
            '<span class="section-note">AI synthesis explanatory; no recommendation impact</span>'
            "</div><p>No decision briefs available.</p></section>"
        )
    cards = []
    for row in rows[:5]:
        row_values = as_list(row)
        symbol = text(row_values[0] if len(row_values) > 0 else "")
        insight_type = text(row_values[1] if len(row_values) > 1 else "")
        headline = text(row_values[2] if len(row_values) > 2 else "")
        why = text(row_values[3] if len(row_values) > 3 else "")
        next_check = text(row_values[4] if len(row_values) > 4 else "")
        cards.append(
            "<div class=\"decision-brief-card\">"
            f"<div class=\"label\">{html.escape(symbol)} · {html.escape(insight_type)}</div>"
            f"<h3>{html.escape(headline)}</h3>"
            f"<p>{html.escape(why)}</p>"
            f"<p><strong>Next:</strong> {html.escape(next_check)}</p>"
            "</div>"
        )
    return f'<section class="decision-briefs"><div class="section-title"><h2>Explanatory Decision Briefs</h2><span class="section-note">AI synthesis explanatory; no recommendation impact</span></div><div class="decision-brief-grid">{"".join(cards)}</div></section>'


def render_allocation(rows: list[Any]) -> str:
    if not rows:
        return "<p>No allocation data available yet.</p>"
    blocks = []
    for row in rows:
        item = as_dict(row)
        pct_value = item.get("pct", 0)
        try:
            width = max(0.0, min(float(pct_value), 100.0))
        except (TypeError, ValueError):
            width = 0.0
        blocks.append(
            '<div class="allocation-row">'
            f'<div class="allocation-label"><strong>{html.escape(text(item.get("symbol")))}</strong><span>{html.escape(text(item.get("value_text")))} · {html.escape(text(item.get("pct_text")))}</span></div>'
            f'<div class="allocation-track"><div class="allocation-fill" style="width:{width:.2f}%"></div></div>'
            "</div>"
        )
    return "".join(blocks)


def render_research_sources(context: dict[str, object]) -> str:
    section = as_dict(context.get("research_sources"))
    rows = as_list(section.get("rows"))
    if not rows:
        return "<p>No research sources configured.</p>"
    table_rows = []
    for row in rows:
        item = as_dict(row)
        operations = as_dict(item.get("operations"))
        integration = as_dict(item.get("integration"))
        quality_metrics = as_dict(item.get("source_quality"))
        tag_rate = quality_metrics.get("tag_rate")
        tag_rate_text = f"{float(tag_rate) * 100:.0f}%" if isinstance(tag_rate, (int, float)) else "n/a"
        avg_confidence = quality_metrics.get("avg_tag_confidence")
        confidence_text = f"{float(avg_confidence):.2f}" if isinstance(avg_confidence, (int, float)) else "n/a"
        table_rows.append(
            [
                item.get("source_name", ""),
                integration.get("source_tier") or "core",
                integration.get("source_category") or item.get("source_type") or "",
                operations.get("status") or "",
                operations.get("records") or 0,
                operations.get("raw_records") or 0,
                quality_metrics.get("quality_label") or "",
                tag_rate_text,
                confidence_text,
                quality_metrics.get("top_matched_terms") or "",
                quality_metrics.get("match_reason_summary") or "",
                quality_metrics.get("confidence_bucket_summary") or "",
                quality_metrics.get("low_confidence_matches") or 0,
                operations.get("last_run") or "Not run",
                operations.get("latest_issue") or "No current issue",
                operations.get("next_action") or "",
                item.get("effective_weight") or "",
            ]
        )
    return html_table(
        [
            "Source",
            "Tier",
            "Category",
            "Status",
            "Records",
            "Raw",
            "Quality Label",
            "Tag Rate",
            "Avg Confidence",
            "Top Matches",
            "Match Reasons",
            "Confidence Buckets",
            "Low Confidence",
            "Last Run",
            "Latest Issue",
            "Next Action",
            "Weight",
        ],
        table_rows,
        "source-status-table",
    )


def dashboard_script(fallback_symbol: str, report_date: str) -> str:
    return f"""
    const tabButtons = document.querySelectorAll('[data-tab-target]');
    const tabPanels = document.querySelectorAll('.tab-panel');
    function activateTab(targetId) {{
      tabButtons.forEach(button => button.setAttribute('aria-selected', String(button.dataset.tabTarget === targetId)));
      tabPanels.forEach(panel => panel.hidden = panel.id !== targetId);
    }}
    tabButtons.forEach(button => button.addEventListener('click', () => activateTab(button.dataset.tabTarget)));
    const recButtons = document.querySelectorAll('[data-rec-tab-target]');
    const recPanels = document.querySelectorAll('.recommendation-subtab');
    function activateRecTab(targetId) {{
      recButtons.forEach(button => button.setAttribute('aria-selected', String(button.dataset.recTabTarget === targetId)));
      recPanels.forEach(panel => panel.hidden = panel.id !== targetId);
    }}
    recButtons.forEach(button => button.addEventListener('click', () => activateRecTab(button.dataset.recTabTarget)));
    const table = document.querySelector('.rank-table tbody');
    const tickerFilter = document.getElementById('tickerFilter');
    const sleeveFilter = document.getElementById('sleeveFilter');
    const actionFilter = document.getElementById('actionFilter');
    const sortScore = document.getElementById('sortScore');
    function cellText(row, index) {{ return row.children[index]?.textContent.trim() || ''; }}
    function applyFilters() {{
      if (!table) return;
      const query = tickerFilter?.value.trim().toLowerCase() || '';
      const sleeve = sleeveFilter?.value || '';
      const action = actionFilter?.value || '';
      for (const row of table.rows) {{
        const haystack = `${{cellText(row, 1)}} ${{cellText(row, 2)}}`.toLowerCase();
        const visible = (!query || haystack.includes(query)) && (!sleeve || cellText(row, 3) === sleeve) && (!action || cellText(row, 5) === action);
        row.hidden = !visible;
      }}
    }}
    [tickerFilter, sleeveFilter, actionFilter].forEach(control => control?.addEventListener('input', applyFilters));
    sortScore?.addEventListener('click', () => {{
      if (!table) return;
      Array.from(table.rows).sort((a, b) => Number(cellText(b, 6)) - Number(cellText(a, 6))).forEach(row => table.appendChild(row));
      applyFilters();
    }});
    const sourceHealthFilters = document.querySelectorAll('[data-source-health-filter].source-health-filter');
    const sourceHealthRows = document.querySelectorAll('.source-health-table tbody tr[data-source-health-filter]');
    const sourceHealthSummary = document.querySelector('.source-health-filter-summary');
    function applySourceHealthFilter(filter) {{
      let visible = 0;
      sourceHealthRows.forEach(row => {{
        const show = filter === 'all' || row.dataset.sourceHealthFilter === filter;
        row.hidden = !show;
        if (show) visible += 1;
      }});
      sourceHealthFilters.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.sourceHealthFilter === filter)));
      if (sourceHealthSummary) {{
        const label = Array.from(sourceHealthFilters).find(button => button.dataset.sourceHealthFilter === filter)?.textContent.trim() || 'alerts';
        sourceHealthSummary.textContent = filter === 'all' ? `Showing all ${{visible}} source health alerts.` : `Showing ${{visible}} ${{label.toLowerCase()}} source health alert${{visible === 1 ? '' : 's'}}.`;
      }}
    }}
    sourceHealthFilters.forEach(button => button.addEventListener('click', () => applySourceHealthFilter(button.dataset.sourceHealthFilter || 'all')));
    if (sourceHealthFilters.length) applySourceHealthFilter('all');
    const feedbackKind = document.getElementById('feedbackKind');
    const feedbackSymbolWrap = document.getElementById('feedbackSymbolWrap');
    const feedbackSourceWrap = document.getElementById('feedbackSourceWrap');
    const feedbackSymbol = document.getElementById('feedbackSymbol');
    const feedbackSource = document.getElementById('feedbackSource');
    const feedbackNotes = document.getElementById('feedbackNotes');
    const feedbackCommand = document.getElementById('feedbackCommand');
    const feedbackStatus = document.getElementById('feedbackStatus');
    const recentFeedbackList = document.getElementById('recentFeedbackList');
    function shellQuote(value) {{ return `'${{String(value).replaceAll("'", "'\\\\''")}}'`; }}
    function setFeedbackStatus(message, mode) {{
      if (!feedbackStatus) return;
      feedbackStatus.textContent = message;
      feedbackStatus.className = `feedback-status ${{mode || ''}}`.trim();
    }}
    function updateFeedbackMode() {{
      const isSource = feedbackKind?.value === 'source';
      if (feedbackSymbolWrap) feedbackSymbolWrap.hidden = isSource;
      if (feedbackSourceWrap) feedbackSourceWrap.hidden = !isSource;
      document.querySelectorAll('[data-feedback]').forEach(button => button.hidden = button.dataset.kind !== feedbackKind?.value);
    }}
    function buildFeedbackCommand(type) {{
      const notes = feedbackNotes?.value.trim() || '';
      if (feedbackKind?.value === 'source') {{
        const delta = type === 'useful_source' ? '0.1' : type === 'noisy_source' ? '-0.1' : '0';
        return `python3 scripts/add_feedback.py source ${{shellQuote(feedbackSource?.value || '')}} --type ${{shellQuote(type)}} --delta ${{delta}} --notes ${{shellQuote(notes)}}`;
      }}
      const symbol = feedbackSymbol?.value.trim().toUpperCase() || '{html.escape(fallback_symbol)}';
      return `python3 scripts/add_feedback.py recommendation ${{shellQuote(symbol)}} --report-date {html.escape(report_date)} --type ${{shellQuote(type)}} --notes ${{shellQuote(notes)}}`;
    }}
    function buildFeedbackPayload(type) {{
      const notes = feedbackNotes?.value.trim() || '';
      if (feedbackKind?.value === 'source') {{
        const sourceName = feedbackSource?.value || '';
        const delta = type === 'useful_source' ? 0.1 : type === 'noisy_source' ? -0.1 : 0;
        return {{ kind: 'source', source_name: sourceName, symbol: '', type, rating_delta: delta, notes }};
      }}
      const symbol = feedbackSymbol?.value.trim().toUpperCase() || '{html.escape(fallback_symbol)}';
      return {{ kind: 'recommendation', symbol, report_date: '{html.escape(report_date)}', type, notes }};
    }}
    function feedbackServerAvailable() {{
      return window.location.protocol === 'http:' || window.location.protocol === 'https:';
    }}
    function renderRecentFeedback(records) {{
      if (!recentFeedbackList) return;
      const safeRecords = Array.isArray(records) ? records : [];
      if (!safeRecords.length) {{
        recentFeedbackList.innerHTML = '<li class="empty-feedback">No feedback saved in this session yet.</li>';
        return;
      }}
      recentFeedbackList.innerHTML = safeRecords.map(record => {{
        const subject = String(record.subject || record.symbol || record.source_name || '');
        const type = String(record.type || record.feedback_type || '');
        const created = String(record.created_at || '');
        const notes = String(record.notes || '');
        const escapeText = value => value.replace(/[&<>"']/g, char => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[char]));
        return `<li><strong>${{escapeText(subject)}}</strong><span>${{escapeText(type)}} · ${{escapeText(created)}}</span><p>${{escapeText(notes)}}</p></li>`;
      }}).join('');
    }}
    async function refreshRecentFeedback() {{
      if (!feedbackServerAvailable()) return;
      try {{
        const response = await fetch('/feedback/recent', {{ headers: {{ 'Accept': 'application/json' }} }});
        const payload = await response.json();
        if (response.ok && payload.ok) renderRecentFeedback(payload.records);
      }} catch (error) {{
        // Static servers do not expose recent feedback; keep the generated fallback panel.
      }}
    }}
    async function saveFeedback(type) {{
      const command = buildFeedbackCommand(type);
      if (feedbackCommand) feedbackCommand.textContent = command;
      if (!feedbackServerAvailable()) {{
        setFeedbackStatus('Command fallback: open this dashboard through scripts/serve_dashboard.py to save directly.', 'fallback');
        return;
      }}
      setFeedbackStatus('Saving feedback locally...', '');
      try {{
        const response = await fetch('/feedback', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json', 'Accept': 'application/json' }},
          body: JSON.stringify(buildFeedbackPayload(type)),
        }});
        const payload = await response.json();
        if (!response.ok || !payload.ok) throw new Error(payload.error || 'Feedback save failed.');
        setFeedbackStatus(payload.feedback?.message || 'Feedback saved locally.', 'saved');
        if (feedbackCommand) feedbackCommand.textContent = `Saved locally. Command fallback:\\n${{command}}`;
        renderRecentFeedback(payload.recent);
      }} catch (error) {{
        setFeedbackStatus(`Command fallback: ${{error.message || 'local feedback server unavailable'}}`, 'fallback');
        if (feedbackCommand) feedbackCommand.textContent = command;
      }}
    }}
    feedbackKind?.addEventListener('change', updateFeedbackMode);
    updateFeedbackMode();
    refreshRecentFeedback();
    document.querySelectorAll('[data-feedback]').forEach(button => button.addEventListener('click', () => saveFeedback(button.dataset.feedback)));
    """


def render_markdown(context: dict[str, object], kind: str = "daily") -> str:
    metadata = as_dict(context.get("metadata"))
    summary = normalized_summary(context)
    reliability = as_dict(context.get("reliability"))
    source_health = as_dict(context.get("source_health"))
    provider_gap_review = as_dict(context.get("provider_gap_review"))
    source_quality = as_dict(context.get("source_quality"))
    price_counts = as_dict(reliability.get("price_counts"))
    decision_gate = as_dict(summary.get("decision_gate"))
    action_label = "Action" if decision_gate.get("safe_to_buy", True) else "Candidate action"
    action_value = summary.get("top_action", "")
    if not decision_gate.get("safe_to_buy", True):
        action_value = text(decision_gate.get("candidate_action") or action_value).replace(" blocked", "")

    title_by_kind = {
        "daily": "Daily What-To-Buy-Next Report",
        "end_of_day": f"End-of-Day Review - {metadata.get('report_date', 'n/a')}",
        "watchlist": f"Next-Day Watchlist - {metadata.get('report_date', 'n/a')}",
    }
    coherence_lines = data_reliability_review_markdown_lines(context)
    if kind in {"daily", "end_of_day"}:
        coherence_lines = [
            *long_term_capital_deployment_markdown_lines(context),
            *earnings_review_markdown_lines(context),
            *tactical_review_markdown_lines(context),
            *product_review_path_markdown_lines(context),
            *coherence_lines,
            *model_evaluation_markdown_lines(context),
            *alerts_review_markdown_lines(context),
            *learning_review_markdown_lines(context),
        ]
    lines = [
        f"# {title_by_kind.get(kind, title_by_kind['daily'])}",
        "",
        f"Generated: {metadata.get('generated_at', 'n/a')}",
        "",
        "Recommendation-only; no automated trading.",
        "",
        "## Summary",
        "",
        f"{summary.get('recommendation_label', 'Top candidate')}: **{summary.get('top_symbol', '')} - {summary.get('top_company', '')}**",
        "",
        f"- Decision safety gate: **{decision_gate.get('status', 'Ready')}**",
        f"- Gate reason: **{decision_gate_detail(summary)}**",
        f"- {action_label}: **{action_value}**",
        f"- Score: **{summary.get('top_score', '')}/100**",
        f"- {summary.get('amount_label', 'Buy capacity')}: **{summary.get('suggested_amount_text', '')}**",
        f"- Current price: **{summary.get('current_price_text', '')}**",
        f"- Blended target: **{summary.get('target_text', '')}**",
        f"- One-year upside: **{summary.get('upside_text', '')}**",
        f"- Confidence: **{summary.get('confidence', '')}**",
        f"- Target quality: **{summary.get('target_quality', '')}**",
        f"- Report reliability: **{reliability.get('mode', 'n/a')}**",
        f"- Latest successful provider refresh: **{reliability.get('latest_provider_refresh', 'n/a')}**",
        "",
        *daily_decision_review_markdown_lines(context),
        *decision_safety_markdown_lines(summary),
        *coherence_lines,
        f"Reason: {summary.get('top_notes', '')}",
        "",
        "## Report Reliability",
        "",
        f"- Workflow run: **{metadata.get('workflow_run_id') or 'direct report run'}**",
        f"- Recommendation run: **{metadata.get('recommendation_run_id', '')}**",
        f"- Fresh prices: **{price_counts.get('fresh', 0)}**",
        f"- Price-history fallback prices: **{price_counts.get('fallback', 0)}**",
        f"- Stale prices: **{price_counts.get('stale', 0)}**",
        f"- Manual prices: **{price_counts.get('manual', 0)}**",
        f"- Missing prices: **{price_counts.get('missing', 0)}**",
        f"- Source-health blocker: **{source_health.get('top_blocker') or 'None'}**",
        "",
    ]
    if kind in {"daily", "end_of_day"}:
        append_table_section(lines, "Current Holdings Used", as_dict(context.get("holdings")), "No holdings found. Add an E*TRADE snapshot or manual positions.")
    target_drilldowns = as_dict(context.get("target_drilldowns"))
    append_table_section(
        lines,
        "Target Source Drilldown",
        as_dict(target_drilldowns.get("table")) or queue(context, "source_drilldown"),
        "No target-source drilldown available.",
    )
    append_table_section(lines, "Next-Day Watchlist", queue(context, "next_day"), "No watchlist candidates available.")
    append_table_section(lines, "Explanatory Decision Briefs", as_dict(context.get("decision_briefs")), "No decision briefs available.")
    append_table_section(lines, "Source Health Alerts", as_dict(source_health.get("alerts")), "No source health alerts.")
    lines.extend(["## Provider Gap Review", "", render_provider_gap_review_markdown(provider_gap_review), ""])
    append_table_section(lines, "Provider Blocker Review", as_dict(source_health.get("provider_blockers")), "No active provider blockers.")
    append_table_section(lines, "Next Ingestion Runs", as_dict(context.get("ingestion_run_plan")), "No ingestion run plan available.")
    append_table_section(lines, "Backfill Queue", as_dict(context.get("ingestion_backfill")), "No source backfill items queued.")
    append_table_section(lines, "Evidence Events", as_dict(context.get("evidence_events")), "No evidence event clusters available.")
    append_table_section(lines, "Evidence Review Queue", as_dict(context.get("evidence_review_queue")), "No evidence review queue available.")
    append_table_section(lines, "AI Synthesis Readiness By Symbol", as_dict(context.get("synthesis_readiness")), "No synthesis readiness rows available.")
    append_table_section(lines, "Source Quality", as_dict(source_quality.get("table")), "No source quality metrics available.")
    append_table_section(lines, "Source Depth Signals", as_dict(context.get("source_depth")), "No curated source-depth signals yet.")
    append_table_section(lines, "Low Relevance / Noisy Sources", as_dict(source_quality.get("low_relevance")), "No low-relevance sources flagged.")
    append_table_section(lines, "Low Confidence Matches", as_dict(source_quality.get("low_confidence_matches")), "No low-confidence matches flagged.")
    append_table_section(lines, "Insight Themes", as_dict(context.get("insight_themes")), "No insight themes found.")
    append_table_section(lines, "Decision Insight History", as_dict(context.get("decision_insight_history")), "No decision insight type changes yet.")
    append_table_section(lines, "Insight Drivers", as_dict(context.get("score_movement")), "No insight drivers found.")
    append_table_section(lines, "What To Verify Next", as_dict(context.get("verification")), "No high-priority verification checks found.")
    append_table_section(lines, "Verification Queue", queue(context, "verification"), "No open verification queue items.")
    append_table_section(lines, "Ranked Data Gap Queue", queue(context, "data_gaps"), "No high-impact data gaps found.")
    append_table_section(lines, "Trend Insights", as_dict(context.get("trend_insights")), "No trend insights found.")
    ai_analysis = as_dict(context.get("ai_analysis"))
    if ai_analysis:
        names = artifact_names(context)
        lines.extend(
            [
                "## AI Analysis Context Ready (Explanatory)",
                "",
                f"- Ready for future summarization: `{ai_analysis.get('context_path', '')}`",
                f"- Auditable AI-style briefs: `{names.get('ai_briefs_markdown', '')}`",
                "- Explanatory only; no recommendation behavior changed.",
                "",
            ]
        )
    if kind == "daily":
        append_table_section(lines, "Score Changes Since Previous Run", as_dict(context.get("score_changes")), "No score changes of 1 point or more since the previous stored run.")
        append_table_section(lines, "Ranked V1 Universe", queue(context, "full_universe"), "No ranked universe rows available.")
        storage_counts = as_dict(context.get("storage_counts"))
        lines.extend(
            [
                "## Notes",
                "",
                "- This report is decision support, not automated trading.",
                "- Low-confidence, wide-range, partial-blend, or verification-blocked candidates stay visible for review but cannot be labeled as the recommended next buy.",
                "- E*TRADE holdings use the latest production read-only snapshot when available; otherwise manual positions are used.",
                f"- Target-source storage captured {storage_counts.get('target_sources', 0)} target inputs.",
                f"- Blended target storage captured {storage_counts.get('blended_targets', 0)} blended targets.",
                f"- Recommendation score storage captured {storage_counts.get('scores', 0)} score rows.",
                f"- Insight signal storage captured {storage_counts.get('score_signals', 0)} active signal rows.",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def append_table_section(lines: list[str], title: str, table: dict[str, Any], empty_text: str) -> None:
    lines.extend([f"## {title}", ""])
    rows = as_list(table.get("rows"))
    rendered = markdown_table(as_list(table.get("headers")), rows)
    lines.append(rendered if rendered else empty_text)
    lines.append("")


def render_email(context: dict[str, object]) -> str:
    metadata = as_dict(context.get("metadata"))
    summary = normalized_summary(context)
    reliability = as_dict(context.get("reliability"))
    source_health = as_dict(context.get("source_health"))
    artifacts = artifact_names(context)
    email = as_dict(context.get("email"))
    recipient = text(email.get("recipient"))
    subject = text(email.get("subject") or f"Stock Trading Daily Report - {metadata.get('report_date', 'n/a')}")
    decision_gate = as_dict(summary.get("decision_gate"))
    action_label = "Action" if decision_gate.get("safe_to_buy", True) else "Candidate action"
    action_value = summary.get("top_action", "")
    if not decision_gate.get("safe_to_buy", True):
        action_value = text(decision_gate.get("candidate_action") or action_value).replace(" blocked", "")
    return f"""To: {recipient}
Subject: {subject}

Daily stock trading summary for {metadata.get('report_date', 'n/a')}

{summary.get('recommendation_label', 'Top candidate')}: {summary.get('top_symbol', '')} - {summary.get('top_company', '')}
Decision safety gate: {decision_gate.get('status', 'Ready')}
Gate reason: {decision_gate_detail(summary)}
{action_label}: {action_value}
Score: {summary.get('top_score', '')}/100
{summary.get('amount_label', 'Buy capacity')}: {summary.get('suggested_amount_text', '')}
Current price: {summary.get('current_price_text', '')}
Blended target: {summary.get('target_text', '')}
One-year upside: {summary.get('upside_text', '')}
Confidence: {summary.get('confidence', '')}
Source health: {source_health.get('summary', {})}
Report reliability: {reliability.get('mode', 'n/a')}
Latest successful provider refresh: {reliability.get('latest_provider_refresh', 'n/a')}
Workflow run: {metadata.get('workflow_run_id') or 'direct report run'}
Recommendation run: {metadata.get('recommendation_run_id', '')}

Reason:
{summary.get('top_notes', '')}

Top source blocker:
{source_health.get('top_blocker') or 'No active source blockers.'}

Dashboard:
{artifacts['dashboard']}

CSV export:
{artifacts['csv']}

End-of-day review:
{artifacts['end_of_day']}

Next-day watchlist:
{artifacts['watchlist']}

Report context:
{artifacts['context']}

Note: This is a generated decision-support summary. It does not place trades, and blocked candidates are review-only until the decision-safety gate clears.
"""


def render_csv(context: dict[str, object], path: Path) -> None:
    fieldnames = [
        "rank",
        "symbol",
        "company",
        "sleeve",
        "trade_type",
        "action",
        "score",
        "current_price",
        "target_price",
        "upside_pct",
        "data_status",
        "sources",
        "score_breakdown",
        "why",
        "confidence",
        "notes",
    ]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for item in recommendations(context):
            writer.writerow(item)


def render_report_context(context: dict[str, object], output_dir: Path) -> list[Path]:
    context = normalized_report_context(context)
    output_dir.mkdir(parents=True, exist_ok=True)
    names = artifact_names(context)
    paths = {
        key: output_dir / name
        for key, name in names.items()
    }
    dashboard = render_dashboard_html(context)
    paths["dashboard"].write_text(dashboard)
    paths["markdown"].write_text(render_markdown(context, "daily"))
    render_csv(context, paths["csv"])
    paths["email"].write_text(render_email(context))
    paths["end_of_day"].write_text(render_markdown(context, "end_of_day"))
    paths["watchlist"].write_text(render_markdown(context, "watchlist"))
    paths["context"].write_text(json.dumps(context, indent=2))
    brief_paths = write_ai_brief_artifacts(context, output_dir, names)
    return [
        paths["markdown"],
        paths["dashboard"],
        paths["csv"],
        paths["email"],
        paths["end_of_day"],
        paths["watchlist"],
        paths["context"],
        *brief_paths,
    ]
