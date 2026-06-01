#!/usr/bin/env python3
"""Tests for Wave 13 shadow model contracts."""

from __future__ import annotations

import copy
import unittest

from stock_trading import shadow_models as subject


def shadow_model_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "model_name": "conservative_long_term",
        "model_version": "shadow-v1",
        "model_role": "shadow",
        "official_or_shadow": "shadow",
        "description": "Conservative long-term add competitor.",
        "allowed_decision_modes": ["long_term_buy_add"],
        "allowed_horizons": ["12_months"],
        "input_requirements": ["decision_time_inputs", "provider_gaps"],
        "output_schema_version": subject.OUTPUT_SCHEMA_VERSION,
        "score_impact": "none",
        "recommendation_impact": "none",
        "target_impact": "none",
        "decision_safety_impact": "none",
        "allocation_impact": "none",
        "promotion_status": "not_eligible",
        "review_only": True,
    }
    row.update(overrides)
    return row


class ShadowModelContractTests(unittest.TestCase):
    def test_valid_shadow_model(self) -> None:
        result = subject.validate_shadow_model_definition(shadow_model_row())

        self.assertTrue(result["valid"], result)
        normalized = result["normalized_model"]
        self.assertEqual(normalized["official_or_shadow"], "shadow")
        self.assertEqual(normalized["score_impact"], "none")
        self.assertEqual(normalized["recommendation_impact"], "none")
        self.assertEqual(normalized["target_impact"], "none")
        self.assertEqual(normalized["decision_safety_impact"], "none")
        self.assertEqual(normalized["allocation_impact"], "none")
        self.assertTrue(normalized["review_only"])
        self.assertIn("Shadow-only", normalized["recommendation_only_note"])

    def test_invalid_official_claim(self) -> None:
        result = subject.validate_shadow_model_definition(shadow_model_row(official_or_shadow="official"))

        self.assertFalse(result["valid"])
        self.assertIn("official_or_shadow", {error["path"] for error in result["errors"]})

    def test_invalid_recommendation_impact_claim(self) -> None:
        result = subject.validate_shadow_model_definition(shadow_model_row(recommendation_impact="changes_actions"))

        self.assertFalse(result["valid"])
        self.assertIn("recommendation_impact", {error["path"] for error in result["errors"]})

    def test_invalid_decision_mode(self) -> None:
        result = subject.validate_shadow_model_definition(shadow_model_row(allowed_decision_modes=["day_trade_bot"]))

        self.assertFalse(result["valid"])
        self.assertIn("allowed_decision_modes[0]", {error["path"] for error in result["errors"]})

    def test_invalid_horizon(self) -> None:
        result = subject.validate_shadow_model_definition(shadow_model_row(allowed_horizons=["3_days"]))

        self.assertFalse(result["valid"])
        self.assertIn("allowed_horizons[0]", {error["path"] for error in result["errors"]})

    def test_missing_model_version(self) -> None:
        result = subject.validate_shadow_model_definition(shadow_model_row(model_version=""))

        self.assertFalse(result["valid"])
        self.assertIn("model_version", {error["path"] for error in result["errors"]})

    def test_invalid_promotion_status(self) -> None:
        result = subject.validate_shadow_model_definition(shadow_model_row(promotion_status="promoted"))

        self.assertFalse(result["valid"])
        self.assertIn("promotion_status", {error["path"] for error in result["errors"]})

    def test_starter_models_validate(self) -> None:
        starters = subject.starter_shadow_models()
        registry = subject.build_shadow_model_registry(starters)

        self.assertEqual(
            {row["model_name"] for row in starters},
            {
                "conservative_long_term",
                "aggressive_growth",
                "tactical_momentum",
                "earnings_event",
                "risk_skeptic",
                "ai_thesis",
                "source_quality_weighted",
                "decision_safety_strict",
                "decision_safety_loose",
            },
        )
        self.assertEqual(len(starters), 9)
        self.assertTrue(registry["review_only"])
        self.assertTrue(registry["shadow_only"])
        self.assertTrue(registry["validation"]["valid"], registry["validation"])
        self.assertEqual(registry["model_count"], 9)
        self.assertTrue(all(row["official_or_shadow"] == "shadow" for row in registry["models"]))
        self.assertTrue(all(row["recommendation_impact"] == "none" for row in registry["models"]))

    def test_no_input_mutation(self) -> None:
        row = shadow_model_row(input_requirements=["decision_time_inputs"])
        before = copy.deepcopy(row)

        subject.normalize_shadow_model_definition(row)
        subject.validate_shadow_model_definition(row)
        subject.build_shadow_model_registry([row])

        self.assertEqual(row, before)


if __name__ == "__main__":
    unittest.main()
