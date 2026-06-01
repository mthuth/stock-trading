"""Broker read-only snapshot contract and validation helpers.

Wave 14 defines a local snapshot format before any new broker connection work.
This module normalizes already-provided account, cash, and position data. It
does not call brokers, preview orders, place trades, write accounts, or change
recommendations.
"""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import date, datetime
from typing import Iterable, Mapping


SNAPSHOT_SOURCES = {"fixture", "manual_import", "future_broker_readonly"}
SYNC_STATUSES = {"ok", "stale", "missing", "unavailable", "error", "unknown", "partial"}
READ_ONLY_NOTE = (
    "Broker read-only snapshot. This data is context for manual review only and "
    "does not enable orders, order previews, broker writes, trade execution, "
    "margin/day-trading decisions, score changes, target changes, decision-safety "
    "changes, source-weight changes, model tuning, or automatic recommendations."
)
BANNED_SECRET_KEY_TOKENS = {
    "token",
    "secret",
    "password",
    "credential",
    "oauth",
    "refresh",
    "session",
    "authorization",
}
BANNED_ORDER_KEY_TOKENS = {
    "order",
    "order_preview",
    "preview_order",
    "place_order",
    "execute",
    "execution",
    "cancel_order",
    "modify_order",
    "trade_permission",
    "trading_permission",
}
ORDER_KEY_EXCEPTIONS = {"no_order_capability"}


def _text(value: object, default: str = "") -> str:
    if value is None:
        return default
    result = str(value).strip()
    return result if result else default


def _token(value: object) -> str:
    return _text(value).lower().replace("-", "_").replace(" ", "_")


def _amount(value: object) -> float | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return None


def _first_value(*values: object) -> object:
    for value in values:
        if value is not None and not (isinstance(value, str) and not value.strip()):
            return value
    return None


def _as_dict(value: object) -> dict[str, object]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _as_list(value: object) -> list[object]:
    if isinstance(value, list):
        return copy.deepcopy(value)
    if isinstance(value, tuple):
        return list(copy.deepcopy(value))
    return []


def _parse_date(value: object) -> date | None:
    raw = _text(value)
    if not raw:
        return None
    for candidate in (raw[:10], raw):
        try:
            return datetime.fromisoformat(candidate).date()
        except ValueError:
            continue
    return None


def _stable_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _stable_hash(value: object, *, length: int = 16) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()[:length]


def _generated_snapshot_id(snapshot: Mapping[str, object]) -> str:
    payload = {
        "as_of": snapshot.get("as_of"),
        "provider": snapshot.get("provider"),
        "source": snapshot.get("source"),
        "accounts": snapshot.get("accounts"),
        "positions": snapshot.get("positions"),
    }
    return f"broker_snapshot_{_stable_hash(payload)}"


def _digits(value: object) -> str:
    return "".join(ch for ch in _text(value) if ch.isdigit())


def is_account_id_masked(value: object) -> bool:
    raw = _text(value)
    if not raw:
        return False
    digits = _digits(raw)
    return "*" in raw and len(digits) <= 4


def redact_account_id(value: object) -> str:
    """Return a deterministic masked account id suitable for fixtures/logs."""

    raw = _text(value)
    if not raw:
        return ""
    if is_account_id_masked(raw):
        return raw
    digits = _digits(raw)
    suffix = digits[-4:] if digits else _stable_hash(raw, length=4)
    return f"acct_****{suffix}"


def _normalize_account(account: Mapping[str, object], *, snapshot_as_of: str, provider: str) -> dict[str, object]:
    row = _as_dict(account)
    raw_id = row.get("account_id_masked") or row.get("account_id") or row.get("accountId")
    normalized: dict[str, object] = {
        "account_id_masked": redact_account_id(raw_id),
        "account_type": _text(row.get("account_type") or row.get("accountType")),
        "display_name": _text(row.get("display_name") or row.get("displayName")),
        "currency": _text(row.get("currency") or "USD"),
        "cash_available": _amount(_first_value(row.get("cash_available"), row.get("cashAvailable"))),
        "total_market_value": _amount(_first_value(row.get("total_market_value"), row.get("totalMarketValue"))),
        "total_equity": _amount(_first_value(row.get("total_equity"), row.get("totalEquity"))),
        "sync_status": _token(row.get("sync_status") or row.get("syncStatus") or "unknown"),
        "as_of": _text(row.get("as_of") or row.get("asOf") or snapshot_as_of),
        "provider": provider,
        "read_only": True,
    }
    if "buying_power" in row or "buyingPower" in row:
        normalized["buying_power"] = _amount(_first_value(row.get("buying_power"), row.get("buyingPower")))
        normalized["buying_power_context_only"] = True
    if "margin_enabled" in row or "marginEnabled" in row:
        normalized["margin_enabled"] = bool(row.get("margin_enabled") if "margin_enabled" in row else row.get("marginEnabled"))
        normalized["margin_enabled_context_only"] = True
    return normalized


