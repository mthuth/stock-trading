#!/usr/bin/env python3
"""Tests for review-only recommendation backtest summaries."""

from __future__ import annotations

import copy
import unittest
from datetime import date, timedelta

from stock_trading import recommendation_backtests as subject


def recommendation(
    *,
    symbol: str = "MSFT",
    report_date: str = "2026-05-01",
    action: str = "Add",
    current_price: float = 100.0,
    target_price: float = 140.0,
    model_version: str = "model-v1",
    decision_mode: str = "long_term_buy_add",
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "report_date": report_date,
        "action": action,
        "score": 82.0,
        "current_price": current_price,
        "target_price": target_price,
        "model_version": model_version,
        "decision_mode": decision_mode,
    }


def price_rows(symbol: str, closes: list[float], start_day: int = 1) -> list[dict[str, object]]:
    return [
        {
            "symbol": symbol,
            "price_date": (date(2026, 5, start_day) + timedelta(days=index)).isoformat(),
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "adjusted_close": close,
            "volume": 1000 + index,
            "provider": "Unit",
        }
        for index, close in enumerate(closes)
    ]


class RecommendationBacktestTests(unittest.TestCase):
    def test_stored_recommendation_positive_outcome(self) -> None:
        recs = [recommendation()]
        rows = subject.recommendation_backtest_rows(
            recs,
            {"MSFT": price_rows("MSFT", [100, 104, 108])},
            windows=("1_day",),
        )

        self.assertEqual(rows[0]["symbol"], "MSFT")
        self.assertEqual(rows[0]["return_pct"], 4.0)
        self.assertEqual(rows[0]["outcome_status"], "positive_follow_through")
        self.assertTrue(rows[0]["hit"])
        self.assertTrue(rows[0]["review_only"])

    def test_stored_recommendation_negative_outcome(self) -> None:
        rows = subject.recommendation_backtest_rows(
            [recommendation(symbol="NVDA")],
            {"NVDA": price_rows("NVDA", [100, 96, 92])},
            windows=("1_day",),
        )

        self.assertEqual(rows[0]["return_pct"], -4.0)
        self.assertEqual(rows[0]["outcome_status"], "negative_follow_through")
        self.assertFalse(rows[0]["hit"])

    def test_missing_price_history_warns_and_counts_not_enough_history(self) -> None:
        review = subject.recommendation_backtest(
            [recommendation(symbol="AMD")],
            {},
            windows=("5_trading_days",),
            minimum_sample_size=2,
        )

        self.assertEqual(review["summary"]["row_count"], 1)
        self.assertEqual(review["summary"]["not_enough_history_count"], 1)
        self.assertIsNone(review["summary"]["average_return"])
        self.assertTrue(any("not have enough later stored price history" in warning for warning in review["summary"]["warnings"]))

    def test_missing_benchmark_warning(self) -> None:
        review = subject.recommendation_backtest(
            [recommendation()],
            {"MSFT": price_rows("MSFT", [100, 104])},
            benchmark_price_history={"QQQ": []},
            windows=("1_day",),
        )

        self.assertIsNone(review["rows"][0]["benchmark_return_pct"])
        self.assertTrue(any("Benchmark data is missing" in warning for warning in review["summary"]["warnings"]))

    def test_benchmark_excess_return(self) -> None:
        review = subject.recommendation_backtest(
            [recommendation()],
            {"MSFT": price_rows("MSFT", [100, 106])},
            benchmark_price_history={"BENCHMARK": price_rows("BENCHMARK", [100, 102])},
            windows=("1_day",),
            minimum_sample_size=1,
        )

        self.assertEqual(review["rows"][0]["benchmark_return_pct"], 2.0)
        self.assertEqual(review["rows"][0]["excess_return_pct"], 4.0)
        self.assertEqual(review["summary"]["average_excess_return_vs_benchmark"], 4.0)

    def test_multiple_windows(self) -> None:
        rows = subject.recommendation_backtest_rows(
            [recommendation()],
            {"MSFT": price_rows("MSFT", [100, 101, 102, 103, 104, 105, 106])},
            windows=("1_day", "5_trading_days"),
        )

        self.assertEqual([row["window"] for row in rows], ["1_day", "5_trading_days"])
        self.assertEqual(rows[0]["return_pct"], 1.0)
        self.assertEqual(rows[1]["return_pct"], 5.0)

    def test_grouped_by_action(self) -> None:
        rows = subject.recommendation_backtest_rows(
            [
                recommendation(symbol="MSFT", action="Add"),
                recommendation(symbol="NVDA", action="Watch"),
            ],
            {
                "MSFT": price_rows("MSFT", [100, 103]),
                "NVDA": price_rows("NVDA", [100, 100.2]),
            },
            windows=("1_day",),
        )
        summary = subject.summarize_recommendation_backtest(rows, recommendations=[], minimum_sample_size=1)

        self.assertEqual(summary["hit_rate_by_action"]["Add"]["hit_rate"], 100.0)
        self.assertEqual(summary["hit_rate_by_action"]["Watch"]["hit_rate"], 100.0)

    def test_grouped_by_model_version(self) -> None:
        rows = subject.recommendation_backtest_rows(
            [
                recommendation(symbol="MSFT", model_version="model-v1"),
                recommendation(symbol="NVDA", model_version="model-v2"),
            ],
            {
                "MSFT": price_rows("MSFT", [100, 103]),
                "NVDA": price_rows("NVDA", [100, 97]),
            },
            windows=("1_day",),
        )
        summary = subject.summarize_recommendation_backtest(rows, recommendations=[], minimum_sample_size=1)

        self.assertEqual(summary["hit_rate_by_model_version"]["model-v1"]["hit_rate"], 100.0)
        self.assertEqual(summary["hit_rate_by_model_version"]["model-v2"]["hit_rate"], 0.0)

    def test_insufficient_sample_size_warning(self) -> None:
        review = subject.recommendation_backtest(
            [recommendation()],
            {"MSFT": price_rows("MSFT", [100, 103])},
            windows=("1_day",),
            minimum_sample_size=5,
        )

        self.assertTrue(any("Insufficient sample size" in warning for warning in review["summary"]["warnings"]))

    def test_missing_model_version_warning(self) -> None:
        rec = recommendation()
        rec.pop("model_version")

        review = subject.recommendation_backtest(
            [rec],
            {"MSFT": price_rows("MSFT", [100, 103])},
            windows=("1_day",),
            minimum_sample_size=1,
        )

        self.assertTrue(any("missing model_version" in warning for warning in review["summary"]["warnings"]))
        self.assertIn("missing", review["summary"]["hit_rate_by_model_version"])

    def test_no_recommendation_mutation(self) -> None:
        recs = [recommendation()]
        before = copy.deepcopy(recs)

        subject.recommendation_backtest(
            recs,
            {"MSFT": price_rows("MSFT", [100, 103])},
            windows=("1_day",),
        )

        self.assertEqual(recs, before)

    def test_empty_recommendation_snapshots_warning(self) -> None:
        review = subject.recommendation_backtest([], {}, windows=("1_day",))

        self.assertEqual(review["summary"]["row_count"], 0)
        self.assertTrue(any("Missing historical recommendation snapshots" in warning for warning in review["summary"]["warnings"]))
        self.assertTrue(review["review_only"])


if __name__ == "__main__":
    unittest.main()
