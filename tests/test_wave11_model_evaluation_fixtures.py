#!/usr/bin/env python3
"""Wave 11 model-evaluation fixture contracts."""

from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "model_evaluation"


EXPECTED_SCENARIOS = {
    "long_term_beats_benchmark": "Long-term recommendation beats benchmark",
    "long_term_underperforms_benchmark": "Long-term recommendation underperforms benchmark",
    "blocked_recommendation_later_declines": "Blocked recommendation later declines",
    "blocked_recommendation_later_rises": "Blocked recommendation later rises",
    "tactical_setup_works": "Tactical setup works over intended horizon",
    "tactical_setup_fails": "Tactical setup fails",
    "earnings_review_improves_after_post_earnings": "Earnings review improves after post-earnings evidence",
    "ai_thesis_validated": "AI thesis validated by later evidence",
    "ai_thesis_contradicted": "AI thesis contradicted by later evidence",
    "not_enough_historical_data": "Not enough historical data",
    "benchmark_data_missing": "Benchmark data missing",
    "model_version_missing": "Model version missing",
}

REQUIRED_GUARDRAILS = {
    "no_automatic_trading",
    "no_broker_write",
    "no_order_preview",
    "no_automatic_score_changes",
    "no_automatic_target_changes",
    "no_automatic_decision_safety_changes",
    "no_automatic_source_weight_changes",
    "no_automatic_recommendation_changes_from_feedback_or_outcomes",
    "no_model_promotion_into_official_recommendations",
}

VALIDITY_GUARDRAILS = {
    "no_lookahead_data",
    "stored_historical_recommendation",
    "official_vs_shadow_distinguished",
    "benchmark_same_window",
    "missing_data_warns_not_optimistic",
    "survivorship_bias_reviewed",
    "review_only_results",
}

PREDICTION_FIELDS = {
    "prediction_id",
    "recommendation_run_id",
    "symbol",
    "company",
    "model_name",
    "model_version",
    "model_role",
    "decision_mode",
    "horizon",
    "created_at",
    "decision_date",
    "official_action",
    "score",
    "target_price",
    "target_confidence",
    "decision_gate_status",
    "expected_direction",
    "expected_return_low",
    "expected_return_high",
    "confidence",
    "thesis",
    "risks",
    "invalidation_conditions",
    "evidence_ids",
    "source_ids",
    "data_available_as_of",
    "outcome_status",
    "evaluated_at",
}

CONTROLLED_ACTIONS = {"Strong Buy", "Buy", "Add", "Hold", "Watch", "Trim", "Avoid"}
MODEL_ROLES = {"official", "shadow"}
DECISION_MODES = {"long_term_buy_add", "speculative_watchlist", "tactical_trade", "earnings_event", "ai_thesis_review"}
TRUST_LEVELS = {"observe", "assist", "lean_in", "aggressive"}
TRUST_CONFIDENCE = {"low", "medium", "high"}


def load_fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURE_DIR / f"{name}.json").read_text())


