"""Local broker read-only snapshot fixture/manual import helpers."""

from __future__ import annotations

import csv
import json
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Mapping


READ_ONLY_NOTE = (
    "Broker snapshot import is read-only fixture/manual context. It must not "
    "connect to live brokers, preview orders, place trades, modify trades, cancel "
    "orders, write broker accounts, alter recommendations, tune scores, change "
    "targets, change decision safety, change allocation formulas, or imply "
    "guaranteed performance."
)
REJECTED_KEY_TERMS = {
    "token",
    "secret",
    "password",
    "oauth",
    "refresh",
    "session",
    "authorization",
    "api_key",
    "apikey",
    "order",
    "trade",
    "option",
    "margin_order",
    "short_sale",
}
MARGIN_CONTEXT_TERMS = {"margin", "buying_power", "day_trading", "options", "short"}
ALLOWED_REJECT_TERM_KEYS = {"no_order_capability"}


def text(value: object, default: str = "") -> str:
    if value is None:
        return default
    result = str(value).strip()
    return result if result else default


def token(value: object) -> str:
    return text(value).lower().replace("-", "_").replace(" ", "_")


def to_float(value: object) -> float | None:
    if value in ("", None):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def first_present(row: Mapping[str, object], *keys: str) -> object:
    for key in keys:
        if key in row and row.get(key) not in ("", None):
            return row.get(key)
    return None


def to_date(value: object) -> date | None:
    raw = text(value)
    if not raw:
        return None
    for candidate in (raw[:10], raw.replace("Z", "+00:00"), raw):
        try:
            return datetime.fromisoformat(candidate).date()
        except ValueError:
            continue
    return None


def mask_account_id(value: object) -> str:
    raw = text(value)
    if not raw:
        return ""
    if "*" in raw or raw.lower().startswith("masked"):
        visible = "".join(char for char in raw if char.isalnum())
        return f"****{visible[-4:]}" if visible else "****"
    clean = "".join(char for char in raw if char.isalnum())
    return f"****{clean[-4:]}" if len(clean) >= 4 else "****"


