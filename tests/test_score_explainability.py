#!/usr/bin/env python3
"""Regression tests for score explainability."""

from __future__ import annotations

import unittest

from stock_trading import analysis_context, analysis_engine, analysis_models, analysis_scoring
from stock_trading.analysis_snapshot import AnalysisSnapshot


def research_input(
    *,
    symbol: str = "NVDA",
    quality: float = 90.0,
    momentum: float = 85.0,
    catalyst: float = 80.0,
    risk: float = 75.0,
    sleeve: str = "long_term",
) -> analysis_models.ResearchInput:
    return analysis_models.ResearchInput(
        symbol=symbol,
        company=f"{symbol} Corp.",
        category="AI",
        sleeve=sleeve,
        trade_type="long_term",
        current_price=100.0,
        target_price=130.0,
        quality_score=quality,
        momentum_score=momentum,
        catalyst_score=catalyst,
        risk_score=risk,
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


def blended_target(symbol: str = "NVDA", upside: float = 40.0) -> analysis_models.BlendedTarget:
    return analysis_models.BlendedTarget(
        symbol=symbol,
        target_price=140.0,
        target_low=120.0,
        target_high=155.0,
        current_price=100.0,
        upside_pct=upside,
        confidence="medium",
        source_count=2,
        blend_status="Analyst + fundamental",
        sources_label="fixture",
        notes="fixture",
    )


class ScoreExplainabilityTests(unittest.TestCase):
    def test_score_explanation_does_not_change_score_math(self) -> None:
        item = research_input()
        target = blended_target()
        positions = {"MSFT": {"market_value": 1000.0}}

        before = analysis_engine.score_stock(item, positions, target)
        explanation = analysis_engine.score_explanation(item, before, target, rationale="fixture rationale")
        after = analysis_engine.score_stock(item, positions, target)

        self.assertEqual(before, after)
        self.assertEqual(explanation["base_score"], round(before.total, 4))
        self.assertEqual(explanation["final_score"], round(before.total, 4))
        self.assertEqual(explanation["components"]["upside"], round(before.upside, 4))
        self.assertIn("quality", explanation["components"])
        self.assertIn("momentum", explanation["components"])
        self.assertIn("catalyst", explanation["components"])
        self.assertIn("risk", explanation["components"])

    def test_score_explanation_identifies_top_drivers_and_risks(self) -> None:
        item = research_input(quality=92.0, momentum=42.0, catalyst=55.0, risk=40.0, sleeve="speculative_ai")
        target = blended_target(upside=10.0)
        breakdown = analysis_engine.ScoreBreakdown(
            total=52.0,
            upside=4.5,
            quality=23.0,
            momentum=8.4,
            catalyst=8.25,
            risk=6.0,
            owned_penalty=5.0,
            speculative_penalty=8.0,
            model="Long-term",
        )
        insight = analysis_engine.InsightSignal(
            symbol="NVDA",
            base_score=52.0,
            final_score=45.0,
            evidence_delta=-2.0,
            trend_delta=-3.0,
            target_delta=1.0,
            data_gap_delta=-3.0,
            drivers=[
                "Evidence is mixed.",
                "Trend is weak.",
                "Target confidence helps slightly.",
                "Data gaps limit confidence.",
            ],
            data_gaps=[],
            trend_insight="Weak trend.",
        )

        explanation = analysis_engine.score_explanation(item, breakdown, target, insight, "Watch rationale")

        self.assertEqual(explanation["components"]["owned_penalty"], -5.0)
        self.assertEqual(explanation["components"]["speculative_penalty"], -8.0)
        self.assertEqual(explanation["components"]["signal_overlay"], -7.0)
        self.assertLessEqual(len(explanation["top_drivers"]), 3)
        self.assertLessEqual(len(explanation["top_risks"]), 3)
        self.assertEqual(explanation["top_drivers"][0]["key"], "quality")
        risk_keys = {risk["key"] for risk in explanation["top_risks"]}
        self.assertTrue({"speculative_penalty", "risk", "data_gap"} & risk_keys)

    def test_report_context_exposes_score_explanation_for_recommendations(self) -> None:
        item = research_input()
        target = blended_target()
        snapshot = AnalysisSnapshot(
            report_date="2026-05-31",
            research=[item],
            targets={"account_value": 50000, "monthly_contribution": 2500},
            positions={},
            research_by_symbol={"NVDA": item},
            account_value=50000,
            monthly_contribution=2500,
            default_buy_amount=2500,
            reliability={"mode": "Fixture", "price_counts": {"fresh": 1}},
        )
        expected_score = analysis_engine.score_stock(item, {}, target).total

        ranked, _ = analysis_scoring.score_recommendations(snapshot, {"NVDA": target})
        context = analysis_context.build_report_context(snapshot, ranked, recommendation_run_id=42)
        recommendation = context["recommendations"][0]
        explanation = recommendation["score_explanation"]

        self.assertEqual(ranked[0]["score"], expected_score)
        self.assertEqual(recommendation["score"], round(expected_score, 2))
        self.assertEqual(explanation["base_score"], round(expected_score, 4))
        self.assertEqual(explanation["final_score"], round(expected_score, 4))
        self.assertEqual(len(explanation["top_drivers"]), 3)
        self.assertIn("component_details", explanation)


if __name__ == "__main__":
    unittest.main()
