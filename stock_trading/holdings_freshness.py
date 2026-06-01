"""Holdings and broker snapshot freshness helpers.

The helper works from already-available local/manual/config/broker snapshot
payloads. It does not call broker APIs, write accounts, preview orders, or
change recommendations.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Any, Mapping


READ_ONLY_GUARDRAIL = (
    "Read-only snapshot for manual review. No order capability is available, "
    "and official recommendations remain unchanged."
)

SOURCE_VALUES = {"broker_readonly", "manual", "config", "fixture", "unknown"}
MISSING_STATUSES = {"missing", "unavailable"}
STALE_STATUSES = {"stale"}
UNKNOWN_STATUSES = {"error", "unknown", "partial"}


def _as_dict(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_list(value: object) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _text(value: object, default: str = "") -> str:
    if value is None:
        return default
    result = str(value).strip()
    return result if result else default


def _token(value: object) -> str:
    return _text(value).lower().replace("-", "_").replace(" ", "_")


def _parse_datetime(value: object) -> datetime | None:
    raw = _text(value)
    if not raw:
        return None
    for candidate in (raw, raw.replace("Z", "+00:00"), raw[:10]):
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            continue
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    return None


def _as_datetime(value: date | datetime | None) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value
    if isinstance(value, date):
        return datetime.combine(value, time.max.replace(microsecond=0))
    return datetime.combine(date.today(), time.min)


def _first_text(*values: object) -> str:
    for value in values:
        result = _text(value)
        if result:
            return result
    return ""


def _snapshot_accounts(snapshot: Mapping[str, object]) -> list[dict[str, Any]]:
    accounts = [_as_dict(account) for account in _as_list(snapshot.get("accounts"))]
    if accounts:
        return accounts
    account = _as_dict(snapshot.get("account"))
    return [account] if account else []


def _position_count(snapshot: Mapping[str, object], accounts: list[Mapping[str, object]]) -> int:
    top_level = _as_list(snapshot.get("positions") or snapshot.get("holdings"))
    nested = 0
    for account in accounts:
        nested += len(_as_list(account.get("positions") or account.get("holdings")))
    return len(top_level) + nested


def _normalize_source(value: object) -> str:
    raw = _token(value)
    if raw in SOURCE_VALUES:
        return raw
    if raw.startswith("fixture"):
        return "fixture"
    if "broker" in raw:
        return "broker_readonly"
    if raw in {"configured", "configuration"}:
        return "config"
    return "unknown"


def _snapshot_status(snapshot: Mapping[str, object], sync_status: Mapping[str, object]) -> str:
    return _token(
        sync_status.get("status")
        or snapshot.get("snapshot_status")
        or snapshot.get("sync_status")
        or snapshot.get("status")
    )


def _snapshot_as_of(snapshot: Mapping[str, object], sync_status: Mapping[str, object]) -> str:
    values = [
        snapshot.get("as_of"),
        snapshot.get("as_of_date"),
        snapshot.get("as_of_timestamp"),
        snapshot.get("snapshot_at"),
        snapshot.get("synced_at"),
        sync_status.get("snapshot_at"),
    ]
    accounts = _snapshot_accounts(snapshot)
    values.extend(account.get("as_of") or account.get("as_of_date") or account.get("snapshot_at") for account in accounts)
    dated = [_text(value) for value in values if _text(value)]
    return max(dated) if dated else ""


def _last_pulled_at(snapshot: Mapping[str, object], sync_status: Mapping[str, object], as_of: str) -> str:
    return _first_text(
        snapshot.get("last_pulled_at"),
        snapshot.get("last_success_at"),
        snapshot.get("synced_at"),
        snapshot.get("imported_at"),
        sync_status.get("last_success_at"),
        as_of,
    )


def build_holdings_freshness(
    snapshot: Mapping[str, object] | None,
    *,
    source: str | None = None,
    today: date | datetime | None = None,
    stale_after_hours: int = 24,
) -> dict[str, object]:
    """Build a JSON-native freshness summary for holdings/cash snapshots."""

    now = _as_datetime(today)
    row = _as_dict(snapshot)
    sync_status = _as_dict(row.get("sync_status"))
    source_value = _normalize_source(source or row.get("source") or row.get("data_source"))
    status = _snapshot_status(row, sync_status)
    as_of = _snapshot_as_of(row, sync_status)
    last_pulled_at = _last_pulled_at(row, sync_status, as_of)
    accounts = _snapshot_accounts(row)
    account_count = len(accounts)
    position_count = _position_count(row, accounts)
    warnings: list[str] = []

    parsed = _parse_datetime(as_of)
    age_hours: int | None = None
    age_days: int | None = None
    if parsed is not None:
        age_hours = max(0, int((now - parsed).total_seconds() // 3600))
        age_days = age_hours // 24

    if not row or status in MISSING_STATUSES:
        freshness_label = "missing"
        warnings.append("Holdings snapshot is missing; manual/config fallback should remain visible.")
    elif status in STALE_STATUSES:
        freshness_label = "stale"
        warnings.append("Holdings snapshot is marked stale; do not treat holdings or cash as current.")
    elif parsed is None:
        freshness_label = "unknown"
        warnings.append("Holdings snapshot has no usable as-of timestamp; freshness is unknown.")
    elif age_hours is not None and age_hours > max(0, stale_after_hours):
        freshness_label = "stale"
        warnings.append(
            f"Holdings snapshot is stale: {age_hours} hours old; do not treat holdings or cash as current."
        )
    elif status in UNKNOWN_STATUSES:
        freshness_label = "unknown"
        warnings.append(f"Holdings snapshot status is {status}; freshness needs review.")
    else:
        freshness_label = "fresh"

    if row and account_count == 0:
        warnings.append("Holdings snapshot has no account data.")
    if row and position_count == 0:
        warnings.append("Holdings snapshot has no position data.")

    warning = " ".join(dict.fromkeys(warnings))
    display_rows = [
        {"label": "Holdings source", "value": source_value},
        {"label": "As of", "value": as_of or "n/a"},
        {"label": "Last pulled", "value": last_pulled_at or "n/a"},
        {"label": "Freshness", "value": freshness_label},
        {"label": "Read-only snapshot", "value": "Yes"},
    ]

    return {
        "source": source_value,
        "source_detail": _text(source or row.get("source") or row.get("data_source"), source_value),
        "as_of": as_of,
        "last_pulled_at": last_pulled_at,
        "freshness_label": freshness_label,
        "age_hours": age_hours,
        "age_days": age_days,
        "warning": warning,
        "warnings": list(dict.fromkeys(warnings)),
        "account_count": account_count,
        "position_count": position_count,
        "read_only": True,
        "no_order_capability": True,
        "recommendation_only": True,
        "guardrail": READ_ONLY_GUARDRAIL,
        "display_rows": display_rows,
    }


def freshness_contains_restricted_language(summary: Mapping[str, object]) -> bool:
    haystack = str(summary).lower()
    return any(
        phrase in haystack
        for phrase in (
            "place order",
            "submit order",
            "execute trade",
            "execute order",
            "preview order",
            "buy now",
            "sell now",
        )
    )


__all__ = [
    "READ_ONLY_GUARDRAIL",
    "build_holdings_freshness",
    "freshness_contains_restricted_language",
]
