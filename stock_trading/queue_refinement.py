"""Review-only queue hierarchy and de-duplication helpers."""

from __future__ import annotations

import copy
from typing import Any, Mapping


QUEUE_DEFINITIONS: dict[str, dict[str, str]] = {
    "top5_opportunities": {
        "queue_purpose": "Top 5 Opportunities: primary first-screen summary.",
        "primary_or_drilldown": "primary",
        "related_primary_section": "",
        "why_this_queue_exists": "Answers the daily question before detailed queue drilldowns.",
    },
    "top_5_opportunities": {
        "queue_purpose": "Top 5 Opportunities: primary first-screen summary.",
        "primary_or_drilldown": "primary",
        "related_primary_section": "",
        "why_this_queue_exists": "Answers the daily question before detailed queue drilldowns.",
    },
    "action_queue": {
        "queue_purpose": "Full Audit Queue: compact drilldown for already-ranked recommendations.",
        "primary_or_drilldown": "drilldown",
        "related_primary_section": "Daily Decision Review",
        "why_this_queue_exists": "Preserves detailed recommendation audit rows without restating the primary decision.",
    },
    "long_term": {
        "queue_purpose": "Long-Term Add Queue: capital deployment candidates.",
        "primary_or_drilldown": "supporting",
        "related_primary_section": "Top 5 Opportunities",
        "why_this_queue_exists": "Shows long-term/core add context, allocation fit, and capital-deployment readiness.",
    },
    "short_term": {
        "queue_purpose": "Tactical Review Queue: review-only short-term setups.",
        "primary_or_drilldown": "supporting",
        "related_primary_section": "Top 5 Opportunities",
        "why_this_queue_exists": "Separates shorter-horizon review prompts from long-term buy/add decisions.",
    },
    "next_day": {
        "queue_purpose": "Daily Watch Queue: next-session review prompts.",
        "primary_or_drilldown": "supporting",
        "related_primary_section": "Top 5 Opportunities",
        "why_this_queue_exists": "Carries forward items that need review before the next session.",
    },
    "speculative": {
        "queue_purpose": "Speculative AI Watchlist: watchlist-first higher-upside names.",
        "primary_or_drilldown": "supporting",
        "related_primary_section": "Top 5 Opportunities",
        "why_this_queue_exists": "Keeps higher-upside ideas visible while preserving watchlist and confidence gates.",
    },
    "data_gaps": {
        "queue_purpose": "Data Maintenance Queue: provider/data work that blocks trust.",
        "primary_or_drilldown": "supporting",
        "related_primary_section": "Data Reliability Review",
        "why_this_queue_exists": "Turns missing, stale, blocked, or thin data into maintainable review work.",
    },
    "full_universe": {
        "queue_purpose": "Full Audit Queue: detailed drilldown only.",
        "primary_or_drilldown": "drilldown",
        "related_primary_section": "Top 5 Opportunities",
        "why_this_queue_exists": "Preserves complete ranking detail without competing with the primary daily answer.",
    },
}

PRIMARY_QUEUE_NAMES = ("top5_opportunities", "top_5_opportunities")
REFERENCE_QUEUE_NAMES = {"action_queue", "full_universe"}


def _as_dict(value: object) -> dict[str, Any]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _as_list(value: object) -> list[Any]:
    return copy.deepcopy(value) if isinstance(value, list) else []


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _column_lookup(headers: list[Any]) -> dict[str, int]:
    return {_text(header).lower(): index for index, header in enumerate(headers)}


def _row_cell(headers: list[Any], row: list[Any], candidates: tuple[str, ...]) -> object:
    lookup = _column_lookup(headers)
    for candidate in candidates:
        index = lookup.get(candidate.lower())
        if index is not None and index < len(row):
            return row[index]
    return ""


def _row_symbol(section: Mapping[str, object], row: object) -> str:
    return _text(_row_cell(_as_list(section.get("headers")), _as_list(row), ("Symbol", "Ticker")))


def _row_context(section_name: str, section: Mapping[str, object], row: object) -> str:
    values = _as_list(row)
    headers = _as_list(section.get("headers"))
    action = _text(_row_cell(headers, values, ("Action",)))
    kind = _text(_row_cell(headers, values, ("Type", "Trade Type", "Queue", "Context")))
    status = _text(_row_cell(headers, values, ("Status", "Data Status")))
    if section_name in {"long_term", "short_term", "speculative", "data_gaps", "next_day"}:
        return section_name
    return "|".join(part for part in (action, kind, status) if part).lower()


