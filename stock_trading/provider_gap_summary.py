#!/usr/bin/env python3
"""Normalize provider gaps into a daily review structure."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Iterable, Mapping, Sequence


SEVERITY_ORDER = {
    "blocker": 0,
    "review needed": 1,
    "stale/missing": 2,
    "informational": 3,
}
SEVERITY_LABELS = tuple(SEVERITY_ORDER)


def row_value(row: object, key: str) -> str:
    if isinstance(row, Mapping):
        return str(row.get(key) or "")
    try:
        return str(row[key] or "")  # type: ignore[index]
    except (KeyError, IndexError, TypeError):
        return ""


def normalized_symbol(value: object) -> str:
    symbol = str(value or "").strip().upper()
    return symbol if symbol and symbol not in {"MARKET", "GLOBAL"} else "GLOBAL"


def provider_gap_status(row: object) -> str:
    return (row_value(row, "status") or "unknown").strip().lower().replace(" ", "_")


def gap_text(provider: str, field_name: str, status: str, message: str) -> str:
    return " ".join([provider, field_name, status, message]).lower()


def provider_gap_severity(status: str, message: str, provider: str = "", field_name: str = "") -> str:
    text = gap_text(provider, field_name, status, message)
    if re.search(r"429|rate[-_ ]?limit|quota|too many requests|blocked|forbidden|unauthorized|401|403|payment required|paid|premium|upgrade|\bplan\b|credential|api[-_ ]?key|token", text):
        return "blocker"
    if status in {"blocked", "rate_limited"}:
        return "blocker"
    if status in {"stale", "missing"} or re.search(r"\bstale\b|\bmissing\b|not found|empty|no records|no target|no price", text):
        return "stale/missing"
    if status in {"not_implemented", "not implemented", "planned"} or re.search(r"not implemented|not run|planned", text):
        return "informational"
    if status in {"ok", "healthy"}:
        return "informational"
    return "review needed"


def provider_gap_issue_type(status: str, message: str, provider: str = "", field_name: str = "") -> str:
    text = gap_text(provider, field_name, status, message)
    if re.search(r"429|rate[-_ ]?limit|quota|too many requests", text):
        return "Rate limited"
    if re.search(r"blocked|forbidden|401|403|unauthorized|payment required|paid|premium|upgrade|\bplan\b|credential|api[-_ ]?key|token", text):
        return "Blocked/access"
    if re.search(r"\bstale\b", text):
        return "Stale data"
    if re.search(r"\bmissing\b|not found|empty|no records|no target|no price", text):
        return "Missing field"
    if re.search(r"parser|parse|no parseable", text):
        return "Parser gap"
    if re.search(r"not implemented|planned|not run", text):
        return "Not implemented"
    if re.search(r"dns|nodename|name resolution|urlopen|connection|timed out|network", text):
        return "Network / DNS"
    if re.search(r"5\d\d|server error|bad gateway|service unavailable|gateway timeout", text):
        return "Provider error"
    return "Provider review"


def recommended_next_action(
    severity: str,
    issue_type: str,
    provider: str,
    field_name: str,
    symbol: str,
) -> str:
    provider_text = provider.lower()
    field_text = field_name.lower()
    symbol_arg = "" if symbol == "GLOBAL" else f" --symbol {symbol}"
    if issue_type == "Rate limited":
        return "Wait for quota reset or adjust provider cadence."
    if issue_type == "Blocked/access":
        if "finnhub" in provider_text:
            return "Check FINNHUB_API_KEY or plan access, then rerun Finnhub ingestion."
        if "benzinga" in provider_text:
            return "Set BENZINGA_API_KEY or use manual analyst target fallback."
        if "sec" in provider_text or "sec" in field_text:
            return "Review SEC access/user-agent, then rerun SEC ingestion."
        if "ir" in provider_text or "official" in provider_text or "ir" in field_text:
            return "Review official IR URL/access, then rerun IR ingestion."
        return "Review provider credentials, plan access, or endpoint availability."
    if issue_type == "Stale data":
        return "Refresh the source or confirm stale data is acceptable for review."
    if issue_type == "Missing field":
        if "target" in field_text or "analyst" in field_text:
            return "Refresh analyst targets or add a manual target-source row."
        if "price" in field_text or "quote" in field_text:
            return "Refresh market data before acting on this symbol."
        return "Refresh provider data or mark the missing field as an accepted gap."
    if issue_type == "Parser gap":
        return "Inspect parser/source format before relying on this evidence."
    if issue_type == "Not implemented":
        return "Track as backlog until this source is implemented."
    if issue_type == "Network / DNS":
        return f"Retry with network access: scripts/show_provider_gaps.py{symbol_arg}"
    if severity == "blocker":
        return "Resolve provider access before treating this source as reliable."
    if severity == "review needed":
        return f"Review provider detail: scripts/show_provider_gaps.py{symbol_arg}"
    return "Keep visible for audit; no immediate action required."


def normalize_provider_gap(row: object, top_symbol: str = "") -> dict[str, object]:
    provider = row_value(row, "provider") or "Unknown provider"
    field_name = row_value(row, "field_name") or row_value(row, "endpoint") or "unknown_field"
    symbol = normalized_symbol(row_value(row, "symbol"))
    status = provider_gap_status(row)
    message = row_value(row, "message")
    last_attempted = row_value(row, "refreshed_at") or row_value(row, "last_attempted") or row_value(row, "created_at")
    last_success = row_value(row, "last_success_at") or row_value(row, "last_success")
    severity = provider_gap_severity(status, message, provider, field_name)
    issue_type = provider_gap_issue_type(status, message, provider, field_name)
    top = top_symbol.strip().upper()
    affects_top_candidate = bool(top and symbol == top)
    return {
        "severity": severity,
        "issue_type": issue_type,
        "provider": provider,
        "endpoint": field_name,
        "field_name": field_name,
        "symbol": symbol,
        "status": status,
        "latest_issue": message or status,
        "message": message,
        "last_attempted": last_attempted,
        "last_success": last_success,
        "recommended_next_action": recommended_next_action(severity, issue_type, provider, field_name, symbol),
        "affects_top_candidate": affects_top_candidate,
    }


def severity_sort_key(record: Mapping[str, object]) -> tuple[int, str, str, str]:
    return (
        SEVERITY_ORDER.get(str(record.get("severity") or ""), 9),
        "0" if record.get("affects_top_candidate") else "1",
        str(record.get("provider") or ""),
        str(record.get("symbol") or ""),
    )


def group_records(records: Sequence[dict[str, object]], key: str) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for record in records:
        grouped[str(record.get(key) or "Unknown")].append(record)
    groups: list[dict[str, object]] = []
    for label, items in grouped.items():
        items = sorted(items, key=severity_sort_key)
        groups.append(
            {
                key: label,
                "count": len(items),
                "highest_severity": str(items[0].get("severity") or "informational"),
                "affected_symbols": sorted({str(item.get("symbol") or "GLOBAL") for item in items}),
                "rows": items,
            }
        )
    groups.sort(key=lambda group: (SEVERITY_ORDER.get(str(group["highest_severity"]), 9), str(group[key])))
    return groups


def compact_rows(records: Sequence[dict[str, object]], limit: int = 12) -> list[list[object]]:
    rows: list[list[object]] = []
    for record in sorted(records, key=severity_sort_key)[:limit]:
        rows.append(
            [
                record.get("severity", ""),
                "Yes" if record.get("affects_top_candidate") else "",
                record.get("provider", ""),
                record.get("symbol", ""),
                record.get("endpoint", ""),
                record.get("status", ""),
                record.get("last_attempted", "") or "Not recorded",
                record.get("latest_issue", ""),
                record.get("recommended_next_action", ""),
            ]
        )
    return rows


def build_provider_gap_review(
    provider_gap_rows: Iterable[object],
    *,
    top_symbol: str = "",
    limit: int = 12,
) -> dict[str, object]:
    records = [
        normalize_provider_gap(row, top_symbol)
        for row in provider_gap_rows
        if provider_gap_status(row) not in {"ok", "healthy"}
    ]
    records.sort(key=severity_sort_key)
    counts = Counter(str(record.get("severity") or "informational") for record in records)
    top_records = [record for record in records if record.get("affects_top_candidate")]
    severity_groups = {
        label: [record for record in records if record.get("severity") == label]
        for label in SEVERITY_LABELS
    }
    return {
        "summary": {
            "total": len(records),
            "blocker": counts.get("blocker", 0),
            "review_needed": counts.get("review needed", 0),
            "stale_missing": counts.get("stale/missing", 0),
            "informational": counts.get("informational", 0),
            "top_candidate": top_symbol.strip().upper(),
            "top_candidate_affected": bool(top_records),
            "top_candidate_gap_count": len(top_records),
            "top_candidate_highest_severity": str(top_records[0].get("severity") if top_records else ""),
            "status_note": "Provider gaps remain visible even when report generation succeeds or a workflow finishes ok_with_warnings.",
        },
        "headers": [
            "Severity",
            "Top Candidate",
            "Provider",
            "Symbol",
            "Endpoint/Field",
            "Status",
            "Last Attempted",
            "Latest Issue",
            "Next Action",
        ],
        "rows": compact_rows(records, limit),
        "records": records,
        "severity_groups": severity_groups,
        "provider_groups": group_records(records, "provider"),
        "symbol_groups": group_records(records, "symbol"),
        "top_candidate_rows": compact_rows(top_records, limit),
    }
