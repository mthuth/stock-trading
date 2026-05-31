#!/usr/bin/env python3
"""Wave 10 tactical-review fixture contracts."""

from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "tactical"


EXPECTED_SCENARIOS = {
    "clean_breakout_setup": "Clean breakout setup",
    "pullback_to_support": "Pullback to support",
    "post_earnings_overreaction": "Post-earnings overreaction",
    "pre_earnings_too_risky": "Pre-earnings too risky",
    "momentum_strong_but_data_gap": "Momentum strong but data gap",
    "reversal_signal_weak": "Reversal signal weak",
    "no_tactical_setup": "No tactical setup",
    "long_term_add_not_overridden": "Long-term add should not be overridden",
    "watchlist_only_remains_blocked": "Watchlist-only name remains blocked from buy-ready",
    "missing_price_history": "Missing price history",
}

REQUIRED_GUARDRAILS = {
    "no_automatic_trading",
    "no_broker_write",
    "no_order_preview",
    "no_short_selling_execution",
    "no_margin_account_logic",
    "no_real_time_trading_console",
    "no_automatic_score_target_decision_safety_changes",
    "no_automatic_model_tuning",
    "no_automatic_source_weight_changes",
    "no_broker_credential_requirement",
    "no_long_term_override",
}

CONTROLLED_ACTIONS = {"Strong Buy", "Buy", "Add", "Hold", "Watch", "Trim", "Avoid"}
TACTICAL_HORIZONS = {"same_day", "1_to_5_days", "5_to_20_days", "20_to_60_days"}
SETUP_TYPES = {
    "breakout_review",
    "pullback_review",
    "momentum_review",
    "reversal_review",
    "post_earnings_reaction_review",
    "pre_earnings_setup_review",
    "news_catalyst_review",
    "avoid_or_wait",
}
REVIEW_ACTIONS = {
    "tactical_buy_review",
    "tactical_sell_review",
    "wait_for_confirmation",
    "watch_intraday",
    "avoid_for_now",
    "hold_existing",
    "data_gap_review",
}
RISK_LEVELS = {"low", "moderate", "elevated", "high", "not_applicable"}
SETUP_STATUSES = {"review_ready", "avoid_or_wait", "data_gap", "weak", "none", "mixed", "watch_only"}
CONFIDENCE_LEVELS = {"high", "medium", "low", "not_applicable"}


def load_fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURE_DIR / f"{name}.json").read_text())


