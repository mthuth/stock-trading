#!/usr/bin/env python3
"""Wave 13 multi-model shadow-competition fixture contracts."""

from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "shadow_models"


EXPECTED_SCENARIOS = {
    "official_model_wins": "Official model wins",
    "aggressive_model_wins_higher_drawdown": "Aggressive model wins but with higher drawdown",
    "conservative_model_avoids_downside": "Conservative model avoids downside",
    "tactical_model_short_term_only": "Tactical model works short-term but fails long-term",
    "earnings_model_window_only": "Earnings model works only around earnings window",
    "risk_skeptic_blocks_losing_idea": "Risk skeptic blocks a losing idea",
    "ai_thesis_overstates_confidence": "AI thesis model overstates confidence",
    "source_quality_avoids_noisy_evidence": "Source-quality model avoids noisy evidence",
    "insufficient_sample_size": "Insufficient sample size",
    "missing_benchmark_data": "Missing benchmark data",
    "shadow_claims_official_rejected": "Shadow model tries to claim official status and is rejected",
}

MODEL_ROLES = {
    "official_baseline",
    "conservative_long_term",
    "aggressive_growth",
    "tactical_momentum",
    "earnings_event",
    "risk_skeptic",
    "ai_thesis",
    "source_quality_weighted",
    "decision_safety_strict",
    "decision_safety_loose",
}

MODEL_FIELDS = {
    "shadow_run_id",
    "model_id",
    "model_role",
    "model_name",
    "model_version",
    "official_status",
    "decision_mode",
    "horizon",
    "sleeve",
    "market_condition",
    "symbol",
    "company",
    "shadow_action",
    "shadow_score",
    "shadow_target",
    "shadow_target_confidence",
    "decision_gate_view",
    "safe_to_buy_view",
    "expected_return",
    "excess_return",
    "drawdown",
    "avoided_downside",
    "missed_upside",
    "risk_explanation_score",
    "thesis",
    "risk_explanation",
    "evidence_ids",
    "source_ids",
    "data_available_as_of",
    "warnings",
    "promotion_claim",
    "review_only",
    "shadow_only_note",
}

CONTEXT_FIELDS = {
    "decision_mode",
    "horizon",
    "sleeve",
    "market_condition",
    "benchmark_status",
    "sample_size",
    "warnings",
}

REQUIRED_GUARDRAILS = {
    "no_automatic_trading",
    "no_broker_write",
    "no_order_preview",
    "no_automatic_model_promotion",
    "no_automatic_official_recommendation_changes",
    "no_automatic_scoring_changes",
    "no_automatic_target_changes",
    "no_automatic_decision_safety_changes",
    "no_automatic_allocation_changes",
    "no_automatic_source_weight_changes",
    "no_live_model_calls_in_tests",
    "no_live_provider_calls_in_tests",
}

EVALUATION_GUARDRAILS = {
    "no_lookahead_data",
    "official_vs_shadow_distinguished",
    "decision_time_inputs_separate",
    "benchmark_same_window",
    "missing_data_warns_not_optimistic",
    "survivor_bias_warned",
    "shadow_only_results",
}

OFFICIAL_STATUSES = {"official", "shadow", "invalid_claim"}
PROMOTION_STATES = {
    "no_review",
    "not_ready",
    "promotion_review_candidate",
    "rejected_invalid_official_claim",
    "rejected_overconfidence",
}


def load_fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURE_DIR / f"{name}.json").read_text())


