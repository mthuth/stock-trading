#!/usr/bin/env python3
"""Tests for plain-English score driver glossary helpers."""

from __future__ import annotations

import unittest

from stock_trading import analysis_engine, analysis_models
from stock_trading.reporting.score_glossary import (
    render_score_glossary_html,
    render_score_glossary_markdown,
)
from stock_trading.score_driver_glossary import (
    REVIEW_ONLY_GUARDRAIL,
    glossary_entries,
    glossary_entry,
    glossary_for_score_component,
)


REQUIRED_TERMS = {
    "base evidence",
    "trend",
    "target",
    "gap",
    "final action",
    "score driver",
    "score risk",
    "target confidence",
    "data status",
    "decision gate",
    "source health",
    "provider gap",
    "allocation cap",
    "watchlist-only",
    "model/user disagreement",
    "review-only output",
}


def research_input() -> analysis_models.ResearchInput:
    return analysis_models.ResearchInput(
        symbol="NVDA",
        company="NVDA Corp.",
        category="AI",
        sleeve="long_term",
        trade_type="long_term",
        current_price=100.0,
        target_price=130.0,
        quality_score=90.0,
        momentum_score=85.0,
        catalyst_score=80.0,
        risk_score=75.0,
        confidence="medium",
        notes="Fixture analysis input.",
        price_source="fixture",
        target_source="fixture",
        estimate_source="",
        sentiment_source="",
        eps_estimate="",
        revenue_estimate="",
        news_sentiment="",
        provider_notes="",
    )


def blended_target() -> analysis_models.BlendedTarget:
    return analysis_models.BlendedTarget(
        symbol="NVDA",
        target_price=140.0,
        target_low=120.0,
        target_high=155.0,
        current_price=100.0,
        upside_pct=40.0,
        confidence="medium",
        source_count=2,
        blend_status="Analyst + fundamental",
        sources_label="fixture",
        notes="fixture",
    )


class ScoreDriverGlossaryTests(unittest.TestCase):
    def test_required_glossary_terms_exist(self) -> None:
        terms = {entry["term"] for entry in glossary_entries()}

        self.assertTrue(REQUIRED_TERMS.issubset(terms))
        for entry in glossary_entries():
            self.assertTrue(entry["review_only"])
            self.assertTrue(entry["no_scoring_change"])
            self.assertIn("does not change scoring", entry["guardrail"])

    def test_unknown_term_is_handled_gracefully(self) -> None:
        entry = glossary_entry("mystery factor")

        self.assertEqual(entry["term"], "mystery factor")
        self.assertFalse(entry["known"])
        self.assertTrue(entry["review_only"])
        self.assertIn("No glossary entry", entry["definition"])

    def test_score_component_maps_to_glossary_entry(self) -> None:
        self.assertEqual(glossary_for_score_component("base_score")["term"], "base evidence")
        self.assertEqual(glossary_for_score_component("trend_delta")["term"], "trend")
        self.assertEqual(glossary_for_score_component("target_delta")["term"], "target")
        self.assertEqual(glossary_for_score_component("data_gap_delta")["term"], "gap")
        self.assertEqual(glossary_for_score_component("final_action")["term"], "final action")
        self.assertEqual(glossary_for_score_component("source_health")["term"], "source health")

    def test_rendered_glossary_contains_guardrail_text(self) -> None:
        markdown = render_score_glossary_markdown()
        html = render_score_glossary_html()

        self.assertIn(REVIEW_ONLY_GUARDRAIL, markdown)
        self.assertIn("Score Driver Glossary", html)
        self.assertIn("review-only", html)
        self.assertIn("does not change scoring", html)
        self.assertIn("base evidence", markdown)

    def test_glossary_does_not_change_scoring_behavior(self) -> None:
        item = research_input()
        target = blended_target()
        positions = {"MSFT": {"market_value": 1000.0}}

        before = analysis_engine.score_stock(item, positions, target)
        glossary_entries()
        glossary_entry("base evidence")
        glossary_for_score_component("data_gap_delta")
        render_score_glossary_markdown()
        render_score_glossary_html()
        after = analysis_engine.score_stock(item, positions, target)

        self.assertEqual(before, after)

    def test_returned_entries_are_caller_safe(self) -> None:
        entries = glossary_entries()
        entries[0]["definition"] = "mutated by caller"

        self.assertNotEqual(glossary_entry("base evidence")["definition"], "mutated by caller")


if __name__ == "__main__":
    unittest.main()
