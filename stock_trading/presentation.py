#!/usr/bin/env python3
"""Public UX presentation facade for stock-trading report contexts."""

from __future__ import annotations

from stock_trading.reporting.renderers import (
    REPORT_SECTION_LABELS,
    REQUIRED_CONTEXT_SECTIONS,
    load_report_context,
    render_csv,
    render_dashboard_html,
    render_email,
    render_markdown,
    render_report_context,
    validate_report_context,
)

__all__ = [
    "REPORT_SECTION_LABELS",
    "REQUIRED_CONTEXT_SECTIONS",
    "load_report_context",
    "render_csv",
    "render_dashboard_html",
    "render_email",
    "render_markdown",
    "render_report_context",
    "validate_report_context",
]
