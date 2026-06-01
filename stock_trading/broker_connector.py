"""Read-only broker connector boundary.

This module defines the future broker-integration seam without implementing a
live broker provider. It is intentionally read-only: connectors may fetch a
snapshot, but they must not expose order, transfer, margin, options, shorting,
or account-write behavior.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Protocol


FORBIDDEN_METHOD_NAMES = (
    "place_order",
    "preview_order",
    "modify_order",
    "cancel_order",
    "transfer_funds",
    "enable_margin",
    "trade_options",
    "short_sell",
)

BROKER_SNAPSHOT_STATUSES = {
    "available",
    "unavailable",
    "disabled",
    "stale",
    "missing",
    "error",
}


class BrokerConnector(Protocol):
    """Read-only broker connector interface."""

    def fetch_readonly_snapshot(self) -> dict[str, object]:
        """Return a JSON-native broker snapshot without account writes."""


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _as_mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _as_list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def broker_snapshot_contract_errors(snapshot: Mapping[str, object]) -> list[str]:
    """Return contract errors for a broker read-only snapshot."""

    errors: list[str] = []
    status = str(snapshot.get("status") or "").strip()
    if status not in BROKER_SNAPSHOT_STATUSES:
        errors.append("status must be one of the broker snapshot statuses")
    if not str(snapshot.get("source") or "").strip():
        errors.append("source is required")
    if not str(snapshot.get("fetched_at") or snapshot.get("as_of") or "").strip():
        errors.append("fetched_at or as_of timestamp is required")
    if snapshot.get("review_only") is not True:
        errors.append("review_only must be true")
    if snapshot.get("recommendation_only") is not True:
        errors.append("recommendation_only must be true")

    accounts = snapshot.get("accounts", [])
    positions = snapshot.get("positions", [])
    cash = snapshot.get("cash", {})
    warnings = snapshot.get("warnings", [])
    if not isinstance(accounts, list):
        errors.append("accounts must be a list")
    if not isinstance(positions, list):
        errors.append("positions must be a list")
    if not isinstance(cash, Mapping):
        errors.append("cash must be an object")
    if not isinstance(warnings, list):
        errors.append("warnings must be a list")

    for index, account in enumerate(_as_list(accounts)):
        account_row = _as_mapping(account)
        if not str(account_row.get("account_id_masked") or "").strip():
            errors.append(f"accounts[{index}].account_id_masked is required")

    for index, position in enumerate(_as_list(positions)):
        position_row = _as_mapping(position)
        if not str(position_row.get("symbol") or "").strip():
            errors.append(f"positions[{index}].symbol is required")
        if "market_value" not in position_row:
            errors.append(f"positions[{index}].market_value is required")

    return errors


def validate_broker_snapshot(snapshot: Mapping[str, object]) -> dict[str, object]:
    """Validate and return a JSON-native broker snapshot."""

    errors = broker_snapshot_contract_errors(snapshot)
    if errors:
        raise ValueError(f"Invalid broker snapshot: {'; '.join(errors)}")
    return dict(snapshot)


class DisabledBrokerConnector:
    """Disabled-by-default connector with no credentials and no network calls."""

    def fetch_readonly_snapshot(self) -> dict[str, object]:
        return validate_broker_snapshot(
            {
                "status": "disabled",
                "source": "disabled_broker_connector",
                "as_of": "",
                "fetched_at": utc_timestamp(),
                "accounts": [],
                "positions": [],
                "cash": {
                    "available_cash": None,
                    "buying_capacity": None,
                    "currency": "USD",
                    "source": "disabled",
                },
                "warnings": [
                    "Broker connector is disabled by default; no credentials or network calls are used."
                ],
                "review_only": True,
                "recommendation_only": True,
                "broker_behavior": "read_only_disabled",
            }
        )


class FixtureBrokerConnector:
    """Fixture-backed connector for deterministic tests and local review."""

    def __init__(self, fixture_path: str | Path) -> None:
        self.fixture_path = Path(fixture_path)

    def fetch_readonly_snapshot(self) -> dict[str, object]:
        with self.fixture_path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            raise ValueError("Broker fixture must contain a JSON object.")
        return validate_broker_snapshot(payload)


__all__ = [
    "BROKER_SNAPSHOT_STATUSES",
    "FORBIDDEN_METHOD_NAMES",
    "BrokerConnector",
    "DisabledBrokerConnector",
    "FixtureBrokerConnector",
    "broker_snapshot_contract_errors",
    "validate_broker_snapshot",
]
