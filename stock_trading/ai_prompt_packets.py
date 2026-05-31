"""Deterministic source-backed prompt packets for future AI research briefs."""

from __future__ import annotations

import json
from typing import Any


PACKET_VERSION = "ai-prompt-packets-v1"
RECOMMENDATION_ONLY_INSTRUCTION = (
    "Recommendation-only decision support. Do not place trades, preview orders, "
    "guarantee performance, or change scores, actions, targets, target confidence, "
    "suggested amounts, decision gates, watchlist eligibility, broker behavior, or allocation rules."
)
WEAK_CORROBORATION = {"company_only", "opinion_only", "single_source", "uncorroborated", "needs_review"}
LOW_CONFIDENCE = {"low", "needs_review", "weak"}


def as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def text(value: object, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def number(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def table_rows(table: object) -> list[dict[str, object]]:
    table_dict = as_dict(table)
    headers = [text(header) for header in as_list(table_dict.get("headers"))]
    if not headers:
        return []
    rows: list[dict[str, object]] = []
    for raw_row in as_list(table_dict.get("rows")):
        values = as_list(raw_row)
        rows.append({header: values[index] if index < len(values) else "" for index, header in enumerate(headers)})
    return rows


def rows_from_context(context: dict[str, object], *keys: str) -> list[dict[str, object]]:
    current: object = context
    for key in keys:
        current = as_dict(current).get(key)
    if isinstance(current, dict):
        return table_rows(current)
    rows = as_list(current)
    return [as_dict(row) for row in rows if isinstance(row, dict)]


def recommendations_from_context(context: dict[str, object]) -> list[dict[str, object]]:
    recommendations = [as_dict(row) for row in as_list(context.get("recommendations")) if isinstance(row, dict)]
    return sorted(recommendations, key=lambda row: int(number(row.get("rank"), 9999)))


def by_symbol(rows: list[dict[str, object]], symbol_keys: tuple[str, ...] = ("symbol", "Symbol")) -> dict[str, list[dict[str, object]]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        symbol = ""
        for key in symbol_keys:
            symbol = text(row.get(key)).upper()
            if symbol:
                break
        if symbol:
            grouped.setdefault(symbol, []).append(row)
    return grouped


def latest_by_symbol(rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    grouped = by_symbol(rows)
    return {symbol: values[0] for symbol, values in grouped.items() if values}


def score_summary(recommendation: dict[str, object]) -> dict[str, object]:
    explanation = as_dict(recommendation.get("score_explanation"))
    top_drivers = [
        {"label": text(row.get("label")), "points": number(row.get("points"))}
        for row in as_list(explanation.get("top_drivers"))
        if isinstance(row, dict)
    ]
    top_risks = [
        {"label": text(row.get("label")), "points": number(row.get("points"))}
        for row in as_list(explanation.get("top_risks"))
        if isinstance(row, dict)
    ]
    return {
        "score": recommendation.get("score"),
        "model": text(explanation.get("model") or recommendation.get("trade_type")),
        "summary": text(recommendation.get("score_breakdown") or recommendation.get("rationale") or recommendation.get("why")),
        "top_drivers": top_drivers,
        "top_risks": top_risks,
    }


def target_summary(recommendation: dict[str, object], target_drilldowns: dict[str, object]) -> dict[str, object]:
    symbol = text(recommendation.get("symbol")).upper()
    drilldown = as_dict(target_drilldowns.get(symbol) or recommendation.get("target_drilldown"))
    source_rows = []
    for source in as_list(drilldown.get("sources")):
        row = as_dict(source)
        source_rows.append(
            {
                "target_type": text(row.get("target_type") or row.get("original_target_type")),
                "source_name": text(row.get("source_name")),
                "source_type": text(row.get("source_type")),
                "target_price_text": text(row.get("target_price_text")),
                "range_text": text(row.get("range_text")),
                "freshness": text(row.get("freshness")),
                "confidence": text(row.get("confidence")),
                "notes": text(row.get("notes")),
            }
        )
    return {
        "confidence": text(recommendation.get("confidence")),
        "data_status": text(recommendation.get("data_status")),
        "target_price": recommendation.get("target_price"),
        "target_price_text": text(recommendation.get("target_price_text")),
        "upside_pct": recommendation.get("upside_pct"),
        "upside_text": text(recommendation.get("upside_text")),
        "blend_label": text(drilldown.get("blend_label")),
        "blend_status": text(drilldown.get("blend_status")),
        "labels": [text(label) for label in as_list(drilldown.get("labels"))],
        "source_count": int(number(drilldown.get("source_count"), 0)),
        "sources": source_rows,
    }


def decision_safety_for_symbol(context: dict[str, object], recommendation: dict[str, object]) -> dict[str, object]:
    symbol = text(recommendation.get("symbol")).upper()
    summary_gate = as_dict(as_dict(context.get("summary")).get("decision_gate"))
    if text(as_dict(context.get("summary")).get("top_symbol")).upper() == symbol and summary_gate:
        gate = summary_gate
    else:
        gate = as_dict(context.get("decision_safety"))
    return {
        "status": text(gate.get("status") or "Review"),
        "safe_to_buy": bool(gate.get("safe_to_buy", False)),
        "candidate_action": text(gate.get("candidate_action") or recommendation.get("action")),
        "blocked_reasons": [text(reason) for reason in as_list(gate.get("reasons"))],
        "summary": text(gate.get("summary")),
    }


def normalize_gap(row: dict[str, object]) -> dict[str, object]:
    return {
        "severity": text(row.get("Severity") or row.get("severity")),
        "provider": text(row.get("Provider") or row.get("provider") or row.get("Source")),
        "field": text(row.get("Field") or row.get("field_name") or row.get("Data Gap")),
        "blocks": text(row.get("Blocks") or row.get("Impact")),
        "likely_cause": text(row.get("Likely Cause") or row.get("Latest Issue")),
        "latest_detail": text(row.get("Latest Detail") or row.get("Result")),
        "next_action": text(row.get("Next Action") or row.get("Best Pull")),
    }


def evidence_row_symbol(row: dict[str, object]) -> str:
    return text(row.get("Symbol") or row.get("symbol")).upper()


def evidence_payload(row: dict[str, object], source: str) -> dict[str, object]:
    return {
        "source_table": source,
        "event_date": text(row.get("Event Date") or row.get("event_date") or row.get("As Of") or row.get("Timestamp")),
        "event_type": text(row.get("Event Type") or row.get("event_type") or row.get("Depth Type") or row.get("Type")),
        "headline": text(row.get("Headline") or row.get("headline") or row.get("Signal") or row.get("Title")),
        "summary": text(row.get("Summary") or row.get("summary") or row.get("Detail")),
        "source_name": text(row.get("Source") or row.get("source_name") or row.get("IR Source")),
        "source_url": text(row.get("Source URL") or row.get("source_url")),
        "corroboration_label": text(row.get("Corroboration") or row.get("corroboration_label")),
        "confidence": text(row.get("Confidence") or row.get("confidence")),
        "source_count": row.get("Sources") or row.get("source_count"),
        "evidence_count": row.get("Evidence") or row.get("evidence_count"),
    }


def exclusion_reason(row: dict[str, object]) -> str:
    confidence = text(row.get("Confidence") or row.get("confidence")).lower()
    corroboration = text(row.get("Corroboration") or row.get("corroboration_label")).lower()
    source_mix = text(row.get("Source Mix") or row.get("source_mix")).lower()
    headline = text(row.get("Headline") or row.get("Title") or row.get("headline")).lower()
    latest = text(row.get("Latest Issue") or row.get("Why Review") or row.get("latest_issue")).lower()
    if confidence in LOW_CONFIDENCE or "low" in confidence:
        return "low-confidence evidence"
    if corroboration in WEAK_CORROBORATION:
        return f"weak corroboration: {corroboration}"
    if "opinion" in source_mix and "primary 0" in source_mix and "independent 0" in source_mix:
        return "opinion-only evidence"
    if "company_only" in corroboration or "official_company_source" in corroboration:
        return "company-only evidence; use with corroboration"
    if "stale" in latest or "stale" in headline:
        return "stale evidence"
    if "noisy" in latest or "duplicate" in latest or "weak symbol" in latest:
        return "noisy or duplicate evidence"
    return ""


def split_evidence(rows: list[dict[str, object]], source: str, limit: int) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    usable: list[dict[str, object]] = []
    excluded: list[dict[str, object]] = []
    for row in rows:
        payload = evidence_payload(row, source)
        reason = exclusion_reason(row)
        if reason:
            payload["exclusion_reason"] = reason
            excluded.append(payload)
            continue
        usable.append(payload)
    return usable[:limit], excluded[:limit]


def synthesis_status(context: dict[str, object]) -> dict[str, dict[str, object]]:
    return latest_by_symbol(rows_from_context(context, "synthesis_readiness"))


def verification_by_symbol(context: dict[str, object]) -> dict[str, list[dict[str, object]]]:
    rows = rows_from_context(context, "verification")
    if not rows:
        rows = rows_from_context(context, "queues", "verification")
    return by_symbol(rows)


def provider_gaps_by_symbol(context: dict[str, object]) -> dict[str, list[dict[str, object]]]:
    blocker_rows = rows_from_context(context, "source_health", "provider_blockers")
    gap_rows = rows_from_context(context, "queues", "data_gaps") + rows_from_context(context, "data_gaps")
    grouped = by_symbol(blocker_rows)
    for symbol, rows in by_symbol(gap_rows).items():
        grouped.setdefault(symbol, []).extend(rows)
    return grouped


def evidence_sections(context: dict[str, object]) -> tuple[dict[str, list[dict[str, object]]], dict[str, list[dict[str, object]]]]:
    evidence_events = by_symbol(rows_from_context(context, "evidence_events"))
    source_depth = by_symbol(rows_from_context(context, "source_depth"))
    low_confidence = by_symbol(rows_from_context(context, "source_quality", "low_confidence_matches"))
    usable_by_symbol: dict[str, list[dict[str, object]]] = {}
    excluded_by_symbol: dict[str, list[dict[str, object]]] = {}
    for symbol in sorted(set(evidence_events) | set(source_depth) | set(low_confidence)):
        usable_events, excluded_events = split_evidence(evidence_events.get(symbol, []), "evidence_events", 6)
        usable_depth, excluded_depth = split_evidence(source_depth.get(symbol, []), "source_depth", 6)
        _, noisy = split_evidence(low_confidence.get(symbol, []), "low_confidence_matches", 6)
        usable_by_symbol[symbol] = [*usable_events, *usable_depth][:8]
        excluded_by_symbol[symbol] = [*excluded_events, *excluded_depth, *noisy][:8]
    return usable_by_symbol, excluded_by_symbol


def classify_evidence(usable: list[dict[str, object]]) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    bull_terms = ("growth", "demand", "launch", "platform", "capacity", "guidance", "margin", "ai", "infrastructure")
    bear_terms = ("risk", "weak", "bear", "stale", "miss", "blocked", "rate", "lawsuit", "competition", "valuation")
    recent_terms = ("update", "launch", "filing", "earnings", "guidance", "recent")
    bull: list[dict[str, object]] = []
    bear: list[dict[str, object]] = []
    changed: list[dict[str, object]] = []
    for item in usable:
        haystack = " ".join(text(item.get(key)).lower() for key in ("event_type", "headline", "summary"))
        if any(term in haystack for term in bear_terms):
            bear.append(item)
        elif any(term in haystack for term in bull_terms):
            bull.append(item)
        if any(term in haystack for term in recent_terms):
            changed.append(item)
    return bull[:4], bear[:4], changed[:4]


def view_change_text(recommendation: dict[str, object], verification: list[dict[str, object]], gaps: list[dict[str, object]]) -> str:
    explicit = text(recommendation.get("what_would_change_the_view"))
    if explicit:
        return explicit
    if verification:
        return "The view changes after the listed verification items are resolved with fresh, corroborated evidence."
    if gaps:
        return "The view changes if provider/source gaps close or reveal stale, missing, or contradictory evidence."
    return "The view changes if fresh primary or independently corroborated evidence contradicts the current thesis."


def build_prompt_packet_context(context: dict[str, object], *, limit: int = 8) -> dict[str, object]:
    metadata = as_dict(context.get("metadata"))
    report_date = text(metadata.get("report_date"))
    target_drilldowns = as_dict(as_dict(context.get("target_drilldowns")).get("by_symbol"))
    synthesis = synthesis_status(context)
    verification = verification_by_symbol(context)
    gaps = provider_gaps_by_symbol(context)
    usable_evidence, excluded_evidence = evidence_sections(context)

    packets: list[dict[str, object]] = []
    for recommendation in recommendations_from_context(context)[:limit]:
        symbol = text(recommendation.get("symbol")).upper()
        if not symbol:
            continue
        symbol_usable = usable_evidence.get(symbol, [])
        symbol_excluded = excluded_evidence.get(symbol, [])
        bull, bear, changed = classify_evidence(symbol_usable)
        symbol_gaps = [normalize_gap(row) for row in gaps.get(symbol, [])]
        symbol_verification = [
            {
                "status": text(row.get("Status") or row.get("status")),
                "type": text(row.get("Type") or row.get("type")),
                "reason": text(row.get("Reason") or row.get("Risk Or Uncertainty") or row.get("Data Gap")),
                "next_check": text(row.get("Command/Next Check") or row.get("Next Check") or row.get("Next Action")),
                "result": text(row.get("Result")),
            }
            for row in verification.get(symbol, [])
        ]
        readiness = as_dict(synthesis.get(symbol))
        packet = {
            "symbol": symbol,
            "company": text(recommendation.get("company")),
            "report_date": report_date,
            "current_action": text(recommendation.get("action")),
            "score": recommendation.get("score"),
            "score_explanation_summary": score_summary(recommendation),
            "target_context": target_summary(recommendation, target_drilldowns),
            "decision_safety": decision_safety_for_symbol(context, recommendation),
            "provider_source_gaps": symbol_gaps,
            "synthesis_readiness": {
                "status": text(readiness.get("Readiness") or readiness.get("readiness_status") or "not_enough_data"),
                "score": text(readiness.get("Score") or readiness.get("readiness_score")),
                "ready_events": readiness.get("Ready Events") or readiness.get("ready_events") or 0,
                "needs_review": readiness.get("Needs Review") or readiness.get("needs_review_events") or 0,
                "needs_corroboration": readiness.get("Needs Corroboration") or readiness.get("needs_corroboration_events") or 0,
                "packet_ref": text(readiness.get("Packet") or readiness.get("packet_ref")),
                "notes": text(readiness.get("Notes") or readiness.get("notes")),
            },
            "top_usable_evidence_events": symbol_usable,
            "source_attribution": [
                {
                    "source_name": text(item.get("source_name")),
                    "source_table": text(item.get("source_table")),
                    "source_url": text(item.get("source_url")),
                    "corroboration_label": text(item.get("corroboration_label")),
                    "confidence": text(item.get("confidence")),
                }
                for item in symbol_usable
            ],
            "bull_case_evidence": bull,
            "bear_risk_evidence": bear,
            "what_changed_recently": changed,
            "what_needs_verification": symbol_verification,
            "what_would_change_the_view": view_change_text(recommendation, symbol_verification, symbol_gaps),
            "excluded_or_flagged_evidence": symbol_excluded,
            "instructions": {
                "recommendation_only": RECOMMENDATION_ONLY_INSTRUCTION,
                "explanatory_only": "Use this packet only to draft explanatory research synthesis. Do not modify deterministic outputs.",
                "missing_evidence_handling": "Name weak, stale, missing, low-confidence, company-only, opinion-only, or uncorroborated evidence explicitly.",
            },
        }
        packets.append(packet)
    return {
        "metadata": {
            "packet_version": PACKET_VERSION,
            "report_date": report_date,
            "generated_at": text(metadata.get("generated_at")),
            "llm_generated": False,
            "source_context": "report_context",
            "recommendation_only": True,
        },
        "packets": packets,
    }


def to_jsonable(packet_context: dict[str, object]) -> dict[str, object]:
    json.dumps(packet_context, sort_keys=True)
    return packet_context
