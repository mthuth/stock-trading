#!/usr/bin/env python3
"""Tests for review-only multi-model competition scoreboard."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from stock_trading.model_competition import GUARDRAILS, REVIEW_ONLY_NOTE, build_model_competition_scoreboard


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "shadow_models" / "model_competition_cases.json"


class ModelCompetitionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = json.loads(FIXTURE.read_text())

    def scoreboard(self, payload: dict[str, object] | None = None) -> dict[str, object]:
        payload = payload or self.fixture
        return build_model_competition_scoreboard(
            payload.get("official_model_results", []),
            payload.get("shadow_model_results", []),
            outcome_rows=payload.get("outcome_rows", []),
            benchmark_comparison_rows=payload.get("benchmark_comparison_rows", []),
            model_trust_rows=payload.get("model_trust_rows", []),
            ai_thesis_evaluation_rows=payload.get("ai_thesis_evaluation_rows", []),
            sample_size_threshold=30,
        )

    def row(self, scoreboard: dict[str, object], model_name: str) -> dict[str, object]:
        for row in scoreboard["scoreboard_rows"]:
            if row["model_name"] == model_name:
                return row
        self.fail(f"Missing scoreboard row for {model_name}")

    def test_official_model_wins_long_term_group(self) -> None:
        result = self.scoreboard()
        official = self.row(result, "official_core")

        self.assertEqual(official["competition_rank"], 1)
        self.assertEqual(official["official_or_shadow"], "official")
        self.assertEqual(result["summary"]["best_by_long_term"]["model_name"], "official_core")
        self.assertTrue(official["review_only"])

    def test_shadow_model_high_return_is_held_back_by_insufficient_sample_size(self) -> None:
        result = self.scoreboard()
        growth = self.row(result, "shadow_growth")

        self.assertFalse(growth["enough_sample_size"])
        self.assertGreater(growth["average_return"], self.row(result, "official_core")["average_return"])
        self.assertIn("insufficient_sample_size:12/30", growth["warnings"])
        self.assertGreater(growth["competition_rank"], 1)

    def test_aggressive_model_high_return_warns_on_high_drawdown(self) -> None:
        result = self.scoreboard()
        aggressive = self.row(result, "shadow_aggressive")

        self.assertEqual(aggressive["average_return"], 15.0)
        self.assertEqual(aggressive["drawdown_warning_rate"], 40.0)
        self.assertIn("high_drawdown_warning_rate", aggressive["warnings"])
        self.assertNotEqual(result["summary"]["best_by_long_term"]["model_name"], "shadow_aggressive")

    def test_conservative_model_has_best_downside_control(self) -> None:
        result = self.scoreboard()
        conservative = self.row(result, "shadow_conservative")

        self.assertLess(conservative["average_return"], self.row(result, "shadow_aggressive")["average_return"])
        self.assertEqual(conservative["drawdown_warning_rate"], 2.0)
        self.assertEqual(result["summary"]["best_risk_control"]["model_name"], "shadow_conservative")

    def test_missing_benchmark_warning(self) -> None:
        result = self.scoreboard()
        missing = self.row(result, "shadow_missing_version")

        self.assertIsNone(missing["average_excess_return"])
        self.assertIn("benchmark_data_missing", missing["warnings"])
        self.assertIn("benchmark_data_missing", result["summary"]["warnings"])

    def test_missing_model_version_warning(self) -> None:
        result = self.scoreboard()
        missing = self.row(result, "shadow_missing_version")

        self.assertEqual(missing["model_version"], "")
        self.assertIn("model_version_missing", missing["warnings"])

    def test_ranking_by_decision_mode(self) -> None:
        result = self.scoreboard()

        self.assertEqual(result["summary"]["best_by_tactical"]["model_name"], "shadow_tactical")
        self.assertEqual(result["summary"]["best_by_tactical"]["official_or_shadow"], "shadow")
        self.assertEqual(result["summary"]["best_by_earnings"]["model_name"], "shadow_earnings")
        self.assertEqual(self.row(result, "shadow_tactical")["competition_rank"], 1)
        self.assertEqual(self.row(result, "official_tactical")["competition_rank"], 2)

    def test_no_model_promotion_or_recommendation_behavior(self) -> None:
        result = self.scoreboard()

        self.assertTrue(result["review_only"])
        self.assertTrue(result["shadow_only"])
        self.assertTrue(result["no_model_promotion"])
        self.assertEqual(result["recommendation_impact"], "none")
        self.assertEqual(result["metadata"]["guardrails"], list(GUARDRAILS))
        self.assertEqual(result["metadata"]["note"], REVIEW_ONLY_NOTE)
        for row in result["scoreboard_rows"]:
            self.assertTrue(row["review_only"])
            self.assertTrue(row["no_model_promotion"])
            self.assertEqual(row["recommendation_impact"], "none")
            self.assertEqual(row["model_promotion"], "none")
            self.assertNotIn("official_action", row)
            self.assertNotIn("suggested_amount", row)

    def test_no_input_mutation_and_output_is_deterministic(self) -> None:
        payload = copy.deepcopy(self.fixture)
        original = copy.deepcopy(payload)

        first = self.scoreboard(payload)
        second = self.scoreboard(payload)

        self.assertEqual(payload, original)
        self.assertEqual(first, second)

    def test_empty_scoreboard_is_safe_review_only_output(self) -> None:
        result = self.scoreboard(
            {
                "official_model_results": [],
                "shadow_model_results": [],
                "outcome_rows": [],
                "benchmark_comparison_rows": [],
                "model_trust_rows": [],
                "ai_thesis_evaluation_rows": [],
            }
        )

        self.assertEqual(result["metadata"]["model_count"], 0)
        self.assertEqual(result["summary"]["best_by_long_term"]["status"], "insufficient_data")
        self.assertEqual(result["summary"]["insufficient_data_models"], [])
        self.assertTrue(result["review_only"])


if __name__ == "__main__":
    unittest.main()
