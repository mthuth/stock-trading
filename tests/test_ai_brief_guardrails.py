#!/usr/bin/env python3
"""Regression tests for deterministic AI brief guardrails."""

from __future__ import annotations

import unittest

from stock_trading.ai_brief_guardrails import validate_ai_brief


def valid_brief(**overrides: object) -> dict[str, object]:
    brief: dict[str, object] = {
        "symbol": "MSFT",
        "brief": (
            "MSFT has a balanced bull and bear setup. Evidence supports the cloud AI thesis, "
            "but provider gap checks remain part of review. No major data gaps found."
        ),
        "risk_or_uncertainty": "Risk or uncertainty: valuation and cloud growth estimates need continued review.",
        "data_gaps": "No major data gaps found.",
        "recommendation_only_disclaimer": "Recommendation-only decision support; not an instruction to trade.",
        "what_would_change_the_view": "A material guide-down or stale evidence would change the view.",
        "audit_refs": ["decision_insights:MSFT", "evidence_events:MSFT"],
        "synthesis_readiness": {"readiness_status": "partially_ready"},
    }
    brief.update(overrides)
    return brief


def failure_categories(brief: dict[str, object]) -> set[str]:
    return {
        str(item["category"])
        for item in validate_ai_brief(brief).to_dict()["failures"]
    }


class AiBriefGuardrailTests(unittest.TestCase):
    def test_valid_source_backed_brief_passes(self) -> None:
        result = validate_ai_brief(valid_brief()).to_dict()

        self.assertTrue(result["passed"])
        self.assertEqual(result["recommended_action"], "accept")
        self.assertEqual(result["failures"], [])

    def test_missing_source_references_fails(self) -> None:
        brief = valid_brief(audit_refs=[])

        self.assertIn("missing_source_references", failure_categories(brief))

    def test_guaranteed_performance_language_fails(self) -> None:
        brief = valid_brief(brief="MSFT is guaranteed to outperform. No major data gaps found.")

        self.assertIn("guaranteed_performance_language", failure_categories(brief))

    def test_order_execution_language_fails(self) -> None:
        brief = valid_brief(brief="Place an order for MSFT after reviewing this brief. No major data gaps found.")

        self.assertIn("order_or_execution_language", failure_categories(brief))

    def test_missing_risk_section_fails(self) -> None:
        brief = valid_brief(risk_or_uncertainty="", brief="MSFT has source-backed evidence. No major data gaps found.")

        self.assertIn("missing_risk_uncertainty", failure_categories(brief))

    def test_unsupported_target_claim_fails(self) -> None:
        brief = valid_brief(brief="MSFT has upside to $500 based on this thesis. No major data gaps found.")

        self.assertIn("unsupported_target_claim", failure_categories(brief))

    def test_not_enough_data_brief_must_acknowledge_low_readiness(self) -> None:
        brief = valid_brief(
            synthesis_readiness={"readiness_status": "not_enough_data"},
            brief="MSFT has a promising setup. No major data gaps found.",
        )

        self.assertIn("ignored_low_readiness", failure_categories(brief))

    def test_target_claim_with_target_source_support_passes_target_guardrail(self) -> None:
        brief = valid_brief(
            brief="MSFT has a price target of $500 from target-source context. No major data gaps found.",
            target_source_refs=["target_sources:MSFT"],
        )

        self.assertNotIn("unsupported_target_claim", failure_categories(brief))


if __name__ == "__main__":
    unittest.main()
