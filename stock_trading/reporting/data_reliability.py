#!/usr/bin/env python3
"""Data reliability review model for report-context rendering."""

from __future__ import annotations

import html
import re
from typing import Any


def as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def text(value: object, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def plain_text(value: object) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", text(value))).split())


def table(headers: list[str], rows: list[list[object]]) -> dict[str, object]:
    return {"headers": headers, "rows": rows, "raw_columns": []}


def table_rows(section: object) -> list[list[object]]:
    return [as_list(row) for row in as_list(as_dict(section).get("rows"))]


def table_headers(section: object) -> list[str]:
    return [text(header) for header in as_list(as_dict(section).get("headers"))]


def first_rows(section: object, limit: int) -> list[list[object]]:
    return table_rows(section)[:limit]


def cell(row: list[object], index: int, default: str = "") -> str:
    return plain_text(row[index]) if index < len(row) else default


def int_value(value: object) -> int:
    try:
        return int(float(str(value or 0).replace(",", "")))
    except ValueError:
        return 0


def status_count(rows: list[list[object]], status_terms: tuple[str, ...]) -> int:
    count = 0
    for row in rows:
        row_text = " ".join(plain_text(value).lower() for value in row)
        if any(term in row_text for term in status_terms):
            count += 1
    return count


def source_depth_rows_for(context: dict[str, object], terms: tuple[str, ...]) -> list[list[object]]:
    rows = table_rows(context.get("source_depth"))
    matches = []
    for row in rows:
        row_text = " ".join(plain_text(value).lower() for value in row)
        if any(term in row_text for term in terms):
            matches.append(row)
    return matches


def fallback_primary_source_table(
    context: dict[str, object],
    explicit_section: str,
    depth_terms: tuple[str, ...],
    empty_label: str,
) -> dict[str, object]:
    explicit = as_dict(context.get(explicit_section))
    if as_list(explicit.get("rows")):
        return explicit
    rows = source_depth_rows_for(context, depth_terms)
    if rows:
        return table(table_headers(context.get("source_depth")), rows[:8])
    return table(["Coverage", "Status", "Next Action"], [[empty_label, "Needs review", "Run the matching primary-source coverage ingestion/check."]])


def provider_gap_status_table(context: dict[str, object]) -> dict[str, object]:
    source_health = as_dict(context.get("source_health"))
    provider_blockers = as_dict(source_health.get("provider_blockers"))
    rows = first_rows(provider_blockers, 8)
    if rows:
        return table(table_headers(provider_blockers), rows)
    alerts = as_dict(source_health.get("alerts"))
    return table(table_headers(alerts), first_rows(alerts, 8))


def source_health_rollup_table(context: dict[str, object]) -> dict[str, object]:
    source_health = as_dict(context.get("source_health"))
    source_quality = as_dict(context.get("source_quality"))
    summary = as_dict(source_health.get("summary"))
    quality_summary = as_dict(source_quality.get("summary"))
    rows = [
        ["Healthy sources", summary.get("healthy", 0), "No immediate action"],
        ["Needs attention", summary.get("needs_attention", 0), source_health.get("top_blocker") or "Review source health alerts"],
        ["Stale sources", summary.get("stale", 0), "Review refresh cadence and next ingestion runs"],
        ["Not implemented", summary.get("not_implemented", 0), "Keep visible as implementation backlog"],
    ]
    if quality_summary:
        rows.extend(
            [
                ["Useful sources", quality_summary.get("useful_source", quality_summary.get("useful", 0)), "Prefer for corroboration"],
                ["Noisy sources", quality_summary.get("noisy_source", quality_summary.get("noisy", 0)), "Review low-relevance/noisy table"],
                ["Parser gaps", quality_summary.get("parser_gap", quality_summary.get("parser_gap_count", 0)), "Fix parser or source mapping"],
            ]
        )
    return table(["Rollup", "Count", "Review Action"], rows)


def source_usefulness_table(context: dict[str, object]) -> dict[str, object]:
    source_quality = as_dict(context.get("source_quality"))
    quality_table = as_dict(source_quality.get("table"))
    rows = first_rows(quality_table, 8)
    if rows:
        return table(table_headers(quality_table), rows)
    low_relevance = as_dict(source_quality.get("low_relevance"))
    return table(table_headers(low_relevance), first_rows(low_relevance, 8))


def refresh_plan_table(context: dict[str, object]) -> dict[str, object]:
    plan = as_dict(context.get("ingestion_run_plan"))
    rows = first_rows(plan, 8)
    if rows:
        return table(table_headers(plan), rows)
    backfill = as_dict(context.get("ingestion_backfill"))
    return table(table_headers(backfill), first_rows(backfill, 8))


def backfill_table(context: dict[str, object]) -> dict[str, object]:
    backfill = as_dict(context.get("ingestion_backfill"))
    return table(table_headers(backfill), first_rows(backfill, 8))


def data_gap_count(context: dict[str, object]) -> int:
    data_gaps = as_dict(as_dict(context.get("queues")).get("data_gaps") or context.get("data_gaps"))
    return len(table_rows(data_gaps))


def build_data_reliability_review(context: dict[str, object]) -> dict[str, object]:
    reliability = as_dict(context.get("reliability"))
    price_counts = as_dict(reliability.get("price_counts"))
    source_health = as_dict(context.get("source_health"))
    source_summary = as_dict(source_health.get("summary") or reliability.get("source_health"))
    provider_rows = table_rows(as_dict(source_health.get("provider_blockers")))
    alert_rows = table_rows(as_dict(source_health.get("alerts")))
    plan_rows = table_rows(context.get("ingestion_run_plan"))
    backfill_rows = table_rows(context.get("ingestion_backfill"))
    source_quality = as_dict(context.get("source_quality"))
    low_relevance_rows = table_rows(as_dict(source_quality.get("low_relevance")))
    quality_rows = table_rows(as_dict(source_quality.get("table")))
    all_health_rows = provider_rows + alert_rows
    blocked_count = status_count(all_health_rows, ("blocked", "blocker", "access", "credential"))
    rate_limited_count = status_count(all_health_rows, ("rate_limited", "rate limit", "429", "quota"))
    stale_count = int_value(source_summary.get("stale")) + int_value(price_counts.get("stale"))
    missing_count = int_value(price_counts.get("missing")) + data_gap_count(context)
    noisy_count = len(low_relevance_rows) + status_count(quality_rows, ("noisy", "low relevance"))
    next_refresh = "Review ingestion plan"
    if plan_rows:
        first = plan_rows[0]
        next_refresh = f"{cell(first, 1, 'Source')} - {cell(first, 3, 'Status')}"
    elif backfill_rows:
        first = backfill_rows[0]
        next_refresh = f"{cell(first, 1, 'Source')} backfill - {cell(first, 4, 'Status')}"

    cards = [
        {
            "label": "Missing data",
            "value": str(missing_count),
            "detail": f"{price_counts.get('missing', 0)} missing price(s); {data_gap_count(context)} ranked data gap(s).",
        },
        {
            "label": "Stale data",
            "value": str(stale_count),
            "detail": f"{price_counts.get('stale', 0)} stale price(s); {source_summary.get('stale', 0)} stale source(s).",
        },
        {
            "label": "Blocked or rate-limited",
            "value": str(blocked_count + rate_limited_count),
            "detail": f"{blocked_count} blocked/access issue(s); {rate_limited_count} rate-limit issue(s).",
        },
        {
            "label": "Useful/noisy sources",
            "value": str(noisy_count),
            "detail": "Review source quality, low relevance, and low confidence matches before trusting synthesis.",
        },
        {
            "label": "Refresh next",
            "value": next_refresh,
            "detail": f"{len(plan_rows)} planned refresh row(s); {len(backfill_rows)} backfill row(s).",
        },
    ]
    return {
        "cards": cards,
        "provider_gap_status": provider_gap_status_table(context),
        "source_health_rollups": source_health_rollup_table(context),
        "sec_coverage": fallback_primary_source_table(
            context,
            "sec_coverage",
            ("sec", "filing", "companyfacts"),
            "SEC coverage",
        ),
        "official_ir_coverage": fallback_primary_source_table(
            context,
            "official_ir_coverage",
            ("official_ir", "official ir", "investor relations", "ir "),
            "Official IR coverage",
        ),
        "source_usefulness": source_usefulness_table(context),
        "refresh_plan": refresh_plan_table(context),
        "backfill": backfill_table(context),
    }
