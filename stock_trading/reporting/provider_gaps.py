#!/usr/bin/env python3
"""Presentation helpers for provider-gap review summaries."""

from __future__ import annotations

import html
from typing import Any


def as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def text(value: object, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def severity_class(value: object) -> str:
    return text(value, "informational").lower().replace("/", "-").replace(" ", "-")


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


def html_table(headers: list[str], rows: list[list[object]]) -> str:
    if not rows:
        return "<p>No active provider gaps.</p>"
    head = "".join(f"<th>{html.escape(text(header))}</th>" for header in headers)
    body = []
    for row in rows:
        severity = row[0] if row else "informational"
        cells = "".join(f"<td>{html.escape(text(value))}</td>" for value in row)
        body.append(f'<tr class="provider-gap-severity-{html.escape(severity_class(severity))}">{cells}</tr>')
    return f'<table class="provider-gap-table"><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table>'


def provider_group_summary(groups: list[Any], key: str) -> str:
    if not groups:
        return "None"
    labels = []
    for group in groups[:4]:
        data = as_dict(group)
        label = text(data.get(key), "Unknown")
        count = text(data.get("count"), "0")
        severity = text(data.get("highest_severity"), "informational")
        labels.append(f"{label} ({count}, {severity})")
    suffix = f" +{len(groups) - 4} more" if len(groups) > 4 else ""
    return ", ".join(labels) + suffix


def render_provider_gap_review_html(review: dict[str, object]) -> str:
    summary = as_dict(review.get("summary"))
    headers = [text(header) for header in as_list(review.get("headers"))]
    rows = as_list(review.get("rows"))
    total = int(summary.get("total") or 0)
    top_symbol = text(summary.get("top_candidate"), "Top candidate") or "Top candidate"
    affected = bool(summary.get("top_candidate_affected"))
    top_status = (
        f"{top_symbol} affected by {summary.get('top_candidate_gap_count')} active gap(s)"
        if affected
        else f"{top_symbol} not directly affected by active provider gaps"
    )
    if total == 0:
        return (
            '<section class="provider-gap-review">'
            '<div class="section-title"><h2>Provider Gap Review</h2><span class="section-note">No active provider gaps</span></div>'
            "<p>No active provider gaps are blocking daily review.</p>"
            "</section>"
        )
    metrics = [
        ("Blockers", summary.get("blocker", 0), "blocker"),
        ("Review needed", summary.get("review_needed", 0), "review-needed"),
        ("Stale/missing", summary.get("stale_missing", 0), "stale-missing"),
        ("Informational", summary.get("informational", 0), "informational"),
    ]
    metric_html = "".join(
        '<span class="provider-gap-count '
        f'provider-gap-count-{html.escape(css_class)}">'
        f'<span>{html.escape(label)}</span><strong>{html.escape(text(value))}</strong></span>'
        for label, value, css_class in metrics
    )
    return (
        '<section class="provider-gap-review">'
        '<div class="section-title"><h2>Provider Gap Review</h2><span class="section-note">Grouped daily provider issues</span></div>'
        f'<div class="provider-gap-counts">{metric_html}</div>'
        f'<p><strong>{html.escape(top_status)}</strong>. {html.escape(text(summary.get("status_note")))}</p>'
        f'<p class="section-note">Top providers: {html.escape(provider_group_summary(as_list(review.get("provider_groups")), "provider"))}. '
        f'Top symbols: {html.escape(provider_group_summary(as_list(review.get("symbol_groups")), "symbol"))}.</p>'
        f"{html_table(headers, rows)}"
        "</section>"
    )


def render_provider_gap_review_markdown(review: dict[str, object]) -> str:
    summary = as_dict(review.get("summary"))
    headers = [text(header) for header in as_list(review.get("headers"))]
    rows = as_list(review.get("rows"))
    total = int(summary.get("total") or 0)
    if total == 0:
        return "No active provider gaps are blocking daily review."
    lines = [
        f"- Active provider gaps: **{total}**",
        f"- Severity counts: **{summary.get('blocker', 0)} blocker**, **{summary.get('review_needed', 0)} review needed**, **{summary.get('stale_missing', 0)} stale/missing**, **{summary.get('informational', 0)} informational**",
        f"- Top candidate affected: **{'Yes' if summary.get('top_candidate_affected') else 'No'}** ({summary.get('top_candidate') or 'n/a'})",
        f"- Note: {summary.get('status_note')}",
        "",
    ]
    table = markdown_table(headers, rows)
    lines.append(table if table else "No active provider gaps.")
    return "\n".join(lines)
