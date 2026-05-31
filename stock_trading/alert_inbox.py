"""Review-only alert inbox view model helpers.

The inbox groups and prioritizes already-created review alerts for future local
console or report display. It does not create trading alerts, execute commands,
call providers, mutate recommendations, or integrate with broker behavior.
"""

from __future__ import annotations

import copy
from datetime import date, datetime
from typing import Iterable, Mapping


SEVERITY_ORDER = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
    "info": 4,
    "unknown": 5,
}
STATUS_ORDER = {
    "new": 0,
    "seen": 1,
    "active": 2,
    "open": 2,
    "deferred": 3,
    "dismissed": 4,
    "resolved": 5,
    "unknown": 6,
}
REVIEW_AREAS = {
    "capital_deployment",
    "earnings_review",
    "tactical_review",
    "provider_data",
    "ai_briefs",
    "model_learning",
    "local_console",
}
DEFAULT_TOP_LIMIT = 5
RECOMMENDATION_ONLY_NOTE = (
    "Review-only alert inbox for manual decision support. Alerts do not change "
    "scores, actions, targets, decision safety, allocation, provider behavior, "
    "source weights, model tuning, broker behavior, order preview, or trading."
)


def _text(value: object, default: str = "") -> str:
    if value is None or value == "":
        return default
    return str(value).strip()


def _token(value: object, default: str = "unknown") -> str:
    raw = _text(value, default).lower().replace("-", "_").replace(" ", "_")
    return raw or default


def _as_set(value: object | Iterable[object] | None) -> set[str]:
    if value is None or value == "":
        return set()
    if isinstance(value, str):
        values: Iterable[object] = [value]
    else:
        try:
            values = value  # type: ignore[assignment]
        except TypeError:
            values = [value]
    return {_token(item) for item in values if _text(item)}


def _parse_date(value: object) -> datetime | None:
    raw = _text(value)
    if not raw:
        return None
    for candidate in (raw, raw[:10]):
        try:
            parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
            return parsed.replace(tzinfo=None)
        except ValueError:
            continue
    return None


def _iso_today(value: object | None) -> str:
    parsed = _parse_date(value)
    if parsed:
        return parsed.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return _text(value, date.today().isoformat())


def _review_area(alert_type: str, explicit: object) -> str:
    area = _token(explicit, "")
    if area in REVIEW_AREAS:
        return area
    alert = _token(alert_type)
    if any(token in alert for token in ("capital", "add_candidate", "decision_gate", "watchlist")):
        return "capital_deployment"
    if "earning" in alert:
        return "earnings_review"
    if "tactical" in alert or "setup" in alert:
        return "tactical_review"
    if any(token in alert for token in ("provider", "data_gap", "source", "price", "target_confidence")):
        return "provider_data"
    if "ai" in alert or "brief" in alert or "guardrail" in alert:
        return "ai_briefs"
    if any(token in alert for token in ("outcome", "model", "benchmark", "source_usefulness")):
        return "model_learning"
    return "local_console"


def normalize_alert(row: Mapping[str, object], *, index: int = 0) -> dict[str, object]:
    """Normalize a loose alert row into the alert inbox contract."""

    alert_type = _token(row.get("alert_type") or row.get("type"))
    severity = _token(row.get("severity"), "medium")
    if severity not in SEVERITY_ORDER:
        severity = "unknown"
    status = _token(row.get("status"), "new")
    if status not in STATUS_ORDER:
        status = "unknown"
    created_at = _text(row.get("created_at") or row.get("updated_at") or row.get("report_date"))
    symbol = _text(row.get("symbol")).upper()
    normalized = {
        "alert_id": _text(row.get("alert_id") or row.get("id"), f"alert-{index + 1}"),
        "symbol": symbol,
        "company": _text(row.get("company")),
        "alert_type": alert_type,
        "review_area": _review_area(alert_type, row.get("review_area")),
        "severity": severity,
        "status": status,
        "title": _text(row.get("title"), alert_type.replace("_", " ").title()),
        "message": _text(row.get("message") or row.get("description") or row.get("reason")),
        "created_at": created_at,
        "report_date": _text(row.get("report_date") or created_at[:10]),
        "source": _text(row.get("source")),
        "is_stale": bool(row.get("is_stale") or row.get("stale")),
        "review_only": True,
        "recommendation_impact": "none",
        "trading_impact": "none",
    }
    return normalized


def _alert_sort_key(row: Mapping[str, object]) -> tuple[object, ...]:
    parsed = _parse_date(row.get("created_at"))
    newest_first = -parsed.timestamp() if parsed else 0
    return (
        SEVERITY_ORDER.get(_token(row.get("severity")), SEVERITY_ORDER["unknown"]),
        STATUS_ORDER.get(_token(row.get("status")), STATUS_ORDER["unknown"]),
        newest_first,
        _text(row.get("symbol")),
        _text(row.get("alert_id")),
    )


def sort_alerts(alerts: Iterable[Mapping[str, object]]) -> list[dict[str, object]]:
    return [copy.deepcopy(row) for row in sorted(alerts, key=_alert_sort_key)]


