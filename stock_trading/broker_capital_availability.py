"""Read-only broker cash adapter for capital availability context.

This module converts an already-fetched broker snapshot into capital context.
It does not connect to brokers, preview orders, place trades, or change
recommendations.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Mapping

from stock_trading.capital_availability import capital_availability_from_config


RECOMMENDATION_ONLY_NOTE = (
    "Recommendation-only broker capital availability context. Broker snapshots "
    "are read-only inputs for manual review only; this helper does not preview "
    "orders, place trades, grant order capability, tune models, or change "
    "official recommendations."
)

BUYING_POWER_WARNING = (
    "Buying power is broker context only and is not treated as deployable cash "
    "or order permission."
)

MARGIN_WARNING = (
    "Margin, options, short, or day-trading fields are broker context only and "
    "are not treated as deployable cash or trading permission."
)

INVALID_STATUS_VALUES = {"blocked", "error", "failed", "invalid", "unavailable"}
BROKER_CASH_FIELDS = ("cash_available", "available_cash", "cash")
BUYING_POWER_FIELDS = (
    "buying_power",
    "margin_buying_power",
    "options_buying_power",
    "day_trading_buying_power",
)
MARGIN_CONTEXT_FIELDS = (
    "margin_available",
    "margin_buying_power",
    "options_buying_power",
    "day_trading_buying_power",
    "short_marginable_value",
)


def _as_mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _parse_amount(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return None
    if amount < 0:
        return None
    return amount


def _parse_date(value: object) -> date | None:
    raw = _text(value)
    if not raw:
        return None
    for candidate in (raw, raw[:10], raw.replace("Z", "+00:00")):
        try:
            return datetime.fromisoformat(candidate).date()
        except ValueError:
            continue
    return None


def _age_days(as_of: str, today: date) -> int | None:
    parsed = _parse_date(as_of)
    if not parsed:
        return None
    return max(0, (today - parsed).days)


def _first_text(snapshot: Mapping[str, object], keys: tuple[str, ...]) -> str:
    balances = _as_mapping(snapshot.get("balances"))
    for key in keys:
        value = _text(snapshot.get(key))
        if value:
            return value
        nested = _text(balances.get(key))
        if nested:
            return nested
    return ""


def _first_amount(snapshot: Mapping[str, object], keys: tuple[str, ...]) -> float | None:
    balances = _as_mapping(snapshot.get("balances"))
    for key in keys:
        amount = _parse_amount(snapshot.get(key))
        if amount is not None:
            return amount
        amount = _parse_amount(balances.get(key))
        if amount is not None:
            return amount
    return None


def _amount_fields(snapshot: Mapping[str, object], keys: tuple[str, ...]) -> dict[str, float]:
    balances = _as_mapping(snapshot.get("balances"))
    values: dict[str, float] = {}
    for key in keys:
        amount = _parse_amount(snapshot.get(key))
        if amount is None:
            amount = _parse_amount(balances.get(key))
        if amount is not None:
            values[key] = amount
    return values


def _mask_account_id(value: object) -> str:
    raw = _text(value)
    if not raw:
        return ""
    suffix = raw[-4:] if len(raw) >= 4 else raw
    return f"acct_****{suffix}"


def _fallback_context(config: Mapping[str, object], today: date, stale_after_days: int) -> dict[str, object]:
    fallback = capital_availability_from_config(config, today=today, stale_after_days=stale_after_days).to_context()
    source = _text(fallback.get("source"))
    if source == "manual_and_configured" or fallback.get("manual_available_cash") is not None:
        public_source = "manual"
    elif fallback.get("monthly_buy_capacity") is not None:
        public_source = "configured"
    else:
        public_source = "unknown"

    return {
        "available_amount": fallback.get("available_amount"),
        "monthly_buy_capacity": fallback.get("monthly_buy_capacity"),
        "manual_available_cash": fallback.get("manual_available_cash"),
        "source": public_source,
        "fallback_source": source,
        "as_of": fallback.get("as_of_date", ""),
        "freshness": fallback.get("freshness", "unknown"),
        "status": fallback.get("status", "needs_manual_update"),
        "notes": fallback.get("notes", ""),
    }


def broker_capital_availability_context(
    broker_snapshot: Mapping[str, object] | None,
    config: Mapping[str, object] | None = None,
    *,
    today: date | None = None,
    broker_stale_after_days: int = 2,
    config_stale_after_days: int = 45,
) -> dict[str, object]:
    """Build capital availability using broker cash when it is fresh and valid.

    The broker snapshot is optional and read-only. Stale, invalid, unavailable,
    or non-cash broker fields produce warnings and fall back to manual/config
    capital availability.
    """

    today = today or date.today()
    snapshot = _as_mapping(broker_snapshot)
    config_mapping = _as_mapping(config)
    fallback = _fallback_context(config_mapping, today, config_stale_after_days)
    warnings: list[str] = []

    account_id = _mask_account_id(snapshot.get("account_id", snapshot.get("accountId")))
    status = _text(snapshot.get("status")).lower()
    as_of = _first_text(snapshot, ("as_of", "as_of_date", "snapshot_at", "captured_at"))
    cash_available = _first_amount(snapshot, BROKER_CASH_FIELDS)
    buying_power = _amount_fields(snapshot, BUYING_POWER_FIELDS)
    margin_context = _amount_fields(snapshot, MARGIN_CONTEXT_FIELDS)

    if buying_power:
        warnings.append(BUYING_POWER_WARNING)
    if margin_context:
        warnings.append(MARGIN_WARNING)

    age = _age_days(as_of, today)
    broker_freshness = "unknown"
    broker_valid = bool(snapshot) and status not in INVALID_STATUS_VALUES and cash_available is not None
    if not snapshot:
        warnings.append("No broker read-only snapshot was provided; using manual/config capital context.")
    elif status in INVALID_STATUS_VALUES:
        warnings.append(f"Broker read-only snapshot status is {status}; using manual/config capital context.")
        broker_valid = False
    elif cash_available is None:
        warnings.append("Broker read-only snapshot does not include valid cash; using manual/config capital context.")
        broker_valid = False

    if broker_valid:
        if age is None:
            broker_freshness = "unknown"
            broker_valid = False
            warnings.append("Broker read-only snapshot has no usable as-of timestamp; using manual/config capital context.")
        elif age > max(0, broker_stale_after_days):
            broker_freshness = "stale"
            broker_valid = False
            warnings.append(
                f"Broker read-only snapshot is {age} days old; using manual/config capital context."
            )
        else:
            broker_freshness = "fresh"

    if broker_valid:
        result = {
            "available_amount": cash_available,
            "monthly_buy_capacity": fallback["monthly_buy_capacity"],
            "manual_available_cash": fallback["manual_available_cash"],
            "source": "broker_readonly",
            "fallback_source": fallback["fallback_source"],
            "as_of": as_of,
            "freshness": broker_freshness,
            "status": "available",
            "notes": "Fresh read-only broker cash is available for manual capital deployment review.",
        }
    else:
        result = fallback

    result.update(
        {
            "warnings": warnings,
            "context_only": True,
            "review_only": True,
            "recommendation_only": True,
            "no_order_capability": True,
            "order_behavior": "none",
            "broker_behavior": "read_only_context",
            "recommendation_only_note": RECOMMENDATION_ONLY_NOTE,
            "broker_cash_context": {
                "account_id": account_id,
                "as_of": as_of,
                "cash_available": cash_available,
                "freshness": broker_freshness,
                "status": status or "unknown",
                "buying_power": buying_power,
                "margin_context": margin_context,
                "context_only": True,
                "no_order_capability": True,
            },
        }
    )
    return result


__all__ = [
    "BROKER_CASH_FIELDS",
    "BUYING_POWER_WARNING",
    "MARGIN_WARNING",
    "RECOMMENDATION_ONLY_NOTE",
    "broker_capital_availability_context",
]