def _primary_sections(queues: Mapping[str, object], summary: Mapping[str, object]) -> dict[str, str]:
    primary: dict[str, str] = {}
    for name in PRIMARY_QUEUE_NAMES:
        section = _as_dict(queues.get(name))
        for row in _as_list(section.get("rows")):
            symbol = _row_symbol(section, row)
            if symbol and symbol not in primary:
                primary[symbol] = name
    top_symbol = _text(summary.get("top_symbol"))
    if top_symbol and top_symbol not in primary:
        primary[top_symbol] = "daily_decision_review"
    return primary


def _has_top5_queue(queues: Mapping[str, object]) -> bool:
    for name in PRIMARY_QUEUE_NAMES:
        section = _as_dict(queues.get(name))
        if _as_list(section.get("rows")):
            return True
    return False


def _top5_source_queue(queues: Mapping[str, object]) -> dict[str, object]:
    for name in ("action_queue", "full_universe", "long_term"):
        section = _as_dict(queues.get(name))
        if _as_list(section.get("rows")):
            return section
    return {}


def _ensure_top5_queue(queues: Mapping[str, object]) -> dict[str, object]:
    refined = _as_dict(queues)
    if _has_top5_queue(refined):
        return refined
    source = _top5_source_queue(refined)
    rows = _as_list(source.get("rows"))
    if not rows:
        return refined
    refined["top5_opportunities"] = {
        "headers": _as_list(source.get("headers")),
        "rows": rows[:5],
        "raw_columns": _as_list(source.get("raw_columns")),
        "source_queue": _text(source.get("name")) or "ranked recommendation queues",
    }
    return refined


def queue_metadata(name: str) -> dict[str, str]:
    default = {
        "queue_purpose": f"{name}: supporting review queue.",
        "primary_or_drilldown": "supporting",
        "related_primary_section": "Top 5 Opportunities",
        "why_this_queue_exists": "Adds review context without changing recommendation rankings.",
    }
    return {**default, **QUEUE_DEFINITIONS.get(name, {})}


def refine_queue_section(
    name: str,
    section: Mapping[str, object],
    primary_by_symbol: Mapping[str, str],
) -> dict[str, object]:
    """Add display metadata to one queue without mutating rows."""

    refined = _as_dict(section)
    refined.update(queue_metadata(name))
    headers = _as_list(refined.get("headers"))
    row_metadata: list[dict[str, object]] = []
    for row in _as_list(refined.get("rows")):
        symbol = _row_symbol(refined, row)
        primary = primary_by_symbol.get(symbol, "")
        duplicate = bool(symbol and primary and name in REFERENCE_QUEUE_NAMES)
        metadata = {
            "symbol": symbol,
            "queue_purpose": refined["queue_purpose"],
            "primary_or_drilldown": refined["primary_or_drilldown"],
            "related_primary_section": primary or refined["related_primary_section"],
            "why_this_queue_exists": refined["why_this_queue_exists"],
            "row_context": _row_context(name, {"headers": headers}, row),
            "duplicate_of": f"{primary}:{symbol}" if duplicate else "",
            "display_mode": "reference" if duplicate else "detail",
        }
        row_metadata.append(metadata)
    refined["row_metadata"] = row_metadata
    return refined


def refine_queue_context(context: Mapping[str, object]) -> dict[str, object]:
    """Return a copy of report context with queue hierarchy metadata.

    This helper never changes recommendation ordering, action labels, scores,
    targets, allocation values, decision safety, or source/provider behavior.
    """

    refined = _as_dict(context)
    queues = _ensure_top5_queue(_as_dict(refined.get("queues")))
    summary = _as_dict(refined.get("summary"))
    primary_by_symbol = _primary_sections(queues, summary)
    refined_queues: dict[str, object] = {}
    for name, section in queues.items():
        if isinstance(section, Mapping):
            refined_queues[name] = refine_queue_section(name, section, primary_by_symbol)
        else:
            refined_queues[name] = copy.deepcopy(section)
    refined["queues"] = refined_queues
    refined["queue_refinement"] = {
        "review_only": True,
        "recommendation_only": True,
        "primary_symbols": dict(primary_by_symbol),
        "rules": [
            "Primary queues answer the daily decision question first.",
            "Drilldown queues preserve full audit detail without restating adjacent primary rows.",
            "The same symbol may appear in a supporting queue when that queue adds distinct context.",
            "Recommendation ranking, scores, labels, targets, allocation, and decision safety are unchanged.",
        ],
    }
    return refined


__all__ = [
    "QUEUE_DEFINITIONS",
    "queue_metadata",
    "refine_queue_context",
    "refine_queue_section",
]