def _count_by(alerts: Iterable[Mapping[str, object]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in alerts:
        value = _token(row.get(key))
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _group_by(alerts: Iterable[Mapping[str, object]], key: str) -> dict[str, list[dict[str, object]]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in alerts:
        value = _token(row.get(key))
        grouped.setdefault(value, []).append(copy.deepcopy(dict(row)))
    return {name: sort_alerts(rows) for name, rows in sorted(grouped.items())}


def _group_by_review_area(alerts: Iterable[Mapping[str, object]]) -> dict[str, list[dict[str, object]]]:
    grouped = _group_by(alerts, "review_area")
    return {area: grouped.get(area, []) for area in sorted(REVIEW_AREAS)}


def _group_by_symbol(alerts: Iterable[Mapping[str, object]]) -> dict[str, list[dict[str, object]]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in alerts:
        symbol = _text(row.get("symbol")).upper()
        if not symbol:
            continue
        grouped.setdefault(symbol, []).append(copy.deepcopy(dict(row)))
    return {name: sort_alerts(rows) for name, rows in sorted(grouped.items())}


def _filtered(
    alerts: Iterable[Mapping[str, object]],
    *,
    status_filter: object | Iterable[object] | None,
    severity_filter: object | Iterable[object] | None,
) -> list[dict[str, object]]:
    statuses = _as_set(status_filter)
    severities = _as_set(severity_filter)
    rows: list[dict[str, object]] = []
    for row in alerts:
        status = _token(row.get("status"))
        severity = _token(row.get("severity"))
        if statuses:
            if status not in statuses:
                continue
        elif status in {"dismissed", "resolved"}:
            continue
        if severities and severity not in severities:
            continue
        rows.append(copy.deepcopy(dict(row)))
    return sort_alerts(rows)


def _active_count(alerts: Iterable[Mapping[str, object]]) -> int:
    return sum(1 for row in alerts if _token(row.get("status")) not in {"deferred", "dismissed", "resolved"})


def _empty_state(active_count: int) -> dict[str, object]:
    if active_count:
        return {"is_empty": False, "message": ""}
    return {
        "is_empty": True,
        "message": "No active review alerts. Generate or load alert rows to populate the local alert inbox.",
    }


def build_alert_inbox(
    alert_rows: Iterable[Mapping[str, object]],
    *,
    current_date: object | None = None,
    report_date: object | None = None,
    status_filter: object | Iterable[object] | None = None,
    severity_filter: object | Iterable[object] | None = None,
    top_limit: int = DEFAULT_TOP_LIMIT,
) -> dict[str, object]:
    """Build a deterministic, read-only alert inbox view model."""

    raw_rows = [copy.deepcopy(dict(row)) for row in alert_rows]
    normalized = [normalize_alert(row, index=index) for index, row in enumerate(raw_rows)]
    sorted_all = sort_alerts(normalized)
    visible = _filtered(sorted_all, status_filter=status_filter, severity_filter=severity_filter)
    active = [
        row
        for row in visible
        if _token(row.get("status")) not in {"deferred", "dismissed", "resolved"}
    ]
    stale_deferred = [
        row
        for row in visible
        if _token(row.get("status")) == "deferred" or bool(row.get("is_stale"))
    ]
    resolved_count = sum(1 for row in normalized if _token(row.get("status")) == "resolved")
    dismissed_count = sum(1 for row in normalized if _token(row.get("status")) == "dismissed")
    active_count = _active_count(visible)
    return {
        "metadata": {
            "schema_version": 1,
            "current_date": _iso_today(current_date),
            "report_date": _iso_today(report_date or current_date),
            "input_count": len(normalized),
            "visible_count": len(visible),
            "status_filter": sorted(_as_set(status_filter)),
            "severity_filter": sorted(_as_set(severity_filter)),
            "review_only": True,
            "recommendation_only": True,
            "note": RECOMMENDATION_ONLY_NOTE,
        },
        "summary": {
            "total_alerts": len(normalized),
            "visible_alerts": len(visible),
            "active_alerts": active_count,
            "top_priority_count": min(max(top_limit, 0), len(active)),
            "stale_deferred_alerts": len(stale_deferred),
            "dismissed_count": dismissed_count,
            "resolved_count": resolved_count,
            "by_severity": _count_by(visible, "severity"),
            "by_status": _count_by(visible, "status"),
            "by_review_area": _count_by(visible, "review_area"),
            "empty_state": _empty_state(active_count),
        },
        "grouped_alerts": {
            "by_severity": _group_by(visible, "severity"),
            "by_alert_type": _group_by(visible, "alert_type"),
            "by_symbol": _group_by_symbol(visible),
            "by_status": _group_by(visible, "status"),
            "by_review_area": _group_by_review_area(visible),
        },
        "top_priority_alerts": [copy.deepcopy(row) for row in active[: max(top_limit, 0)]],
        "stale_deferred_alerts": sort_alerts(stale_deferred),
        "dismissed_resolved_counts": {
            "dismissed": dismissed_count,
            "resolved": resolved_count,
        },
        "review_only": True,
        "recommendation_only_note": RECOMMENDATION_ONLY_NOTE,
    }


__all__ = [
    "DEFAULT_TOP_LIMIT",
    "RECOMMENDATION_ONLY_NOTE",
    "REVIEW_AREAS",
    "SEVERITY_ORDER",
    "STATUS_ORDER",
    "build_alert_inbox",
    "normalize_alert",
    "sort_alerts",
]
