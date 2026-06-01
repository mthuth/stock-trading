#!/usr/bin/env python3
"""Tests for read-only broker capital availability context."""

from __future__ import annotations

import copy
import json
import unittest
from datetime import date
from pathlib import Path

from stock_trading.broker_capital_availability import (
    BUYING_POWER_WARNING,
    MARGIN_WARNING,
    broker_capital_availability_context,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "broker_readonly" / "capital_snapshots.json"


def load_snapshots() -> dict[str, dict[str, object]]:
    return json.loads(FIXTURE_PATH.read_text())


class BrokerCapitalAvailabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.snapshots = load_snapshots()
        self.today = date(2026, 5, 31)
        self.config = {
            "capital_availability": {
                "monthly_buy_capacity": 2500,
                "manual_available_cash": 1000,
                "as_of_date": "2026-05-31",
            }
        }

    def test_valid_broker_cash_used(self) -> None:
        result = broker_capital_availability_context(
            self.snapshots["fresh_broker_cash"],
            self.config,
            today=self.today,
        )

        self.assertEqual(result["available_amount"], 3200.5)
        self.assertEqual(result["monthly_buy_capacity"], 2500)
        self.assertEqual(result["manual_available_cash"], 1000)
        self.assertEqual(result["source"], "broker_readonly")
        self.assertEqual(result["fallback_source"], "manual_and_configured")
        self.assertEqual(result["freshness"], "fresh")
        self.assertEqual(result["status"], "available")
        self.assertEqual(result["broker_cash_context"]["account_id"], "acct_****0001")
        self.assertTrue(result["context_only"])
        self.assertTrue(result["review_only"])
        self.assertTrue(result["recommendation_only"])
        self.assertTrue(result["no_order_capability"])

    def test_stale_broker_snapshot_falls_back(self) -> None:
        result = broker_capital_availability_context(
            self.snapshots["stale_broker_cash"],
            self.config,
            today=self.today,
        )

        self.assertEqual(result["available_amount"], 1000)
        self.assertEqual(result["source"], "manual")
        self.assertEqual(result["fallback_source"], "manual_and_configured")
        self.assertEqual(result["freshness"], "fresh")
        self.assertTrue(any("11 days old" in warning for warning in result["warnings"]))

    def test_invalid_broker_snapshot_falls_back(self) -> None:
        result = broker_capital_availability_context(
            self.snapshots["invalid_broker_cash"],
            {"capital_availability": {"monthly_buy_capacity": 2500, "as_of_date": "2026-05-31"}},
            today=self.today,
        )

        self.assertEqual(result["available_amount"], 2500)
        self.assertEqual(result["source"], "configured")
        self.assertIsNone(result["broker_cash_context"]["cash_available"])
        self.assertTrue(any("does not include valid cash" in warning for warning in result["warnings"]))

    def test_manual_config_fallback_used_without_broker_snapshot(self) -> None:
        result = broker_capital_availability_context(
            None,
            {"capital_availability": {"manual_available_cash": 1800, "as_of_date": "2026-05-31"}},
            today=self.today,
        )

        self.assertEqual(result["available_amount"], 1800)
        self.assertEqual(result["source"], "manual")
        self.assertEqual(result["status"], "available")
        self.assertTrue(any("No broker read-only snapshot" in warning for warning in result["warnings"]))

    def test_no_data_returns_unknown(self) -> None:
        result = broker_capital_availability_context(None, {}, today=self.today)

        self.assertIsNone(result["available_amount"])
        self.assertIsNone(result["monthly_buy_capacity"])
        self.assertEqual(result["source"], "unknown")
        self.assertEqual(result["status"], "needs_manual_update")
        self.assertEqual(result["freshness"], "unknown")
        self.assertTrue(result["context_only"])

    def test_buying_power_is_context_only(self) -> None:
        result = broker_capital_availability_context(
            self.snapshots["buying_power_only"],
            {},
            today=self.today,
        )

        self.assertIsNone(result["available_amount"])
        self.assertEqual(result["source"], "unknown")
        self.assertEqual(result["broker_cash_context"]["buying_power"], {"buying_power": 9000.0})
        self.assertIn(BUYING_POWER_WARNING, result["warnings"])
        self.assertTrue(any("does not include valid cash" in warning for warning in result["warnings"]))

    def test_margin_fields_warn_but_cash_remains_read_only_context(self) -> None:
        result = broker_capital_availability_context(
            self.snapshots["margin_snapshot"],
            self.config,
            today=self.today,
        )

        self.assertEqual(result["available_amount"], 1500)
        self.assertEqual(result["source"], "broker_readonly")
        self.assertIn(BUYING_POWER_WARNING, result["warnings"])
        self.assertIn(MARGIN_WARNING, result["warnings"])
        self.assertEqual(result["broker_cash_context"]["margin_context"]["margin_buying_power"], 12500.0)
        self.assertTrue(result["broker_cash_context"]["context_only"])
        self.assertTrue(result["broker_cash_context"]["no_order_capability"])

    def test_no_order_behavior_or_trade_execution_language(self) -> None:
        result = broker_capital_availability_context(
            self.snapshots["fresh_broker_cash"],
            self.config,
            today=self.today,
        )

        self.assertEqual(result["order_behavior"], "none")
        self.assertTrue(result["no_order_capability"])
        for forbidden_key in ("order_preview", "place_order", "execute_trade", "trade_permission"):
            self.assertNotIn(forbidden_key, result)

        rendered = json.dumps(result).lower()
        self.assertNotIn("place an order", rendered)
        self.assertNotIn("execute trade", rendered)

    def test_no_recommendation_or_input_mutation(self) -> None:
        snapshot = copy.deepcopy(self.snapshots["fresh_broker_cash"])
        config = {
            **self.config,
            "recommendation": {"symbol": "MSFT", "action": "Add", "suggested_amount": 2500},
        }
        before_snapshot = copy.deepcopy(snapshot)
        before_config = copy.deepcopy(config)

        broker_capital_availability_context(snapshot, config, today=self.today)

        self.assertEqual(snapshot, before_snapshot)
        self.assertEqual(config, before_config)


if __name__ == "__main__":
    unittest.main()
