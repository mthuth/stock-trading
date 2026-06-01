#!/usr/bin/env python3
"""Rendering helpers for the score driver glossary."""

from __future__ import annotations

import html
from typing import Any

from stock_trading.score_driver_glossary import REVIEW_ONLY_GUARDRAIL, glossary_entries


def _entry_list(entries: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    return entries if entries is not None else glossary_entries()


def render_score_glossary_markdown(entries: list[dict[str, Any]] | None = None) -> str:
    """Render glossary entries as compact Markdown help text."""
    lines = [
        "## Score Driver Glossary",
        "",
        REVIEW_ONLY_GUARDRAIL,
        "",
    ]
    for entry in _entry_list(entries):
        lines.append(f"- **{entry.get('term', '')}**: {entry.get('definition', '')}")
    return "\n".join(lines).strip()


def render_score_glossary_html(entries: list[dict[str, Any]] | None = None) -> str:
    """Render glossary entries as a compact collapsible HTML section."""
    rows = []
    for entry in _entry_list(entries):
        term = html.escape(str(entry.get("term", "")))
        definition = html.escape(str(entry.get("definition", "")))
        plain_language = html.escape(str(entry.get("plain_language", "")))
        rows.append(
            "<tr>"
            f"<th scope=\"row\">{term}</th>"
            f"<td>{definition}<br><span class=\"muted\">{plain_language}</span></td>"
            "</tr>"
        )
    return (
        '<details class="score-driver-glossary">'
        "<summary>Score Driver Glossary</summary>"
        f"<p>{html.escape(REVIEW_ONLY_GUARDRAIL)}</p>"
        '<table class="compact-table"><thead><tr><th>Term</th><th>Plain-English meaning</th></tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table>"
        "</details>"
    )


__all__ = ["render_score_glossary_html", "render_score_glossary_markdown"]
