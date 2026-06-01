"""Render the static local decision console shell."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
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
    if value is None or value == "":
        return default
    return str(value)


def esc(value: object) -> str:
    return html.escape(text(value))


def artifact_href(path: object) -> str:
    value = text(path)
    if not value:
        return ""
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate.as_uri()
    return value


def render_items(items: object) -> str:
    rows = []
    for item in as_list(items):
        row = as_dict(item)
        rows.append(f"<li><span>{esc(row.get('label'))}</span><strong>{esc(row.get('value'))}</strong></li>")
    return "<ul class=\"metric-list\">" + "".join(rows) + "</ul>" if rows else "<p class=\"muted\">No panel details available yet.</p>"


def render_panel(key: str, panel: dict[str, object]) -> str:
    links = as_list(panel.get("links"))
    body = render_items(panel.get("items"))
    if links:
        body = "<ul class=\"link-list\">" + "".join(
            f"<li><a href=\"{esc(artifact_href(link.get('path')))}\">{esc(link.get('label'))}</a></li>"
            for link in (as_dict(item) for item in links)
        ) + "</ul>"
    return (
        f"<section class=\"panel\" id=\"{esc(key)}\">"
        f"<div class=\"panel-heading\"><h2>{esc(panel.get('title'))}</h2><span>{esc(panel.get('status'))}</span></div>"
        f"{body}"
        f"<p class=\"note\">{esc(panel.get('note'))}</p>"
        "</section>"
    )


def render_artifact_table(artifacts: dict[str, object]) -> str:
    rows = []
    for item in as_list(artifacts.get("items"))[:20]:
        row = as_dict(item)
        href = artifact_href(row.get("path"))
        name = esc(row.get("file_name"))
        link = f"<a href=\"{esc(href)}\">{name}</a>" if href else name
        rows.append(
            "<tr>"
            f"<td>{esc(row.get('label'))}</td>"
            f"<td>{link}</td>"
            f"<td>{esc(row.get('report_date'))}</td>"
            f"<td>{esc(row.get('modified_at'))}</td>"
            "</tr>"
        )
    if not rows:
        rows.append(f"<tr><td colspan=\"4\">{esc(artifacts.get('empty_state') or 'No artifacts indexed yet.')}</td></tr>")
    return (
        "<section class=\"wide-panel\"><h2>Artifact Index</h2>"
        "<table><thead><tr><th>Type</th><th>File</th><th>Report date</th><th>Modified</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></section>"
    )


def render_run_table(runs: dict[str, object]) -> str:
    rows = []
    for item in as_list(runs.get("workflow_runs"))[:8]:
        row = as_dict(item)
        rows.append(
            "<tr>"
            f"<td>Workflow #{esc(row.get('id'))}</td>"
            f"<td>{esc(row.get('status'))}</td>"
            f"<td>{esc(row.get('trigger'))}</td>"
            f"<td>{esc(row.get('started_at'))}</td>"
            f"<td>{esc(row.get('summary') or row.get('message'))}</td>"
            "</tr>"
        )
    for item in as_list(runs.get("recommendation_runs"))[:8]:
        row = as_dict(item)
        rows.append(
            "<tr>"
            f"<td>Recommendation #{esc(row.get('id'))}</td>"
            f"<td>generated</td>"
            f"<td>{esc(row.get('report_date'))}</td>"
            f"<td>{esc(row.get('generated_at'))}</td>"
            f"<td>{esc(row.get('report_path'))}</td>"
            "</tr>"
        )
    if not rows:
        rows.append(f"<tr><td colspan=\"5\">{esc(runs.get('empty_state') or 'No run history is available yet.')}</td></tr>")
    return (
        "<section class=\"wide-panel\"><h2>Run History</h2>"
        "<table><thead><tr><th>Run</th><th>Status</th><th>Trigger/date</th><th>Timestamp</th><th>Summary</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></section>"
    )


def render_guardrails(manifest: dict[str, object]) -> str:
    items = "".join(f"<li>{esc(item)}</li>" for item in as_list(manifest.get("guardrails")))
    return f"<section class=\"guardrails\"><h2>Guardrails</h2><ul>{items}</ul></section>"


def render_workflow(manifest: dict[str, object]) -> str:
    workflow = as_dict(manifest.get("workflow"))
    return (
        "<section class=\"wide-panel\"><h2>Manual Workflow</h2>"
        "<p class=\"note\">The console is static. Run these commands manually from the repo root when you want to refresh it.</p>"
        "<ol class=\"workflow-list\">"
        f"<li><code>{esc(workflow.get('build_manifest'))}</code></li>"
        f"<li><code>{esc(workflow.get('render_console'))}</code></li>"
        f"<li>{esc(workflow.get('open_console'))}</li>"
        "</ol>"
        f"<p class=\"note\">{esc(workflow.get('note'))}</p>"
        "</section>"
    )


def render_local_console(manifest: dict[str, object]) -> str:
    panels = as_dict(manifest.get("panels"))
    report_context = as_dict(manifest.get("report_context"))
    panel_order = (
        "latest_recommendation",
        "decision_quality",
        "capital_deployment",
        "broker_readonly",
        "earnings_review",
        "tactical_review",
        "provider_reliability",
        "ai_brief_status",
        "model_evaluation",
        "alerts_review",
        "multi_model_competition",
        "learning_review",
        "manual_journal_outcomes",
        "artifacts",
        "run_history",
        "strategy_roadmap",
    )
    panel_html = "".join(render_panel(key, as_dict(panels.get(key))) for key in panel_order)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Local Decision Console</title>
  <style>
    :root {{ color-scheme: light; --bg:#f5f6f8; --panel:#fff; --text:#18202a; --muted:#647083; --line:#d9dee7; --blue:#1d5fd0; --green:#137a49; }}
    * {{ box-sizing: border-box; }}
    body {{ margin:0; background:var(--bg); color:var(--text); font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; line-height:1.45; }}
    header {{ background:#101827; color:white; padding:20px 24px; }}
    main {{ max-width:1280px; margin:0 auto; padding:18px 20px 28px; }}
    h1 {{ font-size:25px; margin:0; }}
    h2 {{ font-size:17px; margin:0; }}
    .subtle,.note,.muted {{ color:var(--muted); }}
    .subtle {{ color:#cbd5e1; margin:6px 0 0; }}
    .console-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:14px; }}
    .panel,.wide-panel,.guardrails {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:14px; margin-bottom:14px; }}
    .panel-heading {{ display:flex; justify-content:space-between; gap:12px; align-items:flex-start; margin-bottom:10px; }}
    .panel-heading span {{ color:var(--blue); font-weight:800; text-align:right; }}
    .metric-list,.link-list,.guardrails ul,.workflow-list {{ margin:0; padding-left:18px; }}
    .metric-list li {{ display:flex; justify-content:space-between; gap:12px; border-top:1px solid var(--line); padding:8px 0; }}
    .metric-list li:first-child {{ border-top:0; }}
    .metric-list span {{ color:var(--muted); }}
    .metric-list strong {{ text-align:right; }}
    .guardrails li {{ margin:4px 0; }}
    code {{ background:#eef2f7; border:1px solid var(--line); border-radius:6px; padding:2px 5px; }}
    table {{ width:100%; border-collapse:collapse; font-size:13px; }}
    th,td {{ border-top:1px solid var(--line); padding:8px; text-align:left; vertical-align:top; }}
    th {{ color:var(--muted); font-size:12px; text-transform:uppercase; }}
    a {{ color:var(--blue); }}
  </style>
</head>
<body>
  <header>
    <h1>Local Decision Console</h1>
    <p class="subtle">Recommendation-only static shell generated {esc(manifest.get("generated_at"))}. Report context: {esc(report_context.get("report_date") or "not available")}.</p>
  </header>
  <main>
    {render_guardrails(manifest)}
    <div class="console-grid">{panel_html}</div>
    {render_artifact_table(as_dict(manifest.get("artifacts")))}
    {render_run_table(as_dict(manifest.get("run_history")))}
    {render_workflow(manifest)}
  </main>
</body>
</html>
"""


def load_manifest(path: str | Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text())
    return payload if isinstance(payload, dict) else {}


def write_console(manifest: dict[str, object], output: str | Path) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_local_console(manifest))
    return path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render the static local decision console.")
    parser.add_argument("--manifest", required=True, help="Local console manifest JSON path.")
    parser.add_argument("--output", required=True, help="HTML output path.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    manifest = load_manifest(args.manifest)
    path = write_console(manifest, args.output)
    print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["load_manifest", "main", "render_local_console", "write_console"]
