#!/usr/bin/env python3
"""Tests for deterministic shadow recommendation runner helpers."""

from __future__ import annotations

import copy
import unittest

from stock_trading import shadow_recommendations as subject


def recommendation(
    *,
    symbol: str = "MSFT",
    action: str = "Add",
    score: float = 76.0,
    target_confidence: str = "medium",
    upside_pct: float = 20.0,
    safe_to_buy: bool = True,
    provider_gaps: list[str] | None = None,
    risks: list[str] | None = None,
    decision_mode: str = "long_term_buy_add",
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "company": f"{symbol} Corp",
        "report_date": "2026-06-01",
        "action": action,
        "score": score,
        "target_confidence": target_confidence,
        "upside_pct": upside_pct,
        "safe_to_buy": safe_to_buy,
        "provider_gaps": provider_gaps or [],
        "risks": risks or [],
        "decision_mode": decision_mode,
        "current_price": 100.0,
        "target_price": 120.0,
    }


def first_row(result: dict[str, object], symbol: str) -> dict[str, object]:
    rows = result["rows"]
    assert isinstance(rows, list)
    for row in rows:
        if row["symbol"] == symbol:
            return row
    raise AssertionError(f"Missing row for {symbol}")


class ShadowRecommendationTests(unittest.TestCase):
    def test_conservative_model_differs_from_official(self) -> None:
        official = [
            recommendation(
                symbol="MSFT",
                action="Buy",
                score=72,
                target_confidence="low",
                provider_gaps=["analyst target missing"],
                risks=["single source target"],
            )
        ]

        result = subject.run_shadow_recommendations(
            {"model_name": "conservative_long_term", "model_version": "v1"},
            official,
            report_date="2026-06-01",
        )
        row = result["rows"][0]

        self.assertEqual(row["official_action"], "Buy")
        self.assertEqual(row["shadow_action"], "shadow_watch")
        self.assertNotEqual(row["shadow_action"], row["official_action"])
        self.assertTrue(row["shadow_only"])
        self.assertTrue(row["does_not_change_official"])

    def test_aggressive_model_differs_from_official(self) -> None:
        official = [recommendation(symbol="NVDA", action="Watch", score=58, upside_pct=55, target_confidence="medium")]

        result = subject.run_shadow_recommendations(
            {"model_name": "aggressive_growth", "model_version": "v1"},
            official,
            report_date="2026-06-01",
        )
        row = result["rows"][0]

        self.assertEqual(row["official_action"], "Watch")
        self.assertEqual(row["shadow_action"], "shadow_add")
        self.assertGreater(row["shadow_score"], 80)

    def test_risk_skeptic_blocks_weak_idea(self) -> None:
        official = [
            recommendation(
                symbol="AMD",
                action="Add",
                score=80,
                target_confidence="low",
                safe_to_buy=False,
                provider_gaps=["current price stale", "companyfacts missing"],
                risks=["earnings risk", "valuation risk"],
            )
        ]

        result = subject.run_shadow_recommendations("risk_skeptic", official, report_date="2026-06-01")
        row = result["rows"][0]

        self.assertEqual(row["shadow_action"], "shadow_avoid")
        self.assertEqual(row["confidence"], "low")
        self.assertTrue(any("decision-safety" in note for note in row["risk_notes"]))

    def test_source_quality_model_penalizes_noisy_source(self) -> None:
        official = [recommendation(symbol="CRWD", action="Add", score=76, target_confidence="high")]

        noisy = subject.run_shadow_recommendations(
            "source_quality_weighted",
            official,
            source_context=[{"symbol": "CRWD", "usefulness_label": "noisy"}],
            report_date="2026-06-01",
        )
        clean = subject.run_shadow_recommendations(
            "source_quality_weighted",
            official,
            source_context=[{"symbol": "CRWD", "usefulness_label": "consistently_useful"}],
            report_date="2026-06-01",
        )

        noisy_row = noisy["rows"][0]
        clean_row = clean["rows"][0]
        self.assertLess(noisy_row["shadow_score"], clean_row["shadow_score"])
        self.assertEqual(noisy_row["shadow_action"], "shadow_hold")
        self.assertTrue(any("Source quality penalty" in note for note in noisy_row["risk_notes"]))

    def test_tactical_model_uses_tactical_context(self) -> None:
        official = [recommendation(symbol="META", action="Hold", score=50, upside_pct=12)]

        result = subject.run_shadow_recommendations(
            "tactical_momentum",
            official,
            tactical_context=[
                {
                    "symbol": "META",
                    "setup_label": "momentum",
                    "review_action": "tactical_buy_review",
                    "risk_zone_label": "favorable_review_zone",
                }
            ],
            report_date="2026-06-01",
            evaluation_horizon="5_trading_days",
        )
        row = result["rows"][0]

        self.assertEqual(row["shadow_action"], "shadow_tactical_review")
        self.assertEqual(row["horizon"], "5_trading_days")
        self.assertTrue(row["context_refs"]["tactical_context"])
        self.assertIn("Tactical setup context", row["rationale"])

    def test_earnings_model_uses_earnings_context(self) -> None:
        official = [recommendation(symbol="AVGO", action="Hold", score=48, upside_pct=10)]

        result = subject.run_shadow_recommendations(
            "earnings_event",
            official,
            earnings_context=[
                {
                    "symbol": "AVGO",
                    "reaction_label": "thesis_improved",
                    "recommended_review_action": "review_for_add_after_earnings",
                }
            ],
            report_date="2026-06-01",
            evaluation_horizon="20_trading_days",
        )
        row = result["rows"][0]

        self.assertEqual(row["shadow_action"], "shadow_earnings_review")
        self.assertTrue(row["context_refs"]["earnings_context"])
        self.assertIn("Earnings context", row["rationale"])

    def test_missing_optional_context_handled_gracefully(self) -> None:
        official = [recommendation(symbol="GOOGL", action="Hold", score=52)]

        result = subject.run_shadow_recommendations(
            "tactical_momentum",
            official,
            report_date="2026-06-01",
        )
        row = result["rows"][0]

        self.assertIn(row["shadow_action"], subject.SHADOW_ACTIONS)
        self.assertFalse(row["context_refs"]["tactical_context"])
        self.assertTrue(result["review_only"])

    def test_shadow_output_cannot_overwrite_official_fields(self) -> None:
        official = [recommendation(symbol="SNOW", action="Add", score=70)]

        result = subject.run_shadow_recommendations("conservative_long_term", official, report_date="2026-06-01")
        row = result["rows"][0]

        self.assertNotIn("action", row)
        self.assertNotIn("score", row)
        self.assertEqual(row["official_action"], "Add")
        self.assertIn("shadow_action", row)
        self.assertIn("shadow_score", row)
        self.assertTrue(row["prediction_record"]["shadow_only"])

    def test_no_input_mutation(self) -> None:
        official = [
            recommendation(symbol="MSFT", action="Add", score=77),
            recommendation(symbol="NVDA", action="Watch", score=61, upside_pct=50),
        ]
        source_context = [{"symbol": "NVDA", "usefulness_label": "noisy"}]
        before_official = copy.deepcopy(official)
        before_source = copy.deepcopy(source_context)

        subject.run_shadow_recommendations(
            "source_quality_weighted",
            official,
            source_context=source_context,
            report_date="2026-06-01",
        )

        self.assertEqual(official, before_official)
        self.assertEqual(source_context, before_source)

    def test_report_context_input_and_suite_output_are_shadow_only(self) -> None:
        context = {
            "recommendations": [
                recommendation(symbol="MSFT", action="Add", score=82, target_confidence="high"),
                recommendation(symbol="AMD", action="Watch", score=63, upside_pct=40),
            ]
        }

        result = subject.run_shadow_model_suite(
            ["conservative_long_term", "aggressive_growth"],
            context,
            report_date="2026-06-01",
        )

        self.assertEqual(result["run_count"], 2)
        self.assertTrue(result["shadow_only"])
        self.assertEqual(len(result["runs"][0]["rows"]), 2)
        self.assertTrue(all(row["review_only"] for run in result["runs"] for row in run["rows"]))


if __name__ == "__main__":
    unittest.main()
