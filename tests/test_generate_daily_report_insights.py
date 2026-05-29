#!/usr/bin/env python3
"""Regression tests for V1.6 transparent insight scoring."""

from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import engine_common  # noqa: E402
import generate_daily_report as subject  # noqa: E402


def research_input(symbol: str, sleeve: str = "long_term", current_price: float = 100.0) -> subject.ResearchInput:
    trade_type = "weekly_swing" if sleeve == "short_term" else sleeve
    return subject.ResearchInput(
        symbol=symbol,
        company=f"{symbol} Corp",
        category="AI",
        sleeve=sleeve,
        trade_type=trade_type,
        current_price=current_price,
        target_price=130.0 if current_price > 0 else 0.0,
        quality_score=80.0,
        momentum_score=75.0,
        catalyst_score=75.0,
        risk_score=75.0,
        confidence="Medium",
        notes="test note",
        price_source="test",
        target_source="FMP" if current_price > 0 else "Needs paid target provider",
        estimate_source="",
        sentiment_source="",
        eps_estimate="",
        revenue_estimate="",
        news_sentiment="",
        provider_notes="",
    )


def blended_target(symbol: str = "NVDA") -> subject.BlendedTarget:
    return subject.BlendedTarget(
        symbol=symbol,
        target_price=130.0,
        target_low=115.0,
        target_high=140.0,
        current_price=100.0,
        upside_pct=30.0,
        confidence="medium",
        source_count=3,
        blend_status="Analyst + fundamental + technical",
        sources_label="test",
        notes="test target",
    )


def breakdown(total: float = 70.0) -> subject.ScoreBreakdown:
    return subject.ScoreBreakdown(
        total=total,
        upside=10.0,
        quality=20.0,
        momentum=15.0,
        catalyst=15.0,
        risk=10.0,
        owned_penalty=0.0,
        speculative_penalty=0.0,
        model="Long-term",
    )


def rising_history(days: int = 60) -> list[dict[str, float]]:
    return [
        {"date": f"2026-04-{(index % 28) + 1:02d}", "high": 90 + index, "low": 88 + index, "close": 90 + index, "volume": 1000, "provider": "test"}
        for index in range(days)
    ]


class GenerateDailyReportInsightTests(unittest.TestCase):
    def test_fresh_corroborated_evidence_adds_capped_positive_delta(self) -> None:
        item = research_input("NVDA")
        evidence = {
            "NVDA": [
                {
                    "symbol": "NVDA",
                    "evidence_type": "sec_filing",
                    "source_name": "SEC EDGAR submissions API",
                    "source_type": "sec filing",
                    "source_timestamp": "2026-05-28",
                    "title": "NVDA reports growth and raised guidance",
                    "summary": "Revenue growth and margin strength.",
                    "confidence": "high",
                    "corroboration_status": "corroborated",
                }
            ]
        }

        insight = subject.compute_insight_signal(
            item,
            breakdown(),
            blended_target(),
            {"NVDA": rising_history()},
            evidence,
            {"NVDA": {"analyst": 2, "all": 3}},
            {},
        )

        self.assertGreater(insight.evidence_delta, 0)
        self.assertLessEqual(insight.evidence_delta, 4)
        self.assertGreater(insight.final_score, insight.base_score)

    def test_risk_evidence_reduces_evidence_delta(self) -> None:
        item = research_input("CRWD")
        evidence = {
            "CRWD": [
                {
                    "symbol": "CRWD",
                    "evidence_type": "company_news",
                    "source_name": "Finnhub company news",
                    "source_type": "news",
                    "source_timestamp": "2026-05-28",
                    "title": "CRWD downgrade cites weak demand and valuation risk",
                    "summary": "Analyst downgrade on competition.",
                    "confidence": "medium",
                    "corroboration_status": "",
                }
            ]
        }

        insight = subject.compute_insight_signal(
            item,
            breakdown(),
            blended_target("CRWD"),
            {"CRWD": rising_history()},
            evidence,
            {"CRWD": {"analyst": 1, "all": 3}},
            {},
        )

        self.assertLess(insight.evidence_delta, 0)

    def test_missing_price_and_target_breadth_apply_visible_gap_penalty(self) -> None:
        item = research_input("SNOW", current_price=0.0)

        insight = subject.compute_insight_signal(
            item,
            breakdown(),
            None,
            {},
            {},
            {"SNOW": {"analyst": 0, "all": 0}},
            {},
        )

        self.assertLess(insight.data_gap_delta, 0)
        self.assertTrue(any(gap["gap"] == "Missing current price" for gap in insight.data_gaps))
        self.assertTrue(any(gap["gap"] == "No analyst target breadth" for gap in insight.data_gaps))

    def test_short_term_names_weight_price_trend_more_than_long_term(self) -> None:
        long_item = research_input("MSFT", sleeve="long_term")
        short_item = research_input("NET", sleeve="short_term")

        long_insight = subject.compute_insight_signal(
            long_item,
            breakdown(),
            blended_target("MSFT"),
            {"MSFT": rising_history()},
            {},
            {"MSFT": {"analyst": 1, "all": 3}},
            {},
        )
        short_insight = subject.compute_insight_signal(
            short_item,
            breakdown(),
            blended_target("NET"),
            {"NET": rising_history()},
            {},
            {"NET": {"analyst": 1, "all": 3}},
            {},
        )

        self.assertGreater(abs(short_insight.trend_delta), abs(long_insight.trend_delta))

    def test_speculative_ai_names_remain_watchlist_only(self) -> None:
        item = research_input("SOUN", sleeve="speculative_ai")

        action = subject.action_for(item, 95.0, 1.0, {"speculative_ai": {"allow_buy_recommendations": False}})

        self.assertEqual(action, "Watch")

    def test_score_signal_rows_are_persisted(self) -> None:
        item = research_input("NVDA")
        insight = subject.compute_insight_signal(
            item,
            breakdown(),
            blended_target(),
            {"NVDA": rising_history()},
            {},
            {"NVDA": {"analyst": 2, "all": 3}},
            {},
        )
        ranked = [{"input": item, "insight": insight}]
        rows = subject.score_signal_storage_rows(101, "2026-05-28", ranked)

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            db_file = temp_path / "stock_trading.sqlite"
            with (
                patch.object(engine_common, "DATA_DIR", temp_path),
                patch.object(engine_common, "DB_FILE", db_file),
            ):
                inserted = engine_common.record_score_signals(rows)
                conn = sqlite3.connect(db_file)
                count = conn.execute("SELECT COUNT(*) FROM score_signals").fetchone()[0]
                conn.close()

        self.assertEqual(inserted, len(rows))
        self.assertEqual(count, len(rows))

    def test_report_section_labels_are_present_in_template(self) -> None:
        source = Path(subject.__file__).read_text()

        for label in ("Insight Drivers", "Score Movement", "Trend Insights", "Ranked Data Gap Queue"):
            self.assertIn(label, source)


if __name__ == "__main__":
    unittest.main()
