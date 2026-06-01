"""Read-only broker holdings and allocation context.

This module works from already-imported broker snapshots or fixtures. It does
not connect to brokers, preview orders, place trades, or mutate official
recommendations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Iterable, Mapping


READ_ONLY_NOTE = (
    "Read-only broker holdings context. This helper does not connect to brokers, "
    "preview orders, place trades, change scores, change targets, change decision "
    "safety, change allocation formulas, or mutate official recommendations."
)


def _as_mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _as_sequence(value: object) -> list[object]:
    if value is None or isinstance(value, (str, bytes, Mapping)):
        return []
    try:
        return list(value)  # type: ignore[arg-type]
    except TypeError:
        return []


def _text(value: object, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def _amount(value: object, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, str) and not value.strip():
        return default
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return default


def _optional_amount(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return None


def _round(value: float | None) -> float | None:
    return round(value, 2) if value is not None else None


def _pct(part: float, whole: float) -> float:
    return round((part / whole) * 100, 2) if whole > 0 else 0.0


def _parse_date(value: object) -> date | None:
    raw = _text(value)
    if not raw:
        return None
    for candidate in (raw, raw[:10]):
        try:
            return datetime.fromisoformat(candidate).date()
        except ValueError:
            continue
    return None


def _as_date(value: date | datetime | str | None) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    parsed = _parse_date(value)
    return parsed or date.today()


def _latest_as_of(snapshot: Mapping[str, object], accounts: Iterable[Mapping[str, object]]) -> str:
    values = [_text(snapshot.get("as_of") or snapshot.get("as_of_date"))]
    values.extend(_text(account.get("as_of") or account.get("as_of_date")) for account in accounts)
    dated = [value for value in values if value]
    if not dated:
        return ""
    return max(dated)


def _normalise_sleeve(value: object) -> str:
    raw = _text(value).lower()
    aliases = {
        "core": "long_term",
        "long_term_core": "long_term",
        "long-term": "long_term",
        "short_term": "tactical",
        "short-term": "tactical",
        "speculative": "speculative_ai",
    }
    return aliases.get(raw, raw or "unknown")


def _account_positions(account: Mapping[str, object]) -> list[Mapping[str, object]]:
    positions = account.get("positions")
    if isinstance(positions, Mapping):
        rows: list[Mapping[str, object]] = []
        for symbol, position in positions.items():
            row = dict(_as_mapping(position))
            row.setdefault("symbol", symbol)
            rows.append(row)
        return rows
    return [_as_mapping(row) for row in _as_sequence(positions)]


def _snapshot_accounts(snapshot: Mapping[str, object]) -> list[Mapping[str, object]]:
    accounts = [_as_mapping(account) for account in _as_sequence(snapshot.get("accounts"))]
    if accounts:
        return accounts
    return [
        {
            "account_id": snapshot.get("account_id", "snapshot"),
            "cash_available": snapshot.get("cash_available"),
            "positions": snapshot.get("positions", []),
            "as_of": snapshot.get("as_of") or snapshot.get("as_of_date"),
        }
    ]


@dataclass(frozen=True)
class BrokerHoldingsContext:
    total_market_value: float
    total_account_value: float
    cash_available: float
    account_count: int
    position_count: int
    positions_by_symbol: dict[str, dict[str, object]]
    sleeve_exposure: dict[str, dict[str, object]]
    long_term_core_exposure: dict[str, object]
    tactical_speculative_exposure: dict[str, object]
    single_stock_concentration: dict[str, object]
    cap_pressure_warnings: list[str] = field(default_factory=list)
    missing_cost_basis_warnings: list[str] = field(default_factory=list)
    stale_snapshot_warnings: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    source: str = "broker_read_only_snapshot"
    as_of: str = ""
    snapshot_status: str = "available"
    capital_availability_fallback: dict[str, object] = field(default_factory=dict)
    read_only: bool = True
    context_only: bool = True
    recommendation_only: bool = True

    def to_context(self) -> dict[str, object]:
        return {
            "total_market_value": _round(self.total_market_value),
            "total_account_value": _round(self.total_account_value),
            "cash_available": _round(self.cash_available),
            "account_count": self.account_count,
            "position_count": self.position_count,
            "positions_by_symbol": dict(self.positions_by_symbol),
            "sleeve_exposure": dict(self.sleeve_exposure),
            "long_term_core_exposure": dict(self.long_term_core_exposure),
            "tactical_speculative_exposure": dict(self.tactical_speculative_exposure),
            "single_stock_concentration": dict(self.single_stock_concentration),
            "cap_pressure_warnings": list(self.cap_pressure_warnings),
            "missing_cost_basis_warnings": list(self.missing_cost_basis_warnings),
            "stale_snapshot_warnings": list(self.stale_snapshot_warnings),
            "warnings": list(self.warnings),
            "source": self.source,
            "as_of": self.as_of,
            "snapshot_status": self.snapshot_status,
            "capital_availability_fallback": dict(self.capital_availability_fallback),
            "read_only": self.read_only,
            "context_only": self.context_only,
            "recommendation_only": self.recommendation_only,
            "broker_behavior": "read_only",
            "order_behavior": "none",
            "notes": READ_ONLY_NOTE,
        }


def _manual_cash_from_fallback(fallback: Mapping[str, object]) -> float:
    for key in ("manual_available_cash", "available_amount", "monthly_buy_capacity"):
        amount = _optional_amount(fallback.get(key))
        if amount is not None:
            return amount
    return 0.0


def _missing_snapshot_context(
    manual_capital_fallback: Mapping[str, object] | None,
) -> dict[str, object]:
    fallback = dict(manual_capital_fallback or {})
    cash = _manual_cash_from_fallback(fallback)
    warning = (
        "broker_snapshot_missing: holdings and allocation context unavailable; "
        "manual/config capital availability fallback preserved for review"
    )
    context = BrokerHoldingsContext(
        total_market_value=0.0,
        total_account_value=cash,
        cash_available=cash,
        account_count=0,
        position_count=0,
        positions_by_symbol={},
        sleeve_exposure={},
        long_term_core_exposure={"market_value": 0.0, "pct_of_holdings": 0.0},
        tactical_speculative_exposure={"market_value": 0.0, "pct_of_holdings": 0.0},
        single_stock_concentration={"symbol": "", "market_value": 0.0, "pct_of_holdings": 0.0},
        warnings=[warning],
        source=_text(fallback.get("source"), "manual_or_config_fallback"),
        snapshot_status="missing",
        capital_availability_fallback=fallback,
    )
    return context.to_context()


def _position_sleeve(
    symbol: str,
    position: Mapping[str, object],
    sleeve_mapping: Mapping[str, object],
    warnings: list[str],
) -> str:
    sleeve = position.get("sleeve")
    if sleeve is None:
        sleeve = sleeve_mapping.get(symbol)
    normalized = _normalise_sleeve(sleeve)
    if normalized == "unknown":
        warnings.append(f"sleeve_mapping_missing:{symbol}")
    return normalized


def _add_cap_pressure(
    warnings: list[str],
    *,
    label: str,
    identifier: str,
    pct_value: float,
    cap_pct: float | None,
) -> None:
    if cap_pct is None:
        return
    cap_as_pct = cap_pct * 100 if cap_pct <= 1 else cap_pct
    if pct_value > cap_as_pct:
        warnings.append(f"{label}:{identifier}:{pct_value:.2f}%>{cap_as_pct:.2f}%")


def build_broker_holdings_context(
    broker_snapshot: Mapping[str, object] | None,
    *,
    sleeve_mapping: Mapping[str, object] | None = None,
    portfolio_caps: Mapping[str, object] | None = None,
    current_date: date | datetime | str | None = None,
    stale_after_days: int = 3,
    manual_capital_fallback: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Summarize a read-only broker snapshot as allocation review context.

    The helper accepts fixture/imported data only. It does not call a live
    broker and never changes official recommendations.
    """

    snapshot = _as_mapping(broker_snapshot)
    if not snapshot:
        return _missing_snapshot_context(manual_capital_fallback)

    sleeve_lookup = {
        str(symbol).upper(): sleeve for symbol, sleeve in dict(sleeve_mapping or {}).items()
    }
    caps = dict(portfolio_caps or {})
    warnings: list[str] = []
    missing_cost_basis_warnings: list[str] = []
    cap_pressure_warnings: list[str] = []
    stale_snapshot_warnings: list[str] = []
    positions_by_symbol: dict[str, dict[str, object]] = {}
    sleeve_values: dict[str, float] = {}

    accounts = _snapshot_accounts(snapshot)
    cash_available = sum(_amount(account.get("cash_available")) for account in accounts)
    position_count = 0

    for account in accounts:
        account_id = _text(account.get("account_id"), "unknown_account")
        for position in _account_positions(account):
            symbol = _text(position.get("symbol")).upper()
            if not symbol:
                warnings.append(f"position_symbol_missing:{account_id}")
                continue
            market_value = _amount(position.get("market_value"))
            quantity = _amount(position.get("quantity"))
            cost_basis = _optional_amount(position.get("cost_basis"))
            sleeve = _position_sleeve(symbol, position, sleeve_lookup, warnings)
            row = positions_by_symbol.setdefault(
                symbol,
                {
                    "symbol": symbol,
                    "company": _text(position.get("company")),
                    "quantity": 0.0,
                    "market_value": 0.0,
                    "cost_basis": 0.0,
                    "cost_basis_status": "available",
                    "sleeve": sleeve,
                    "account_ids": [],
                    "read_only": True,
                    "context_only": True,
                },
            )
            row["quantity"] = _round(float(row["quantity"]) + quantity)
            row["market_value"] = _round(float(row["market_value"]) + market_value)
            if cost_basis is None or cost_basis <= 0:
                row["cost_basis_status"] = "missing"
                missing_cost_basis_warnings.append(f"missing_cost_basis:{symbol}")
            else:
                row["cost_basis"] = _round(float(row["cost_basis"]) + cost_basis)
            account_ids = list(row["account_ids"])
            if account_id not in account_ids:
                account_ids.append(account_id)
            row["account_ids"] = sorted(account_ids)
            if not row["company"] and position.get("company"):
                row["company"] = _text(position.get("company"))
            if row["sleeve"] == "unknown" and sleeve != "unknown":
                row["sleeve"] = sleeve
            sleeve_values[sleeve] = sleeve_values.get(sleeve, 0.0) + market_value
            position_count += 1

    total_market_value = sum(float(row["market_value"]) for row in positions_by_symbol.values())
    total_account_value = total_market_value + cash_available

    for row in positions_by_symbol.values():
        market_value = float(row["market_value"])
        row["pct_of_holdings"] = _pct(market_value, total_market_value)

    sleeve_exposure: dict[str, dict[str, object]] = {}
    sleeve_caps = _as_mapping(caps.get("sleeve_caps") or caps.get("sleeves"))
    for sleeve, value in sorted(sleeve_values.items()):
        pct_value = _pct(value, total_market_value)
        cap_value = _optional_amount(
            sleeve_caps.get(sleeve)
            if not isinstance(sleeve_caps.get(sleeve), Mapping)
            else _as_mapping(sleeve_caps.get(sleeve)).get("target_pct")
        )
        sleeve_exposure[sleeve] = {
            "sleeve": sleeve,
            "market_value": _round(value),
            "pct_of_holdings": pct_value,
            "cap_pct": _round(cap_value * 100 if cap_value and cap_value <= 1 else cap_value),
            "read_only": True,
            "context_only": True,
        }
        _add_cap_pressure(
            cap_pressure_warnings,
            label="sleeve_cap_pressure",
            identifier=sleeve,
            pct_value=pct_value,
            cap_pct=cap_value,
        )

    concentration_symbol = ""
    concentration_value = 0.0
    for symbol, row in positions_by_symbol.items():
        value = float(row["market_value"])
        if value > concentration_value:
            concentration_symbol = symbol
            concentration_value = value
    concentration_pct = _pct(concentration_value, total_market_value)
    single_stock_cap = _optional_amount(caps.get("single_stock_max_pct"))
    _add_cap_pressure(
        cap_pressure_warnings,
        label="single_stock_concentration",
        identifier=concentration_symbol,
        pct_value=concentration_pct,
        cap_pct=single_stock_cap,
    )

    as_of = _latest_as_of(snapshot, accounts)
    today = _as_date(current_date)
    parsed_as_of = _parse_date(as_of)
    snapshot_status = "available"
    if not parsed_as_of:
        stale_snapshot_warnings.append("snapshot_as_of_missing")
        snapshot_status = "freshness_unknown"
    else:
        age_days = max(0, (today - parsed_as_of).days)
        if age_days > max(0, stale_after_days):
            stale_snapshot_warnings.append(f"snapshot_stale:{age_days}d>{stale_after_days}d")
            snapshot_status = "stale"

    warnings.extend(sorted(set(missing_cost_basis_warnings)))
    warnings.extend(cap_pressure_warnings)
    warnings.extend(stale_snapshot_warnings)
    warnings = list(dict.fromkeys(warnings))

    long_term_value = sleeve_values.get("long_term", 0.0)
    tactical_speculative_value = sum(
        value for sleeve, value in sleeve_values.items() if sleeve in {"tactical", "speculative_ai"}
    )
    context = BrokerHoldingsContext(
        total_market_value=total_market_value,
        total_account_value=total_account_value,
        cash_available=cash_available,
        account_count=len(accounts),
        position_count=position_count,
        positions_by_symbol=dict(sorted(positions_by_symbol.items())),
        sleeve_exposure=sleeve_exposure,
        long_term_core_exposure={
            "sleeve": "long_term",
            "market_value": _round(long_term_value),
            "pct_of_holdings": _pct(long_term_value, total_market_value),
            "read_only": True,
            "context_only": True,
        },
        tactical_speculative_exposure={
            "sleeves": ["tactical", "speculative_ai"],
            "market_value": _round(tactical_speculative_value),
            "pct_of_holdings": _pct(tactical_speculative_value, total_market_value),
            "read_only": True,
            "context_only": True,
        },
        single_stock_concentration={
            "symbol": concentration_symbol,
            "market_value": _round(concentration_value),
            "pct_of_holdings": concentration_pct,
            "cap_pct": _round(
                single_stock_cap * 100 if single_stock_cap and single_stock_cap <= 1 else single_stock_cap
            ),
            "read_only": True,
            "context_only": True,
        },
        cap_pressure_warnings=cap_pressure_warnings,
        missing_cost_basis_warnings=sorted(set(missing_cost_basis_warnings)),
        stale_snapshot_warnings=stale_snapshot_warnings,
        warnings=warnings,
        source=_text(snapshot.get("source"), "broker_read_only_snapshot"),
        as_of=as_of,
        snapshot_status=snapshot_status,
        capital_availability_fallback=dict(manual_capital_fallback or {}),
    )
    return context.to_context()


def broker_holdings_context(*args: object, **kwargs: object) -> dict[str, object]:
    return build_broker_holdings_context(*args, **kwargs)


__all__ = [
    "BrokerHoldingsContext",
    "READ_ONLY_NOTE",
    "broker_holdings_context",
    "build_broker_holdings_context",
]