class Wave11ModelEvaluationFixtureTests(unittest.TestCase):
    maxDiff = None

    def test_expected_fixture_set_exists(self) -> None:
        fixture_ids = {
            path.stem
            for path in FIXTURE_DIR.glob("*.json")
            if path.stem in EXPECTED_SCENARIOS
        }

        self.assertEqual(fixture_ids, set(EXPECTED_SCENARIOS))

    def test_common_fixture_contract(self) -> None:
        for scenario_id, scenario_label in EXPECTED_SCENARIOS.items():
            with self.subTest(scenario_id=scenario_id):
                fixture = load_fixture(scenario_id)

                self.assertEqual(fixture["scenario_id"], scenario_id)
                self.assertEqual(fixture["scenario_label"], scenario_label)
                self.assertEqual(fixture["evaluation_mode"], "model_evaluation")
                self.assertIs(fixture["review_only"], True)
                self.assertIs(fixture["recommendation_only"], True)

                prediction = fixture["prediction_record"]
                self.assertEqual(set(prediction), PREDICTION_FIELDS)
                self.assertIn(prediction["official_action"], CONTROLLED_ACTIONS)
                self.assertIn(prediction["model_role"], MODEL_ROLES)
                self.assertIn(prediction["decision_mode"], DECISION_MODES)
                self.assertIn(prediction["decision_gate_status"], {"Ready", "Blocked"})
                self.assertIsInstance(prediction["risks"], list)
                self.assertIsInstance(prediction["invalidation_conditions"], list)
                self.assertIsInstance(prediction["evidence_ids"], list)
                self.assertIsInstance(prediction["source_ids"], list)

                benchmark = fixture["benchmark_comparison"]
                for field in (
                    "benchmark_id",
                    "benchmark_symbol",
                    "benchmark_name",
                    "benchmark_return",
                    "comparison_window_start",
                    "comparison_window_end",
                    "excess_return",
                    "benchmark_data_status",
                    "benchmark_warning",
                ):
                    self.assertIn(field, benchmark)

                outcome = fixture["outcome"]
                for field in ("actual_return", "drawdown", "target_progress", "worked", "outcome_label"):
                    self.assertIn(field, outcome)

                validity = fixture["validity_guardrails"]
                self.assertEqual(set(validity), VALIDITY_GUARDRAILS)
                for value in validity.values():
                    self.assertIs(value, True)

                trust = fixture["model_trust_score_v1"]
                for field in ("trust_score", "trust_level", "sample_size", "confidence", "warnings", "drivers", "review_only"):
                    self.assertIn(field, trust)
                self.assertIn(trust["trust_level"], TRUST_LEVELS)
                self.assertIn(trust["confidence"], TRUST_CONFIDENCE)
                self.assertIsInstance(trust["warnings"], list)
                self.assertIsInstance(trust["drivers"], list)
                self.assertIs(trust["review_only"], True)

                expected = fixture["expected_behavior"]
                self.assertIn("evaluation_result", expected)
                self.assertIsInstance(expected["scenario_assertions"], list)
                self.assertIn("official_recommendation_unchanged", expected["scenario_assertions"])

                guardrails = fixture["guardrails"]
                self.assertEqual(set(guardrails), REQUIRED_GUARDRAILS)
                for value in guardrails.values():
                    self.assertIs(value, True)

    def test_long_term_benchmark_outcomes_cover_win_and_loss(self) -> None:
        beats = load_fixture("long_term_beats_benchmark")
        underperforms = load_fixture("long_term_underperforms_benchmark")

        self.assertGreater(beats["benchmark_comparison"]["excess_return"], 0)
        self.assertTrue(beats["outcome"]["worked"])
        self.assertLess(underperforms["benchmark_comparison"]["excess_return"], 0)
        self.assertFalse(underperforms["outcome"]["worked"])

    def test_decision_safety_block_outcomes_cover_downside_and_missed_upside(self) -> None:
        declined = load_fixture("blocked_recommendation_later_declines")
        rose = load_fixture("blocked_recommendation_later_rises")

        self.assertEqual(declined["prediction_record"]["decision_gate_status"], "Blocked")
        self.assertLess(declined["outcome"]["actual_return"], 0)
        self.assertIn("blocked_later_declined", declined["expected_behavior"]["scenario_assertions"])
        self.assertEqual(rose["prediction_record"]["decision_gate_status"], "Blocked")
        self.assertGreater(rose["outcome"]["actual_return"], 0)
        self.assertIn("blocked_later_rose", rose["expected_behavior"]["scenario_assertions"])

    def test_tactical_outcomes_use_intended_horizons(self) -> None:
        worked = load_fixture("tactical_setup_works")
        failed = load_fixture("tactical_setup_fails")

        self.assertEqual(worked["prediction_record"]["decision_mode"], "tactical_trade")
        self.assertEqual(worked["prediction_record"]["horizon"], "1_to_5_days")
        self.assertTrue(worked["outcome"]["worked"])
        self.assertEqual(failed["prediction_record"]["decision_mode"], "tactical_trade")
        self.assertEqual(failed["prediction_record"]["horizon"], "5_to_20_days")
        self.assertFalse(failed["outcome"]["worked"])

    def test_earnings_and_ai_evaluations_remain_review_only(self) -> None:
        earnings = load_fixture("earnings_review_improves_after_post_earnings")
        ai_valid = load_fixture("ai_thesis_validated")
        ai_contra = load_fixture("ai_thesis_contradicted")

        self.assertEqual(earnings["prediction_record"]["decision_mode"], "earnings_event")
        self.assertIn("earnings_review_improved", earnings["expected_behavior"]["scenario_assertions"])
        self.assertEqual(ai_valid["prediction_record"]["model_role"], "shadow")
        self.assertIn("ai_thesis_supported", ai_valid["expected_behavior"]["scenario_assertions"])
        self.assertEqual(ai_contra["prediction_record"]["model_role"], "shadow")
        self.assertIn("ai_thesis_contradicted", ai_contra["expected_behavior"]["scenario_assertions"])

    def test_missing_data_scenarios_warn_instead_of_assuming_success(self) -> None:
        no_history = load_fixture("not_enough_historical_data")
        missing_benchmark = load_fixture("benchmark_data_missing")
        missing_version = load_fixture("model_version_missing")

        self.assertIn("not_enough_historical_data", no_history["model_trust_score_v1"]["warnings"])
        self.assertIsNone(no_history["outcome"]["actual_return"])
        self.assertIn("benchmark_data_missing", missing_benchmark["model_trust_score_v1"]["warnings"])
        self.assertIsNone(missing_benchmark["benchmark_comparison"]["benchmark_return"])
        self.assertIn("no_zero_benchmark_assumption", missing_benchmark["expected_behavior"]["scenario_assertions"])
        self.assertIsNone(missing_version["prediction_record"]["model_version"])
        self.assertIn("model_version_missing", missing_version["model_trust_score_v1"]["warnings"])

    def test_official_and_shadow_models_are_distinguished(self) -> None:
        roles = {load_fixture(scenario_id)["prediction_record"]["model_role"] for scenario_id in EXPECTED_SCENARIOS}

        self.assertEqual(roles, {"official", "shadow"})

    def test_no_fixture_promotes_or_tunes_model(self) -> None:
        for scenario_id in EXPECTED_SCENARIOS:
            with self.subTest(scenario_id=scenario_id):
                fixture = load_fixture(scenario_id)
                serialized = json.dumps(fixture).lower()

                self.assertTrue(fixture["guardrails"]["no_model_promotion_into_official_recommendations"])
                self.assertTrue(fixture["guardrails"]["no_automatic_score_changes"])
                self.assertTrue(fixture["guardrails"]["no_automatic_target_changes"])
                self.assertTrue(fixture["guardrails"]["no_automatic_decision_safety_changes"])
                self.assertTrue(fixture["guardrails"]["no_automatic_source_weight_changes"])
                self.assertNotIn("guaranteed", serialized)


if __name__ == "__main__":
    unittest.main()
