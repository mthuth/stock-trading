#!/usr/bin/env python3
"""Tests for read-only broker holdings allocation context."""

from __future__ import annotations

import json
import unittest
from copy import deepcopy
from pathlib import Path

from stock_trading.broker_holdings_context import build_broker_holdings_context


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "broker_readonly" / "read_only_snapshot.json"


def load_snapshot() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def sleeve_mapping() -> dict[str, str]:
    return {
        "MSFT": "long_term",
        "NVDA": "long_term",
        "AMD": "long_term",
        "SOUN": "speculative_ai",
    }


def portfolio_caps() -> dict[str, object]:
    return {
        "single_stock_max_pct": 0.25,
        "sleeve_caps": {
            "long_term": 0.80,
            "speculative_ai": 0.05,
            "tactical": 0.25,
        },
    }


class BrokerHoldingsContextTests(unittest.TestCase):
    def build_context(self, **overrides: object) -> dict[str, object]:
        options: dict[str, object] = {
            "sleeve_mapping": sleeve_mapping(),
            "portfolio_caps": portfolio_caps(),
            "current_date": "2026-06-02",
        }
        options.update(overrides)
        return build_broker_holdings_context(load_snapshot(), **options)

    def test_holdings_are_summarized_by_symbol(self) -> None:
        context = self.build_context()
        positions = context["positions_by_symbol"]

        self.assertEqual(positions["MSFT"]["quantity"], 15.0)
        self.assertEqual(positions["MSFT"]["market_value"], 6300.0)
        self.assertEqual(positions["MSFT"]["account_ids"], ["acct-***-001", "acct-***-002"])
        self.assertTrue(positions["MSFT"]["read_only"])
        self.assertTrue(positions["MSFT"]["context_only"])

    def test_total_market_value_and_cash_available_are_reported(self) -> None:
        context = self.build_context()

        self.assertEqual(context["total_market_value"], 17400.0)
        self.assertEqual(context["cash_available"], 4000.0)
        self.assertEqual(context["total_account_value"], 21400.0)

    def test_multiple_accounts_and_position_count_are_reported(self) -> None:
        context = self.build_context()

        self.assertEqual(context["account_count"], 2)
        self.assertEqual(context["position_count"], 5)
        self.assertEqual(context["source"], "fixture_broker_read_only_snapshot")
        self.assertEqual(context["as_of"], "2026-06-01T08:00:00")

    def test_sleeve_mapping_present_builds_exposure(self) -> None:
        context = self.build_context()

        self.assertEqual(context["sleeve_exposure"]["long_term"]["market_value"], 16500.0)
        self.assertEqual(context["long_term_core_exposure"]["pct_of_holdings"], 94.83)
        self.assertEqual(context["tactical_speculative_exposure"]["market_value"], 900.0)

    def test_missing_sleeve_mapping_returns_unknown_and_warning(self) -> None:
        context = self.build_context(sleeve_mapping={"MSFT": "long_term"})

        self.assertEqual(context["positions_by_symbol"]["NVDA"]["sleeve"], "unknown")
        self.assertIn("sleeve_mapping_missing:NVDA", context["warnings"])
        self.assertIn("unknown", context["sleeve_exposure"])

    def test_single_stock_concentration_warning_is_review_only(self) -> None:
        context = self.build_context()

        concentration = context["single_stock_concentration"]
        self.assertEqual(concentration["symbol"], "NVDA")
        self.assertEqual(concentration["pct_of_holdings"], 41.38)
        self.assertIn(
            "single_stock_concentration:NVDA:41.38%>25.00%",
            context["cap_pressure_warnings"],
        )
        self.assertTrue(concentration["read_only"])

    def test_cap_pressure_warning_includes_sleeve_pressure(self) -> None:
        context = self.build_context()

        self.assertIn(
            "sleeve_cap_pressure:long_term:94.83%>80.00%",
            context["cap_pressure_warnings"],
        )
        self.assertIn(
            "sleeve_cap_pressure:speculative_ai:5.17%>5.00%",
            context["cap_pressure_warnings"],
        )

    def test_missing_cost_basis_warning_is_visible(self) -> None:
        context = self.build_context()

        self.assertEqual(context["positions_by_symbol"]["AMD"]["cost_basis_status"], "missing")
        self.assertIn("missing_cost_basis:AMD", context["missing_cost_basis_warnings"])

    def test_stale_snapshot_warning_is_visible(self) -> None:
        context = self.build_context(current_date="2026-06-10", stale_after_days=3)

        self.assertEqual(context["snapshot_status"], "stale")
        self.assertIn("snapshot_stale:9d>3d", context["stale_snapshot_warnings"])

    def test_missing_snapshot_preserves_manual_capital_fallback(self) -> None:
        fallback = {
            "manual_available_cash": 1000,
            "monthly_buy_capacity": 2500,
            "source": "configured",
        }
        context = build_broker_holdings_context(None, manual_capital_fallback=fallback)

        self.assertEqual(context["snapshot_status"], "missing")
        self.assertEqual(context["cash_available"], 1000.0)
        self.assertEqual(context["capital_availability_fallback"], fallback)
        self.assertIn("broker_snapshot_missing", context["warnings"][0])

    def test_no_recommendation_or_trading_mutation(self) -> None:
        recommendations = [
            {"symbol": "MSFT", "action": "Add", "score": 82.0, "suggested_amount": 2500.0}
        ]
        before = deepcopy(recommendations)
        context = self.build_context()

        self.assertEqual(recommendations, before)
        self.assertTrue(context["read_only"])
        self.assertTrue(context["context_only"])
        self.assertTrue(context["recommendation_only"])
        self.assertEqual(context["broker_behavior"], "read_only")
        self.assertEqual(context["order_behavior"], "none")
        self.assertIn("does not connect to brokers", context["notes"])


if __name__ == "__main__":
    unittest.main()
