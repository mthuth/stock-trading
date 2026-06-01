#!/usr/bin/env python3
"""Tests for review-only model promotion readiness."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from stock_trading.model_promotion_readiness import (
    READINESS_LABELS,
    REVIEW_ONLY_NOTE,
    build_model_promotion_readiness,
    build_model_promotion_readiness_review,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "shadow_models" / "promotion_readiness_cases.json"


class ModelPromotionReadinessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cases = json.loads(FIXTURE.read_text())

    def readiness(self, case_name: str) -> dict[str, object]:
        return build_model_promotion_readiness(self.cases[case_name])

    def assert_review_only(self, result: dict[str, object]) -> None:
        self.assertTrue(result["review_only"])
        self.assertTrue(result["no_auto_promotion"])
        self.assertEqual(result["notes"], REVIEW_ONLY_NOTE)
        self.assertNotIn("official_status", result)
        self.assertNotIn("registry_update", result)
        self.assertNotIn("recommendation_change", result)
        self.assertNotIn("score_change", result)
        self.assertNotIn("target_change", result)
        self.assertNotIn("suggested_amount", result)

    def test_not_enough_data(self) -> None:
        result = self.readiness("not_enough_data")

        self.assertEqual(result["promotion_readiness_label"], "not_enough_data")
        self.assertFalse(result["minimum_sample_met"])
        self.assertEqual(result["recommended_human_review_action"], "collect_more_shadow_outcomes")
        self.assertTrue(any("Sample size" in blocker for blocker in result["blockers"]))
        self.assert_review_only(result)

    def test_promising_but_too_small_sample(self) -> None:
        result = self.readiness("promising_but_too_small")

        self.assertEqual(result["promotion_readiness_label"], "promising_shadow")
        self.assertFalse(result["minimum_sample_met"])
        self.assertGreater(result["readiness_score"], self.readiness("not_enough_data")["readiness_score"])
        self.assertTrue(any("excess return" in strength for strength in result["strengths"]))
        self.assertTrue(any("Collect more shadow-model outcomes" in item for item in result["required_next_evidence"]))
        self.assert_review_only(result)

    def test_ready_for_human_review(self) -> None:
        result = self.readiness("ready_for_human_review")

        self.assertEqual(result["promotion_readiness_label"], "ready_for_human_review")
        self.assertTrue(result["minimum_sample_met"])
        self.assertGreaterEqual(result["readiness_score"], 75)
        self.assertEqual(result["recommended_human_review_action"], "queue_human_promotion_review")
        self.assertEqual(result["blockers"], [])
        self.assert_review_only(result)

    def test_high_drawdown_blocks_readiness(self) -> None:
        result = self.readiness("high_drawdown")

        self.assertEqual(result["promotion_readiness_label"], "keep_shadow")
        self.assertTrue(result["minimum_sample_met"])
        self.assertTrue(any("drawdown" in blocker.lower() for blocker in result["blockers"]))
        self.assertEqual(result["recommended_human_review_action"], "review_drawdown_before_promotion_review")
        self.assert_review_only(result)

    def test_missing_benchmark_blocks_readiness(self) -> None:
        result = self.readiness("benchmark_missing")

        self.assertEqual(result["promotion_readiness_label"], "keep_shadow")
        self.assertTrue(any("Benchmark comparison is missing" in blocker for blocker in result["blockers"]))
        self.assertEqual(result["recommended_human_review_action"], "add_benchmark_comparison_before_review")
        self.assert_review_only(result)

    def test_guardrail_failure_blocks_readiness(self) -> None:
        result = self.readiness("guardrail_failure")

        self.assertEqual(result["promotion_readiness_label"], "reject_or_rework")
        self.assertTrue(any("guardrail" in blocker.lower() for blocker in result["blockers"]))
        self.assertEqual(result["recommended_human_review_action"], "rework_model_before_any_promotion_review")
        self.assert_review_only(result)

    def test_reject_or_rework_case(self) -> None:
        result = self.readiness("reject_or_rework")

        self.assertEqual(result["promotion_readiness_label"], "reject_or_rework")
        self.assertTrue(result["minimum_sample_met"])
        self.assertLess(result["readiness_score"], 35)
        self.assertEqual(result["recommended_human_review_action"], "reject_or_rework_shadow_model")
        self.assertTrue(any("outperformance" in blocker for blocker in result["blockers"]))
        self.assert_review_only(result)

    def test_high_severity_bias_warning_blocks_human_review(self) -> None:
        result = self.readiness("bias_warning")

        self.assertEqual(result["promotion_readiness_label"], "keep_shadow")
        self.assertIn("look_ahead_bias", result["warning_flags"])
        self.assertTrue(any("bias warning" in blocker.lower() for blocker in result["blockers"]))
        self.assertEqual(result["recommended_human_review_action"], "resolve_bias_warnings_before_review")
        self.assert_review_only(result)

    def test_missing_model_version_is_required_next_evidence(self) -> None:
        case = copy.deepcopy(self.cases["ready_for_human_review"])
        case["model_version"] = ""

        result = build_model_promotion_readiness(case)

        self.assertNotEqual(result["promotion_readiness_label"], "ready_for_human_review")
        self.assertTrue(any("Model version is missing" in blocker for blocker in result["blockers"]))
        self.assertTrue(any("model_version" in item for item in result["required_next_evidence"]))
        self.assert_review_only(result)

    def test_no_auto_promotion_and_no_input_mutation(self) -> None:
        case = copy.deepcopy(self.cases["ready_for_human_review"])
        original = copy.deepcopy(case)

        first = build_model_promotion_readiness(case)
        second = build_model_promotion_readiness(case)

        self.assertEqual(case, original)
        self.assertEqual(first, second)
        self.assertEqual(first["recommended_human_review_action"], "queue_human_promotion_review")
        self.assertTrue(first["no_auto_promotion"])
        self.assert_review_only(first)

    def test_batch_review_counts_labels(self) -> None:
        review = build_model_promotion_readiness_review(
            [
                self.cases["ready_for_human_review"],
                self.cases["promising_but_too_small"],
                self.cases["benchmark_missing"],
            ]
        )

        self.assertTrue(review["metadata"]["review_only"])
        self.assertTrue(review["metadata"]["no_auto_promotion"])
        self.assertEqual(review["metadata"]["model_count"], 3)
        self.assertEqual(review["metadata"]["label_counts"]["ready_for_human_review"], 1)
        self.assertEqual(review["metadata"]["label_counts"]["promising_shadow"], 1)
        self.assertEqual(review["metadata"]["label_counts"]["keep_shadow"], 1)
        self.assertEqual(set(review["metadata"]["labels"]), READINESS_LABELS)


if __name__ == "__main__":
    unittest.main()
