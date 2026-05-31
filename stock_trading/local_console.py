"""Static local decision console rendering helpers.

The console shell is artifact/context driven. It does not run workflows, call
providers, invoke broker APIs, preview orders, or change recommendations.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Mapping


CONSOLE_VERSION = "local-decision-console-shell-v1"
RECOMMENDATION_ONLY_GUARDRAILS = (
    "Recommendation-only decision support",
    "No automatic trading",
    "No order preview",
    "No broker writes",
    "Review-only sections do not change scores, targets, actions, gates, allocation, source weights, or provider behavior",
)
SECTION_ORDER = (
    ("current_decision", "Current Decision"),
    ("capital_deployment", "Long-Term Capital Deployment"),
    ("earnings_review", "Earnings Review"),
    ("data_reliability", "Data Reliability / Provider Gaps"),
    ("ai_briefs", "AI Briefs"),
    ("learning_review", "Learning Review"),
    ("manual_journal", "Manual Journal"),
    ("outcomes", "Outcomes"),
    ("artifacts", "Artifacts / Run History"),
    ("strategy_roadmap", "Strategy / Roadmap Links"),
)


def text(value: object, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def load_local_console_manifest(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError("Local console manifest must be a JSON object.")
    return value


def _anchor(section_id: str) -> str:
    return "".join(char.lower() if char.isalnum() else "-" for char in section_id).strip("-") or "section"


def _href(value: object) -> str:
    raw = text(value)
    if not raw:
        return "#"
    if raw.startswith(("http://", "https://", "/", "./", "../")):
        return raw
    return raw.replace("\\", "/")


def _status_class(status: object) -> str:
    normalized = text(status).lower().replace("_", "-").replace(" ", "-")
    if any(token in normalized for token in ("blocked", "missing", "needs-review", "stale", "risk")):
        return "status-review"
    if any(token in normalized for token in ("ready", "current", "accepted", "reviewed", "available", "ok")):
        return "status-ready"
    if any(token in normalized for token in ("watch", "draft", "pending", "partial")):
        return "status-watch"
    return "status-neutral"


def _render_link(link: Mapping[str, object]) -> str:
    label = html.escape(text(link.get("label") or link.get("title") or link.get("path") or "Open artifact"))
    href = html.escape(_href(link.get("href") or link.get("path") or link.get("url")), quote=True)
    detail = html.escape(text(link.get("detail") or link.get("notes")))
    suffix = f"<span>{detail}</span>" if detail else ""
    return f'<li><a href="{href}">{label}</a>{suffix}</li>'


def _render_item(item: Mapping[str, object]) -> str:
    label = html.escape(text(item.get("label") or item.get("title") or item.get("name") or item.get("symbol") or "Item"))
    value = html.escape(text(item.get("value") or item.get("status") or item.get("summary") or item.get("detail")))
    detail = html.escape(text(item.get("detail") or item.get("notes") or item.get("reason")))
    href = text(item.get("href") or item.get("path") or item.get("url"))
    label_html = f'<a href="{html.escape(_href(href), quote=True)}">{label}</a>' if href else label
    meta = f"<strong>{value}</strong>" if value else ""
    body = f"<p>{detail}</p>" if detail else ""
    return f"<li>{label_html}{meta}{body}</li>"


def _render_section(section_id: str, title: str, section: Mapping[str, object]) -> str:
    status = text(section.get("status") or section.get("state") or "Review")
    summary = text(section.get("summary") or section.get("description") or section.get("empty_message"))
    review_only = bool(section.get("review_only", True))
    items = [as_dict(item) for item in as_list(section.get("items")) if isinstance(item, dict)]
    links = [as_dict(link) for link in as_list(section.get("links")) if isinstance(link, dict)]
    empty_message = text(section.get("empty_message") or "No manifest entries are available for this section yet.")

    cards = []
    if items:
        cards.append('<ul class="item-list">' + "".join(_render_item(item) for item in items) + "</ul>")
    if links:
        cards.append('<h3>Links</h3><ul class="link-list">' + "".join(_render_link(link) for link in links) + "</ul>")
    if not cards:
        cards.append(f'<p class="empty-state">{html.escape(empty_message)}</p>')
    review_badge = '<span class="badge review-only">Review-only</span>' if review_only else ""
    return f"""
    <section id="{html.escape(_anchor(section_id), quote=True)}" class="console-section">
      <div class="section-heading">
        <div>
          <p class="eyebrow">{html.escape(section_id.replace("_", " ").title())}</p>
          <h2>{html.escape(title)}</h2>
        </div>
        <div class="section-badges">
          {review_badge}
          <span class="badge {_status_class(status)}">{html.escape(status)}</span>
        </div>
      </div>
      <p class="section-summary">{html.escape(summary or empty_message)}</p>
      {"".join(cards)}
    </section>
    """


def empty_console_manifest(source_path: Path | None = None) -> dict[str, object]:
    missing = str(source_path) if source_path else "the requested manifest"
    sections = {
        section_id: {
            "status": "Missing manifest",
            "summary": (
                f"No local console manifest was found at {missing}. "
                "Generate or provide reports/local-console-manifest.json, or render with a fixture manifest."
            ),
            "review_only": True,
            "items": [],
            "links": [],
        }
        for section_id, _title in SECTION_ORDER
    }
    return {
        "metadata": {
            "title": "Local Decision Console",
            "report_date": "",
            "generated_at": "",
            "version": CONSOLE_VERSION,
            "empty_state": True,
        },
        "guardrails": list(RECOMMENDATION_ONLY_GUARDRAILS),
        "sections": sections,
    }


def manifest_from_report_context(context: Mapping[str, object]) -> dict[str, object]:
    metadata = as_dict(context.get("metadata"))
    summary = as_dict(context.get("summary"))
    artifacts = as_dict(context.get("artifacts"))
    recommendations = as_list(context.get("recommendations"))
    top = as_dict(recommendations[0]) if recommendations and isinstance(recommendations[0], dict) else {}
    report_date = text(metadata.get("report_date"))
    title_symbol = text(summary.get("top_symbol") or top.get("symbol") or "Latest recommendation")
    return {
        "metadata": {
            "title": "Local Decision Console",
            "report_date": report_date,
            "generated_at": text(metadata.get("generated_at")),
            "version": CONSOLE_VERSION,
            "source": "report_context_fallback",
        },
        "guardrails": list(RECOMMENDATION_ONLY_GUARDRAILS),
        "sections": {
            "current_decision": {
                "status": text(summary.get("decision_gate_status") or "Review"),
                "summary": text(summary.get("decision_gate_summary") or summary.get("headline") or "Latest report-context recommendation review."),
                "review_only": True,
                "items": [
                    {
                        "label": title_symbol,
                        "value": text(top.get("action") or summary.get("top_action") or "Review"),
                        "detail": text(top.get("rationale") or top.get("score_breakdown") or ""),
                    }
                ],
            },
            "artifacts": {
                "status": "Available" if artifacts else "Missing manifest",
                "summary": "Report-context artifact references are available." if artifacts else "No artifact map was found in report context.",
                "review_only": True,
                "links": [{"label": key.replace("_", " ").title(), "path": value} for key, value in artifacts.items()],
            },
        },
    }


def render_local_console(manifest: Mapping[str, object] | None, *, source_path: Path | None = None) -> str:
    data = dict(manifest or empty_console_manifest(source_path))
    metadata = as_dict(data.get("metadata"))
    sections = as_dict(data.get("sections"))
    guardrails = [text(item) for item in as_list(data.get("guardrails")) if text(item)] or list(RECOMMENDATION_ONLY_GUARDRAILS)
    title = text(metadata.get("title") or "Local Decision Console")
    report_date = text(metadata.get("report_date"))
    generated_at = text(metadata.get("generated_at"))
    source_label = text(metadata.get("source") or (str(source_path) if source_path else "manifest"))
    nav = "\n".join(
        f'<a href="#{html.escape(_anchor(section_id), quote=True)}">{html.escape(title_label)}</a>'
        for section_id, title_label in SECTION_ORDER
    )
    rendered_sections = "\n".join(
        _render_section(section_id, title_label, as_dict(sections.get(section_id)))
        for section_id, title_label in SECTION_ORDER
    )
    guardrail_html = "".join(f"<li>{html.escape(guardrail)}</li>" for guardrail in guardrails)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #172026;
      --muted: #5b6873;
      --line: #d8dee5;
      --panel: #ffffff;
      --page: #f4f6f8;
      --accent: #0f766e;
      --warn: #a16207;
      --risk: #b42318;
      --ready: #027a48;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--page);
      color: var(--ink);
      line-height: 1.45;
    }}
    header {{
      padding: 28px min(5vw, 56px);
      background: #102027;
      color: #fff;
    }}
    header p {{ max-width: 960px; margin: 8px 0 0; color: #d8e4e8; }}
    h1 {{ margin: 0; font-size: clamp(1.8rem, 3vw, 3rem); letter-spacing: 0; }}
    h2 {{ margin: 0; font-size: 1.25rem; letter-spacing: 0; }}
    h3 {{ margin: 18px 0 8px; font-size: 1rem; }}
    .meta, .guardrails, nav, main {{ padding-left: min(5vw, 56px); padding-right: min(5vw, 56px); }}
    .meta {{
      display: flex;
      gap: 16px;
      flex-wrap: wrap;
      padding-top: 14px;
      padding-bottom: 14px;
      color: var(--muted);
      background: #fff;
      border-bottom: 1px solid var(--line);
    }}
    .guardrails {{
      background: #fff7ed;
      border-bottom: 1px solid #fed7aa;
      padding-top: 14px;
      padding-bottom: 14px;
    }}
    .guardrails ul {{ margin: 8px 0 0; padding-left: 20px; }}
    nav {{
      position: sticky;
      top: 0;
      z-index: 5;
      display: flex;
      gap: 8px;
      overflow-x: auto;
      padding-top: 10px;
      padding-bottom: 10px;
      background: rgba(244, 246, 248, 0.95);
      border-bottom: 1px solid var(--line);
    }}
    nav a {{
      white-space: nowrap;
      color: var(--ink);
      text-decoration: none;
      padding: 8px 10px;
      border: 1px solid var(--line);
      background: #fff;
      border-radius: 6px;
      font-size: 0.9rem;
    }}
    main {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 16px;
      padding-top: 18px;
      padding-bottom: 40px;
    }}
    .console-section {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 18px;
      min-width: 0;
    }}
    .section-heading {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: flex-start;
    }}
    .section-badges {{ display: flex; gap: 6px; flex-wrap: wrap; justify-content: flex-end; }}
    .eyebrow {{
      margin: 0 0 4px;
      color: var(--accent);
      font-size: 0.74rem;
      text-transform: uppercase;
      font-weight: 700;
    }}
    .section-summary, .empty-state {{ color: var(--muted); }}
    .badge {{
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      padding: 4px 8px;
      font-size: 0.75rem;
      font-weight: 700;
      background: #eef2f6;
      color: var(--ink);
    }}
    .review-only {{ background: #e0f2fe; color: #075985; }}
    .status-ready {{ background: #dcfce7; color: var(--ready); }}
    .status-review {{ background: #fee2e2; color: var(--risk); }}
    .status-watch {{ background: #fef3c7; color: var(--warn); }}
    .status-neutral {{ background: #eef2f6; color: var(--muted); }}
    .item-list, .link-list {{ margin: 12px 0 0; padding-left: 18px; }}
    .item-list li, .link-list li {{ margin: 10px 0; }}
    .item-list strong {{
      display: inline-block;
      margin-left: 8px;
      color: var(--accent);
    }}
    .item-list p {{ margin: 4px 0 0; color: var(--muted); }}
    .link-list span {{ display: block; color: var(--muted); font-size: 0.88rem; }}
    a {{ color: #075985; }}
    @media (max-width: 720px) {{
      main {{ grid-template-columns: 1fr; }}
      .section-heading {{ display: block; }}
      .section-badges {{ justify-content: flex-start; margin-top: 10px; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>{html.escape(title)}</h1>
    <p>Static local shell for reviewing the latest artifacts and decision surfaces. It is not a live trading console.</p>
  </header>
  <div class="meta">
    <span>Version: {html.escape(text(metadata.get("version") or CONSOLE_VERSION))}</span>
    <span>Report date: {html.escape(report_date or "not set")}</span>
    <span>Generated: {html.escape(generated_at or "not set")}</span>
    <span>Source: {html.escape(source_label or "manifest")}</span>
  </div>
  <section class="guardrails" aria-label="Guardrails">
    <strong>Guardrails</strong>
    <ul>{guardrail_html}</ul>
  </section>
  <nav aria-label="Console sections">{nav}</nav>
  <main>{rendered_sections}</main>
</body>
</html>
"""


def write_local_console(
    *,
    output_path: Path,
    manifest_path: Path | None = None,
    report_context_path: Path | None = None,
) -> Path:
    manifest: dict[str, object]
    source_path = manifest_path
    if manifest_path and manifest_path.exists():
        manifest = load_local_console_manifest(manifest_path)
    elif report_context_path and report_context_path.exists():
        manifest = manifest_from_report_context(load_local_console_manifest(report_context_path))
        source_path = report_context_path
    else:
        manifest = empty_console_manifest(manifest_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_local_console(manifest, source_path=source_path))
    return output_path
