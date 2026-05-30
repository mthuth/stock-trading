"""Deterministic, auditable AI-style insight briefs.

These briefs are intentionally not LLM-generated. They package the existing
decision insight, score movement, verification queue, source-health rows, and
evidence event clusters into shareable summaries with explicit source references.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any


BRIEF_VERSION = "ai-briefs-v1.10"


def as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def text(value: object, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def number_text(value: object, default: str = "n/a") -> str:
    try:
        return f"{float(value):.1f}"
    except (TypeError, ValueError):
        return default


def table_rows(table: object) -> list[dict[str, object]]:
    table_dict = as_dict(table)
    headers = [text(header) for header in as_list(table_dict.get("headers"))]
    rows = as_list(table_dict.get("rows"))
    if not headers:
        return []
    result: list[dict[str, object]] = []
    for row in rows:
        values = as_list(row)
        result.append({header: values[index] if index < len(values) else "" for index, header in enumerate(headers)})
    return result


def decision_insights_from_context(context: dict[str, object]) -> list[dict[str, object]]:
    direct_rows = as_list(context.get("decision_insights"))
    if direct_rows:
        return [as_dict(row) for row in direct_rows]
    ai_rows = as_list(as_dict(context.get("ai_analysis")).get("decision_insights"))
    return [as_dict(row) for row in ai_rows]


def verification_queue_from_context(context: dict[str, object]) -> list[dict[str, object]]:
    direct_rows = as_list(context.get("verification_queue"))
    if direct_rows and all(isinstance(row, dict) for row in direct_rows):
        return [as_dict(row) for row in direct_rows]
    ai_rows = as_list(as_dict(context.get("ai_analysis")).get("verification_queue"))
    if ai_rows:
        return [as_dict(row) for row in ai_rows]
    return table_rows(as_dict(context.get("queues")).get("verification"))


def provider_blockers_from_context(context: dict[str, object]) -> list[dict[str, object]]:
    source_health = as_dict(context.get("source_health"))
    blockers = source_health.get("provider_blockers")
    if isinstance(blockers, dict):
        return table_rows(blockers)
    headers = ["Severity", "Symbol", "Provider", "Field", "Blocks", "Likely Cause", "Decision Context", "Latest Detail", "Next Action"]
    rows = as_list(blockers)
    result: list[dict[str, object]] = []
    for row in rows:
        values = as_list(row)
        result.append({header: values[index] if index < len(values) else "" for index, header in enumerate(headers)})
    return result


def score_movement_by_symbol(context: dict[str, object]) -> dict[str, dict[str, object]]:
    return {
        text(row.get("Symbol")).upper(): row
        for row in table_rows(context.get("score_movement"))
        if row.get("Symbol")
    }


def trend_by_symbol(context: dict[str, object]) -> dict[str, dict[str, object]]:
    return {
        text(row.get("Symbol")).upper(): row
        for row in table_rows(context.get("trend_insights"))
        if row.get("Symbol")
    }


def evidence_events_from_context(context: dict[str, object]) -> list[dict[str, object]]:
    direct = context.get("evidence_events")
    if isinstance(direct, dict):
        return table_rows(direct)
    rows = as_list(direct)
    if rows and all(isinstance(row, dict) for row in rows):
        return [as_dict(row) for row in rows]
    ai_rows = as_dict(context.get("ai_analysis")).get("evidence_events")
    if isinstance(ai_rows, dict):
        return table_rows(ai_rows)
    return [as_dict(row) for row in as_list(ai_rows)]


def synthesis_readiness_from_context(context: dict[str, object]) -> list[dict[str, object]]:
    direct = context.get("synthesis_readiness")
    if isinstance(direct, dict):
        return table_rows(direct)
    ai_rows = as_dict(context.get("ai_analysis")).get("synthesis_readiness")
    if isinstance(ai_rows, dict):
        return table_rows(ai_rows)
    return [as_dict(row) for row in as_list(ai_rows)]


def latest_queue_by_symbol(rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for row in rows:
        symbol = text(row.get("symbol") or row.get("Symbol")).upper()
        if symbol and symbol not in result:
            result[symbol] = row
    return result


def blockers_by_symbol(rows: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    result: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        symbol = text(row.get("Symbol") or row.get("symbol")).upper()
        if symbol:
            result.setdefault(symbol, []).append(row)
    return result


def evidence_by_symbol(rows: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    result: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        symbol = text(row.get("Symbol") or row.get("symbol")).upper()
        if symbol:
            result.setdefault(symbol, []).append(row)
    return result


def synthesis_by_symbol(rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    return {
        text(row.get("Symbol") or row.get("symbol")).upper(): row
        for row in rows
        if row.get("Symbol") or row.get("symbol")
    }


def movement_summary(row: dict[str, object]) -> str:
    if not row:
        return "Score movement was not available in the current context."
    return (
        f"Base {row.get('Base', 'n/a')} plus evidence {row.get('Evidence', 'n/a')}, "
        f"trend {row.get('Trend', 'n/a')}, target {row.get('Targets', 'n/a')}, "
        f"and gap {row.get('Gaps', 'n/a')} produced final {row.get('Final', 'n/a')}."
    )


def provider_summary(rows: list[dict[str, object]]) -> str:
    if not rows:
        return "No active provider blocker is tied directly to this symbol."
    first = rows[0]
    return (
        f"{first.get('Provider', 'Provider')} {first.get('Field', 'field')} is blocking "
        f"{first.get('Blocks', 'insight confidence')} due to {first.get('Likely Cause', 'provider review needed')}."
    )


def queue_summary(row: dict[str, object]) -> str:
    if not row:
        return "No open verification queue item is tied directly to this symbol."
    status = row.get("status") or row.get("Status") or "queued"
    reason = row.get("reason") or row.get("Reason") or "verification needed"
    command = row.get("command_mapping") or row.get("Command/Next Check") or row.get("next_check") or ""
    return f"Verification queue is {status}: {reason}. Next command/check: {command}."


def evidence_summary(rows: list[dict[str, object]]) -> str:
    if not rows:
        return "No clustered evidence event is tied directly to this symbol yet."
    first = rows[0]
    headline = text(first.get("Headline") or first.get("headline"), "Evidence event")
    event_type = text(first.get("Event Type") or first.get("event_type"), "event")
    corroboration = text(first.get("Corroboration") or first.get("corroboration_label"), "uncorroborated")
    evidence_count = text(first.get("Evidence") or first.get("evidence_count"), "0")
    source_count = text(first.get("Sources") or first.get("source_count"), "0")
    return (
        f"Top evidence event is {event_type}: {headline} "
        f"({evidence_count} evidence item(s), {source_count} source(s), {corroboration})."
    )


def synthesis_summary(row: dict[str, object]) -> str:
    if not row:
        return "No synthesis-readiness packet is available for this symbol yet."
    return (
        f"Synthesis readiness is {row.get('Readiness') or row.get('readiness_status')} "
        f"with {row.get('Ready Events') or row.get('ready_events') or 0} ready event(s), "
        f"{row.get('Needs Review') or row.get('needs_review_events') or 0} review item(s), "
        f"and packet {row.get('Packet') or row.get('packet_ref') or 'n/a'}."
    )


def build_ai_insight_briefs(context: dict[str, object], limit: int = 8) -> dict[str, object]:
    metadata = as_dict(context.get("metadata"))
    decisions = sorted(
        decision_insights_from_context(context),
        key=lambda row: int(float(row.get("rank") or row.get("Rank") or 9999)),
    )
    movements = score_movement_by_symbol(context)
    trends = trend_by_symbol(context)
    queue = latest_queue_by_symbol(verification_queue_from_context(context))
    blockers = blockers_by_symbol(provider_blockers_from_context(context))
    evidence_events = evidence_by_symbol(evidence_events_from_context(context))
    synthesis = synthesis_by_symbol(synthesis_readiness_from_context(context))

    briefs: list[dict[str, object]] = []
    for row in decisions[:limit]:
        symbol = text(row.get("symbol") or row.get("Symbol")).upper()
        if not symbol:
            continue
        movement = movements.get(symbol, {})
        trend = trends.get(symbol, {})
        queue_row = queue.get(symbol, {})
        blocker_rows = blockers.get(symbol, [])
        evidence_rows = evidence_events.get(symbol, [])
        synthesis_row = synthesis.get(symbol, {})
        score = row.get("score") or row.get("Score") or movement.get("Final")
        insight_type = text(row.get("insight_type") or row.get("Type"), "Insight")
        action = text(row.get("action") or row.get("Action"), "Review")
        headline = text(row.get("headline") or row.get("Headline") or f"{symbol} needs review.")
        uncertainty = text(row.get("risk_or_uncertainty") or row.get("Risk Or Uncertainty") or provider_summary(blocker_rows))
        next_check = text(row.get("next_check") or row.get("Next Check") or queue_row.get("next_check") or queue_row.get("Command/Next Check"))
        brief = (
            f"{symbol} is {action} at {number_text(score)}/100 and is classified as {insight_type}. "
            f"{headline} {movement_summary(movement)} "
            f"{evidence_summary(evidence_rows)} {synthesis_summary(synthesis_row)} "
            f"{provider_summary(blocker_rows)} {queue_summary(queue_row)}"
        )
        refs = [
            f"decision_insights:{symbol}",
            f"score_movement:{symbol}" if movement else "",
            f"trend_insights:{symbol}" if trend else "",
            f"evidence_events:{symbol}" if evidence_rows else "",
            f"synthesis_readiness:{symbol}" if synthesis_row else "",
            f"verification_queue:{symbol}" if queue_row else "",
            f"provider_blockers:{symbol}" if blocker_rows else "",
        ]
        briefs.append(
            {
                "symbol": symbol,
                "rank": int(float(row.get("rank") or row.get("Rank") or len(briefs) + 1)),
                "action": action,
                "score": float(score) if str(score).replace(".", "", 1).replace("-", "", 1).isdigit() else score,
                "insight_type": insight_type,
                "headline": headline,
                "brief": brief,
                "why_it_matters": text(row.get("why_it_matters") or row.get("Why It Matters")),
                "supporting_data": [
                    text(row.get("supporting_data") or row.get("Supporting Data")),
                    movement_summary(movement),
                    evidence_summary(evidence_rows),
                    synthesis_summary(synthesis_row),
                    text(trend.get("Trend Insight") or ""),
                ],
                "evidence_events": evidence_rows[:3],
                "synthesis_readiness": synthesis_row,
                "risk_or_uncertainty": uncertainty,
                "next_check": next_check,
                "what_would_change_the_view": text(row.get("what_would_change_the_view") or row.get("What Would Change The View")),
                "audit_refs": [ref for ref in refs if ref],
            }
        )

    return {
        "metadata": {
            "report_date": metadata.get("report_date", ""),
            "generated_at": metadata.get("generated_at", ""),
            "brief_version": BRIEF_VERSION,
            "llm_generated": False,
            "source_context": as_dict(context.get("artifacts")).get("context") or metadata.get("purpose", "report_context"),
        },
        "briefs": briefs,
    }


def render_ai_briefs_markdown(brief_context: dict[str, object]) -> str:
    metadata = as_dict(brief_context.get("metadata"))
    lines = [
        f"# AI Insight Briefs - {metadata.get('report_date', 'n/a')}",
        "",
        "Deterministic summary for future AI analysis. No LLM generated these briefs.",
        "",
    ]
    for brief in [as_dict(item) for item in as_list(brief_context.get("briefs"))]:
        lines.extend(
            [
                f"## {brief.get('symbol', '')} - {brief.get('insight_type', 'Insight')}",
                "",
                text(brief.get("brief")),
                "",
                f"- Why it matters: {brief.get('why_it_matters', '')}",
                f"- Risk or uncertainty: {brief.get('risk_or_uncertainty', '')}",
                f"- Next check: `{brief.get('next_check', '')}`",
                f"- What would change the view: {brief.get('what_would_change_the_view', '')}",
                f"- Audit refs: {', '.join(text(ref) for ref in as_list(brief.get('audit_refs')))}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def render_ai_briefs_html(brief_context: dict[str, object]) -> str:
    metadata = as_dict(brief_context.get("metadata"))
    cards = []
    for brief in [as_dict(item) for item in as_list(brief_context.get("briefs"))]:
        refs = ", ".join(text(ref) for ref in as_list(brief.get("audit_refs")))
        cards.append(
            "<section>"
            f"<h2>{html.escape(text(brief.get('symbol')))} - {html.escape(text(brief.get('insight_type')))}</h2>"
            f"<p>{html.escape(text(brief.get('brief')))}</p>"
            f"<p><strong>Risk:</strong> {html.escape(text(brief.get('risk_or_uncertainty')))}</p>"
            f"<p><strong>Next check:</strong> {html.escape(text(brief.get('next_check')))}</p>"
            f"<p><strong>Audit refs:</strong> {html.escape(refs)}</p>"
            "</section>"
        )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AI Insight Briefs - {html.escape(text(metadata.get("report_date"), "n/a"))}</title>
  <style>
    body {{ font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; margin:0; background:#f6f7f9; color:#18202a; line-height:1.45; }}
    main {{ max-width:960px; margin:0 auto; padding:24px; }}
    header,section {{ background:#fff; border:1px solid #d8dde5; border-radius:8px; padding:16px; margin-bottom:14px; }}
    h1,h2 {{ margin:0 0 8px; }} p {{ margin:8px 0; }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>AI Insight Briefs</h1>
      <p>Deterministic summary for future AI analysis. LLM generated: false.</p>
    </header>
    {"".join(cards)}
  </main>
</body>
</html>
"""


def write_ai_brief_artifacts(context: dict[str, object], output_dir: Path, names: dict[str, str]) -> list[Path]:
    brief_context = build_ai_insight_briefs(context)
    markdown_path = output_dir / text(names.get("ai_briefs_markdown"))
    json_path = output_dir / text(names.get("ai_briefs_json"))
    html_path = output_dir / text(names.get("ai_briefs_html"))
    markdown_path.write_text(render_ai_briefs_markdown(brief_context))
    json_path.write_text(json.dumps(brief_context, indent=2))
    html_path.write_text(render_ai_briefs_html(brief_context))
    return [markdown_path, json_path, html_path]