def _walk_rejected_keys(value: object, path: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = token(key)
            if key_text not in ALLOWED_REJECT_TERM_KEYS and any(term in key_text for term in REJECTED_KEY_TERMS):
                found.append(f"{path}.{key}")
            found.extend(_walk_rejected_keys(item, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(_walk_rejected_keys(item, f"{path}[{index}]"))
    return found


def _warnings_for_margin_context(value: object, path: str = "$") -> list[str]:
    warnings: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = token(key)
            if any(term in key_text for term in MARGIN_CONTEXT_TERMS):
                warnings.append(
                    f"Broker field {path}.{key} is imported as read-only context only; it is not trading permission."
                )
            warnings.extend(_warnings_for_margin_context(item, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            warnings.extend(_warnings_for_margin_context(item, f"{path}[{index}]"))
    return warnings


def validate_no_secrets_or_orders(payload: object) -> None:
    found = _walk_rejected_keys(payload)
    if found:
        raise ValueError(
            "Broker snapshot contains secret/token/order/trading fields that are not allowed: "
            + ", ".join(sorted(found))
        )


def list_rows(value: object) -> list[dict[str, object]]:
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, Mapping)]
    if isinstance(value, Mapping):
        return [dict(value)]
    return []


def source_label(payload: Mapping[str, object], fallback: str) -> str:
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {}
    return text(
        payload.get("source")
        or metadata.get("source")
        or payload.get("broker")
        or metadata.get("broker")
        or fallback
    )


def snapshot_as_of(payload: Mapping[str, object]) -> str:
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {}
    return text(
        payload.get("as_of")
        or payload.get("as_of_date")
        or metadata.get("as_of")
        or metadata.get("as_of_date")
        or metadata.get("snapshot_at")
    )


def normalize_position(row: Mapping[str, object], account_id_masked: str = "") -> dict[str, object]:
    quantity = to_float(first_present(row, "quantity", "qty"))
    market_value = to_float(first_present(row, "market_value", "value"))
    last_price = to_float(first_present(row, "last_price", "price"))
    if market_value is None and quantity is not None and last_price is not None:
        market_value = quantity * last_price
    return {
        "account_id_masked": account_id_masked or mask_account_id(row.get("account_id") or row.get("account")),
        "symbol": text(row.get("symbol")).upper(),
        "description": text(row.get("description") or row.get("company") or row.get("security_name")),
        "quantity": quantity,
        "market_value": market_value,
        "last_price": last_price,
        "asset_type": text(row.get("asset_type") or row.get("security_type") or "equity"),
        "sleeve": text(row.get("sleeve")),
        "source": text(row.get("source") or "manual_fixture"),
        "read_only": True,
    }


def normalize_account(row: Mapping[str, object], positions: Iterable[Mapping[str, object]] = ()) -> dict[str, object]:
    masked_id = mask_account_id(row.get("account_id") or row.get("account_number") or row.get("id"))
    cash = to_float(first_present(row, "cash", "available_cash", "cash_available"))
    buying_capacity = to_float(first_present(row, "buying_capacity", "buying_power", "available_to_buy"))
    normalized_positions = [normalize_position(position, masked_id) for position in positions]
    total_market_value = sum(
        value for value in (position.get("market_value") for position in normalized_positions) if isinstance(value, (int, float))
    )
    return {
        "account_id_masked": masked_id,
        "account_name": text(row.get("account_name") or row.get("name")),
        "account_type": text(row.get("account_type") or row.get("type")),
        "cash": cash,
        "buying_capacity": buying_capacity,
        "market_value": to_float(row.get("market_value")) if row.get("market_value") not in ("", None) else total_market_value,
        "currency": text(row.get("currency") or "USD"),
        "positions": sorted(normalized_positions, key=lambda item: text(item.get("symbol"))),
        "position_count": len(normalized_positions),
        "read_only": True,
        "no_order_capability": True,
    }


def positions_by_account(rows: Iterable[Mapping[str, object]]) -> dict[str, list[dict[str, object]]]:
    result: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        masked = mask_account_id(row.get("account_id") or row.get("account") or row.get("account_number"))
        result.setdefault(masked, []).append(dict(row))
    return result


def normalize_json_payload(payload: Mapping[str, object], *, input_ref: str, today: date | None = None, stale_after_days: int = 7) -> dict[str, object]:
    validate_no_secrets_or_orders(payload)
    today = today or date.today()
    warnings = _warnings_for_margin_context(payload)
    source = source_label(payload, "manual_json")
    as_of = snapshot_as_of(payload)
    account_rows = list_rows(payload.get("accounts"))
    top_positions = list_rows(payload.get("positions"))
    by_account = positions_by_account(top_positions)
    accounts: list[dict[str, object]] = []
    if account_rows:
        for account in account_rows:
            nested_positions = list_rows(account.get("positions"))
            masked = mask_account_id(account.get("account_id") or account.get("account_number") or account.get("id"))
            positions = nested_positions or by_account.get(masked, [])
            accounts.append(normalize_account(account, positions))
    elif top_positions:
        accounts.append(normalize_account({"account_id": "manual-import", "account_name": "Manual imported account"}, top_positions))
    else:
        warnings.append("Broker snapshot has no account or position rows.")

    warnings.extend(snapshot_warnings(accounts, as_of, today=today, stale_after_days=stale_after_days))
    return build_snapshot(
        accounts,
        source=source,
        as_of=as_of,
        input_ref=input_ref,
        warnings=warnings,
    )


def snapshot_warnings(
    accounts: Iterable[Mapping[str, object]],
    as_of: str,
    *,
    today: date,
    stale_after_days: int,
) -> list[str]:
    warnings: list[str] = []
    if not as_of:
        warnings.append("Broker snapshot is missing an as-of timestamp.")
    else:
        parsed = to_date(as_of)
        if not parsed:
            warnings.append("Broker snapshot as-of timestamp could not be parsed.")
        else:
            age = max(0, (today - parsed).days)
            if age > stale_after_days:
                warnings.append(f"Broker snapshot is stale: as-of date is {age} days old.")
    for account in accounts:
        if account.get("cash") is None:
            warnings.append(f"Account {account.get('account_id_masked') or 'unknown'} is missing cash.")
        if account.get("buying_capacity") is None:
            warnings.append(
                f"Account {account.get('account_id_masked') or 'unknown'} is missing buying capacity; manual/config fallback may still be needed."
            )
    return warnings


def build_snapshot(
    accounts: list[dict[str, object]],
    *,
    source: str,
    as_of: str,
    input_ref: str,
    warnings: Iterable[str],
) -> dict[str, object]:
    account_count = len(accounts)
    position_count = sum(int(account.get("position_count") or 0) for account in accounts)
    total_cash = sum(value for value in (account.get("cash") for account in accounts) if isinstance(value, (int, float)))
    total_buying_capacity = sum(
        value for value in (account.get("buying_capacity") for account in accounts) if isinstance(value, (int, float))
    )
    total_market_value = sum(value for value in (account.get("market_value") for account in accounts) if isinstance(value, (int, float)))
    return {
        "schema_version": "broker_readonly_snapshot_v1",
        "source": source,
        "input_ref": input_ref,
        "as_of": as_of,
        "read_only": True,
        "recommendation_only": True,
        "no_order_capability": True,
        "broker_api_called": False,
        "accounts": sorted(accounts, key=lambda item: text(item.get("account_id_masked"))),
        "summary": {
            "account_count": account_count,
            "position_count": position_count,
            "total_cash": round(total_cash, 4),
            "total_buying_capacity": round(total_buying_capacity, 4),
            "total_market_value": round(total_market_value, 4),
            "read_only": True,
            "no_order_capability": True,
        },
        "validation": {
            "ok": True,
            "warnings": list(dict.fromkeys(warnings)),
            "rejected_fields": [],
            "read_only": True,
            "no_order_capability": True,
        },
        "notes": READ_ONLY_NOTE,
    }


def load_json_snapshot(path: Path, *, today: date | None = None, stale_after_days: int = 7) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("Broker JSON snapshot must be an object.")
    return normalize_json_payload(payload, input_ref=str(path), today=today, stale_after_days=stale_after_days)


def load_csv_rows(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def load_csv_snapshot(directory: Path, *, today: date | None = None, stale_after_days: int = 7) -> dict[str, object]:
    accounts_path = directory / "accounts.csv"
    positions_path = directory / "positions.csv"
    account_rows = load_csv_rows(accounts_path)
    position_rows = load_csv_rows(positions_path)
    payload = {
        "source": "manual_csv",
        "as_of": "",
        "accounts": account_rows,
        "positions": position_rows,
    }
    if account_rows:
        payload["as_of"] = text(account_rows[0].get("as_of") or account_rows[0].get("as_of_date"))
    validate_no_secrets_or_orders(payload)
    if not account_rows and not position_rows:
        raise ValueError("CSV broker snapshot directory must contain accounts.csv or positions.csv.")
    return normalize_json_payload(payload, input_ref=str(directory), today=today, stale_after_days=stale_after_days)


def import_broker_snapshot(path: str | Path, *, today: date | None = None, stale_after_days: int = 7) -> dict[str, object]:
    """Import a local JSON file or accounts.csv/positions.csv directory."""

    input_path = Path(path)
    if input_path.is_dir():
        return load_csv_snapshot(input_path, today=today, stale_after_days=stale_after_days)
    if input_path.suffix.lower() == ".json":
        return load_json_snapshot(input_path, today=today, stale_after_days=stale_after_days)
    raise ValueError("Broker snapshot input must be a JSON file or a directory containing accounts.csv/positions.csv.")


def write_snapshot(snapshot: Mapping[str, object], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


__all__ = [
    "READ_ONLY_NOTE",
    "import_broker_snapshot",
    "load_csv_snapshot",
    "load_json_snapshot",
    "mask_account_id",
    "normalize_json_payload",
    "write_snapshot",
]
