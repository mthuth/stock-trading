"""Optional LLM-drafted research briefs from approved prompt packets.

This module is deliberately side-effect free: it does not call live model
providers by itself, mutate deterministic analysis outputs, or update storage.
Callers must pass an explicit client to draft briefs.
"""

from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from stock_trading.ai_brief_guardrails import validate_ai_brief, validate_ai_briefs
from stock_trading.ai_prompt_packets import RECOMMENDATION_ONLY_INSTRUCTION


BRIEF_VERSION = "llm-research-briefs-v1"
READY_STATUSES = {"ready_for_ai_synthesis", "partially_ready"}
DISCLAIMER = (
    "AI-generated Recommendation-only decision support; this brief does not place trades, "
    "preview orders, guarantee performance, or change scores, actions, targets, target "
    "confidence, suggested amounts, decision gates, watchlist eligibility, broker behavior, "
    "or allocation rules."
)
REQUIRED_LLM_FIELDS = {
    "summary",
    "bull_case",
    "bear_case",
    "key_evidence",
    "open_data_gaps",
    "what_would_change_the_view",
}


class LLMResearchBriefClient(Protocol):
    provider: str
    model: str

    def draft_research_brief(self, prompt: str, packet: dict[str, object]) -> dict[str, object]:
        """Return a JSON-like brief draft for one prompt packet."""


class MockLLMResearchBriefClient:
    """Deterministic local client for CLI dry runs and tests."""

    provider = "mock"
    model = "mock-research-brief-v1"

    def draft_research_brief(self, prompt: str, packet: dict[str, object]) -> dict[str, object]:
        symbol = text(packet.get("symbol"))
        evidence = as_list(packet.get("top_usable_evidence_events"))
        bull = as_list(packet.get("bull_case_evidence"))
        bear = as_list(packet.get("bear_risk_evidence"))
        gaps = as_list(packet.get("provider_source_gaps"))
        first_evidence = as_dict(evidence[0]) if evidence else {}
        first_bull = as_dict(bull[0]) if bull else first_evidence
        first_bear = as_dict(bear[0]) if bear else {}
        return {
            "summary": f"{symbol} has a source-backed setup, but the brief remains explanatory only.",
            "bull_case": text(first_bull.get("summary") or first_bull.get("headline") or "Usable evidence supports the bull case."),
            "bear_case": text(first_bear.get("summary") or first_bear.get("headline") or "Risks remain tied to valuation, execution, or source freshness."),
            "key_evidence": [
                text(row.get("headline") or row.get("summary") or row.get("source_name"))
                for row in [as_dict(item) for item in evidence[:3]]
                if text(row.get("headline") or row.get("summary") or row.get("source_name"))
            ],
            "open_data_gaps": [
                text(row.get("field") or row.get("latest_detail") or row.get("next_action"))
                for row in [as_dict(item) for item in gaps[:3]]
                if text(row.get("field") or row.get("latest_detail") or row.get("next_action"))
            ] or ["No major data gaps found."],
            "what_would_change_the_view": text(
                packet.get("what_would_change_the_view"),
                "Fresh primary or independently corroborated evidence contradicting the thesis would change the view.",
            ),
        }


def as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def text(value: object, default: str = "") -> str:
    if value is None:
        return default
    result = str(value).strip()
    return result if result else default


def generated_at_text(value: str | None = None) -> str:
    return value or datetime.utcnow().isoformat(timespec="seconds")


def packet_readiness(packet: dict[str, object]) -> str:
    readiness = as_dict(packet.get("synthesis_readiness"))
    return text(
        readiness.get("status")
        or readiness.get("readiness_status")
        or packet.get("readiness_status")
        or "not_enough_data"
    )


def packet_source_references(packet: dict[str, object]) -> list[dict[str, object]]:
    refs: list[dict[str, object]] = []
    for item in [as_dict(row) for row in as_list(packet.get("source_attribution"))]:
        source_name = text(item.get("source_name") or item.get("source_table"))
        if not source_name:
            continue
        refs.append(
            {
                "source_name": source_name,
                "source_table": text(item.get("source_table")),
                "source_url": text(item.get("source_url")),
                "corroboration_label": text(item.get("corroboration_label")),
                "confidence": text(item.get("confidence")),
            }
        )
    if refs:
        return refs
    for item in [as_dict(row) for row in as_list(packet.get("top_usable_evidence_events"))]:
        source_name = text(item.get("source_name") or item.get("source_table"))
        if source_name:
            refs.append({"source_name": source_name, "source_table": text(item.get("source_table"))})
    return refs


