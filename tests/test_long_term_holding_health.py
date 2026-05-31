#!/usr/bin/env python3
"""Tests for review-only long-term holding health."""

from __future__ import annotations

import copy
import json
import unittest

from stock_trading import long_term_holding_health as subject


def holding(symbol: str = "MSFT", company: str = "Microsoft") -> dict[str, object]:
    return {
        "symbol": symbol,
        "company": company,
        "sleeve": "long_term",
        "portfolio_pct": 4.0,
    }


def recommendation(
    *,
    symbol: str = "MSFT",
    company: str = "Microsoft",
    action: str = "Hold",
    score: float = 82.0,
    current_price: float = 100.0,
    target_price: float = 130.0,
    upside_pct: float = 30.0,
    target_confidence: str = "medium",
    data_status: str = "Blended",
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "company": company,
        "sleeve": "long_term",
        "action": action,
        "score": score,
        "current_price": current_price,
        "target_price": target_price,
        "upside_pct": upside_pct,
        "target_confidence": target_confidence,
        "data_status": data_status,
    }


class LongTermHoldingHealthTests(unittest.TestCase):
    def test_healthy_holding(self) -> None:
        result = subject.evaluate_holding_health(
            holding(),
            recommendation=recommendation(action="Add", score=86, target_confidence="high"),
            score_trend=[{"score": 80}, {"score": 86}],
            source_usefulness=[{"symbol": "MSFT", "label": "consistently_useful"}],
            catalyst_follow_through=[{"symbol": "MSFT", "outcome_label": "likely_useful"}],
            recommendation_outcomes=[{"symbol": "MSFT", "outcome_status": "positive_follow_through"}],
        )

        self.assertEqual(result["health_label"], "healthy")
        self.assertGreaterEqual(result["health_score"], 90)
        self.assertTrue(result["review_only"])
        self.assertEqual(result["recommendation_impact"], "none")
        self.assertEqual(result["broker_behavior"], "none")
        self.assertIn("routine long-term thesis monitoring", result["review_actions"][0])

    def test_thesis_weakening_from_action_score_trend_and_outcomes(self) -> None:
        result = subject.evaluate_holding_health(
            holding("NVDA", "NVIDIA"),
            recommendation=recommendation(symbol="NVDA", company="NVIDIA", action="Watch", score=68),
            score_trend=[{"score": 84}, {"score": 70}],
            recommendation_outcomes=[{"symbol": "NVDA", "outcome_status": "negative_follow_through"}],
        )

        self.assertEqual(result["health_label"], "thesis_weakening")
        self.assertLess(result["health_score"], 80)
        self.assertTrue(any("thesis" in reason.lower() for reason in result["reasons"]))
        self.assertTrue(any("score trend" in reason.lower() for reason in result["reasons"]))

    def test_valuation_stretched(self) -> None:
        result = subject.evaluate_holding_health(
            holding("META", "Meta Platforms"),
            recommendation=recommendation(
                symbol="META",
                company="Meta Platforms",
                action="Hold",
                score=80,
                current_price=105,
                target_price=104,
                upside_pct=-1,
            ),
            allocation_context={"current_position_pct": 9.8},
        )

        self.assertEqual(result["health_label"], "valuation_stretched")
        self.assertTrue(any("valuation" in reason.lower() for reason in result["reasons"]))
        self.assertTrue(any("concentration" in action.lower() for action in result["review_actions"]))

    def test_risk_rising(self) -> None:
        result = subject.evaluate_holding_health(
            holding("SNOW", "Snowflake"),
            recommendation=recommendation(symbol="SNOW", company="Snowflake", action="Avoid", score=52),
            ai_status={
                "readiness_status": "partially_ready",
                "risk_or_uncertainty": "Risk or uncertainty: execution risk and unsupported growth assumptions.",
            },
        )

        self.assertEqual(result["health_label"], "risk_rising")
        self.assertTrue(any("risk" in reason.lower() for reason in result["reasons"]))

    def test_data_insufficient_without_recommendation_context(self) -> None:
        result = subject.evaluate_holding_health(holding("AMZN", "Amazon"))

        self.assertEqual(result["health_label"], "data_insufficient")
        self.assertIn("Missing current recommendation context", " ".join(result["data_gaps"]))
        self.assertEqual(result["confidence"], "low")

    def test_negative_catalyst_follow_through_flags_thesis_review(self) -> None:
        result = subject.evaluate_holding_health(
            holding("AMD", "Advanced Micro Devices"),
            recommendation=recommendation(symbol="AMD", company="Advanced Micro Devices", action="Hold", score=74),
            catalyst_follow_through=[
                {
                    "symbol": "AMD",
                    "outcome_label": "likely_noisy",
                    "outcome_reasons": ["negative_follow_through"],
                }
            ],
            recommendation_outcomes=[{"symbol": "AMD", "outcome_status": "negative_follow_through"}],
        )

        self.assertEqual(result["health_label"], "thesis_weakening")
        self.assertTrue(any("catalyst" in reason.lower() for reason in result["reasons"]))

    def test_poor_source_and_provider_quality_flags_data_insufficient(self) -> None:
        result = subject.evaluate_holding_health(
            holding("GOOGL", "Alphabet"),
            recommendation=recommendation(
                symbol="GOOGL",
                company="Alphabet",
                action="Hold",
                score=76,
                target_confidence="low",
                data_status="Stale target",
            ),
            provider_gaps=[
                {
                    "symbol": "GOOGL",
                    "provider": "FMP",
                    "field_name": "analyst_target",
                    "status": "blocked",
                }
            ],
            source_usefulness=[{"symbol": "GOOGL", "label": "stale_or_blocked"}],
        )

        self.assertEqual(result["health_label"], "data_insufficient")
        self.assertTrue(any("provider/data gap" in gap.lower() for gap in result["data_gaps"]))
        self.assertTrue(any("source usefulness" in gap.lower() for gap in result["data_gaps"]))

    def test_no_recommendation_mutation(self) -> None:
        rec = recommendation(action="Hold", score=80)
        original = copy.deepcopy(rec)

        subject.evaluate_holding_health(holding(), recommendation=rec)

        self.assertEqual(rec, original)

    def test_no_sell_order_or_execution_language(self) -> None:
        result = subject.evaluate_holding_health(
            holding("MDB", "MongoDB"),
            recommendation=recommendation(symbol="MDB", company="MongoDB", action="Watch", score=64),
        )
        serialized = json.dumps(result).lower()

        self.assertTrue(result["review_only"])
        self.assertIn("no_sell_instruction", result)
        self.assertNotIn("sell now", serialized)
        self.assertNotIn("place order", serialized)
        self.assertNotIn("order preview", serialized)
        self.assertNotIn("execute trade", serialized)

    def test_build_holding_health_review_summary(self) -> None:
        review = subject.build_holding_health_review(
            [holding("MSFT", "Microsoft"), holding("AMZN", "Amazon")],
            recommendations_by_symbol={
                "MSFT": recommendation(symbol="MSFT", company="Microsoft", action="Add", score=86, target_confidence="high"),
                "AMZN": recommendation(symbol="AMZN", company="Amazon", action="Hold", score=80),
            },
            source_usefulness=[{"symbol": "MSFT", "label": "consistently_useful"}],
        )

        self.assertTrue(review["metadata"]["review_only"])
        self.assertEqual(review["metadata"]["holding_count"], 2)
        self.assertEqual(len(review["holdings"]), 2)
        self.assertIn(review["holdings"][0]["health_label"], subject.HEALTH_LABELS)


if __name__ == "__main__":
    unittest.main()
