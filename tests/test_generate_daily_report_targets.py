#!/usr/bin/env python3
"""Regression tests for analyst-target source capture."""

from __future__ import annotations

import unittest
from unittest.mock import patch


from scripts import generate_daily_report as subject


def research_input(symbol: str, target_price: float = 0, target_source: str = "") -> subject.ResearchInput:
    return subject.ResearchInput(
        symbol=symbol,
        company=f"{symbol} Inc.",
        category="AI",
        sleeve="long_term",
        trade_type="long_term",
        current_price=100.0,
        target_price=target_price,
        quality_score=80.0,
        momentum_score=70.0,
        catalyst_score=75.0,
        risk_score=80.0,
        confidence="medium",
        notes="",
        price_source="test",
        target_source=target_source,
        estimate_source="",
        sentiment_source="",
        eps_estimate="",
        revenue_estimate="",
        news_sentiment="",
        provider_notes="",
    )


class GenerateDailyReportTargetTests(unittest.TestCase):
    def test_manual_analyst_targets_create_source_rows(self) -> None:
        item = research_input("SNOW")
        manual_targets = {
            "SNOW": [
                {
                    "source_name": "Manual analyst target",
                    "target_price": 250.0,
                    "target_low": 220.0,
                    "target_high": 275.0,
                    "as_of_date": "2026-05-28",
                    "confidence": "low",
                    "provider_endpoint": "manual_analyst_targets.csv",
                    "notes": "Broker target captured manually.",
                }
            ]
        }

        with (
            patch.object(subject, "load_manual_analyst_targets", return_value=manual_targets),
            patch.object(subject, "latest_sec_facts_by_symbol", return_value={}),
            patch.object(subject, "latest_price_history_by_symbol", return_value={}),
            patch.object(subject, "fundamental_target_row", return_value=None),
            patch.object(subject, "technical_target_row", return_value=None),
        ):
            rows = subject.target_source_rows([item], 42, "2026-05-28", {})

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["symbol"], "SNOW")
        self.assertEqual(rows[0]["target_type"], "analyst")
        self.assertEqual(rows[0]["source_type"], "manual_analyst_target")
        self.assertEqual(rows[0]["target_price"], 250.0)
        self.assertEqual(rows[0]["upside_pct"], 150.0)

    def test_fmp_and_manual_targets_both_contribute_analyst_breadth(self) -> None:
        item = research_input("NVDA", target_price=140.0, target_source="FMP")
        manual_targets = {
            "NVDA": [
                {
                    "source_name": "Benzinga analyst ratings",
                    "target_price": 150.0,
                    "confidence": "medium",
                    "provider_endpoint": "Benzinga calendar ratings API",
                }
            ]
        }

        with (
            patch.object(subject, "load_manual_analyst_targets", return_value=manual_targets),
            patch.object(subject, "latest_sec_facts_by_symbol", return_value={}),
            patch.object(subject, "latest_price_history_by_symbol", return_value={}),
            patch.object(subject, "fundamental_target_row", return_value=None),
            patch.object(subject, "technical_target_row", return_value=None),
        ):
            rows = subject.target_source_rows([item], 42, "2026-05-28", {})

        counts = subject.target_counts_by_symbol(rows)
        self.assertEqual(counts["NVDA"]["analyst"], 2)
        self.assertEqual(counts["NVDA"]["all"], 2)
        self.assertEqual([row["source_name"] for row in rows], ["Financial Modeling Prep", "Benzinga analyst ratings"])

    def test_missing_price_data_status_requires_price(self) -> None:
        item = research_input("ALAB")
        item.current_price = 0

        self.assertEqual(subject.data_status_for_target(item, None), "Needs price")

    def test_wide_target_range_downgrades_blended_confidence(self) -> None:
        item = research_input("NVDA")
        target_rows = [
            {
                "symbol": "NVDA",
                "target_type": "analyst",
                "source_name": "Analyst",
                "target_price": 120.0,
                "target_low": 60.0,
                "target_high": 220.0,
                "current_price": 100.0,
            },
            {
                "symbol": "NVDA",
                "target_type": "fundamental",
                "source_name": "Model",
                "target_price": 140.0,
                "target_low": 90.0,
                "target_high": 200.0,
                "current_price": 100.0,
            },
        ]

        blended, _ = subject.blended_target_rows(
            target_rows,
            42,
            {"blended_target_model": {"long_term_weights": {"analyst": 0.5, "fundamental": 0.5}}},
            {"NVDA": item},
        )

        self.assertEqual(blended["NVDA"].confidence, "low")
        self.assertIn("wide target range", blended["NVDA"].blend_status)

    def test_stale_price_source_downgrades_blended_confidence(self) -> None:
        item = research_input("MSFT")
        item.price_source = "manual/stale"
        target_rows = [
            {
                "symbol": "MSFT",
                "target_type": "analyst",
                "source_name": "Analyst",
                "target_price": 120.0,
                "current_price": 100.0,
            },
            {
                "symbol": "MSFT",
                "target_type": "fundamental",
                "source_name": "Model",
                "target_price": 125.0,
                "current_price": 100.0,
            },
        ]

        blended, _ = subject.blended_target_rows(
            target_rows,
            42,
            {"blended_target_model": {"long_term_weights": {"analyst": 0.5, "fundamental": 0.5}}},
            {"MSFT": item},
        )

        self.assertEqual(blended["MSFT"].confidence, "low")
        self.assertIn("stale price", blended["MSFT"].blend_status)


if __name__ == "__main__":
    unittest.main()