class Wave13ShadowModelFixtureTests(unittest.TestCase):
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
                self.assertEqual(fixture["shadow_layer"], "multi_model_shadow_competition")
                self.assertIs(fixture["review_only"], True)
                self.assertIs(fixture["shadow_only"], True)
                self.assertIs(fixture["official_recommendation_unchanged"], True)

                context = fixture["comparison_context"]
                self.assertEqual(set(context), CONTEXT_FIELDS)
                self.assertIsInstance(context["sample_size"], int)
                self.assertIsInstance(context["warnings"], list)

                models = fixture["models"]
                self.assertGreaterEqual(len(models), 2)
                model_ids = {model["model_id"] for model in models}
                self.assertEqual(len(model_ids), len(models))
                self.assertIn("official_baseline", {model["model_role"] for model in models})

                for model in models:
                    self.assertEqual(set(model), MODEL_FIELDS)
                    self.assertIn(model["model_role"], MODEL_ROLES)
                    self.assertIn(model["official_status"], OFFICIAL_STATUSES)
                    self.assertIsInstance(model["evidence_ids"], list)
                    self.assertIsInstance(model["source_ids"], list)
                    self.assertIsInstance(model["warnings"], list)
                    self.assertIs(model["review_only"], True)
                    self.assertNotEqual(model["shadow_only_note"], "")
                    if model["model_role"] == "official_baseline":
                        self.assertEqual(model["official_status"], "official")
                    else:
                        self.assertNotEqual(model["official_status"], "official")

                winner = fixture["winner"]
                self.assertIn(winner["model_role"], MODEL_ROLES)
                self.assertIn(winner["model_id"], model_ids)
                self.assertNotEqual(winner["reason"], "")

                debate = fixture["debate_packet"]
                self.assertIsInstance(debate["models_compared"], list)
                self.assertIsInstance(debate["agreements"], list)
                self.assertIsInstance(debate["disagreements"], list)
                self.assertIsInstance(debate["evidence_ids"], list)
                self.assertIsInstance(debate["warnings"], list)
                self.assertIs(debate["review_only"], True)

                self.assertIn(fixture["promotion_readiness"]["status"], PROMOTION_STATES)
                self.assertIs(fixture["promotion_readiness"]["review_only"], True)

                expected = fixture["expected_behavior"]
                self.assertIn("comparison_result", expected)
                self.assertIsInstance(expected["scenario_assertions"], list)
                self.assertIn("official_recommendation_unchanged", expected["scenario_assertions"])

                guardrails = fixture["guardrails"]
                self.assertEqual(set(guardrails), REQUIRED_GUARDRAILS)
                for value in guardrails.values():
                    self.assertIs(value, True)

                evaluation_guardrails = fixture["evaluation_guardrails"]
                self.assertEqual(set(evaluation_guardrails), EVALUATION_GUARDRAILS)
                for value in evaluation_guardrails.values():
                    self.assertIs(value, True)

    def test_model_roles_cover_required_shadow_taxonomy(self) -> None:
        found_roles = {
            model["model_role"]
            for scenario_id in EXPECTED_SCENARIOS
            for model in load_fixture(scenario_id)["models"]
        }

        self.assertEqual(found_roles, MODEL_ROLES)

    def test_aggressive_win_carries_drawdown_warning(self) -> None:
        fixture = load_fixture("aggressive_model_wins_higher_drawdown")
        official = next(model for model in fixture["models"] if model["model_role"] == "official_baseline")
        aggressive = next(model for model in fixture["models"] if model["model_role"] == "aggressive_growth")

        self.assertEqual(fixture["winner"]["model_role"], "aggressive_growth")
        self.assertGreater(aggressive["expected_return"], official["expected_return"])
        self.assertLess(aggressive["drawdown"], official["drawdown"])
        self.assertIn("higher_drawdown", aggressive["warnings"])
        self.assertIn("winner_not_promotion", fixture["expected_behavior"]["scenario_assertions"])

    def test_conservative_and_risk_skeptic_downside_cases(self) -> None:
        conservative = load_fixture("conservative_model_avoids_downside")
        skeptic = load_fixture("risk_skeptic_blocks_losing_idea")

        self.assertEqual(conservative["winner"]["model_role"], "conservative_long_term")
        self.assertTrue(next(model for model in conservative["models"] if model["model_role"] == "conservative_long_term")["avoided_downside"])
        self.assertEqual(skeptic["winner"]["model_role"], "risk_skeptic")
        self.assertTrue(next(model for model in skeptic["models"] if model["model_role"] == "risk_skeptic")["avoided_downside"])

    def test_tactical_and_earnings_models_stay_window_limited(self) -> None:
        tactical = load_fixture("tactical_model_short_term_only")
        earnings = load_fixture("earnings_model_window_only")

        self.assertEqual(tactical["winner"]["model_role"], "tactical_momentum")
        self.assertIn("fails_long_term", tactical["comparison_context"]["warnings"])
        self.assertIn("long_term_recommendation_not_overridden", tactical["expected_behavior"]["scenario_assertions"])
        self.assertEqual(earnings["winner"]["model_role"], "earnings_event")
        self.assertIn("window_limited", earnings["comparison_context"]["warnings"])

    def test_ai_and_source_quality_cases_handle_evidence_quality(self) -> None:
        ai = load_fixture("ai_thesis_overstates_confidence")
        source_quality = load_fixture("source_quality_avoids_noisy_evidence")

        ai_model = next(model for model in ai["models"] if model["model_role"] == "ai_thesis")
        self.assertIn("overstates_confidence", ai_model["warnings"])
        self.assertEqual(ai["promotion_readiness"]["status"], "rejected_overconfidence")
        self.assertEqual(source_quality["winner"]["model_role"], "source_quality_weighted")
        self.assertIn("noisy_evidence_avoided", source_quality["expected_behavior"]["scenario_assertions"])

    def test_missing_data_scenarios_warn_instead_of_assuming_success(self) -> None:
        small_sample = load_fixture("insufficient_sample_size")
        missing_benchmark = load_fixture("missing_benchmark_data")

        self.assertIn("sample_size_too_small", small_sample["comparison_context"]["warnings"])
        self.assertEqual(small_sample["promotion_readiness"]["status"], "not_ready")
        self.assertEqual(missing_benchmark["comparison_context"]["benchmark_status"], "missing")
        self.assertIn("benchmark_data_missing", missing_benchmark["comparison_context"]["warnings"])
        self.assertIn("no_zero_benchmark_assumption", missing_benchmark["expected_behavior"]["scenario_assertions"])

    def test_shadow_model_cannot_claim_official_status(self) -> None:
        fixture = load_fixture("shadow_claims_official_rejected")
        invalid = next(model for model in fixture["models"] if model["official_status"] == "invalid_claim")

        self.assertNotEqual(invalid["model_role"], "official_baseline")
        self.assertEqual(invalid["promotion_claim"], "rejected_invalid_official_claim")
        self.assertEqual(fixture["promotion_readiness"]["status"], "rejected_invalid_official_claim")
        self.assertIn("shadow_official_claim_rejected", fixture["expected_behavior"]["scenario_assertions"])

    def test_no_fixture_promotes_or_changes_recommendations(self) -> None:
        forbidden_phrases = ("place order", "order preview", "broker write", "guaranteed return")
        for scenario_id in EXPECTED_SCENARIOS:
            with self.subTest(scenario_id=scenario_id):
                fixture = load_fixture(scenario_id)
                serialized = json.dumps(fixture).lower()

                for phrase in forbidden_phrases:
                    self.assertNotIn(phrase, serialized)
                self.assertTrue(fixture["guardrails"]["no_automatic_model_promotion"])
                self.assertTrue(fixture["guardrails"]["no_automatic_official_recommendation_changes"])
                self.assertTrue(fixture["guardrails"]["no_live_model_calls_in_tests"])
                self.assertTrue(fixture["guardrails"]["no_live_provider_calls_in_tests"])


if __name__ == "__main__":
    unittest.main()