def _normalize_position(position: Mapping[str, object], *, snapshot_as_of: str, provider: str) -> dict[str, object]:
    row = _as_dict(position)
    raw_id = row.get("account_id_masked") or row.get("account_id") or row.get("accountId")
    return {
        "account_id_masked": redact_account_id(raw_id),
        "symbol": _text(row.get("symbol")).upper(),
        "quantity": _amount(row.get("quantity")),
        "market_value": _amount(_first_value(row.get("market_value"), row.get("marketValue"))),
        "price": _amount(_first_value(row.get("price"), row.get("last_price"), row.get("lastPrice"))),
        "cost_basis": _amount(_first_value(row.get("cost_basis"), row.get("costBasis"))),
        "unrealized_gain_loss": _amount(_first_value(row.get("unrealized_gain_loss"), row.get("unrealizedGainLoss"))),
        "sleeve": _text(row.get("sleeve")),
        "as_of": _text(row.get("as_of") or row.get("asOf") or snapshot_as_of),
        "source": _text(row.get("source") or provider),
        "read_only": True,
    }


def _cash_summary(accounts: Iterable[Mapping[str, object]], provided: Mapping[str, object] | None = None) -> dict[str, object]:
    provided_row = _as_dict(provided)
    cash_values = [value for value in (_amount(row.get("cash_available")) for row in accounts) if value is not None]
    total_cash = _amount(_first_value(provided_row.get("cash_available"), provided_row.get("total_cash")))
    if total_cash is None and cash_values:
        total_cash = round(sum(cash_values), 4)
    currencies = sorted({_text(row.get("currency") or "USD") for row in accounts if _text(row.get("currency") or "USD")})
    return {
        "cash_available": total_cash,
        "currency": _text(provided_row.get("currency")) or (currencies[0] if len(currencies) == 1 else "mixed" if currencies else "USD"),
        "source": _text(provided_row.get("source") or "accounts"),
        "status": "missing" if total_cash is None else "available",
        "context_only": True,
    }


def normalize_broker_snapshot(snapshot: Mapping[str, object]) -> dict[str, object]:
    """Normalize a read-only broker snapshot without mutating input."""

    row = _as_dict(snapshot)
    provider = _text(row.get("provider") or "unknown")
    as_of = _text(row.get("as_of") or row.get("asOf"))
    accounts = [
        _normalize_account(account, snapshot_as_of=as_of, provider=provider)
        for account in _as_list(row.get("accounts"))
        if isinstance(account, Mapping)
    ]
    positions = [
        _normalize_position(position, snapshot_as_of=as_of, provider=provider)
        for position in _as_list(row.get("positions"))
        if isinstance(position, Mapping)
    ]
    accounts.sort(key=lambda item: (_text(item.get("account_id_masked")), _text(item.get("account_type"))))
    positions.sort(key=lambda item: (_text(item.get("account_id_masked")), _text(item.get("symbol"))))
    normalized = {
        "snapshot_id": _text(row.get("snapshot_id")),
        "created_at": _text(row.get("created_at")),
        "as_of": as_of,
        "provider": provider,
        "source": _token(row.get("source") or "manual_import"),
        "sync_status": _token(row.get("sync_status") or row.get("syncStatus") or "unknown"),
        "accounts": accounts,
        "positions": positions,
        "cash_summary": _cash_summary(accounts, row.get("cash_summary") if isinstance(row.get("cash_summary"), Mapping) else None),
        "warnings": [_text(item) for item in _as_list(row.get("warnings")) if _text(item)],
        "read_only": True,
        "no_order_capability": True,
        "recommendation_only_note": _text(row.get("recommendation_only_note") or READ_ONLY_NOTE),
    }
    if not normalized["snapshot_id"]:
        normalized["snapshot_id"] = _generated_snapshot_id(normalized)
    return normalized


