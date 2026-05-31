#!/usr/bin/env python3
"""Integration tests for Wave 6 learning review report output."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from stock_trading import presentation as subject


def base_context() -> dict[str, object]:
    context = {section: {} for section in subject.REQUIRED_CONTEXT_SECTIONS}
    context["metadata"] = {"report_date": "2026-05-31", "generated_at": "2026-05-31T08:00:00", "recommendation_only": True}
    context["summary"] = {
        "top_symbol": "MSFT",
        "top_company": "Microsoft",
        "top_action": "Add",
        "top_score": 82.0,
        "recommendation_label": "Recommended next buy",
        "suggested_amount": 2500.0,
        "suggested_amount_text": "$2,500.00",
        "decision_gate": {
            "safe_to_buy": True,
            "status": "Ready",
            "candidate_action": "Add",
            "reasons": [],
            "summary": "Decision-safe buy candidate.",
        },
    }
    context["reliability"] = {"mode": "Fixture", "price_counts": {"fresh": 1, "missing": 0}}
    context["source_health"] = {"summary": {"needs_attention": 0, "healthy": 1, "stale": 0, "not_implemented": 0}}
    context["recommendations"] = [{"symbol": "MSFT", "action": "Add", "score": 82.0}]
    return context


def learning_review_with_data() -> dict[str, object]:
    return {
        "review_only": True,
        "note": "Review-only learning outputs. These outputs do not change recommendations.",
        "manual_journal": {
            "review_only": True,
            "summary": {"entry_count": 1, "actions": {"bought": 1}},
            "recent_actions": [
                {
                    "decision_date": "2026-05-31",
                    "symbol": "MSFT",
                    "action_taken": "bought",
                    "amount": 2500,
                    "notes": "Manual purchase after review.",
                }
            ],
        },
        "recommendation_outcomes": {
            "review_only": True,
            "summary": {"outcome_count": 1, "outcomes_by_status": {"positive_follow_through": 1}},
            "top_outcomes": [
                {
                    "symbol": "MSFT",
                    "report_date": "2026-05-01",
                    "original_action": "Add",
                    "outcome_status": "positive_follow_through",
                    "percent_change": 6.5,
                    "later_price": 106.5,
                    "window_trading_days": 20,
                }
            ],
        },
        "catalyst_follow_through": {
            "review_only": True,
            "summary": {"outcome_count": 1, "outcomes_by_label": {"likely_useful": 1}},
            "top_outcomes": [
                {
                    "symbol": "MSFT",
                    "event_type": "AI platform update",
                    "headline": "Azure AI demand remained strong",
                    "outcome_label": "likely_useful",
                }
            ],
        },
        "source_usefulness": {
            "review_only": True,
            "summary": {"source_count": 1, "labels": {"useful_but_sparse": 1}},
            "top_sources": [
                {
                    "source_name": "Microsoft IR",
                    "label": "useful_but_sparse",
                    "evidence_count": 2,
                    "feedback_delta": 0.1,
                    "latest_issue": "",
                }
            ],
        },
        "decision_safety_effectiveness": {
            "review_only": True,
            "summary": {"row_count": 1, "blocks_likely_avoided_risk": 0, "blocks_may_have_missed_upside": 0},
            "top_rows": [
                {
                    "symbol": "MSFT",
                    "decision_gate_status": "Ready",
                    "review_bucket": "decision_safe_candidate",
                    "later_price_movement_pct": 6.5,
                    "assessment": "Ready candidate later rose.",
                }
            ],
        },
    }


class Wave6LearningIntegrationTests(unittest.TestCase):
    def test_learning_review_renders_with_learning_data(self) -> None:
        context = base_context()
        context["learning_review"] = learning_review_with_data()
        summary_before = copy.deepcopy(context["summary"])
        recommendations_before = copy.deepcopy(context["recommendations"])

        dashboard = subject.render_dashboard_html(context)
        markdown = subject.render_markdown(context)

        self.assertIn("Learning Review", dashboard)
        self.assertIn("What the app recommended", dashboard)
        self.assertIn("What the user did manually", dashboard)
        self.assertIn("Catalyst follow-through", dashboard)
        self.assertIn("Source usefulness / noise", dashboard)
        self.assertIn("Decision safety effectiveness", dashboard)
        self.assertIn("Microsoft IR", dashboard)
        self.assertIn("Ready candidate later rose", dashboard)
        self.assertIn("## Learning Review", markdown)
        self.assertIn("Review-only learning outputs", markdown)
        self.assertEqual(context["summary"], summary_before)
        self.assertEqual(context["recommendations"], recommendations_before)

    def test_learning_review_renders_empty_states_without_learning_data(self) -> None:
        context = base_context()
        context["learning_review"] = {"review_only": True}

        dashboard = subject.render_dashboard_html(context)
        markdown = subject.render_markdown(context)

        self.assertIn("Learning Review", dashboard)
        self.assertIn("No manual journal entries recorded yet", dashboard)
        self.assertIn("Not enough recommendation outcome history yet", dashboard)
        self.assertIn("No decision-safety effectiveness history available yet", dashboard)
        self.assertIn("## Learning Review", markdown)
        self.assertIn("No manual journal entries recorded yet", markdown)

    def test_rendered_context_preserves_recommendation_summary(self) -> None:
        context = base_context()
        context["learning_review"] = learning_review_with_data()

        with tempfile.TemporaryDirectory() as tmpdir:
            subject.render_report_context(context, Path(tmpdir))
            rendered = json.loads((Path(tmpdir) / "report-context-2026-05-31.json").read_text())

        self.assertEqual(rendered["summary"]["top_symbol"], "MSFT")
        self.assertEqual(rendered["summary"]["top_action"], "Add")
        self.assertEqual(rendered["summary"]["suggested_amount"], 2500.0)
        self.assertTrue(rendered["learning_review"]["review_only"])


if __name__ == "__main__":
    unittest.main()
