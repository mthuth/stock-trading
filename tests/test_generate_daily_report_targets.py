#!/usr/bin/env python3
"""Regression tests for analyst-target source capture."""

from __future__ import annotations

from datetime import date, timedelta
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


def price_history(
    *,
    days: int = 220,
    start: float = 80.0,
    step: float = 0.12,
    end_date: date = date(2026, 5, 28),
    volatility_pattern: list[float] | None = None,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    price = start
    for index in range(days):
        if volatility_pattern:
            price *= 1 + volatility_pattern[index % len(volatility_pattern)]
        else:
            price += step
        rows.append(
            {
                "date": str(end_date - timedelta(days=days - index - 1)),
                "high": round(price * 1.01, 4),
                "low": round(price * 0.99, 4),
                "close": round(price, 4),
                "provider": "fixture",
                "volume": 1_000_000,
            }
        )
    return rows


def drilldown_for(
    item: subject.ResearchInput,
    target_rows: list[dict[str, object]],
    provider_gaps: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    blended, _ = subject.blended_target_rows(
        target_rows,
        42,
        {
            "blended_target_model": {
                "long_term_weights": {"analyst": 0.45, "fundamental": 0.45, "technical": 0.10},
                "confidence_rules": {
                    "technical_target_needed_for_high": True,
                    "wide_range_downgrades_confidence": True,
                },
            }
        },
        {item.symbol: item},
        provider_gaps or [],
    )
    target = blended.get(item.symbol)
    return subject.target_drilldowns_by_symbol(
        [{"input": item, "target": target}],
        target_rows,
    )[item.symbol]


class GenerateDailyReportTargetTests(unittest.TestCase):
    def test_high_confidence_requires_multiple_fresh_independent_sources(self) -> None:
        item = research_input("NVDA")
        target_rows = [
            target_row("NVDA", "analyst", "Analyst consensus", 120.0, source_type="data_provider"),
            target_row("NVDA", "fundamental", "Internal fundamental model", 124.0),
            target_row("NVDA", "technical", "Internal technical model", 112.0),
        ]

        blended, _ = subject.blended_target_rows(
            target_rows,
            42,
            {
                "blended_target_model": {
                    "long_term_weights": {"analyst": 0.45, "fundamental": 0.45, "technical": 0.10},
                    "confidence_rules": {"technical_target_needed_for_high": True},
                }
            },
            {"NVDA": item},
        )

        self.assertEqual(blended["NVDA"].confidence, "high")
        self.assertIn("multi_source_fresh_breadth", blended["NVDA"].confidence_reasons)

    def test_medium_confidence_allows_one_strong_source_with_supporting_context(self) -> None:
        item = research_input("MSFT")
        item.estimate_source = "SEC companyfacts + analyst estimate"
        item.revenue_estimate = "forward revenue growth available"

        blended, _ = subject.blended_target_rows(
            [target_row("MSFT", "analyst", "Analyst consensus", 130.0, confidence="high")],
            42,
            {"blended_target_model": {"long_term_weights": {"analyst": 1.0}}},
            {"MSFT": item},
        )

        self.assertEqual(blended["MSFT"].confidence, "medium")
        self.assertIn("strong_single_source_with_support", blended["MSFT"].confidence_reasons)

    def test_single_source_without_support_stays_low_confidence(self) -> None:
        item = research_input("AMD")

        blended, _ = subject.blended_target_rows(
            [target_row("AMD", "analyst", "Analyst consensus", 130.0, confidence="medium")],
            42,
            {"blended_target_model": {"long_term_weights": {"analyst": 1.0}}},
            {"AMD": item},
        )

        self.assertEqual(blended["AMD"].confidence, "low")
        self.assertIn("single_source_target", blended["AMD"].confidence_reasons)

    def test_missing_current_price_confidence_needs_review(self) -> None:
        item = research_input("ALAB")
        item.current_price = 0

        self.assertEqual(subject.target_confidence_text(item, None), "Needs Review")

    def test_severely_stale_target_needs_review(self) -> None:
        item = research_input("AMZN")

        blended, _ = subject.blended_target_rows(
            [
                target_row("AMZN", "analyst", "Analyst consensus", 140.0, freshness_days=200),
                target_row("AMZN", "fundamental", "Internal fundamental model", 135.0),
            ],
            42,
            {"blended_target_model": {"long_term_weights": {"analyst": 0.5, "fundamental": 0.5}}},
            {"AMZN": item},
        )

        self.assertEqual(blended["AMZN"].confidence, "needs_review")
        self.assertIn("stale_target", blended["AMZN"].confidence_reasons)

    def test_speculative_watchlist_caps_high_confidence(self) -> None:
        item = research_input("SOUN")
        item.sleeve = "speculative_ai"
        item.trade_type = "speculative_ai"
        item.category = "Speculative AI"
        target_rows = [
            target_row("SOUN", "analyst", "Analyst consensus", 8.0, source_type="data_provider"),
            target_row("SOUN", "fundamental", "Internal fundamental model", 7.5),
            target_row("SOUN", "technical", "Internal technical model", 7.0),
        ]

        blended, _ = subject.blended_target_rows(
            target_rows,
            42,
            {
                "blended_target_model": {
                    "long_term_weights": {"analyst": 0.45, "fundamental": 0.45, "technical": 0.10},
                    "confidence_rules": {"technical_target_needed_for_high": True},
                }
            },
            {"SOUN": item},
        )

        self.assertEqual(blended["SOUN"].confidence, "medium")
        self.assertIn("speculative_cap", blended["SOUN"].confidence_reasons)

    def test_provider_gap_affecting_target_confidence_needs_review(self) -> None:
        item = research_input("META")
        target_rows = [
            target_row("META", "analyst", "Analyst consensus", 120.0, source_type="data_provider"),
            target_row("META", "fundamental", "Internal fundamental model", 124.0),
            target_row("META", "technical", "Internal technical model", 112.0),
        ]

        blended, _ = subject.blended_target_rows(
            target_rows,
            42,
            {
                "blended_target_model": {
                    "long_term_weights": {"analyst": 0.45, "fundamental": 0.45, "technical": 0.10},
                    "confidence_rules": {"technical_target_needed_for_high": True},
                }
            },
            {"META": item},
            [
                {
                    "symbol": "META",
                    "provider": "Financial Modeling Prep",
                    "field_name": "analyst_target",
                    "status": "blocked",
                    "message": "403 provider plan blocks target refresh",
                }
            ],
        )

        self.assertEqual(blended["META"].confidence, "needs_review")
        self.assertIn("provider_gap_affects_target", blended["META"].confidence_reasons)
        self.assertIn("provider gap affects target confidence", blended["META"].blend_status)

    def test_target_blending_weights_do_not_change(self) -> None:
        item = research_input("AVGO")

        blended, rows = subject.blended_target_rows(
            [
                target_row("AVGO", "analyst", "Analyst consensus", 110.0),
                target_row("AVGO", "fundamental", "Internal fundamental model", 130.0),
                target_row("AVGO", "technical", "Internal technical model", 150.0),
            ],
            42,
            {"blended_target_model": {"long_term_weights": {"analyst": 0.45, "fundamental": 0.45, "technical": 0.10}}},
            {"AVGO": item},
        )

        self.assertEqual(blended["AVGO"].target_price, 123.0)
        self.assertIn('"analyst": 0.45', rows[0]["weights_json"])
        self.assertIn('"fundamental": 0.45', rows[0]["weights_json"])
        self.assertIn('"technical": 0.1', rows[0]["weights_json"])

    def test_recommendation_labels_remain_controlled(self) -> None:
        item = research_input("NVDA")
        allowed = {"Strong Buy", "Buy", "Add", "Hold", "Watch", "Trim", "Avoid"}

        labels = {
            subject.action_for(item, 82, 5, {}),
            subject.action_for(item, 73, 5, {}),
            subject.action_for(item, 50, 5, {}),
            subject.action_for(item, 82, 11, {}),
        }

        self.assertLessEqual(labels, allowed)

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

    def test_technical_target_v2_healthy_price_history_is_reviewable(self) -> None:
        item = research_input("NVDA")
        item.current_price = 106.4

        row = subject.technical_target_row(
            item,
            42,
            "2026-05-28",
            {
                "windows": {
                    "short_trend_days": 20,
                    "medium_trend_days": 50,
                    "long_trend_days": 200,
                    "support_lookback_days": 60,
                    "resistance_lookback_days": 60,
                },
                "buffers": {
                    "breakout_buffer_pct": 0.03,
                    "stop_review_buffer_below_support_pct": 0.05,
                },
                "quality_thresholds": {
                    "minimum_history_days": 20,
                    "stale_history_days": 5,
                    "volatile_daily_move_pct": 0.04,
                },
            },
            {"NVDA": price_history()},
        )

        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["target_type"], "technical")
        self.assertEqual(row["confidence"], "medium")
        self.assertEqual(row["freshness_days"], 0)
        self.assertGreater(row["target_high"], row["target_low"])
        self.assertIn("MA20", row["notes"])
        self.assertIn("MA50", row["notes"])
        self.assertIn("MA200", row["notes"])
        self.assertIn("support", row["notes"])
        self.assertIn("resistance", row["notes"])
        self.assertIn("breakout buffer", row["notes"])
        self.assertIn("review buffer", row["notes"])

    def test_technical_target_v2_missing_price_history_returns_no_source(self) -> None:
        item = research_input("MSFT")

        row = subject.technical_target_row(item, 42, "2026-05-28", {}, {"MSFT": []})

        self.assertIsNone(row)

    def test_technical_target_v2_stale_price_history_lowers_confidence(self) -> None:
        item = research_input("AMZN")
        item.current_price = 106.4

        row = subject.technical_target_row(
            item,
            42,
            "2026-05-28",
            {"quality_thresholds": {"minimum_history_days": 20, "stale_history_days": 5}},
            {"AMZN": price_history(end_date=date(2026, 5, 15))},
        )

        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["confidence"], "low")
        self.assertEqual(row["freshness_days"], 13)
        self.assertIn("stale price history", row["notes"])

    def test_technical_target_v2_volatile_price_history_lowers_confidence(self) -> None:
        item = research_input("NET")
        history = price_history(
            start=100.0,
            step=0,
            volatility_pattern=[0.07, -0.06, 0.08, -0.07],
        )
        item.current_price = float(history[-1]["close"])

        row = subject.technical_target_row(
            item,
            42,
            "2026-05-28",
            {"quality_thresholds": {"volatile_daily_move_pct": 0.04}},
            {"NET": history},
        )

        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["confidence"], "low")
        self.assertIn("volatile tape", row["notes"])

    def test_technical_target_v2_clear_uptrend_and_mixed_trend_are_distinct(self) -> None:
        uptrend_item = research_input("AVGO")
        uptrend_item.current_price = 106.4
        mixed_item = research_input("META")
        mixed_history = price_history(days=220, start=100.0, step=0.0)
        mixed_item.current_price = float(mixed_history[-1]["close"])

        uptrend = subject.technical_target_row(
            uptrend_item,
            42,
            "2026-05-28",
            {},
            {"AVGO": price_history()},
        )
        mixed = subject.technical_target_row(
            mixed_item,
            42,
            "2026-05-28",
            {},
            {"META": mixed_history},
        )

        self.assertIsNotNone(uptrend)
        self.assertIsNotNone(mixed)
        assert uptrend is not None and mixed is not None
        self.assertIn("trend clear uptrend", uptrend["notes"])
        self.assertIn("trend mixed", mixed["notes"])
        self.assertGreater(mixed["target_high"], mixed["target_low"])
        self.assertIn("target range", mixed["notes"])

    def test_technical_target_v2_long_term_blend_keeps_configured_cap(self) -> None:
        item = research_input("NVDA")
        target_rows = [
            target_row("NVDA", "analyst", "Analyst", 100.0),
            target_row("NVDA", "fundamental", "Model", 100.0),
            target_row("NVDA", "technical", "Internal technical model", 200.0),
        ]

        blended, db_rows = subject.blended_target_rows(
            target_rows,
            42,
            {
                "blended_target_model": {
                    "long_term_weights": {"analyst": 0.45, "fundamental": 0.45, "technical": 0.10},
                    "short_term_weights": {"analyst": 0.20, "fundamental": 0.20, "technical": 0.60},
                }
            },
            {"NVDA": item},
        )

        self.assertEqual(blended["NVDA"].target_price, 110.0)
        self.assertIn('"technical": 0.1', db_rows[0]["weights_json"])

    def test_target_drilldown_can_show_technical_target_assumptions(self) -> None:
        item = research_input("NVDA")
        technical = target_row(
            "NVDA",
            "technical",
            "Internal technical model",
            112.0,
            target_low=98.0,
            target_high=118.0,
            confidence="medium",
            notes="inputs: current 100.00; MA20 104.00; support 98.00; resistance 114.00; breakout buffer 3.0%; review buffer 5.0%.",
        )

        drilldown = drilldown_for(item, [technical])

        source = drilldown["sources"][0]
        self.assertEqual(source["target_type"], "technical")
        self.assertIn("MA20", source["notes"])
        self.assertIn("support", source["notes"])
        self.assertIn("resistance", source["notes"])


if __name__ == "__main__":
    unittest.main()