def _walk_key_paths(value: object, *, prefix: str = "") -> list[tuple[str, object]]:
    paths: list[tuple[str, object]] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            paths.append((path, item))
            paths.extend(_walk_key_paths(item, prefix=path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            paths.extend(_walk_key_paths(item, prefix=f"{prefix}[{index}]"))
    return paths


def _has_banned_key_token(path: str, tokens: set[str]) -> bool:
    key = _token(path.rsplit(".", 1)[-1])
    if key in ORDER_KEY_EXCEPTIONS:
        return False
    return key in tokens or any(token in key for token in tokens)


def _validation_result(
    errors: list[dict[str, str]],
    warnings: list[dict[str, str]],
    normalized: Mapping[str, object],
) -> dict[str, object]:
    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "normalized_snapshot": copy.deepcopy(dict(normalized)),
    }


def _error(path: str, message: str) -> dict[str, str]:
    return {"path": path, "message": message}


def _warning(path: str, message: str) -> dict[str, str]:
    return {"path": path, "message": message}


def validate_broker_snapshot(
    snapshot: Mapping[str, object],
    *,
    today: date | None = None,
    stale_after_days: int = 3,
) -> dict[str, object]:
    """Validate a broker read-only snapshot and return structured results."""

    raw = _as_dict(snapshot)
    normalized = normalize_broker_snapshot(raw)
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    if raw.get("read_only") is False or normalized.get("read_only") is not True:
        errors.append(_error("read_only", "Broker snapshots must be read_only: true."))
    if raw.get("no_order_capability") is False or normalized.get("no_order_capability") is not True:
        errors.append(_error("no_order_capability", "Broker snapshots must declare no_order_capability: true."))
    if _text(normalized.get("source")) not in SNAPSHOT_SOURCES:
        errors.append(_error("source", "Snapshot source must be fixture, manual_import, or future_broker_readonly."))
    if _text(normalized.get("sync_status")) not in SYNC_STATUSES:
        errors.append(_error("sync_status", f"Unknown sync_status: {normalized.get('sync_status')}."))

    for path, _value in _walk_key_paths(raw):
        if _has_banned_key_token(path, BANNED_SECRET_KEY_TOKENS):
            errors.append(_error(path, "Broker snapshots must not include credentials, tokens, sessions, or secrets."))
        if _has_banned_key_token(path, BANNED_ORDER_KEY_TOKENS):
            errors.append(_error(path, "Broker snapshots must not include order, order-preview, execution, or trading-permission fields."))

    raw_accounts = [item for item in _as_list(raw.get("accounts")) if isinstance(item, Mapping)]
    raw_positions = [item for item in _as_list(raw.get("positions")) if isinstance(item, Mapping)]
    accounts = [item for item in normalized.get("accounts", []) if isinstance(item, Mapping)]
    positions = [item for item in normalized.get("positions", []) if isinstance(item, Mapping)]

    if not accounts:
        warnings.append(_warning("accounts", "Snapshot has no accounts."))
    for index, account in enumerate(accounts):
        account_id = _text(account.get("account_id_masked"))
        raw_account = raw_accounts[index] if index < len(raw_accounts) else {}
        raw_masked = raw_account.get("account_id_masked") if isinstance(raw_account, Mapping) else None
        if not account_id:
            errors.append(_error(f"accounts[{index}].account_id_masked", "Account id is required and must be masked."))
        if raw_masked is not None and not is_account_id_masked(raw_masked):
            errors.append(_error(f"accounts[{index}].account_id_masked", "account_id_masked must not contain an unredacted account id."))
        if raw_account.get("account_id") or raw_account.get("accountId"):
            warnings.append(_warning(f"accounts[{index}].account_id", "Raw account id was redacted during normalization."))
        if account.get("buying_power") is not None and account.get("buying_power_context_only") is not True:
            errors.append(_error(f"accounts[{index}].buying_power_context_only", "Buying power must be context-only."))
        if account.get("margin_enabled") is not None and account.get("margin_enabled_context_only") is not True:
            errors.append(_error(f"accounts[{index}].margin_enabled_context_only", "Margin fields must be context-only."))
        if account.get("cash_available") is None:
            warnings.append(_warning(f"accounts[{index}].cash_available", "Cash availability is missing for this account."))
        if _text(account.get("sync_status")) not in SYNC_STATUSES:
            errors.append(_error(f"accounts[{index}].sync_status", f"Unknown account sync_status: {account.get('sync_status')}."))

    for index, position in enumerate(positions):
        raw_position = raw_positions[index] if index < len(raw_positions) else {}
        if not _text(position.get("account_id_masked")):
            errors.append(_error(f"positions[{index}].account_id_masked", "Position account id is required and must be masked."))
        raw_masked = raw_position.get("account_id_masked") if isinstance(raw_position, Mapping) else None
        if raw_masked is not None and not is_account_id_masked(raw_masked):
            errors.append(_error(f"positions[{index}].account_id_masked", "Position account_id_masked must be redacted."))
        if raw_position.get("account_id") or raw_position.get("accountId"):
            warnings.append(_warning(f"positions[{index}].account_id", "Raw position account id was redacted during normalization."))
        if not _text(position.get("symbol")):
            errors.append(_error(f"positions[{index}].symbol", "Position symbol is required."))

    cash_summary = normalized.get("cash_summary") if isinstance(normalized.get("cash_summary"), Mapping) else {}
    if cash_summary.get("cash_available") is None:
        warnings.append(_warning("cash_summary.cash_available", "Snapshot cash summary is missing."))
    if cash_summary.get("context_only") is not True:
        errors.append(_error("cash_summary.context_only", "Cash summary must be context-only."))

    parsed_as_of = _parse_date(normalized.get("as_of"))
    if parsed_as_of is None:
        warnings.append(_warning("as_of", "Snapshot as_of timestamp is missing or invalid."))
    else:
        today = today or date.today()
        age = max(0, (today - parsed_as_of).days)
        if age > max(0, stale_after_days):
            warnings.append(_warning("as_of", f"Broker snapshot is stale ({age} days old)."))

    return _validation_result(errors, warnings, normalized)


__all__ = [
    "READ_ONLY_NOTE",
    "SNAPSHOT_SOURCES",
    "SYNC_STATUSES",
    "is_account_id_masked",
    "normalize_broker_snapshot",
    "redact_account_id",
    "validate_broker_snapshot",
]
