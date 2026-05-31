#!/usr/bin/env python3
"""Regression tests for rendered decision-safety review output."""

from __future__ import annotations

import unittest

from stock_trading import presentation as subject
from stock_trading.reporting.renderers import normalized_report_context


CONTROLLED_BUY_ACTIONS = {"Strong Buy", "Buy", "Add"}


def report_context(
    gate: dict[str, object],
    *,
    suggested_amount_text: str = "$2,500.00",
    confidence: str = "Medium",
    data_status: str = "Blended",
) -> dict[str, object]:
    context = {section: {} for section in subject.REQUIRED_CONTEXT_SECTIONS}
    context["metadata"] = {"report_date": "2026-05-29", "generated_at": "2026-05-29T18:00:00", "recommendation_only": True}
    context["summary"] = {
        "top_symbol": "NVDA",
        "top_company": "NVIDIA",
        "top_action": "Add",
        "top_score": 82.0,
        "recommendation_label": "Recommended next buy",
        "amount_label": "Suggested buy amount",
        "suggested_amount": 2500.0,
        "suggested_amount_text": suggested_amount_text,
        "current_price_text": "$135.00",
        "target_text": "$170.00",
        "upside_text": "25.9%",
        "confidence": confidence,
        "data_status": data_status,
        "top_notes": "Fixture top candidate.",
        "decision_gate": gate,
    }
    context["reliability"] = {"mode": "Fixture", "price_counts": {"fresh": 1, "missing": 0}}
    context["source_health"] = {"summary": {"needs_attention": 0, "healthy": 1, "stale": 0, "not_implemented": 0}}
    return context


def blocked_gate(reason: str) -> dict[str, object]:
    return {
        "safe_to_buy": False,
        "status": "Blocked",
        "candidate_action": "Add",
        "reasons": [reason],
        "summary": reason,
    }


class DecisionSafetyReviewTests(unittest.TestCase):
    def assert_blocked_review(self, reason: str, *, confidence: str = "Medium", data_status: str = "Blended") -> None:
        context = report_context(blocked_gate(reason), confidence=confidence, data_status=data_status)
        normalized = normalized_report_context(context)
        markdown = subject.render_markdown(context)
        dashboard = subject.render_dashboard_html(context)

        self.assertEqual(normalized["decision_safety"]["candidate_action"], "Add")
        self.assertIn(normalized["decision_safety"]["candidate_action"], CONTROLLED_BUY_ACTIONS)
        self.assertFalse(normalized["decision_safety"]["safe_to_buy"])
        self.assertEqual(normalized["summary"]["suggested_amount"], 0.0)
        self.assertEqual(normalized["summary"]["suggested_amount_text"], "$0.00")
        self.assertIn("## Decision Safety Review", markdown)
        self.assertIn("- Review state: **Blocked buy candidate**", markdown)
        self.assertIn("- Candidate action: **Add**", markdown)
        self.assertIn("- Suggested amount: **$0.00**", markdown)
        self.assertNotIn("- Candidate action: **Add blocked**", markdown)
        self.assertIn(reason, markdown)
        self.assertIn("Decision Safety Review", dashboard)
        self.assertIn("Blocked buy candidate", dashboard)
        self.assertIn(reason, dashboard)

    def test_low_confidence_block_is_plain_english(self) -> None:
        self.assert_blocked_review("Low target confidence", confidence="Low")

    def test_wide_range_block_is_plain_english(self) -> None:
        self.assert_blocked_review("Wide target range", data_status="Wide range")

    def test_partial_blend_block_is_plain_english(self) -> None:
        self.assert_blocked_review("Partial target blend", data_status="Partial blend")

    def test_verification_needed_block_is_plain_english(self) -> None:
        self.assert_blocked_review("Verification check is still open")

    def test_data_gap_block_is_plain_english(self) -> None:
        self.assert_blocked_review("Required data gap is still open", data_status="Needs price refresh")

    def test_safe_buy_candidate_shows_passed_gate(self) -> None:
        context = report_context(
            {
                "safe_to_buy": True,
                "status": "Ready",
                "candidate_action": "Add",
                "reasons": [],
                "summary": "Decision-safe buy candidate.",
            }
        )
        normalized = normalized_report_context(context)
        markdown = subject.render_markdown(context)
        dashboard = subject.render_dashboard_html(context)

        self.assertTrue(normalized["decision_safety"]["safe_to_buy"])
        self.assertEqual(normalized["decision_safety"]["status"], "Ready")
        self.assertEqual(normalized["decision_safety"]["candidate_action"], "Add")
        self.assertEqual(normalized["summary"]["suggested_amount_text"], "$2,500.00")
        self.assertIn("- Review state: **Decision-safe next buy**", markdown)
        self.assertIn("- Blocked reasons: None", markdown)
        self.assertIn("- Suggested amount: **$2,500.00**", markdown)
        self.assertIn("Decision-safe next buy", dashboard)
        self.assertNotIn("Blocked buy candidate", dashboard)


if __name__ == "__main__":
    unittest.main()
