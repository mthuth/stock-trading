"""Read-only broker context view model helpers.

These helpers turn already-available broker snapshot payloads into local
console/report-ready review context. They do not call broker APIs, read
credentials, place or preview orders, write account state, or change official
recommendations.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Iterable, Mapping


RECOMMENDATION_ONLY_NOTE = (
    "Broker context is read-only and recommendation-only. It is for manual capital "
    "deployment and exposure review only; it does not place trades, preview orders, "
    "write to broker accounts, change scores, change targets, change decision-safety "
    "rules, alter allocation formulas, tune models, or change official recommendations."
)
EMPTY_STATE_NOTE = (
    "No broker snapshot is available. Use manual/config capital availability as the fallback "
    "until a read-only snapshot is imported."
)
RESTRICTED_LANGUAGE = (
    "place order",
    "place a trade",
    "submit order",
    "submit a trade",
    "execute trade",
    "execute order",
    "order ticket",
    "preview order",
    "buy now",
    "sell now",
    "margin permission",
)


def as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: object) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def text(value: object, default: str = "") -> str:
    if value is None or value == "":
        return default
    return str(value).strip()


def token(value: object) -> str:
    return text(value).lower().replace("-", "_").replace(" ", "_")


def amount(value: object, default: float = 0.0) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def optional_amount(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def rounded(value: float | None) -> float | None:
    return round(value, 2) if value is not None else None


def parse_date(value: object) -> date | None:
    raw = text(value)
    if not raw:
        return None
    for candidate in (raw, raw[:10]):
        try:
            return datetime.fromisoformat(candidate.replace("Z", "+00:00")).date()
        except ValueError:
            continue
    return None


def age_days(as_of: object, today: date) -> int | None:
    parsed = parse_date(as_of)
    if not parsed:
        return None
    return max(0, (today - parsed).days)


def money_text(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"${value:,.2f}"


def mask_account_id(value: object) -> str:
    raw = "".join(char for char in text(value) if char.isalnum())
    if not raw:
        return "masked-account"
    tail = raw[-4:] if len(raw) >= 4 else raw
    return f"acct-****{tail}"


def account_label(account: Mapping[str, object]) -> str:
    label = text(account.get("account_label") or account.get("account_name") or account.get("accountType"))
    masked = mask_account_id(account.get("account_id") or account.get("accountId") or account.get("accountIdKey"))
    return f"{label} ({masked})" if label else masked


def account_cash(account: Mapping[str, object]) -> float:
    cash = as_dict(account.get("cash"))
    candidates = (
        cash.get("available_cash"),
        cash.get("cash_available"),
        cash.get("cash_balance"),
        cash.get("cash"),
        account.get("available_cash"),
        account.get("cash_balance"),
    )
    for candidate in candidates:
        value = optional_amount(candidate)
        if value is not None:
            return max(0.0, value)
    return 0.0


def account_buying_capacity(account: Mapping[str, object]) -> float:
    cash = as_dict(account.get("cash"))
    candidates = (
        cash.get("buying_capacity"),
        cash.get("buying_power"),
        account.get("buying_capacity"),
        account.get("buying_power"),
        account_cash(account),
    )
    for candidate in candidates:
        value = optional_amount(candidate)
        if value is not None:
            return max(0.0, value)
    return 0.0


def margin_or_complex_fields(account: Mapping[str, object]) -> list[str]:
    cash = as_dict(account.get("cash"))
    fields: list[str] = []
    for key in (
        "margin_buying_power",
        "day_trading_buying_power",
        "option_buying_power",
        "short_market_value",
        "margin_balance",
    ):
        if key in cash or key in account:
            fields.append(key)
    return fields


def snapshot_accounts(snapshot: Mapping[str, object]) -> list[dict[str, Any]]:
    accounts = as_list(snapshot.get("accounts"))
    if accounts:
        return [as_dict(account) for account in accounts]
    account = as_dict(snapshot.get("account"))
    return [account] if account else []


def account_positions(account: Mapping[str, object]) -> list[dict[str, Any]]:
    return [as_dict(position) for position in as_list(account.get("positions") or account.get("holdings"))]


def normalize_position(position: Mapping[str, object], account: Mapping[str, object]) -> dict[str, object]:
    symbol = text(position.get("symbol") or position.get("ticker") or position.get("security_symbol")).upper()
    market_value = optional_amount(position.get("market_value") or position.get("marketValue"))
    quantity = optional_amount(position.get("quantity") or position.get("qty"))
    sleeve = token(position.get("sleeve") or position.get("portfolio_sleeve") or position.get("decision_mode") or "unknown")
    return {
        "symbol": symbol,
        "company": text(position.get("company") or position.get("security_name") or position.get("description")),
        "quantity": rounded(quantity),
        "market_value": rounded(market_value if market_value is not None else 0.0),
        "market_value_text": money_text(market_value if market_value is not None else 0.0),
        "sleeve": sleeve,
        "account_label": account_label(account),
        "account_masked_id": mask_account_id(account.get("account_id") or account.get("accountId") or account.get("accountIdKey")),
        "source": text(position.get("source") or account.get("source")),
    }


def all_positions(accounts: Iterable[Mapping[str, object]]) -> list[dict[str, object]]:
    positions: list[dict[str, object]] = []
    for account in accounts:
        positions.extend(normalize_position(position, account) for position in account_positions(account))
    positions.sort(key=lambda row: amount(row.get("market_value")), reverse=True)
    return positions


def sleeve_exposure(positions: Iterable[Mapping[str, object]], total_value: float) -> dict[str, dict[str, object]]:
    exposures: dict[str, float] = {}
    for position in positions:
        sleeve = token(position.get("sleeve") or "unknown")
        exposures[sleeve] = exposures.get(sleeve, 0.0) + amount(position.get("market_value"))
    return {
        sleeve: {
            "market_value": rounded(value),
            "market_value_text": money_text(value),
            "pct_of_total": round((value / total_value) * 100, 2) if total_value > 0 else None,
        }
        for sleeve, value in sorted(exposures.items())
    }


def concentration_warnings(
    positions: Iterable[Mapping[str, object]],
    total_value: float,
    *,
    concentration_threshold_pct: float,
) -> list[str]:
    warnings: list[str] = []
    if total_value <= 0:
        return warnings
    for position in positions:
        pct = (amount(position.get("market_value")) / total_value) * 100
        if pct > concentration_threshold_pct:
            warnings.append(
                f"{text(position.get('symbol'), 'Unknown')} is {pct:.1f}% of broker-reported positions, above the {concentration_threshold_pct:.1f}% review threshold."
            )
    return warnings


def build_empty_view(
    *,
    capital_availability: Mapping[str, object] | None,
    data_source: str,
    as_of: str,
) -> dict[str, object]:
    capital = as_dict(capital_availability)
    fallback = {
        "available_amount": rounded(optional_amount(capital.get("available_amount"))),
        "available_amount_text": money_text(optional_amount(capital.get("available_amount"))),
        "source": text(capital.get("source"), "manual_or_config"),
        "status": text(capital.get("status"), "fallback_available" if capital else "needs_manual_update"),
        "as_of_date": text(capital.get("as_of_date")),
    }
    return {
        "available": False,
        "status": "missing_snapshot",
        "cash_summary": {
            "total_cash": None,
            "total_cash_text": "n/a",
            "buying_capacity": None,
            "buying_capacity_text": "n/a",
            "manual_config_fallback": fallback,
        },
        "account_count": 0,
        "masked_account_labels": [],
        "position_count": 0,
        "top_holdings": [],
        "long_term_core_exposure": None,
        "sleeve_exposure": {},
        "concentration_warnings": [],
        "warnings": [EMPTY_STATE_NOTE],
        "data_source": data_source,
        "as_of": as_of,
        "empty_state": EMPTY_STATE_NOTE,
        "read_only": True,
        "no_order_capability": True,
        "recommendation_only_note": RECOMMENDATION_ONLY_NOTE,
    }


def build_broker_readonly_view(
    broker_snapshot: Mapping[str, object] | None,
    *,
    capital_availability: Mapping[str, object] | None = None,
    today: date | None = None,
    stale_after_days: int = 3,
    concentration_threshold_pct: float = 10.0,
    top_holding_limit: int = 5,
) -> dict[str, object]:
    """Build a deterministic read-only broker context view model."""

    today = today or date.today()
    snapshot = as_dict(broker_snapshot)
    data_source = text(snapshot.get("source") or snapshot.get("data_source"), "broker_snapshot")
    as_of = text(snapshot.get("as_of") or snapshot.get("as_of_timestamp") or snapshot.get("synced_at"))
    accounts = snapshot_accounts(snapshot)
    if not snapshot or not accounts:
        return build_empty_view(capital_availability=capital_availability, data_source=data_source, as_of=as_of)

    positions = all_positions(accounts)
    total_cash = sum(account_cash(account) for account in accounts)
    buying_capacity = sum(account_buying_capacity(account) for account in accounts)
    total_position_value = sum(amount(position.get("market_value")) for position in positions)
    total_value = total_cash + total_position_value
    age = age_days(as_of, today)
    warnings: list[str] = []
    if age is None:
        warnings.append("Broker snapshot is missing an as-of timestamp.")
    elif age > stale_after_days:
        warnings.append(f"Broker snapshot is stale: {age} days old.")
    if not positions:
        warnings.append("Broker snapshot has no positions.")
    for account in accounts:
        complex_fields = margin_or_complex_fields(account)
        if complex_fields:
            warnings.append(
                "Broker snapshot includes margin/options/short/day-trading fields; they are read-only context and not trade permission."
            )
            break
    warnings.extend(
        concentration_warnings(
            positions,
            total_position_value,
            concentration_threshold_pct=concentration_threshold_pct,
        )
    )
    exposures = sleeve_exposure(positions, total_position_value)
    long_term = exposures.get("long_term_core") or exposures.get("long_term") or exposures.get("long_term_buy_add")

    return {
        "available": True,
        "status": "stale" if any("stale" in warning.lower() for warning in warnings) else "available",
        "cash_summary": {
            "total_cash": rounded(total_cash),
            "total_cash_text": money_text(total_cash),
            "buying_capacity": rounded(buying_capacity),
            "buying_capacity_text": money_text(buying_capacity),
            "manual_config_fallback": as_dict(capital_availability),
        },
        "account_count": len(accounts),
        "masked_account_labels": [account_label(account) for account in accounts],
        "position_count": len(positions),
        "total_position_market_value": rounded(total_position_value),
        "total_position_market_value_text": money_text(total_position_value),
        "top_holdings": positions[: max(0, int(top_holding_limit))],
        "long_term_core_exposure": long_term,
        "sleeve_exposure": exposures,
        "concentration_warnings": [
            warning for warning in warnings if "above the" in warning and "review threshold" in warning
        ],
        "warnings": list(dict.fromkeys(warnings)),
        "data_source": data_source,
        "as_of": as_of,
        "snapshot_age_days": age,
        "empty_state": "",
        "read_only": True,
        "no_order_capability": True,
        "recommendation_only_note": RECOMMENDATION_ONLY_NOTE,
    }


def view_contains_restricted_language(view: Mapping[str, object]) -> bool:
    haystack = str(view).lower()
    return any(phrase in haystack for phrase in RESTRICTED_LANGUAGE)


__all__ = [
    "EMPTY_STATE_NOTE",
    "RECOMMENDATION_ONLY_NOTE",
    "build_broker_readonly_view",
    "mask_account_id",
    "view_contains_restricted_language",
]