def audit_refs(packet: dict[str, object]) -> list[str]:
    symbol = text(packet.get("symbol")).upper()
    refs = [f"ai_prompt_packet:{symbol}"] if symbol else ["ai_prompt_packet"]
    if as_list(packet.get("top_usable_evidence_events")):
        refs.append(f"prompt_packet_evidence:{symbol}")
    if as_list(packet.get("provider_source_gaps")):
        refs.append(f"prompt_packet_gaps:{symbol}")
    if as_dict(packet.get("target_context")):
        refs.append(f"target_context:{symbol}")
    return refs


def source_reference_labels(refs: list[dict[str, object]]) -> list[str]:
    labels = []
    for ref in refs:
        label = text(ref.get("source_name") or ref.get("source_table"))
        if label:
            labels.append(label)
    return labels


def build_research_brief_prompt(packet: dict[str, object]) -> str:
    """Build a constrained prompt from one approved packet."""

    prompt_packet = {
        "symbol": packet.get("symbol"),
        "company": packet.get("company"),
        "readiness_status": packet_readiness(packet),
        "score_explanation_summary": packet.get("score_explanation_summary"),
        "target_context": packet.get("target_context"),
        "decision_safety": packet.get("decision_safety"),
        "top_usable_evidence_events": packet.get("top_usable_evidence_events"),
        "bull_case_evidence": packet.get("bull_case_evidence"),
        "bear_risk_evidence": packet.get("bear_risk_evidence"),
        "what_changed_recently": packet.get("what_changed_recently"),
        "provider_source_gaps": packet.get("provider_source_gaps"),
        "source_attribution": packet.get("source_attribution"),
        "what_would_change_the_view": packet.get("what_would_change_the_view"),
        "instructions": {
            "return_json_only": sorted(REQUIRED_LLM_FIELDS),
            "recommendation_only": RECOMMENDATION_ONLY_INSTRUCTION,
            "explanatory_only": "Do not change deterministic scores, actions, targets, target confidence, suggested amounts, decision gates, watchlist eligibility, or allocation rules.",
        },
    }
    return json.dumps(prompt_packet, indent=2, sort_keys=True)


def refusal_brief(
    packet: dict[str, object],
    *,
    generated_at: str,
    provider: str,
    model: str,
    reason: str,
) -> dict[str, object]:
    symbol = text(packet.get("symbol")).upper()
    refs = packet_source_references(packet)
    readiness = packet_readiness(packet)
    summary = f"Not enough evidence to draft an AI research brief for {symbol}: {reason}"
    data_gaps = [text(row.get("field") or row.get("latest_detail") or row.get("next_action")) for row in [as_dict(item) for item in as_list(packet.get("provider_source_gaps"))]]
    brief = {
        "symbol": symbol,
        "company": text(packet.get("company")),
        "generated_at": generated_at,
        "provider": provider,
        "model": model,
        "llm_generated": True,
        "status": "refused",
        "readiness_status": readiness,
        "summary": summary,
        "bull_case": "Not drafted because approved source-backed evidence was insufficient.",
        "bear_case": "Not drafted because weak, stale, missing, or uncorroborated evidence must be reviewed first.",
        "key_evidence": [],
        "source_references": refs,
        "open_data_gaps": [gap for gap in data_gaps if gap] or ["Insufficient source-backed evidence for AI synthesis."],
        "what_would_change_the_view": text(
            packet.get("what_would_change_the_view"),
            "Fresh primary or independently corroborated evidence would be needed before drafting.",
        ),
        "recommendation_only_disclaimer": DISCLAIMER,
        "risk_or_uncertainty": "Insufficient evidence or readiness prevents a source-backed AI research brief.",
        "data_gaps": "Data gaps or insufficient evidence prevent AI synthesis.",
        "audit_refs": audit_refs(packet),
    }
    brief["guardrails"] = validate_ai_brief(brief).to_dict()
    return brief


def normalize_llm_response(response: object) -> dict[str, object]:
    if not isinstance(response, dict):
        raise ValueError("LLM response was not a JSON object.")
    missing = sorted(field for field in REQUIRED_LLM_FIELDS if field not in response)
    if missing:
        raise ValueError(f"LLM response missing required field(s): {', '.join(missing)}.")
    return response


