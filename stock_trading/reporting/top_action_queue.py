"""Top action queue dashboard rendering helpers."""

from __future__ import annotations

import html
import re
from typing import Any


def as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def text(value: object, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def plain_text(value: object) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", text(value))).split())


def column_lookup(headers: list[str]) -> dict[str, int]:
    return {header.lower(): index for index, header in enumerate(headers)}


def row_cell(headers: list[str], row: list[Any], candidates: list[str]) -> object:
    lookup = column_lookup(headers)
    index = next((lookup.get(candidate.lower()) for candidate in candidates if candidate.lower() in lookup), None)
    if index is None or index >= len(row):
        return ""
    return row[index]


def queue(context: dict[str, object], name: str) -> dict[str, Any]:
    return as_dict(as_dict(context.get("queues")).get(name))


def html_table(headers: list[str], rows: list[list[object]], class_name: str = "compact-table") -> str:
    if not headers or not rows:
        return "<p>No rows available.</p>"
    head = "".join(f"<th>{html.escape(text(header))}</th>" for header in headers)
    body = []
    for row in rows:
        padded = [*row, *[""] * max(0, len(headers) - len(row))]
        cells = "".join(f"<td>{html.escape(plain_text(value))}</td>" for value in padded[: len(headers)])
        body.append(f"<tr>{cells}</tr>")
    return f'<table class="{class_name}"><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table>'


def matching_table_rows(
    table: dict[str, Any],
    symbol: str,
    *,
    symbol_headers: list[str] | None = None,
    limit: int = 4,
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
    return headers, [row for row in rows if symbol_index < len(row) and plain_text(row[symbol_index]) == symbol][:limit]


def recommendation_by_symbol(context: dict[str, object]) -> dict[str, dict[str, Any]]:
    return {
        text(as_dict(item).get("symbol")): as_dict(item)
        for item in as_list(context.get("recommendations"))
        if text(as_dict(item).get("symbol"))
    }


def action_label(value: object) -> str:
    return plain_text(value) or "Review"


def safe_status(context: dict[str, object], symbol: str, row_status: str, recommendation: dict[str, Any]) -> tuple[str, str, list[str]]:
    summary = as_dict(context.get("summary"))
    gate = as_dict(recommendation.get("decision_gate"))
    if not gate and text(summary.get("top_symbol")) == symbol:
        gate = as_dict(summary.get("decision_gate"))

    if gate:
        safe = bool(gate.get("safe_to_buy"))
        status = text(gate.get("status"), "Ready" if safe else "Blocked")
        reasons = [plain_text(reason) for reason in as_list(gate.get("reasons")) if plain_text(reason)]
        note = text(gate.get("summary")) or ("Passed decision-safety review." if safe else "; ".join(reasons))
        return ("Decision-safe" if safe else status or "Blocked", note, reasons)

    if row_status:
        lowered = row_status.lower()
        if any(marker in lowered for marker in ("blocked", "missing", "gap", "stale", "wide range", "partial")):
            return (
                "Review required",
                "Data issue lowers confidence/readiness; it is not a bearish thesis by itself.",
                [row_status],
            )
        return ("Review", row_status, [])

    return ("Data unavailable", "Data unavailable in this report context.", [])


def target_summary(row_headers: list[str], row: list[Any]) -> str:
    target = plain_text(row_cell(row_headers, row, ["Target", "Blended Target"]))
    upside = plain_text(row_cell(row_headers, row, ["Upside", "1Y Upside"]))
    if target and upside:
        return f"{target} / {upside}"
    return target or upside or "n/a"


def suggested_amount(context: dict[str, object], symbol: str, recommendation: dict[str, Any]) -> str:
    for key in ("suggested_amount_text", "suggested_amount", "amount_label", "capital_action"):
        value = recommendation.get(key)
        if text(value):
            return plain_text(value)
    summary = as_dict(context.get("summary"))
    if text(summary.get("top_symbol")) == symbol:
        return plain_text(summary.get("suggested_amount_text") or summary.get("amount_label") or summary.get("suggested_amount"))
    return "n/a"


def top_blocker(status_note: str, gap_rows: list[list[object]], gate_reasons: list[str]) -> str:
    if gate_reasons:
        first_reason = gate_reasons[0]
        if any(marker in first_reason.lower() for marker in ("missing", "stale", "gap", "wide range", "partial")):
            return f"{first_reason} is a reliability/readiness issue, not a bearish thesis."
        return gate_reasons[0]
    if status_note and status_note.lower() not in {"blended", "ok", "ready"}:
        return f"{status_note} is a reliability/readiness issue, not a bearish thesis."
    if gap_rows:
        return plain_text(gap_rows[0][-1]) or "Provider gap affects this symbol."
    return "No top blocker in this report context."


def provider_gap_rows(context: dict[str, object], symbol: str) -> tuple[list[str], list[list[object]]]:
    provider_gap_review = as_dict(context.get("provider_gap_review"))
    headers, rows = matching_table_rows(provider_gap_review, symbol, limit=5)
    if rows:
        return headers, rows

    source_health = as_dict(context.get("source_health"))
    return matching_table_rows(as_dict(source_health.get("provider_blockers")), symbol, limit=5)


def target_rows(context: dict[str, object], symbol: str) -> tuple[list[str], list[list[object]]]:
    target_drilldowns = as_dict(context.get("target_drilldowns"))
    symbol_targets = as_dict(as_dict(target_drilldowns.get("by_symbol")).get(symbol))
    source_rows: list[list[object]] = []
    for source in as_list(symbol_targets.get("sources")):
        source_item = as_dict(source)
        source_rows.append(
            [
                source_item.get("target_type", ""),
                source_item.get("source_name", ""),
                source_item.get("source_type", ""),
                source_item.get("target_price_text", ""),
                source_item.get("range_text", "n/a"),
                source_item.get("as_of_date", ""),
                source_item.get("confidence", ""),
            ]
        )
    if source_rows:
        return ["Type", "Source", "Source Type", "Target", "Range", "As Of", "Confidence"], source_rows

    table = as_dict(target_drilldowns.get("table")) or queue(context, "source_drilldown")
    return matching_table_rows(table, symbol, limit=5)


def score_rows(context: dict[str, object], symbol: str) -> tuple[list[str], list[list[object]]]:
    return matching_table_rows(as_dict(context.get("score_movement")), symbol, limit=5)


def score_driver_html(context: dict[str, object], symbol: str, recommendation: dict[str, Any]) -> str:
    explanation = as_dict(recommendation.get("score_explanation"))
    parts: list[str] = []
    drivers = [as_dict(item) for item in as_list(explanation.get("top_drivers"))]
    if drivers:
        items = []
        for driver in drivers[:5]:
            label = text(driver.get("label") or driver.get("key"), "Driver")
            points = driver.get("points")
            points_text = f" ({float(points):+.1f})" if isinstance(points, (int, float)) else ""
            description = text(driver.get("description"))
            items.append(f"<li><strong>{html.escape(label)}</strong>{html.escape(points_text)}{': ' + html.escape(description) if description else ''}</li>")
        parts.append(f'<div><span class="label">Top positive drivers</span><ul>{"".join(items)}</ul></div>')

    risks = [as_dict(item) for item in as_list(explanation.get("top_risks"))]
    if risks:
        items = "".join(
            f"<li><strong>{html.escape(text(risk.get('label') or risk.get('key'), 'Risk'))}</strong>: {html.escape(text(risk.get('description')))}</li>"
            for risk in risks[:5]
        )
        parts.append(f'<div><span class="label">Top risks / negative drivers</span><ul>{items}</ul></div>')

    components = [as_dict(item) for item in as_list(explanation.get("component_details"))]
    if components:
        rows = [
            [
                component.get("label", ""),
                component.get("raw", ""),
                component.get("points", ""),
                component.get("description", ""),
            ]
            for component in components
        ]
        parts.append(html_table(["Component", "Raw", "Points", "Explanation"], rows, "compact-table"))

    headers, rows = score_rows(context, symbol)
    if rows:
        parts.append(html_table(headers, rows, "compact-table"))

    if text(recommendation.get("score_breakdown")):
        parts.append(f"<p>{html.escape(text(recommendation.get('score_breakdown')))}</p>")

    if not parts:
        return "<p>No score-driver detail available.</p>"
    return "".join(parts)


def decision_review_html(
    context: dict[str, object],
    symbol: str,
    action: str,
    score: str,
    amount: str,
    row_status: str,
    confidence: str,
    recommendation: dict[str, Any],
) -> str:
    gate_label, gate_note, reasons = safe_status(context, symbol, row_status, recommendation)
    reason_items = "".join(f"<li>{html.escape(reason)}</li>" for reason in reasons) or "<li>None listed in this report context.</li>"
    ready_note = (
        "Resolve the listed blockers, refresh missing/stale data, and re-check decision safety."
        if reasons or "unavailable" in gate_label.lower() or "review" in gate_label.lower()
        else "No buy-readiness blocker is listed in this report context."
    )
    return (
        '<div class="top-action-facts">'
        f'<span><span class="label">Action</span><strong>{html.escape(action or "n/a")}</strong></span>'
        f'<span><span class="label">Score</span><strong>{html.escape(score or "n/a")}</strong></span>'
        f'<span><span class="label">Decision gate</span><strong>{html.escape(gate_label)}</strong></span>'
        f'<span><span class="label">Suggested amount / capacity</span><strong>{html.escape(amount or "n/a")}</strong></span>'
        f'<span><span class="label">Target confidence</span><strong>{html.escape(confidence or "n/a")}</strong></span>'
        f'<span><span class="label">Data status</span><strong>{html.escape(row_status or "n/a")}</strong></span>'
        "</div>"
        f"<p>{html.escape(gate_note)}</p>"
        f'<div><span class="label">Blocked reasons</span><ul>{reason_items}</ul></div>'
        f'<p><strong>What would make it buy-ready:</strong> {html.escape(ready_note)}</p>'
    )


def target_detail_html(context: dict[str, object], symbol: str, confidence: str, target: str) -> str:
    headers, rows = target_rows(context, symbol)
    intro = (
        f'<p><strong>Target confidence:</strong> {html.escape(confidence or "n/a")}. '
        f'<strong>Target/upside:</strong> {html.escape(target or "n/a")}.</p>'
    )
    if not rows:
        return intro + "<p>Data unavailable in this report context. No target-source drilldown available.</p>"
    return intro + html_table(headers, rows, "compact-table")


def provider_gap_html(context: dict[str, object], symbol: str) -> str:
    headers, rows = provider_gap_rows(context, symbol)
    if not rows:
        return "<p>No provider gaps found for this symbol.</p>"
    return html_table(headers, rows, "compact-table")


def selected_action_rows(headers: list[str], rows: list[Any], limit: int) -> list[list[Any]]:
    selected: list[list[Any]] = []
    seen: set[str] = set()
    for row in rows:
        values = as_list(row)
        symbol = plain_text(row_cell(headers, values, ["Symbol", "Ticker"]))
        dedupe_key = symbol or f"row-{len(selected)}"
        if symbol and dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        selected.append(values)
        if len(selected) >= limit:
            break
    return selected


def render_top_action_queue_html(context: dict[str, object], *, limit: int = 10) -> str:
    section = queue(context, "action_queue")
    headers = [text(header) for header in as_list(section.get("headers"))]
    rows = as_list(section.get("rows"))
    if not headers or not rows:
        return (
            '<section class="top-action-queue-section" id="top-action-queue">'
            '<div class="section-title"><h2>Top 10 Action Queue</h2><span class="section-note">Primary daily decision scan</span></div>'
            "<p>No action queue rows available.</p>"
            "</section>"
        )

    recommendations = recommendation_by_symbol(context)
    items: list[str] = []
    for row in selected_action_rows(headers, rows, limit):
        rank = plain_text(row_cell(headers, row, ["Rank"]))
        symbol = plain_text(row_cell(headers, row, ["Symbol", "Ticker"]))
        recommendation = recommendations.get(symbol, {})
        company = plain_text(recommendation.get("company") or recommendation.get("name") or row_cell(headers, row, ["Company", "Name"]))
        action = action_label(row_cell(headers, row, ["Action"]))
        score = plain_text(row_cell(headers, row, ["Score"]))
        row_status = plain_text(row_cell(headers, row, ["Data Status", "Status"]))
        confidence = plain_text(row_cell(headers, row, ["Confidence", "Target Confidence"]))
        target = target_summary(headers, row)
        amount = suggested_amount(context, symbol, recommendation)
        gap_headers, gaps = provider_gap_rows(context, symbol)
        del gap_headers
        gate_label, _gate_note, gate_reasons = safe_status(context, symbol, row_status, recommendation)
        blocker = top_blocker(row_status, gaps, gate_reasons)
        rationale = plain_text(row_cell(headers, row, ["Rationale", "Why"]) or recommendation.get("rationale") or recommendation.get("notes"))
        summary_label = f"#{rank}" if rank else "Top queue item"
        title = f"{symbol} - {company}" if company else symbol or "Unknown symbol"
        status_class = "safe" if "safe" in gate_label.lower() or "ready" in gate_label.lower() else "blocked"
        items.append(
            '<details class="top-action-item">'
            '<summary class="top-action-summary">'
            f'<span class="top-action-rank">{html.escape(summary_label)}</span>'
            '<span class="top-action-main">'
            f"<strong>{html.escape(title)}</strong>"
            f'<span>{html.escape(rationale or "No rationale available.")}</span>'
            "</span>"
            f'<span><span class="label">Action</span><strong>{html.escape(action)}</strong></span>'
            f'<span><span class="label">Score</span><strong>{html.escape(score or "n/a")}</strong></span>'
            f'<span class="top-action-status top-action-status-{status_class}"><span class="label">Gate</span><strong>{html.escape(gate_label)}</strong></span>'
            f'<span><span class="label">Amount / capacity</span><strong>{html.escape(amount or "n/a")}</strong></span>'
            f'<span><span class="label">Target / upside</span><strong>{html.escape(target)}</strong></span>'
            f'<span><span class="label">Top blocker</span><strong>{html.escape(blocker)}</strong></span>'
            "</summary>"
            '<div class="top-action-detail">'
            '<div class="top-action-detail-block">'
            "<h3>Decision Review</h3>"
            f"{decision_review_html(context, symbol, action, score, amount, row_status, confidence, recommendation)}"
            "</div>"
            '<div class="top-action-detail-block">'
            "<h3>Score Drivers</h3>"
            f"{score_driver_html(context, symbol, recommendation)}"
            "</div>"
            '<div class="top-action-detail-block">'
            "<h3>Target Sources</h3>"
            f"{target_detail_html(context, symbol, confidence, target)}"
            "</div>"
            '<div class="top-action-detail-block">'
            "<h3>Provider Gaps</h3>"
            f"{provider_gap_html(context, symbol)}"
            "</div>"
            "</div>"
            "</details>"
        )

    count_label = f"{len(items)} item" if len(items) == 1 else f"{len(items)} items"
    return (
        '<section class="top-action-queue-section" id="top-action-queue">'
        '<div class="section-title"><h2>Top 10 Action Queue</h2><span class="section-note">Primary daily decision scan</span></div>'
        f'<p class="section-note">Showing {html.escape(count_label)} from the existing ranked action queue. '
        "Expandable rows reuse existing decision, score, target, and provider-gap context.</p>"
        f'<div class="top-action-list">{"".join(items)}</div>'
        "</section>"
    )
