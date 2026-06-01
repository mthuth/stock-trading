#!/usr/bin/env python3
"""Tests for the read-only broker connector boundary."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from stock_trading.broker_connector import (
    FORBIDDEN_METHOD_NAMES,
    BrokerConnector,
    DisabledBrokerConnector,
    FixtureBrokerConnector,
    validate_broker_snapshot,
)


class BrokerConnectorTests(unittest.TestCase):
    def test_disabled_connector_returns_disabled_snapshot_without_network(self) -> None:
        connector = DisabledBrokerConnector()

        with patch("socket.create_connection", side_effect=AssertionError("network call attempted")):
            snapshot = connector.fetch_readonly_snapshot()

        self.assertEqual(snapshot["status"], "disabled")
        self.assertEqual(snapshot["source"], "disabled_broker_connector")
        self.assertEqual(snapshot["accounts"], [])
        self.assertEqual(snapshot["positions"], [])
        self.assertTrue(snapshot["review_only"])
        self.assertTrue(snapshot["recommendation_only"])
        self.assertIn("no credentials or network calls", str(snapshot["warnings"][0]))
        validate_broker_snapshot(snapshot)

    def test_fixture_connector_reads_fixture_snapshot(self) -> None:
        payload = {
            "status": "available",
            "source": "fixture_broker_snapshot",
            "as_of": "2026-05-31T13:30:00+00:00",
            "fetched_at": "2026-05-31T13:31:00+00:00",
            "accounts": [
                {
                    "account_id_masked": "****0001",
                    "account_type": "IRA_ROLLOVER",
                }
            ],
            "positions": [
                {
                    "symbol": "MSFT",
                    "quantity": 4,
                    "market_value": 1700.25,
                    "sleeve": "long_term_core",
                }
            ],
            "cash": {
                "available_cash": 1250.0,
                "buying_capacity": 1250.0,
                "currency": "USD",
                "source": "fixture",
            },
            "warnings": [],
            "review_only": True,
            "recommendation_only": True,
            "broker_behavior": "read_only_fixture",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture_path = Path(temp_dir) / "broker_snapshot.json"
            fixture_path.write_text(json.dumps(payload), encoding="utf-8")

            snapshot = FixtureBrokerConnector(fixture_path).fetch_readonly_snapshot()

        self.assertEqual(snapshot["source"], "fixture_broker_snapshot")
        self.assertEqual(snapshot["cash"]["available_cash"], 1250.0)
        self.assertEqual(snapshot["positions"][0]["symbol"], "MSFT")
        validate_broker_snapshot(snapshot)

    def test_forbidden_order_and_account_write_methods_do_not_exist(self) -> None:
        connector_classes = (BrokerConnector, DisabledBrokerConnector, FixtureBrokerConnector)
        for connector_class in connector_classes:
            for method_name in FORBIDDEN_METHOD_NAMES:
                self.assertFalse(
                    hasattr(connector_class, method_name),
                    f"{connector_class.__name__} must not expose {method_name}",
                )

    def test_snapshot_contract_rejects_missing_readonly_flags(self) -> None:
        with self.assertRaises(ValueError):
            validate_broker_snapshot(
                {
                    "status": "available",
                    "source": "bad_fixture",
                    "fetched_at": "2026-05-31T13:31:00+00:00",
                    "accounts": [],
                    "positions": [],
                    "cash": {},
                    "warnings": [],
                    "review_only": False,
                    "recommendation_only": True,
                }
            )

    def test_no_credentials_required_for_disabled_or_fixture_tests(self) -> None:
        payload = {
            "status": "unavailable",
            "source": "fixture_broker_snapshot",
            "as_of": "2026-05-31T13:30:00+00:00",
            "accounts": [],
            "positions": [],
            "cash": {"available_cash": None, "buying_capacity": None, "currency": "USD"},
            "warnings": ["Fixture intentionally unavailable."],
            "review_only": True,
            "recommendation_only": True,
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture_path = Path(temp_dir) / "broker_snapshot.json"
            fixture_path.write_text(json.dumps(payload), encoding="utf-8")

            with patch.dict(os.environ, {}, clear=True):
                disabled_snapshot = DisabledBrokerConnector().fetch_readonly_snapshot()
                fixture_snapshot = FixtureBrokerConnector(fixture_path).fetch_readonly_snapshot()

        self.assertEqual(disabled_snapshot["status"], "disabled")
        self.assertEqual(fixture_snapshot["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
