#!/usr/bin/env python3
"""Tests for review-only Model Trust Score v1."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from stock_trading.model_trust import GUARDRAILS, REVIEW_ONLY_NOTE, build_model_trust_score


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "model_evaluation" / "model_trust_cases.json"


class ModelTrustTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cases = json.loads(FIXTURE.read_text())

    def trust(self, case_name: str) -> dict[str, object]:
        return build_model_trust_score(self.cases[case_name])

    def assert_review_only(self, result: dict[str, object]) -> None:
        self.assertTrue(result["review_only"])
        self.assertTrue(result["no_model_promotion"])
        self.assertEqual(result["notes"], REVIEW_ONLY_NOTE)
        self.assertEqual(result["guardrails"], list(GUARDRAILS))
        self.assertIn("trust_score_does_not_change_official_recommendations", result["guardrails"])
        self.assertIn("trust_score_does_not_promote_models_automatically", result["guardrails"])
        self.assertNotIn("recommended_action", result)
        self.assertNotIn("action", result)
        self.assertNotIn("suggested_amount", result)

    def test_low_sample_size_stays_observe(self) -> None:
        result = self.trust("low_sample_size")

        self.assertEqual(result["trust_level"], "observe")
        self.assertFalse(result["enough_sample_size"])
        self.assertLessEqual(result["trust_score"], 34)
        self.assertEqual(result["recommended_review_action"], "collect_more_outcomes")
        self.assertIn("Sample size 8 is below", " ".join(result["warnings"]))
        self.assert_review_only(result)

    def test_weak_model_stays_observe(self) -> None:
        result = self.trust("weak_model")

        self.assertEqual(result["trust_level"], "observe")
        self.assertTrue(result["enough_sample_size"])
        self.assertLess(result["trust_score"], 50)
        self.assertEqual(result["recommended_review_action"], "continue_observing")
        self.assertTrue(any("Hit rate" in weakness for weakness in result["weaknesses"]))
        self.assert_review_only(result)

    def test_useful_model_moves_to_assist(self) -> None:
        result = self.trust("useful_model")

        self.assertEqual(result["trust_level"], "assist")
        self.assertGreaterEqual(result["trust_score"], 50)
        self.assertEqual(result["recommended_review_action"], "use_for_review_prioritization")
        self.assertEqual(result["confidence"], "medium")
        self.assert_review_only(result)

    def test_strong_model_moves_to_lean_in(self) -> None:
        result = self.trust("strong_model")

        self.assertEqual(result["trust_level"], "lean_in")
        self.assertGreaterEqual(result["trust_score"], 70)
        self.assertLess(result["sample_size"], 100)
        self.assertEqual(result["recommended_review_action"], "prepare_model_impact_review")
        self.assert_review_only(result)

    def test_aggressive_candidate_requires_sufficient_evidence(self) -> None:
        result = self.trust("aggressive_candidate")

        self.assertEqual(result["trust_level"], "aggressive_candidate")
        self.assertGreaterEqual(result["sample_size"], 100)
        self.assertGreaterEqual(result["trust_score"], 85)
        self.assertEqual(result["confidence"], "high")
        self.assertEqual(result["recommended_review_action"], "review_for_future_model_promotion")
        self.assert_review_only(result)

    def test_aggressive_score_without_enough_sample_stays_observe(self) -> None:
        case = copy.deepcopy(self.cases["aggressive_candidate"])
        case["sample_size"] = 20

        result = build_model_trust_score(case)

        self.assertEqual(result["trust_level"], "observe")
        self.assertFalse(result["enough_sample_size"])
        self.assertLessEqual(result["trust_score"], 34)
        self.assert_review_only(result)

    def test_benchmark_missing_warning_lowers_confidence(self) -> None:
        result = self.trust("benchmark_missing")

        self.assertEqual(result["confidence"], "low")
        self.assertEqual(result["trust_level"], "observe")
        self.assertTrue(any("Benchmark comparison is missing" in warning for warning in result["warnings"]))
        self.assertTrue(any("Benchmark comparison is missing" in weakness for weakness in result["weaknesses"]))
        self.assert_review_only(result)

    def test_high_drawdown_lowers_trust(self) -> None:
        strong = self.trust("aggressive_candidate")
        drawdown = self.trust("high_drawdown")

        self.assertLess(drawdown["trust_score"], strong["trust_score"])
        self.assertNotEqual(drawdown["trust_level"], "aggressive_candidate")
        self.assertTrue(any("High drawdown" in warning for warning in drawdown["warnings"]))
        self.assertTrue(any("drawdown" in weakness.lower() for weakness in drawdown["weaknesses"]))
        self.assert_review_only(drawdown)

    def test_output_is_deterministic_and_does_not_mutate_input(self) -> None:
        case = copy.deepcopy(self.cases["useful_model"])
        original = copy.deepcopy(case)

        first = build_model_trust_score(case)
        second = build_model_trust_score(case)

        self.assertEqual(case, original)
        self.assertEqual(first, second)

    def test_recommendation_context_is_not_mutated_or_returned_as_behavior_change(self) -> None:
        case = copy.deepcopy(self.cases["useful_model"])
        case["official_recommendation"] = {
            "symbol": "NVDA",
            "action": "Add",
            "suggested_amount": 2500,
            "decision_gate_status": "Ready",
        }
        original = copy.deepcopy(case)

        result = build_model_trust_score(case)

        self.assertEqual(case, original)
        self.assertNotIn("official_recommendation", result)
        self.assert_review_only(result)


if __name__ == "__main__":
    unittest.main()
