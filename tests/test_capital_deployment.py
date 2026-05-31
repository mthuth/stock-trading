#!/usr/bin/env python3
"""Tests for review-only capital deployment context."""

from __future__ import annotations

import ast
import copy
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from stock_trading.allocation_safety import allocation_safety_for_candidate
from stock_trading.capital_deployment import capital_deployment_context, long_term_sleeve_context


ROOT = Path(__file__).resolve().parents[1]


def targets(**capital_availability: object) -> dict[str, object]:
    config: dict[str, object] = {
        "account_value": 50000,
        "capital_availability": capital_availability,
        "sleeves": {
            "long_term": {
                "target_pct": 0.75,
                "max_single_stock_pct": 0.10,
            },
            "short_term": {
                "target_pct": 0.25,
                "max_single_stock_pct": 0.05,
            },
        },
        "speculative_ai": {"allow_buy_recommendations": False},
    }
    return config


def candidate(symbol: str = "MSFT", sleeve: str = "long_term") -> dict[str, object]:
    return {
        "input": SimpleNamespace(symbol=symbol, company="Microsoft", sleeve=sleeve, trade_type="long_term"),
        "action": "Add",
        "score": 82.0,
    }


def ready_gate() -> dict[str, object]:
    return {"safe_to_buy": True, "status": "Ready", "candidate_action": "Add", "reasons": []}


def blocked_gate() -> dict[str, object]:
    return {
        "safe_to_buy": False,
        "status": "Blocked",
        "candidate_action": "Add",
        "reasons": ["Low target confidence"],
    }


