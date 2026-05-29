#!/usr/bin/env python3
"""UX presentation renderer for saved report-context data."""

from __future__ import annotations

import csv
import html
import json
from pathlib import Path
from typing import Any


def load_report_context(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def money(value: object) -> str:
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return "n/a"


def pct(value: object) -> str:
    try:
        return f"{float(value):,.1f}%"
    except (TypeError, ValueError):
        return "n/a"


def context_filename_date(context: dict[str, Any]) -> str:
    return str(context.get("metadata", {}).get("report_date") or "context")


def render_dashboard_html(context: dict[str, Any]) -> str:
    metadata = context.get("metadata", {})
    summary = context.get("summary", {})
    reliability = context.get("reliability", {})
    price_counts = reliability.get("price_counts", {}) if isinstance(reliability, dict) else {}
    recommendations = context.get("recommendations", [])
    rows = []
    for item in recommendations:
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(item.get('rank', '')))}</td>"
            f"<td>{html.escape(str(item.get('symbol', '')))}</td>"
            f"<td>{html.escape(str(item.get('company', '')))}</td>"
            f"<td>{html.escape(str(item.get('action', '')))}</td>"
            f"<td>{html.escape(str(item.get('score', '')))}</td>"
            f"<td>{html.escape(money(item.get('current_price')))}</td>"
            f"<td>{html.escape(money(item.get('target_price')))}</td>"
            f"<td>{html.escape(pct(item.get('upside_pct')))}</td>"
            f"<td>{html.escape(str(item.get('confidence', '')))}</td>"
            f"<td>{html.escape(str(item.get('data_status', '')))}</td>"
            f"<td>{html.escape(str(item.get('rationale', '')))}</td>"
            "</tr>"
        )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Stock Report Context</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 0; color: #172033; background: #f6f8fb; }}
    header, main {{ max-width: 1180px; margin: 0 auto; padding: 24px; }}
    .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }}
    .metric, section {{ background: #fff; border: 1px solid #d8e0ea; border-radius: 8px; padding: 16px; }}
    .label {{ color: #607086; font-size: 12px; text-transform: uppercase; }}
    strong {{ display: block; font-size: 22px; margin-top: 4px; }}
    table {{ width: 100%; border-collapse: collapse; background: #fff; }}
    th, td {{ text-align: left; padding: 10px; border-bottom: 1px solid #e1e7ef; vertical-align: top; }}
    th {{ font-size: 12px; text-transform: uppercase; color: #607086; }}
  </style>
</head>
<body>
  <header>
    <h1>Stock Trading Report Context</h1>
    <p>Generated from presentation context only. Recommendation-only; no automated trading.</p>
  </header>
  <main>
    <div class="summary">
      <div class="metric"><span class="label">Top Candidate</span><strong>{html.escape(str(summary.get('top_symbol', '')))}</strong>{html.escape(str(summary.get('top_action', '')))}</div>
      <div class="metric"><span class="label">Top Score</span><strong>{html.escape(str(summary.get('top_score', '')))}</strong></div>
      <div class="metric"><span class="label">Reliability</span><strong>{html.escape(str(reliability.get('mode', 'n/a')))}</strong>Fresh {html.escape(str(price_counts.get('fresh', 0)))} · stale {html.escape(str(price_counts.get('stale', 0)))} · missing {html.escape(str(price_counts.get('missing', 0)))}</div>
      <div class="metric"><span class="label">Analysis Run</span><strong>{html.escape(str(metadata.get('analysis_run_id') or 'fixture'))}</strong>Model {html.escape(str(metadata.get('model_version', 'n/a')))}</div>
    </div>
    <section>
      <h2>Recommendations</h2>
      <table>
        <thead><tr><th>Rank</th><th>Symbol</th><th>Company</th><th>Action</th><th>Score</th><th>Current</th><th>Target</th><th>Upside</th><th>Confidence</th><th>Status</th><th>Rationale</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </section>
  </main>
</body>
</html>
"""


def render_markdown(context: dict[str, Any]) -> str:
    metadata = context.get("metadata", {})
    summary = context.get("summary", {})
    reliability = context.get("reliability", {})
    lines = [
        f"# Stock Trading Report Context - {metadata.get('report_date', 'n/a')}",
        "",
        "Recommendation-only; no automated trading.",
        "",
        "## Summary",
        "",
        f"- Top candidate: **{summary.get('top_symbol', '')}**",
        f"- Action: **{summary.get('top_action', '')}**",
        f"- Score: **{summary.get('top_score', '')}**",
        f"- Reliability: **{reliability.get('mode', 'n/a')}**",
        "",
        "## Recommendations",
        "",
        "| Rank | Symbol | Action | Score | Confidence | Status | Rationale |",
        "| --- | --- | --- | ---: | --- | --- | --- |",
    ]
    for item in context.get("recommendations", []):
        lines.append(
            f"| {item.get('rank', '')} | {item.get('symbol', '')} | {item.get('action', '')} | "
            f"{item.get('score', '')} | {item.get('confidence', '')} | {item.get('data_status', '')} | "
            f"{str(item.get('rationale', '')).replace('|', '/')} |"
        )
    return "\n".join(lines) + "\n"


def render_email(context: dict[str, Any]) -> str:
    metadata = context.get("metadata", {})
    summary = context.get("summary", {})
    reliability = context.get("reliability", {})
    return f"""Subject: Stock Trading Report Context - {metadata.get('report_date', 'n/a')}

Recommendation-only; no automated trading.

Top candidate: {summary.get('top_symbol', '')}
Action: {summary.get('top_action', '')}
Score: {summary.get('top_score', '')}
Reliability: {reliability.get('mode', 'n/a')}
"""


def render_csv(context: dict[str, Any], path: Path) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "rank",
                "symbol",
                "company",
                "action",
                "score",
                "current_price",
                "target_price",
                "upside_pct",
                "confidence",
                "data_status",
                "rationale",
            ],
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(context.get("recommendations", []))


def render_report_context(context: dict[str, Any], output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    date_label = context_filename_date(context)
    dashboard_path = output_dir / f"dashboard-{date_label}.html"
    markdown_path = output_dir / f"daily-recommendation-{date_label}.md"
    csv_path = output_dir / f"daily-recommendation-{date_label}.csv"
    email_path = output_dir / f"email-summary-{date_label}.txt"
    watchlist_path = output_dir / f"next-day-watchlist-{date_label}.md"
    dashboard_path.write_text(render_dashboard_html(context))
    markdown_path.write_text(render_markdown(context))
    render_csv(context, csv_path)
    email_path.write_text(render_email(context))
    watchlist_path.write_text(render_markdown(context))
    return [dashboard_path, markdown_path, csv_path, email_path, watchlist_path]