class Wave10TacticalFixtureTests(unittest.TestCase):
    maxDiff = None

    def test_expected_fixture_set_exists(self) -> None:
        fixture_ids = {path.stem for path in FIXTURE_DIR.glob("*.json")}

        self.assertEqual(fixture_ids, set(EXPECTED_SCENARIOS))

    def test_common_fixture_contract(self) -> None:
        for scenario_id, scenario_label in EXPECTED_SCENARIOS.items():
            with self.subTest(scenario_id=scenario_id):
                fixture = load_fixture(scenario_id)

                self.assertEqual(fixture["scenario_id"], scenario_id)
                self.assertEqual(fixture["scenario_label"], scenario_label)
                self.assertEqual(fixture["decision_mode"], "tactical_trade")
                self.assertIs(fixture["recommendation_only"], True)
                self.assertIs(fixture["review_only"], True)
                self.assertIn(fixture["scope"], {"owned", "watchlist", "approved_universe"})
                self.assertIn(fixture["tactical_horizon"], TACTICAL_HORIZONS)
                self.assertIn(fixture["setup_type"], SETUP_TYPES)

                setup = fixture["setup"]
                for field in ("status", "thesis", "evidence", "confidence", "prior_setup_outcome"):
                    self.assertIn(field, setup)
                self.assertIn(setup["status"], SETUP_STATUSES)
                self.assertIn(setup["confidence"], CONFIDENCE_LEVELS)
                self.assertIsInstance(setup["evidence"], list)

                recommendation = fixture["current_recommendation"]
                self.assertIn(recommendation["action"], CONTROLLED_ACTIONS)
                self.assertIn(recommendation["decision_gate_status"], {"Ready", "Blocked"})
                self.assertIsInstance(recommendation["safe_to_buy"], bool)
                self.assertEqual(recommendation["official_recommendation_impact"], "none_review_only")

                review = fixture["tactical_review"]
                self.assertIn(review["review_action"], REVIEW_ACTIONS)
                self.assertIs(review["long_term_override"], False)

                risk_zone = fixture["risk_zone"]
                for field in (
                    "risk_level",
                    "review_zone",
                    "downside_reference",
                    "upside_reference",
                    "volatility_context",
                    "liquidity_context",
                    "position_context",
                    "notes",
                ):
                    self.assertIn(field, risk_zone)
                self.assertIn(risk_zone["risk_level"], RISK_LEVELS)
                self.assertIsInstance(risk_zone["notes"], list)

                invalidation = fixture["invalidation"]
                for field in ("invalidates_if", "confirmation_needed", "time_stop", "data_gaps"):
                    self.assertIn(field, invalidation)
                self.assertIsInstance(invalidation["invalidates_if"], list)
                self.assertIsInstance(invalidation["confirmation_needed"], list)
                self.assertIsInstance(invalidation["data_gaps"], list)

                provider_data = fixture["provider_data"]
                for field in ("price_history", "technical_evidence", "news_catalyst", "earnings_context", "provider_gaps"):
                    self.assertIn(field, provider_data)
                self.assertIsInstance(provider_data["provider_gaps"], list)

                ai_context = fixture["ai_context"]
                self.assertIs(ai_context["may_change_official_recommendation"], False)

                expected = fixture["expected_behavior"]
                self.assertIn("queue_status", expected)
                self.assertIsInstance(expected["scenario_assertions"], list)
                self.assertIn("official_recommendation_unchanged", expected["scenario_assertions"])

                guardrails = fixture["guardrails"]
                self.assertEqual(REQUIRED_GUARDRAILS, set(guardrails))
                for value in guardrails.values():
                    self.assertIs(value, True)

    def test_setup_types_cover_required_tactical_cases(self) -> None:
        setup_types = {load_fixture(scenario_id)["setup_type"] for scenario_id in EXPECTED_SCENARIOS}

        self.assertEqual(setup_types, SETUP_TYPES)

    def test_review_actions_cover_required_actions(self) -> None:
        actions = {load_fixture(scenario_id)["tactical_review"]["review_action"] for scenario_id in EXPECTED_SCENARIOS}

        self.assertTrue(REVIEW_ACTIONS.issuperset(actions))
        self.assertIn("tactical_buy_review", actions)
        self.assertIn("wait_for_confirmation", actions)
        self.assertIn("watch_intraday", actions)
        self.assertIn("avoid_for_now", actions)
        self.assertIn("hold_existing", actions)
        self.assertIn("data_gap_review", actions)

    def test_earnings_boundary_scenarios_do_not_change_official_recommendations(self) -> None:
        for scenario_id in ("post_earnings_overreaction", "pre_earnings_too_risky"):
            with self.subTest(scenario_id=scenario_id):
                fixture = load_fixture(scenario_id)

                self.assertIn("earnings", fixture["setup_type"])
                self.assertEqual(fixture["current_recommendation"]["official_recommendation_impact"], "none_review_only")
                self.assertIn("official_recommendation_unchanged", fixture["expected_behavior"]["scenario_assertions"])

    def test_long_term_add_is_not_overridden_by_tactical_metadata(self) -> None:
        fixture = load_fixture("long_term_add_not_overridden")

        self.assertEqual(fixture["sleeve"], "long_term_core")
        self.assertEqual(fixture["current_recommendation"]["action"], "Add")
        self.assertTrue(fixture["current_recommendation"]["safe_to_buy"])
        self.assertEqual(fixture["tactical_review"]["review_action"], "hold_existing")
        self.assertFalse(fixture["tactical_review"]["long_term_override"])
        self.assertIn("long_term_add_not_overridden", fixture["expected_behavior"]["scenario_assertions"])

    def test_watchlist_only_name_remains_blocked_from_buy_ready(self) -> None:
        fixture = load_fixture("watchlist_only_remains_blocked")

        self.assertEqual(fixture["scope"], "watchlist")
        self.assertEqual(fixture["sleeve"], "speculative_ai")
        self.assertEqual(fixture["current_recommendation"]["decision_gate_status"], "Blocked")
        self.assertFalse(fixture["current_recommendation"]["safe_to_buy"])
        self.assertEqual(fixture["tactical_review"]["review_action"], "watch_intraday")
        self.assertIn("watchlist_only_not_buy_ready", fixture["expected_behavior"]["scenario_assertions"])

    def test_data_gap_scenarios_surface_provider_gaps(self) -> None:
        for scenario_id in ("momentum_strong_but_data_gap", "missing_price_history"):
            with self.subTest(scenario_id=scenario_id):
                fixture = load_fixture(scenario_id)

                self.assertEqual(fixture["tactical_review"]["review_action"], "data_gap_review")
                self.assertGreaterEqual(len(fixture["provider_data"]["provider_gaps"]), 1)
                self.assertGreaterEqual(len(fixture["invalidation"]["data_gaps"]), 1)

    def test_no_tactical_setup_does_not_invent_a_setup(self) -> None:
        fixture = load_fixture("no_tactical_setup")

        self.assertEqual(fixture["setup"]["status"], "none")
        self.assertEqual(fixture["setup"]["evidence"], [])
        self.assertEqual(fixture["risk_zone"]["risk_level"], "not_applicable")
        self.assertIn("no_tactical_setup_invented", fixture["expected_behavior"]["scenario_assertions"])

    def test_fixtures_do_not_enable_execution_or_broker_requirements(self) -> None:
        forbidden_terms = ("order_preview", "broker_write", "automatic_trading", "short_selling_execution")
        for scenario_id in EXPECTED_SCENARIOS:
            with self.subTest(scenario_id=scenario_id):
                fixture = load_fixture(scenario_id)
                serialized = json.dumps(fixture).lower()

                for term in forbidden_terms:
                    self.assertIn(f"no_{term}", serialized)
                self.assertTrue(fixture["guardrails"]["no_broker_credential_requirement"])
                self.assertTrue(fixture["guardrails"]["no_real_time_trading_console"])


if __name__ == "__main__":
    unittest.main()