class CapitalDeploymentTests(unittest.TestCase):
    def test_configured_monthly_buy_capacity_is_deployable(self) -> None:
        context = capital_deployment_context(
            targets(monthly_buy_capacity=2500, source="configured"),
            candidate=candidate(),
            decision_gate=ready_gate(),
            allocation_safety={"suggested_amount": 2500, "decision_safety_status": "Ready"},
            sleeve_market_values={"long_term": 10000},
            today=date(2026, 5, 31),
        )

        self.assertEqual(context["available_capital"], 2500)
        self.assertEqual(context["monthly_buy_capacity"], 2500)
        self.assertEqual(context["capital_source"], "configured")
        self.assertEqual(context["deployable_amount"], 2500)
        self.assertEqual(context["held_amount"], 0)
        self.assertEqual(context["status"], "deployable")
        self.assertTrue(context["recommendation_only"])

    def test_manual_available_cash_is_capital_source(self) -> None:
        context = capital_deployment_context(
            targets(manual_available_cash=1800, as_of_date="2026-05-30"),
            candidate=candidate(),
            decision_gate=ready_gate(),
            allocation_safety={"suggested_amount": 1800, "decision_safety_status": "Ready"},
            today=date(2026, 5, 31),
        )

        self.assertEqual(context["available_capital"], 1800)
        self.assertEqual(context["manual_available_cash"], 1800)
        self.assertEqual(context["capital_source"], "manual")
        self.assertEqual(context["capital_freshness"], "fresh")

    def test_unknown_capital_availability_needs_manual_update(self) -> None:
        context = capital_deployment_context(targets(), candidate=candidate(), decision_gate=ready_gate())

        self.assertIsNone(context["available_capital"])
        self.assertIsNone(context["deployable_amount"])
        self.assertIsNone(context["held_amount"])
        self.assertEqual(context["capital_source"], "unknown")
        self.assertEqual(context["capital_status"], "needs_manual_update")
        self.assertEqual(context["status"], "needs_manual_update")

    def test_stale_as_of_date_is_visible(self) -> None:
        context = capital_deployment_context(
            targets(manual_available_cash=2000, as_of_date="2026-03-01"),
            candidate=candidate(),
            decision_gate=ready_gate(),
            allocation_safety={"suggested_amount": 2000, "decision_safety_status": "Ready"},
            today=date(2026, 5, 31),
        )

        self.assertEqual(context["capital_status"], "stale")
        self.assertEqual(context["capital_freshness"], "stale")
        self.assertEqual(context["capital_as_of_date"], "2026-03-01")

    def test_safe_add_uses_deployable_amount_from_existing_allocation_output(self) -> None:
        allocation = allocation_safety_for_candidate(
            candidate(),
            ready_gate(),
            positions={},
            targets=targets(monthly_buy_capacity=2500),
            account_value=50000,
            buy_capacity=2500,
            sleeve_market_values={"long_term": 10000},
        )

        context = capital_deployment_context(
            targets(monthly_buy_capacity=2500),
            candidate=candidate(),
            decision_gate=ready_gate(),
            allocation_safety=allocation,
            sleeve_market_values={"long_term": 10000},
            today=date(2026, 5, 31),
        )

        self.assertEqual(context["deployable_amount"], 2500)
        self.assertEqual(context["held_amount"], 0)
        self.assertEqual(context["allocation_safety"]["suggested_amount"], 2500)

    def test_blocked_add_holds_capital(self) -> None:
        allocation = allocation_safety_for_candidate(
            candidate(),
            blocked_gate(),
            positions={},
            targets=targets(monthly_buy_capacity=2500),
            account_value=50000,
            buy_capacity=2500,
            sleeve_market_values={"long_term": 10000},
        )

        context = capital_deployment_context(
            targets(monthly_buy_capacity=2500),
            candidate=candidate(),
            decision_gate=blocked_gate(),
            allocation_safety=allocation,
            today=date(2026, 5, 31),
        )

        self.assertEqual(context["deployable_amount"], 0)
        self.assertEqual(context["held_amount"], 2500)
        self.assertEqual(context["status"], "held_no_safe_add")
        self.assertIn("not decision-safe", context["reason"])

    def test_allocation_cap_reduces_deployable_amount(self) -> None:
        allocation = allocation_safety_for_candidate(
            candidate("NVDA"),
            ready_gate(),
            positions={"NVDA": {"market_value": 4800}},
            targets=targets(monthly_buy_capacity=2500),
            account_value=50000,
            buy_capacity=2500,
            sleeve_market_values={"long_term": 10000},
        )

        context = capital_deployment_context(
            targets(monthly_buy_capacity=2500),
            candidate=candidate("NVDA"),
            decision_gate=ready_gate(),
            allocation_safety=allocation,
            sleeve_market_values={"long_term": 10000},
            today=date(2026, 5, 31),
        )

        self.assertEqual(context["deployable_amount"], 200)
        self.assertEqual(context["held_amount"], 2300)
        self.assertEqual(context["status"], "reduced_by_allocation")
        self.assertIn("single-stock cap", " ".join(context["reduction_reasons"]))

    def test_long_term_sleeve_context_includes_target_and_current_positioning(self) -> None:
        sleeve = long_term_sleeve_context(
            targets(monthly_buy_capacity=2500),
            sleeve_market_values={"long_term": 30000},
        ).to_context()

        self.assertEqual(sleeve["sleeve"], "long_term")
        self.assertEqual(sleeve["label"], "Long-term/core")
        self.assertEqual(sleeve["target_pct"], 75.0)
        self.assertEqual(sleeve["target_amount"], 37500)
        self.assertEqual(sleeve["current_value"], 30000)
        self.assertEqual(sleeve["remaining_to_target"], 7500)
        self.assertEqual(sleeve["status"], "below_target")

    def test_future_broker_snapshot_source_is_labeled_without_broker_behavior(self) -> None:
        context = capital_deployment_context(
            targets(monthly_buy_capacity=900, source="future_broker_snapshot"),
            candidate=candidate(),
            decision_gate=ready_gate(),
            allocation_safety={"suggested_amount": 900, "decision_safety_status": "Ready"},
            today=date(2026, 5, 31),
        )

        self.assertEqual(context["capital_source"], "future_broker_snapshot")
        self.assertEqual(context["broker_behavior"], "none")
        self.assertEqual(context["order_behavior"], "none")
        self.assertIn("does not connect to brokers", context["notes"])

    def test_no_broker_behavior_or_imports(self) -> None:
        source = (ROOT / "stock_trading" / "capital_deployment.py").read_text()
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
        rec = candidate()
        config = targets(monthly_buy_capacity=2500)
        before_rec = copy.deepcopy(rec)
        before_config = copy.deepcopy(config)

        capital_deployment_context(
            config,
            candidate=rec,
            decision_gate=ready_gate(),
            allocation_safety={"suggested_amount": 2500, "decision_safety_status": "Ready"},
            today=date(2026, 5, 31),
        )

        self.assertEqual(rec, before_rec)
        self.assertEqual(config, before_config)


if __name__ == "__main__":
    unittest.main()