def generated_brief(
    packet: dict[str, object],
    response: dict[str, object],
    *,
    generated_at: str,
    provider: str,
    model: str,
) -> dict[str, object]:
    symbol = text(packet.get("symbol")).upper()
    refs = packet_source_references(packet)
    key_evidence = [text(item) for item in as_list(response.get("key_evidence")) if text(item)]
    data_gaps = [text(item) for item in as_list(response.get("open_data_gaps")) if text(item)]
    brief = {
        "symbol": symbol,
        "company": text(packet.get("company")),
        "generated_at": generated_at,
        "provider": provider,
        "model": model,
        "llm_generated": True,
        "status": "generated",
        "readiness_status": packet_readiness(packet),
        "summary": text(response.get("summary")),
        "bull_case": text(response.get("bull_case")),
        "bear_case": text(response.get("bear_case")),
        "key_evidence": key_evidence,
        "source_references": refs,
        "open_data_gaps": data_gaps or ["No major data gaps found."],
        "what_would_change_the_view": text(response.get("what_would_change_the_view")),
        "recommendation_only_disclaimer": DISCLAIMER,
        "risk_or_uncertainty": text(response.get("bear_case")),
        "data_gaps": "; ".join(data_gaps) if data_gaps else "No major data gaps found.",
        "audit_refs": audit_refs(packet),
        "prompt_preview": build_research_brief_prompt(packet),
    }
    brief["guardrails"] = validate_ai_brief(brief).to_dict()
    return brief


def build_llm_research_briefs(
    packet_context: dict[str, object],
    *,
    client: LLMResearchBriefClient | None = None,
    generated_at: str | None = None,
    limit: int = 8,
) -> dict[str, object]:
    """Draft or refuse LLM research briefs from approved prompt packets."""

    timestamp = generated_at_text(generated_at)
    provider = getattr(client, "provider", "disabled")
    model = getattr(client, "model", "no-live-model-configured")
    briefs: list[dict[str, object]] = []
    for packet in [as_dict(item) for item in as_list(packet_context.get("packets"))[:limit]]:
        readiness = packet_readiness(packet)
        refs = packet_source_references(packet)
        if client is None:
            briefs.append(
                refusal_brief(
                    packet,
                    generated_at=timestamp,
                    provider=provider,
                    model=model,
                    reason="live model calls are disabled until an explicit LLM client/config is provided",
                )
            )
            continue
        if readiness not in READY_STATUSES:
            briefs.append(
                refusal_brief(
                    packet,
                    generated_at=timestamp,
                    provider=provider,
                    model=model,
                    reason=f"readiness status is {readiness}",
                )
            )
            continue
        if not refs:
            briefs.append(
                refusal_brief(
                    packet,
                    generated_at=timestamp,
                    provider=provider,
                    model=model,
                    reason="packet has no usable source references",
                )
            )
            continue
        try:
            prompt = build_research_brief_prompt(packet)
            response = normalize_llm_response(client.draft_research_brief(prompt, packet))
            briefs.append(
                generated_brief(
                    packet,
                    response,
                    generated_at=timestamp,
                    provider=provider,
                    model=model,
                )
            )
        except Exception as exc:  # noqa: BLE001 - brief artifact should capture provider/malformed failures.
            briefs.append(
                refusal_brief(
                    packet,
                    generated_at=timestamp,
                    provider=provider,
                    model=model,
                    reason=f"LLM draft failed: {exc}",
                )
            )

    guardrails = validate_ai_briefs(briefs)
    metadata = as_dict(packet_context.get("metadata"))
    return {
        "metadata": {
            "brief_version": BRIEF_VERSION,
            "report_date": metadata.get("report_date", ""),
            "generated_at": timestamp,
            "llm_generated": True,
            "live_model_calls_enabled": client is not None and provider != "mock",
            "provider": provider,
            "model": model,
            "source_context": "ai_prompt_packets",
            "recommendation_only": True,
            "guardrails": {key: value for key, value in guardrails.items() if key != "results"},
        },
        "briefs": briefs,
    }


