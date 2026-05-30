#!/usr/bin/env python3
"""Regression tests for the application and AI-analysis boundary."""

from __future__ import annotations

import unittest
from unittest.mock import patch


from stock_trading import analysis as subject
from stock_trading import analysis_context, analysis_models, analysis_scoring, analysis_snapshot, analysis_targets


def research_input() -> analysis_models.ResearchInput:
    return analysis_models.ResearchInput(
        symbol="NVDA",
        company="NVIDIA Corp.",
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


class AnalysisBoundaryTests(unittest.TestCase):
    def test_score_recommendations_builds_context_without_provider_calls(self) -> None:
        item = research_input()
        snapshot = subject.AnalysisSnapshot(
            report_date="2026-05-28",
            research=[item],
            targets={"account_value": 50000, "monthly_contribution": 2500},
            positions={},
            research_by_symbol={"NVDA": item},
            account_value=50000,
            monthly_contribution=2500,
            default_buy_amount=2500,
            reliability={"mode": "Fresh provider data", "price_counts": {"fresh": 1}},
        )
        target = analysis_models.BlendedTarget(
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

        with patch("stock_trading.provider_client.fetch_json_url") as fetch_json_url:
            ranked, score_rows = subject.score_recommendations(snapshot, {"NVDA": target})
            context = subject.build_report_context(snapshot, ranked, recommendation_run_id=42)

        fetch_json_url.assert_not_called()
        self.assertEqual(score_rows[0]["symbol"], "NVDA")
        self.assertIn(score_rows[0]["action"], {"Add", "Watch", "Hold", "Avoid"})
        self.assertEqual(context["metadata"]["recommendation_run_id"], 42)
        self.assertEqual(context["recommendations"][0]["symbol"], "NVDA")

    def test_analysis_facade_uses_focused_modules(self) -> None:
        self.assertIs(subject.AnalysisSnapshot, analysis_snapshot.AnalysisSnapshot)
        self.assertIs(subject.BlendedTarget, analysis_models.BlendedTarget)
        self.assertIs(subject.score_recommendations, analysis_scoring.score_recommendations)
        self.assertIs(subject.compute_target_sources, analysis_targets.compute_target_sources)
        self.assertIs(subject.build_report_context, analysis_context.build_report_context)


if __name__ == "__main__":
    unittest.main()
