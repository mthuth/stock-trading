#!/usr/bin/env python3
"""Regression tests for explainable suggested-buy allocation safety."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from stock_trading.allocation_safety import allocation_safety_for_candidate


def candidate(symbol: str = "MSFT", sleeve: str = "long_term") -> dict[str, object]:
    return {"input": SimpleNamespace(symbol=symbol, sleeve=sleeve)}


def ready_gate() -> dict[str, object]:
    return {
        "safe_to_buy": True,
        "status": "Ready",
        "candidate_action": "Add",
        "reasons": [],
    }


def blocked_gate() -> dict[str, object]:
    return {
        "safe_to_buy": False,
        "status": "Blocked",
        "candidate_action": "Add",
        "reasons": ["Verification check is still open"],
    }


def targets(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "speculative_ai": {
            "allow_buy_recommendations": False,
            "max_single_stock_pct": 0.05,
        },
        "sleeves": {
            "long_term": {
                "target_pct": 0.75,
                "max_single_stock_pct": 0.10,
            },
            "short_term": {
                "target_pct": 0.25,
                "max_single_stock_pct": 0.05,
            },
            "etf": {
                "target_pct": 0.25,
                "max_single_etf_pct": 0.20,
            },
        },
    }
    for key, value in overrides.items():
        base[key] = value
    return base


class AllocationSafetyTests(unittest.TestCase):
    def test_normal_full_suggested_amount(self) -> None:
        result = allocation_safety_for_candidate(
            candidate(),
            ready_gate(),
            positions={},
            targets=targets(),
            account_value=50000,
            buy_capacity=2500,
            sleeve_market_values={"long_term": 10000},
        )

        self.assertEqual(result.suggested_amount, 2500)
        self.assertEqual(result.applied_limit, "buy_capacity")
        self.assertIn("Full buy capacity", result.reason)

    def test_single_stock_cap_reduces_suggested_amount(self) -> None:
        result = allocation_safety_for_candidate(
            candidate("NVDA"),
            ready_gate(),
            positions={"NVDA": {"market_value": 4800}},
            targets=targets(),
            account_value=50000,
            buy_capacity=2500,
            sleeve_market_values={"long_term": 10000},
        )

        self.assertEqual(result.suggested_amount, 200)
        self.assertEqual(result.applied_limit, "single_stock_cap")
        self.assertIn("single-stock cap", result.reason)

    def test_sleeve_cap_reduces_suggested_amount(self) -> None:
        result = allocation_safety_for_candidate(
            candidate("MSFT"),
            ready_gate(),
            positions={"MSFT": {"market_value": 1000}},
            targets=targets(),
            account_value=50000,
            buy_capacity=2500,
            sleeve_market_values={"long_term": 37000},
        )

        self.assertEqual(result.suggested_amount, 500)
        self.assertEqual(result.applied_limit, "sleeve_cap")
        self.assertIn("sleeve cap", result.reason)

    def test_speculative_cap_reduces_suggested_amount_when_buys_allowed(self) -> None:
        config = targets(
            speculative_ai={
                "allow_buy_recommendations": True,
                "max_single_stock_pct": 0.03,
            }
        )
        result = allocation_safety_for_candidate(
            candidate("SOUN", sleeve="speculative_ai"),
            ready_gate(),
            positions={"SOUN": {"market_value": 1000}},
            targets=config,
            account_value=50000,
            buy_capacity=2500,
            sleeve_market_values={},
        )

        self.assertEqual(result.suggested_amount, 500)
        self.assertEqual(result.applied_limit, "speculative_cap")
        self.assertIn("speculative cap", result.reason)

    def test_already_owned_position_at_cap_holds_buy_capacity(self) -> None:
        result = allocation_safety_for_candidate(
            candidate("NVDA"),
            ready_gate(),
            positions={"NVDA": {"market_value": 5100}},
            targets=targets(),
            account_value=50000,
            buy_capacity=2500,
            sleeve_market_values={"long_term": 10000},
        )

        self.assertEqual(result.suggested_amount, 0)
        self.assertEqual(result.buy_capacity_held, 2500)
        self.assertEqual(result.applied_limit, "single_stock_cap")
        self.assertIn("Buy capacity held", result.reason)

    def test_decision_safety_block_zeroes_suggested_amount(self) -> None:
        result = allocation_safety_for_candidate(
            candidate("MSFT"),
            blocked_gate(),
            positions={},
            targets=targets(),
            account_value=50000,
            buy_capacity=2500,
            sleeve_market_values={"long_term": 10000},
        )

        self.assertEqual(result.suggested_amount, 0)
        self.assertEqual(result.applied_limit, "decision_safety")
        self.assertIn("Verification check is still open", result.reason)

    def test_no_safe_buy_available_is_explainable_in_context(self) -> None:
        result = allocation_safety_for_candidate(
            candidate("MSFT"),
            ready_gate(),
            positions={"MSFT": {"market_value": 5000}},
            targets=targets(),
            account_value=50000,
            buy_capacity=2500,
            sleeve_market_values={"long_term": 10000},
        )
        context = result.to_context()

        self.assertEqual(context["suggested_amount"], 0.0)
        self.assertEqual(context["buy_capacity_held"], 2500)
        self.assertEqual(context["applied_limit"], "single_stock_cap")
        self.assertIn("Buy capacity held", context["reason"])


if __name__ == "__main__":
    unittest.main()
