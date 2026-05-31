#!/usr/bin/env python3
"""Tests for manual/config capital availability context."""

from __future__ import annotations

import ast
import copy
import unittest
from datetime import date
from pathlib import Path

from stock_trading.capital_availability import (
    capital_availability_context,
    capital_availability_from_config,
)


ROOT = Path(__file__).resolve().parents[1]


class CapitalAvailabilityTests(unittest.TestCase):
    def test_configured_monthly_buy_capacity(self) -> None:
        result = capital_availability_from_config(
            {"capital_availability": {"monthly_buy_capacity": 2500, "source": "configured"}}
        )

        self.assertEqual(result.available_amount, 2500)
        self.assertEqual(result.monthly_buy_capacity, 2500)
        self.assertIsNone(result.manual_available_cash)
        self.assertEqual(result.source, "configured")
        self.assertEqual(result.status, "available")
        self.assertTrue(result.review_only)
        self.assertTrue(result.recommendation_only)

    def test_legacy_monthly_contribution_is_read_only_fallback(self) -> None:
        result = capital_availability_from_config({"monthly_contribution": 1250})

        self.assertEqual(result.available_amount, 1250)
        self.assertEqual(result.monthly_buy_capacity, 1250)
        self.assertEqual(result.source, "configured")
        self.assertIn("no as-of date", result.notes.lower())

    def test_manual_available_cash(self) -> None:
        result = capital_availability_from_config(
            {"capital_availability": {"manual_available_cash": 1800, "as_of_date": "2026-05-30"}},
            today=date(2026, 5, 31),
        )

        self.assertEqual(result.available_amount, 1800)
        self.assertEqual(result.manual_available_cash, 1800)
        self.assertIsNone(result.monthly_buy_capacity)
        self.assertEqual(result.source, "manual")
        self.assertEqual(result.freshness, "fresh")

    def test_both_monthly_and_manual_values_use_conservative_available_amount(self) -> None:
        result = capital_availability_from_config(
            {
                "capital_availability": {
                    "monthly_buy_capacity": 2500,
                    "manual_available_cash": 1000,
                    "as_of_date": "2026-05-31",
                }
            },
            today=date(2026, 5, 31),
        )

        self.assertEqual(result.available_amount, 1000)
        self.assertEqual(result.monthly_buy_capacity, 2500)
        self.assertEqual(result.manual_available_cash, 1000)
        self.assertEqual(result.source, "manual_and_configured")

    def test_manual_cash_above_monthly_capacity_uses_monthly_capacity(self) -> None:
        result = capital_availability_from_config(
            {
                "capital_availability": {
                    "monthly_buy_capacity": 2500,
                    "manual_available_cash": 5000,
                    "as_of_date": "2026-05-31",
                }
            },
            today=date(2026, 5, 31),
        )

        self.assertEqual(result.available_amount, 2500)
        self.assertEqual(result.source, "manual_and_configured")

    def test_missing_values_return_needs_manual_update(self) -> None:
        result = capital_availability_from_config({})

        self.assertIsNone(result.available_amount)
        self.assertIsNone(result.monthly_buy_capacity)
        self.assertIsNone(result.manual_available_cash)
        self.assertEqual(result.source, "unknown")
        self.assertEqual(result.status, "needs_manual_update")
        self.assertEqual(result.freshness, "unknown")

    def test_stale_as_of_date(self) -> None:
        result = capital_availability_from_config(
            {"capital_availability": {"manual_available_cash": 2000, "as_of_date": "2026-03-01"}},
            today=date(2026, 5, 31),
            stale_after_days=45,
        )

        self.assertEqual(result.status, "stale")
        self.assertEqual(result.freshness, "stale")
        self.assertIn("91 days old", result.notes)

    def test_zero_cash_is_known_available_amount(self) -> None:
        result = capital_availability_from_config({"capital_availability": {"manual_available_cash": 0}})

        self.assertEqual(result.available_amount, 0)
        self.assertEqual(result.status, "available")
        self.assertEqual(result.source, "manual")

    def test_context_shape_is_json_native(self) -> None:
        context = capital_availability_context(
            {"capital_availability": {"monthly_buy_capacity": "2500", "as_of_date": "2026-05-31"}},
            today=date(2026, 5, 31),
        )

        self.assertEqual(context["available_amount"], 2500)
        self.assertEqual(context["broker_behavior"], "none")
        self.assertIn("recommendation-only", str(context["notes"]).lower())

    def test_no_broker_behavior_or_imports(self) -> None:
        source = (ROOT / "stock_trading" / "capital_availability.py").read_text()
        tree = ast.parse(source)
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)

        self.assertFalse(any("etrade" in imported.lower() for imported in imports))
        self.assertFalse(any("broker" in imported.lower() for imported in imports))
        self.assertNotIn("provider_client", imports)

    def test_no_recommendation_mutation(self) -> None:
        config = {
            "capital_availability": {
                "monthly_buy_capacity": 2500,
                "manual_available_cash": 1000,
                "as_of_date": "2026-05-31",
            },
            "recommendation": {"symbol": "MSFT", "action": "Add", "suggested_amount": 2500},
        }
        before = copy.deepcopy(config)

        capital_availability_from_config(config, today=date(2026, 5, 31))

        self.assertEqual(config, before)


if __name__ == "__main__":
    unittest.main()
