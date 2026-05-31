#!/usr/bin/env python3
"""Regression tests for report-context schema and safety validation."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from stock_trading.report_context_schema import (
    validate_recommendation_only_language,
    validate_report_context,
    validate_review_only_sections,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "report_context.json"


def minimal_context() -> dict[str, object]:
    return {
        "metadata": {
            "report_date": "2026-05-31",
            "generated_at": "2026-05-31T08:00:00",
            "recommendation_only": True,
        },
        "summary": {
            "top_symbol": "MSFT",
            "top_action": "Add",
            "top_score": 82.0,
            "decision_gate": {"status": "Ready", "safe_to_buy": True},
        },
        "recommendations": [
            {
                "symbol": "MSFT",
                "action": "Add",
                "score": 82.0,
                "score_explanation": {"summary": "Fixture score explanation."},
                "target_drilldown": {"blend_label": "Fixture blend"},
            }
        ],
    }


def messages(result: object) -> list[str]:
    return [issue.message for issue in result.errors + result.warnings]


class ReportContextSchemaTests(unittest.TestCase):
    maxDiff = None

    def test_valid_fixture_context_validates(self) -> None:
        context = json.loads(FIXTURE.read_text())

        result = validate_report_context(context)

        self.assertTrue(result.ok, result.to_dict())

    def test_missing_optional_learning_section_is_compatible(self) -> None:
        context = minimal_context()

        result = validate_report_context(context)

        self.assertTrue(result.ok, result.to_dict())
        self.assertNotIn("learning_review", context)

    def test_malformed_learning_section_is_detected(self) -> None:
        context = minimal_context()
        context["learning_review"] = "not a structured review"

        result = validate_report_context(context)

        self.assertFalse(result.ok)
        self.assertIn("Review-only section must be a dictionary or list.", messages(result))

    def test_review_only_section_missing_review_only_flag_is_detected(self) -> None:
        context = minimal_context()
        context["recommendation_outcomes"] = {
            "metadata": {"windows": [1, 5, 20, 60]},
            "outcomes": [],
        }

        result = validate_review_only_sections(context)

        self.assertFalse(result.ok)
        self.assertEqual(result.errors[0].path, "recommendation_outcomes")
        self.assertIn("review_only: true", result.errors[0].message)

    def test_review_only_section_claiming_score_impact_is_detected(self) -> None:
        context = minimal_context()
        context["source_usefulness"] = {
            "metadata": {"review_only": True},
            "summary": "This section directly changes the score after source review.",
        }

        result = validate_report_context(context)

        self.assertFalse(result.ok)
        self.assertTrue(any("claims model impact" in message for message in messages(result)))

    def test_review_only_guarded_non_impact_language_is_allowed(self) -> None:
        context = minimal_context()
        context["catalyst_follow_through"] = {
            "metadata": {"review_only": True},
            "summary": "Review-only catalyst results must not automatically change scores or actions.",
        }

        result = validate_review_only_sections(context)

        self.assertTrue(result.ok, result.to_dict())

    def test_missing_summary_fields_are_detected(self) -> None:
        context = minimal_context()
        context["summary"] = {"top_symbol": "MSFT"}

        result = validate_report_context(context)

        self.assertFalse(result.ok)
        error_paths = {issue.path for issue in result.errors}
        self.assertIn("summary.top_action", error_paths)
        self.assertIn("summary.top_score", error_paths)

    def test_older_context_with_optional_sections_missing_is_valid(self) -> None:
        context = {
            "metadata": {"report_date": "2026-05-28", "recommendation_only": True},
            "summary": {"top_symbol": "NVDA", "top_action": "Add", "top_score": 84.2},
            "recommendations": [{"symbol": "NVDA", "action": "Add", "score": 84.2}],
        }

        result = validate_report_context(context)

        self.assertTrue(result.ok, result.to_dict())

    def test_recommendation_only_language_detects_execution_claims(self) -> None:
        context = minimal_context()
        context["summary"]["top_notes"] = "This dashboard can place trades automatically."

        result = validate_recommendation_only_language(context)

        self.assertFalse(result.ok)
        self.assertIn("execution language", result.errors[0].message)

    def test_validator_does_not_mutate_context(self) -> None:
        context = minimal_context()
        before = copy.deepcopy(context)

        validate_report_context(context)

        self.assertEqual(context, before)


if __name__ == "__main__":
    unittest.main()
