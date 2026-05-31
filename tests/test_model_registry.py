#!/usr/bin/env python3
"""Tests for review-only model registry helpers."""

from __future__ import annotations

import copy
import unittest

from stock_trading import model_registry as subject


def model_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "model_name": "daily_report_rules",
        "model_version": "daily-report-rules-v1",
        "model_role": "official",
        "official_or_shadow": "official",
        "description": "Deterministic daily recommendation rules.",
        "created_at": "2026-05-31T12:00:00",
        "allowed_decision_modes": ["long_term_buy_add"],
        "allowed_horizons": ["12_months"],
        "score_impact": "none",
        "recommendation_impact": "none",
        "notes": "Review-only registry row.",
    }
    row.update(overrides)
    return row


class ModelRegistryTests(unittest.TestCase):
    def test_official_model_with_no_recommendation_impact_claims(self) -> None:
        row = subject.normalize_model_registration(model_row())
        result = subject.validate_model_registration(row)

        self.assertTrue(result["ok"], result)
        self.assertEqual(row["score_impact"], "none")
        self.assertEqual(row["recommendation_impact"], "none")
        self.assertTrue(row["review_only"])
        self.assertIn("Review-only", row["recommendation_only_note"])

    def test_shadow_model_marked_non_authoritative(self) -> None:
        row = subject.normalize_model_registration(
            model_row(
                model_name="daily_report_shadow",
                model_version="shadow-v1",
                model_role="shadow",
                official_or_shadow="shadow",
                allowed_decision_modes=["long_term_buy_add", "tactical_trade"],
                allowed_horizons=["12_months", "5_trading_days"],
            )
        )

        result = subject.validate_model_registration(row)

        self.assertTrue(result["ok"], result)
        self.assertEqual(row["official_or_shadow"], "shadow")
        self.assertEqual(row["recommendation_impact"], "none")

    def test_missing_model_version_is_invalid(self) -> None:
        result = subject.validate_model_registration(model_row(model_version=""))

        self.assertFalse(result["ok"])
        self.assertIn("model_version", {error["path"] for error in result["errors"]})

    def test_invalid_decision_mode_and_horizon_are_invalid(self) -> None:
        result = subject.validate_model_registration(
            model_row(
                allowed_decision_modes=["moonshot_mode"],
                allowed_horizons=["three_days"],
            )
        )

        self.assertFalse(result["ok"])
        paths = {error["path"] for error in result["errors"]}
        self.assertIn("allowed_decision_modes[0]", paths)
        self.assertIn("allowed_horizons[0]", paths)

    def test_recommendation_impact_requires_explicit_approval_reference(self) -> None:
        result = subject.validate_model_registration(model_row(recommendation_impact="changes_actions"))

        self.assertFalse(result["ok"])
        self.assertIn("recommendation_impact", {error["path"] for error in result["errors"]})

        approved = subject.validate_model_registration(
            model_row(recommendation_impact="changes_actions", impact_approval_ref="future-approved-model-impact-pr")
        )
        self.assertTrue(approved["ok"], approved)

    def test_registry_build_is_deterministic_and_review_only(self) -> None:
        registry = subject.build_model_registry(
            [
                model_row(model_name="shadow", model_role="shadow", official_or_shadow="shadow"),
                model_row(model_name="official"),
            ],
            created_at="2026-05-31T12:00:00",
        )

        self.assertTrue(registry["review_only"])
        self.assertEqual(registry["model_count"], 2)
        self.assertTrue(registry["validation"]["ok"])
        self.assertEqual([row["model_name"] for row in registry["models"]], ["official", "shadow"])

    def test_no_input_mutation(self) -> None:
        row = model_row(allowed_decision_modes=["long_term_buy_add"])
        before = copy.deepcopy(row)

        subject.normalize_model_registration(row)
        subject.validate_model_registration(row)

        self.assertEqual(row, before)


if __name__ == "__main__":
    unittest.main()
