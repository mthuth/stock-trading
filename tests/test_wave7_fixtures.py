#!/usr/bin/env python3
"""Wave 7 fixture contracts for long-term capital deployment scenarios."""

from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "wave7"


EXPECTED_SCENARIOS = {
    "clear_safe_long_term_add": "Clear safe long-term add",
    "top_blocked_safe_fallback": "Top candidate blocked with safe fallback",
    "all_candidates_blocked": "All candidates blocked",
    "missing_capital_availability": "Missing capital availability",
    "allocation_cap_reduces_amount": "Allocation cap reduces amount",
    "long_term_holding_healthy": "Long-term holding healthy",
    "long_term_holding_needs_review": "Long-term holding needs review",
}

REQUIRED_GUARDRAILS = {
    "no_automatic_trading",
    "no_broker_write",
    "no_order_preview",
    "ai_explanatory_only",
    "no_model_tuning",
}

CONTROLLED_ACTIONS = {"Strong Buy", "Buy", "Add", "Hold", "Watch", "Trim", "Avoid"}
DECISION_MODES = {"long_term_buy_add", "long_term_hold_health"}
HOLDING_HEALTH_STATUSES = {"healthy", "watch", "needs_review"}


def load_fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURE_DIR / f"{name}.json").read_text())


class Wave7FixtureTests(unittest.TestCase):
    maxDiff = None

    def test_expected_fixture_set_exists(self) -> None:
        fixture_ids = {path.stem for path in FIXTURE_DIR.glob("*.json")}

        self.assertEqual(fixture_ids, set(EXPECTED_SCENARIOS))

    def test_fixture_contract_shape(self) -> None:
        for scenario_id, scenario_label in EXPECTED_SCENARIOS.items():
            with self.subTest(scenario_id=scenario_id):
                fixture = load_fixture(scenario_id)

                self.assertEqual(fixture["scenario_id"], scenario_id)
                self.assertEqual(fixture["scenario_label"], scenario_label)
                self.assertIn(fixture["decision_mode"], DECISION_MODES)
                self.assertIs(fixture["recommendation_only"], True)

                capital = fixture["capital_availability"]
                self.assertIsInstance(capital, dict)
                for field in ("status", "source", "suggested_deployment", "hold_reason"):
                    self.assertIn(field, capital)

                expected = fixture["expected_behavior"]
                self.assertIsInstance(expected, dict)
                for field in ("deployment_decision", "suggested_amount", "scenario_assertions"):
                    self.assertIn(field, expected)
                self.assertIsInstance(expected["scenario_assertions"], list)

                guardrails = fixture["guardrails"]
                self.assertEqual(REQUIRED_GUARDRAILS, set(guardrails))
                for value in guardrails.values():
                    self.assertIs(value, True)

    def test_long_term_add_queue_candidate_contract(self) -> None:
        for scenario_id in (
            "clear_safe_long_term_add",
            "top_blocked_safe_fallback",
            "all_candidates_blocked",
            "missing_capital_availability",
            "allocation_cap_reduces_amount",
        ):
            with self.subTest(scenario_id=scenario_id):
                fixture = load_fixture(scenario_id)

                self.assertEqual(fixture["decision_mode"], "long_term_buy_add")
                queue = fixture["long_term_add_queue"]
                self.assertGreaterEqual(len(queue), 1)
                ranks = [row["rank"] for row in queue]
                self.assertEqual(ranks, sorted(ranks))

                for row in queue:
                    self.assertEqual(row["sleeve"], "long_term_core")
                    self.assertIn(row["action"], CONTROLLED_ACTIONS)
                    self.assertIn(row["candidate_role"], {"top_candidate", "fallback_candidate", "blocked_candidate"})
                    self.assertIn(row["target_confidence"], {"High", "Medium", "Low", "Needs review"})

                    gate = row["decision_gate"]
                    self.assertIn(gate["status"], {"Ready", "Blocked"})
                    self.assertIsInstance(gate["safe_to_buy"], bool)
                    self.assertIsInstance(gate["reasons"], list)

                    allocation = row["allocation_safety"]
                    self.assertIn("status", allocation)
                    self.assertIn("suggested_amount", allocation)
                    self.assertIn("reason", allocation)

                    if not gate["safe_to_buy"]:
                        self.assertEqual(allocation["suggested_amount"], 0.0)

    def test_clear_safe_long_term_add_scenario(self) -> None:
        fixture = load_fixture("clear_safe_long_term_add")
        top = fixture["long_term_add_queue"][0]

        self.assertEqual(top["candidate_role"], "top_candidate")
        self.assertIs(top["decision_gate"]["safe_to_buy"], True)
        self.assertGreater(top["allocation_safety"]["suggested_amount"], 0)
        self.assertEqual(fixture["capital_availability"]["status"], "available")
        self.assertIn("top_candidate_safe", fixture["expected_behavior"]["scenario_assertions"])

    def test_top_blocked_safe_fallback_scenario(self) -> None:
        fixture = load_fixture("top_blocked_safe_fallback")
        top, fallback = fixture["long_term_add_queue"]

        self.assertEqual(top["candidate_role"], "blocked_candidate")
        self.assertIs(top["decision_gate"]["safe_to_buy"], False)
        self.assertEqual(top["allocation_safety"]["suggested_amount"], 0.0)
        self.assertEqual(fallback["candidate_role"], "fallback_candidate")
        self.assertIs(fallback["decision_gate"]["safe_to_buy"], True)
        self.assertGreater(fallback["allocation_safety"]["suggested_amount"], 0)
        self.assertEqual(fixture["expected_behavior"]["fallback_symbol"], fallback["symbol"])

    def test_all_candidates_blocked_scenario(self) -> None:
        fixture = load_fixture("all_candidates_blocked")

        self.assertTrue(all(not row["decision_gate"]["safe_to_buy"] for row in fixture["long_term_add_queue"]))
        self.assertTrue(all(row["allocation_safety"]["suggested_amount"] == 0.0 for row in fixture["long_term_add_queue"]))
        self.assertEqual(fixture["capital_availability"]["suggested_deployment"], 0.0)
        self.assertIn("no_safe_fallback", fixture["expected_behavior"]["scenario_assertions"])

    def test_missing_capital_availability_scenario(self) -> None:
        fixture = load_fixture("missing_capital_availability")
        top = fixture["long_term_add_queue"][0]

        self.assertEqual(fixture["capital_availability"]["status"], "missing")
        self.assertIs(top["decision_gate"]["safe_to_buy"], True)
        self.assertEqual(top["allocation_safety"]["suggested_amount"], 0.0)
        self.assertEqual(fixture["expected_behavior"]["deployment_decision"], "hold_for_capital_context")

    def test_allocation_cap_reduces_amount_scenario(self) -> None:
        fixture = load_fixture("allocation_cap_reduces_amount")
        capital = fixture["capital_availability"]
        top = fixture["long_term_add_queue"][0]

        self.assertIs(top["decision_gate"]["safe_to_buy"], True)
        self.assertEqual(top["allocation_safety"]["status"], "reduced_by_allocation_cap")
        self.assertLess(top["allocation_safety"]["suggested_amount"], capital["monthly_buy_capacity"])
        self.assertIn("allocation_cap_reduces_amount", fixture["expected_behavior"]["scenario_assertions"])

    def test_holding_health_scenarios_are_review_only(self) -> None:
        expected_statuses = {
            "long_term_holding_healthy": "healthy",
            "long_term_holding_needs_review": "needs_review",
        }
        for scenario_id, status in expected_statuses.items():
            with self.subTest(scenario_id=scenario_id):
                fixture = load_fixture(scenario_id)
                health = fixture["holding_health"][0]

                self.assertEqual(fixture["decision_mode"], "long_term_hold_health")
                self.assertEqual(fixture["long_term_add_queue"], [])
                self.assertEqual(health["sleeve"], "long_term_core")
                self.assertEqual(health["status"], status)
                self.assertIn(health["status"], HOLDING_HEALTH_STATUSES)
                self.assertIs(health["review_only"], True)
                self.assertEqual(fixture["expected_behavior"]["suggested_amount"], 0.0)
                self.assertIn("no_sell_now_language", fixture["expected_behavior"]["scenario_assertions"])


if __name__ == "__main__":
    unittest.main()
