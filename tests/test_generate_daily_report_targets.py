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


def target_row(
    symbol: str,
    target_type: str,
    source_name: str,
    target_price: float,
    *,
    source_type: str = "model",
    current_price: float = 100.0,
    target_low: float | None = None,
    target_high: float | None = None,
    freshness_days: int = 0,
    confidence: str = "medium",
    notes: str = "",
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "target_type": target_type,
        "source_name": source_name,
        "source_type": source_type,
        "target_price": target_price,
        "target_low": target_low,
        "target_high": target_high,
        "current_price": current_price,
        "freshness_days": freshness_days,
        "confidence": confidence,
        "as_of_date": "2026-05-28",
        "notes": notes,
    }


def drilldown_for(
    item: subject.ResearchInput,
    target_rows: list[dict[str, object]],
) -> dict[str, object]:
    blended, _ = subject.blended_target_rows(
        target_rows,
        42,
        {"blended_target_model": {"long_term_weights": {"analyst": 0.45, "fundamental": 0.45, "technical": 0.10}}},
        {item.symbol: item},
    )
    target = blended.get(item.symbol)
    return subject.target_drilldowns_by_symbol(
        [{"input": item, "target": target}],
        target_rows,
    )[item.symbol]


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

    def test_target_drilldown_labels_one_source_target(self) -> None:
        item = research_input("NVDA")
        drilldown = drilldown_for(
            item,
            [target_row("NVDA", "analyst", "Financial Modeling Prep", 140.0, source_type="data_provider")],
        )

        self.assertEqual(drilldown["blend_label"], "single-source target")
        self.assertEqual(drilldown["confidence"], "low")
        self.assertIn("missing input: fundamental", drilldown["labels"])
        self.assertIn("missing input: technical", drilldown["labels"])
        self.assertEqual(drilldown["sources"][0]["target_type"], "analyst")

    def test_target_drilldown_labels_two_source_partial_blend(self) -> None:
        item = research_input("MSFT")
        drilldown = drilldown_for(
            item,
            [
                target_row("MSFT", "analyst", "Analyst consensus", 120.0, source_type="data_provider"),
                target_row("MSFT", "fundamental", "Internal fundamental model", 125.0),
            ],
        )

        self.assertEqual(drilldown["blend_label"], "partial blend")
        self.assertEqual(drilldown["confidence"], "medium")
        self.assertIn("missing input: technical", drilldown["labels"])
        self.assertEqual(drilldown["source_count"], 2)

    def test_target_drilldown_labels_stale_target_source(self) -> None:
        item = research_input("AMZN")
        drilldown = drilldown_for(
            item,
            [
                target_row("AMZN", "analyst", "Analyst consensus", 145.0, freshness_days=120),
                target_row("AMZN", "fundamental", "Internal fundamental model", 135.0),
            ],
        )

        self.assertTrue(drilldown["stale_target"])
        self.assertIn("stale target", drilldown["labels"])
        self.assertEqual(drilldown["sources"][0]["freshness"], "Stale (120 days)")

    def test_target_drilldown_labels_missing_target_input(self) -> None:
        item = research_input("ALAB")
        drilldowns = subject.target_drilldowns_by_symbol(
            [{"input": item, "target": None}],
            [],
        )

        drilldown = drilldowns["ALAB"]
        self.assertEqual(drilldown["blend_label"], "missing input")
        self.assertEqual(drilldown["target_price_text"], "Needs target")
        self.assertIn("missing input: analyst", drilldown["labels"])
        self.assertIn("missing input: fundamental", drilldown["labels"])
        self.assertIn("missing input: technical", drilldown["labels"])

    def test_target_drilldown_labels_wide_range(self) -> None:
        item = research_input("META")
        drilldown = drilldown_for(
            item,
            [
                target_row("META", "analyst", "Analyst consensus", 130.0, target_low=80.0, target_high=170.0),
                target_row("META", "fundamental", "Internal fundamental model", 128.0),
            ],
        )

        self.assertTrue(drilldown["wide_range"])
        self.assertIn("wide range", drilldown["labels"])

    def test_target_drilldown_preserves_manual_target_note(self) -> None:
        item = research_input("SNOW")
        drilldown = drilldown_for(
            item,
            [
                target_row(
                    "SNOW",
                    "analyst",
                    "Manual analyst target",
                    250.0,
                    source_type="manual_analyst_target",
                    notes="Broker target captured manually.",
                )
            ],
        )

        source = drilldown["sources"][0]
        self.assertEqual(source["target_type"], "manual")
        self.assertEqual(source["source_type"], "manual_analyst_target")
        self.assertEqual(source["notes"], "Broker target captured manually.")


if __name__ == "__main__":
    unittest.main()
