"""Presentation helpers for the Top 5 opportunity view."""

from __future__ import annotations

import html
from typing import Any


def _as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: object, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _money(value: object) -> str:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return "n/a"
    return f"${amount:,.2f}"


def _bucket_label(value: object) -> str:
    return _text(value, "unknown").replace("_", " ").title()


def _status_label(row: dict[str, Any]) -> str:
    status = _text(row.get("decision_gate_status"), "Review")
    capital = _text(row.get("capital_action"), "review_only").replace("_", " ")
    return f"{status} / {capital}"


def render_top5_opportunities_html(top5: dict[str, Any]) -> str:
    rows = [_as_dict(row) for row in _as_list(top5.get("rows"))]
    note = _text(
        top5.get("note"),
        "Recommendation-only Top 5 opportunity view; official recommendations are unchanged.",
    )
    if not rows:
        return (
            '<section class="top5-opportunities">'
            '<div class="section-title"><h2>Top 5 Ranked Opportunities</h2>'
            '<span class="section-note">Primary daily decision surface</span></div>'
            f'<p class="section-note">{html.escape(note)}</p>'
            "<p>No ranked opportunities are available in this report context.</p>"
            "</section>"
        )

    cards = []
    for row in rows:
        symbol = _text(row.get("symbol"))
        company = _text(row.get("company"))
        amount = _money(row.get("suggested_amount")) if row.get("suggested_amount") is not None else "n/a"
        blocker = _text(row.get("top_blocker")) or "No top blocker."
        data_gap = _text(row.get("data_gap_summary")) or "No major data gaps found."
        reason = _text(row.get("top_reason")) or "Existing ranked recommendation candidate."
        why_bits = [
            _text(row.get("why_now")),
            _text(row.get("why_this")),
        ]
        why = " ".join(bit for bit in why_bits if bit)
        if why:
            reason = f"{reason} {why}"
        cards.append(
            '<article class="action-card top5-card">'
            '<div class="action-card-head">'
            '<div class="action-card-title">'
            f'<span class="action-rank">#{html.escape(_text(row.get("rank")))}</span>'
            f'<strong>{html.escape(symbol)}</strong>'
            f'<span class="pill">{html.escape(_text(row.get("action"), "Review"))}</span>'
            "</div>"
            '<div class="action-card-score">'
            '<span class="label">Score</span>'
            f'<strong>{html.escape(_text(row.get("score"), "n/a"))}</strong>'
            "</div>"
            "</div>"
            '<div class="action-card-metrics">'
            f'<span><span class="label">Bucket</span><strong>{html.escape(_bucket_label(row.get("opportunity_bucket")))}</strong></span>'
            f'<span><span class="label">Gate / capital</span><strong>{html.escape(_status_label(row))}</strong></span>'
            f'<span><span class="label">Confidence</span><strong>{html.escape(_text(row.get("target_confidence"), "n/a"))}</strong></span>'
            f'<span><span class="label">Data</span><strong>{html.escape(_text(row.get("data_status"), "n/a"))}</strong></span>'
            f'<span><span class="label">Amount</span><strong>{html.escape(amount)}</strong></span>'
            "</div>"
            f'<p class="action-card-rationale"><strong>{html.escape(company or symbol)}</strong> · {html.escape(reason)}</p>'
            f'<p class="section-note"><strong>Blocker:</strong> {html.escape(blocker)} <strong>Data:</strong> {html.escape(data_gap)}</p>'
            "</article>"
        )

    summary = _as_dict(top5.get("summary"))
    summary_text = (
        f"{summary.get('safe_to_buy_count', 0)} decision-safe / "
        f"{summary.get('blocked_count', 0)} blocked / "
        f"{summary.get('missing_data_count', 0)} with data blockers"
    )
    hold = _text(top5.get("hold_capacity_message"))
    hold_html = f'<p class="section-note">{html.escape(hold)}</p>' if hold else ""
    return (
        '<section class="top5-opportunities">'
        '<div class="section-title"><h2>Top 5 Ranked Opportunities</h2>'
        f'<span class="section-note">Primary daily decision surface · {html.escape(summary_text)}</span></div>'
        f'<p class="section-note">{html.escape(note)}</p>'
        f"{hold_html}"
        f'<div class="action-queue-list top5-list">{"".join(cards)}</div>'
        "</section>"
    )


def top5_opportunities_markdown_lines(top5: dict[str, Any]) -> list[str]:
    rows = [_as_dict(row) for row in _as_list(top5.get("rows"))]
    lines = [
        "## Top 5 Ranked Opportunities",
        "",
        _text(
            top5.get("note"),
            "Recommendation-only Top 5 opportunity view; official recommendations are unchanged.",
        ),
        "",
    ]
    hold = _text(top5.get("hold_capacity_message"))
    if hold:
        lines.extend([f"- Capital posture: **{hold}**", ""])
    if not rows:
        lines.extend(["No ranked opportunities are available in this report context.", ""])
        return lines
    for row in rows:
        amount = _money(row.get("suggested_amount")) if row.get("suggested_amount") is not None else "n/a"
        lines.extend(
            [
                (
                    f"{row.get('rank', '')}. **{row.get('symbol', '')} - {row.get('company', '')}** "
                    f"({_bucket_label(row.get('opportunity_bucket'))})"
                ),
                (
                    f"   - Action: **{row.get('action', '')}**; score: **{row.get('score', '')}**; "
                    f"gate: **{row.get('decision_gate_status', '')}**; capital: **{row.get('capital_action', '')}**; "
                    f"amount: **{amount}**"
                ),
                f"   - Reason: {row.get('top_reason', '')}",
                f"   - Blocker: {row.get('top_blocker', '') or 'No top blocker.'}",
                f"   - Data gaps: {row.get('data_gap_summary', '') or 'No major data gaps found.'}",
                "",
            ]
        )
    return lines


__all__ = [
    "render_top5_opportunities_html",
    "top5_opportunities_markdown_lines",
]
