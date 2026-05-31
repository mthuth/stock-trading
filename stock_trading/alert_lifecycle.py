"""Review-only alert deduplication and lifecycle helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Mapping


REVIEW_ONLY_NOTE = (
    "Review-only alert metadata. Alerts must not automatically change scores, "
    "actions, recommendation labels, targets, target confidence, decision-safety "
    "rules, allocation, source weights, broker behavior, or trading."
)

SEVERITY_ORDER = {
    "informational": 0,
    "info": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}
CANONICAL_SEVERITY = {
    "info": "informational",
}
VALID_STATUSES = ("new", "seen", "acknowledged", "deferred", "dismissed", "resolved")
VALID_TRANSITIONS = {
    "new": {"seen", "acknowledged", "deferred", "dismissed", "resolved"},
    "seen": {"acknowledged", "deferred", "dismissed", "resolved"},
    "acknowledged": {"deferred", "dismissed", "resolved"},
    "deferred": {"dismissed", "resolved"},
    "dismissed": set(),
    "resolved": set(),
}
ACTIVE_STATUSES = {"new", "seen", "acknowledged", "deferred"}
PRESERVED_STATUSES = {"acknowledged", "dismissed"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def text(value: object) -> str:
    return str(value or "").strip()


def normalize_list(values: object) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        raw_values = [part for part in values.replace("|", ",").split(",")]
    else:
        try:
            raw_values = list(values)  # type: ignore[arg-type]
        except TypeError:
            raw_values = [values]
    normalized = sorted({text(value) for value in raw_values if text(value)})
    return normalized


def normalize_severity(value: object) -> str:
    severity = text(value).lower().replace("-", "_").replace(" ", "_")
    severity = CANONICAL_SEVERITY.get(severity, severity)
    return severity if severity in SEVERITY_ORDER else "informational"


def severity_rank(value: object) -> int:
    return SEVERITY_ORDER[normalize_severity(value)]


def highest_severity(*values: object) -> str:
    return max((normalize_severity(value) for value in values), key=severity_rank)


def normalize_status(value: object) -> str:
    status = text(value).lower().replace("-", "_").replace(" ", "_")
    return status if status in VALID_STATUSES else "new"


def event_date_for(alert: Mapping[str, object]) -> str:
    return text(alert.get("report_date") or alert.get("event_date") or alert.get("created_at"))


def dedupe_key_for(alert: Mapping[str, object]) -> str:
    provided = text(alert.get("dedupe_key"))
    if provided:
        return provided
    alert_type = text(alert.get("alert_type") or alert.get("type")).lower()
    symbol = text(alert.get("symbol")).upper()
    event_date = event_date_for(alert)
    reason_codes = "+".join(normalize_list(alert.get("reason_codes") or alert.get("reason_code")))
    source_refs = "+".join(normalize_list(alert.get("source_refs") or alert.get("source_ref")))
    key_parts = [alert_type, symbol, event_date, reason_codes, source_refs]
    return "|".join(key_parts)


def alert_id_for(alert: Mapping[str, object]) -> str:
    return text(alert.get("alert_id") or alert.get("id") or dedupe_key_for(alert))


def normalize_alert(alert: Mapping[str, object], *, created_at: str | None = None) -> dict[str, object]:
    dedupe_key = dedupe_key_for(alert)
    timestamp = created_at or text(alert.get("created_at")) or utc_now()
    updated_at = text(alert.get("updated_at")) or timestamp
    return {
        "alert_id": alert_id_for(alert),
        "dedupe_key": dedupe_key,
        "alert_type": text(alert.get("alert_type") or alert.get("type")),
        "symbol": text(alert.get("symbol")).upper(),
        "event_date": event_date_for(alert),
        "report_date": text(alert.get("report_date")),
        "reason_codes": normalize_list(alert.get("reason_codes") or alert.get("reason_code")),
        "source_refs": normalize_list(alert.get("source_refs") or alert.get("source_ref")),
        "severity": normalize_severity(alert.get("severity")),
        "status": normalize_status(alert.get("status")),
        "created_at": timestamp,
        "updated_at": updated_at,
        "last_seen_at": text(alert.get("last_seen_at")),
        "deferred_until": text(alert.get("deferred_until")),
        "occurrence_count": int(alert.get("occurrence_count") or alert.get("occurrences") or 1),
        "summary": text(alert.get("summary") or alert.get("headline")),
        "notes": text(alert.get("notes")) or REVIEW_ONLY_NOTE,
        "review_only": True,
    }


def merge_unique(existing: object, incoming: object) -> list[str]:
    return sorted({*normalize_list(existing), *normalize_list(incoming)})


def status_after_duplicate(existing: Mapping[str, object], incoming: Mapping[str, object]) -> tuple[str, str]:
    existing_status = normalize_status(existing.get("status"))
    if existing_status in PRESERVED_STATUSES and severity_rank(incoming.get("severity")) <= severity_rank(existing.get("severity")):
        return existing_status, "preserved"
    if severity_rank(incoming.get("severity")) > severity_rank(existing.get("severity")):
        return "new", "renewed"
    return existing_status, "preserved"


def collapse_duplicate(existing: Mapping[str, object], incoming: Mapping[str, object]) -> dict[str, object]:
    status, lifecycle_event = status_after_duplicate(existing, incoming)
    created_at = max(text(existing.get("created_at")), text(incoming.get("created_at")))
    updated_at = max(text(existing.get("updated_at")), text(incoming.get("updated_at")), text(incoming.get("created_at")))
    severity = highest_severity(existing.get("severity"), incoming.get("severity"))
    return {
        **existing,
        "alert_id": text(existing.get("alert_id")) or text(incoming.get("alert_id")),
        "reason_codes": merge_unique(existing.get("reason_codes"), incoming.get("reason_codes")),
        "source_refs": merge_unique(existing.get("source_refs"), incoming.get("source_refs")),
        "severity": severity,
        "status": status,
        "created_at": created_at,
        "updated_at": updated_at,
        "last_seen_at": max(text(existing.get("last_seen_at")), text(incoming.get("last_seen_at"))),
        "occurrence_count": int(existing.get("occurrence_count") or 1) + int(incoming.get("occurrence_count") or 1),
        "summary": text(incoming.get("summary")) or text(existing.get("summary")),
        "notes": text(existing.get("notes")) or REVIEW_ONLY_NOTE,
        "lifecycle_event": lifecycle_event,
        "review_only": True,
    }


def dedupe_alerts(alerts: Iterable[Mapping[str, object]]) -> dict[str, object]:
    """Collapse duplicate review alerts without mutating input rows."""

    by_key: dict[str, dict[str, object]] = {}
    duplicate_count = 0
    for alert in alerts:
        normalized = normalize_alert(alert)
        key = text(normalized.get("dedupe_key"))
        if key in by_key:
            duplicate_count += 1
            by_key[key] = collapse_duplicate(by_key[key], normalized)
        else:
            by_key[key] = normalized

    items = sorted(
        by_key.values(),
        key=lambda item: (
            -severity_rank(item.get("severity")),
            text(item.get("event_date")),
            text(item.get("symbol")),
            text(item.get("alert_type")),
        ),
    )
    return {
        "alerts": items,
        "duplicate_count": duplicate_count,
        "review_only": True,
        "notes": REVIEW_ONLY_NOTE,
    }


def transition_alert_status(
    alert: Mapping[str, object],
    status: object,
    *,
    changed_at: str | None = None,
    deferred_until: str = "",
    note: str = "",
) -> dict[str, object]:
    """Return a structured lifecycle transition result for one alert."""

    normalized = normalize_alert(alert)
    current_status = normalize_status(normalized.get("status"))
    next_status = normalize_status(status)
    errors: list[str] = []
    warnings: list[str] = []

    if text(status).lower().replace("-", "_").replace(" ", "_") not in VALID_STATUSES:
        errors.append(f"Invalid alert status: {status}.")
    elif next_status == current_status:
        warnings.append(f"Alert is already {next_status}.")
    elif next_status not in VALID_TRANSITIONS[current_status]:
        errors.append(f"Invalid alert transition: {current_status} -> {next_status}.")

    if next_status == "deferred" and not deferred_until:
        warnings.append("Deferred alert has no deferred_until value.")

    if errors:
        return {
            "ok": False,
            "alert": normalized,
            "errors": errors,
            "warnings": warnings,
            "review_only": True,
        }

    updated = {
        **normalized,
        "status": next_status,
        "updated_at": changed_at or utc_now(),
        "review_only": True,
    }
    if next_status == "seen":
        updated["last_seen_at"] = changed_at or text(updated.get("updated_at"))
    if next_status == "deferred":
        updated["deferred_until"] = deferred_until
    if note:
        updated["lifecycle_note"] = note

    return {
        "ok": True,
        "alert": updated,
        "errors": [],
        "warnings": warnings,
        "review_only": True,
    }


__all__ = [
    "ACTIVE_STATUSES",
    "REVIEW_ONLY_NOTE",
    "VALID_STATUSES",
    "VALID_TRANSITIONS",
    "alert_id_for",
    "dedupe_alerts",
    "dedupe_key_for",
    "normalize_alert",
    "normalize_severity",
    "normalize_status",
    "severity_rank",
    "transition_alert_status",
]