def render_llm_research_briefs_markdown(brief_context: dict[str, object]) -> str:
    metadata = as_dict(brief_context.get("metadata"))
    lines = [
        f"# LLM Research Briefs - {metadata.get('report_date', 'n/a')}",
        "",
        "AI-generated, source-backed research draft artifacts. Recommendation-only decision support.",
        "",
    ]
    for brief in [as_dict(item) for item in as_list(brief_context.get("briefs"))]:
        source_refs = source_reference_labels([as_dict(ref) for ref in as_list(brief.get("source_references"))])
        lines.extend(
            [
                f"## {brief.get('symbol', '')} - {brief.get('status', 'generated')}",
                "",
                f"- Company: {brief.get('company', '')}",
                f"- Generated at: {brief.get('generated_at', '')}",
                f"- Provider/model: {brief.get('provider', '')} / {brief.get('model', '')}",
                f"- LLM generated: {str(brief.get('llm_generated')).lower()}",
                f"- Readiness: {brief.get('readiness_status', '')}",
                "",
                f"### Summary\n{brief.get('summary', '')}",
                "",
                f"### Bull Case\n{brief.get('bull_case', '')}",
                "",
                f"### Bear Case\n{brief.get('bear_case', '')}",
                "",
                "### Key Evidence",
                *[f"- {item}" for item in as_list(brief.get("key_evidence"))],
                "",
                "### Source References",
                *[f"- {item}" for item in source_refs],
                "",
                "### Open Data Gaps",
                *[f"- {item}" for item in as_list(brief.get("open_data_gaps"))],
                "",
                f"### What Would Change The View\n{brief.get('what_would_change_the_view', '')}",
                "",
                f"### Recommendation Only\n{brief.get('recommendation_only_disclaimer', '')}",
                "",
                f"- Guardrails: {as_dict(brief.get('guardrails')).get('recommended_action', 'n/a')}",
                f"- Audit refs: {', '.join(text(ref) for ref in as_list(brief.get('audit_refs')))}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def render_llm_research_briefs_html(brief_context: dict[str, object]) -> str:
    metadata = as_dict(brief_context.get("metadata"))
    cards = []
    for brief in [as_dict(item) for item in as_list(brief_context.get("briefs"))]:
        refs = ", ".join(source_reference_labels([as_dict(ref) for ref in as_list(brief.get("source_references"))]))
        evidence = "".join(f"<li>{html.escape(text(item))}</li>" for item in as_list(brief.get("key_evidence")))
        gaps = "".join(f"<li>{html.escape(text(item))}</li>" for item in as_list(brief.get("open_data_gaps")))
        cards.append(
            "<section>"
            f"<h2>{html.escape(text(brief.get('symbol')))} - {html.escape(text(brief.get('status')))}</h2>"
            f"<p><strong>Company:</strong> {html.escape(text(brief.get('company')))}</p>"
            f"<p><strong>Provider/model:</strong> {html.escape(text(brief.get('provider')))} / {html.escape(text(brief.get('model')))}</p>"
            f"<p><strong>Readiness:</strong> {html.escape(text(brief.get('readiness_status')))}</p>"
            f"<p><strong>Summary:</strong> {html.escape(text(brief.get('summary')))}</p>"
            f"<p><strong>Bull case:</strong> {html.escape(text(brief.get('bull_case')))}</p>"
            f"<p><strong>Bear case:</strong> {html.escape(text(brief.get('bear_case')))}</p>"
            f"<p><strong>Key evidence:</strong></p><ul>{evidence}</ul>"
            f"<p><strong>Source references:</strong> {html.escape(refs)}</p>"
            f"<p><strong>Open data gaps:</strong></p><ul>{gaps}</ul>"
            f"<p><strong>What would change the view:</strong> {html.escape(text(brief.get('what_would_change_the_view')))}</p>"
            f"<p><strong>Recommendation-only:</strong> {html.escape(text(brief.get('recommendation_only_disclaimer')))}</p>"
            f"<p><strong>Guardrails:</strong> {html.escape(text(as_dict(brief.get('guardrails')).get('recommended_action'), 'n/a'))}</p>"
            "</section>"
        )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>LLM Research Briefs - {html.escape(text(metadata.get("report_date"), "n/a"))}</title>
  <style>
    body {{ font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; margin:0; background:#f6f7f9; color:#18202a; line-height:1.45; }}
    main {{ max-width:960px; margin:0 auto; padding:24px; }}
    header,section {{ background:#fff; border:1px solid #d8dde5; border-radius:8px; padding:16px; margin-bottom:14px; }}
    h1,h2,h3 {{ margin:0 0 8px; }} p {{ margin:8px 0; }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>LLM Research Briefs</h1>
      <p>AI-generated source-backed draft artifacts. Recommendation-only decision support.</p>
    </header>
    {"".join(cards)}
  </main>
</body>
</html>
"""


def write_llm_research_brief_artifacts(
    brief_context: dict[str, object],
    output_dir: Path,
    report_date: str,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = output_dir / f"llm-research-briefs-{report_date}.md"
    json_path = output_dir / f"llm-research-briefs-{report_date}.json"
    html_path = output_dir / f"llm-research-briefs-{report_date}.html"
    markdown_path.write_text(render_llm_research_briefs_markdown(brief_context))
    json_path.write_text(json.dumps(brief_context, indent=2, sort_keys=True))
    html_path.write_text(render_llm_research_briefs_html(brief_context))
    return [markdown_path, json_path, html_path]


__all__ = [
    "BRIEF_VERSION",
    "LLMResearchBriefClient",
    "MockLLMResearchBriefClient",
    "build_llm_research_briefs",
    "build_research_brief_prompt",
    "render_llm_research_briefs_html",
    "render_llm_research_briefs_markdown",
    "write_llm_research_brief_artifacts",
]
