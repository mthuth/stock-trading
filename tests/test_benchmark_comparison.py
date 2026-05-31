#!/usr/bin/env python3
"""Regression tests for review-only benchmark excess return comparison."""

from __future__ import annotations

import ast
import copy
import json
import unittest
from datetime import date, timedelta
from pathlib import Path

from stock_trading import benchmark_comparison as subject


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "model_evaluation" / "outcomes.json"


def outcome(
    *,
    symbol: str = "MSFT",
    report_date: str = "2026-05-01",
    window_trading_days: int = 5,
    percent_change: float = 8.0,
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "report_date": report_date,
        "window_trading_days": window_trading_days,
        "percent_change": percent_change,
        "action": "Add",
        "score": 82.0,
        "decision_gate_status": "Ready",
    }


def tactical_outcome(
    *,
    symbol: str = "NET",
    setup_date: str = "2026-05-01",
    window_trading_days: int = 1,
    percent_change: float = 3.0,
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "setup_date": setup_date,
        "window_trading_days": window_trading_days,
        "percent_change": percent_change,
        "setup_label": "breakout",
        "review_action": "tactical_buy_review",
    }


def price_rows(symbol: str, closes: list[float], *, start_day: int = 1) -> list[dict[str, object]]:
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


def price_row(symbol: str, price_date: str, close: float) -> dict[str, object]:
    return {
        "symbol": symbol,
        "price_date": price_date,
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "adjusted_close": close,
        "volume": 1000,
        "provider": "Unit",
    }


class BenchmarkComparisonTests(unittest.TestCase):
    def compare(
        self,
        row: dict[str, object] | None = None,
        histories: dict[str, list[dict[str, object]]] | None = None,
        *,
        metadata: dict[str, object] | None = None,
        explicit_benchmark: str = "",
        fallback_benchmark: str = subject.DEFAULT_FALLBACK_BENCHMARK,
        stale_after_days: int = 5,
    ) -> dict[str, object]:
        return subject.compare_outcome_to_benchmark(
            outcome() if row is None else row,
            {"QQQ": price_rows("QQQ", [100, 101, 102, 103, 104, 105])} if histories is None else histories,
            metadata=metadata or {"category": "Mega-cap AI/platform"},
            explicit_benchmark=explicit_benchmark,
            fallback_benchmark=fallback_benchmark,
            stale_after_days=stale_after_days,
        )

    def test_beats_benchmark(self) -> None:
        row = self.compare()

        self.assertEqual(row["benchmark_symbol"], "QQQ")
        self.assertEqual(row["benchmark_return_pct"], 5.0)
        self.assertEqual(row["symbol_return_pct"], 8.0)
        self.assertEqual(row["excess_return_pct"], 3.0)
        self.assertTrue(row["beat_benchmark"])
        self.assertEqual(row["data_status"], "ok")
        self.assertTrue(row["review_only"])

    def test_underperforms_benchmark(self) -> None:
        row = self.compare(outcome(percent_change=1.0))

        self.assertEqual(row["benchmark_return_pct"], 5.0)
        self.assertEqual(row["excess_return_pct"], -4.0)
        self.assertFalse(row["beat_benchmark"])

    def test_missing_benchmark_history(self) -> None:
        row = self.compare(histories={})

        self.assertEqual(row["data_status"], "benchmark_missing")
        self.assertIsNone(row["benchmark_return_pct"])
        self.assertIn("benchmark_missing:SPY", row["warnings"])
        self.assertIn("benchmark_missing_history", row["warnings"])

    def test_stale_benchmark_history(self) -> None:
        row = self.compare(
            outcome(report_date="2026-05-10", window_trading_days=1, percent_change=3.0),
            {"SPY": [price_row("SPY", "2026-05-01", 100), price_row("SPY", "2026-05-11", 101)]},
            metadata={"category": "other"},
            explicit_benchmark="SPY",
        )

        self.assertEqual(row["benchmark_symbol"], "SPY")
        self.assertEqual(row["benchmark_return_pct"], 1.0)
        self.assertEqual(row["data_status"], "benchmark_stale")
        self.assertIn("benchmark_stale:9d", row["warnings"])

    def test_explicit_benchmark_override(self) -> None:
        row = self.compare(
            histories={
                "QQQ": price_rows("QQQ", [100, 110]),
                "VGT": price_rows("VGT", [100, 101, 102, 103, 104, 106]),
            },
            explicit_benchmark="VGT",
        )

        self.assertEqual(row["benchmark_symbol"], "VGT")
        self.assertEqual(row["benchmark_return_pct"], 6.0)

    def test_semiconductor_selection_uses_smh_when_available(self) -> None:
        row = self.compare(
            outcome(symbol="AMD", percent_change=6.0),
            {
                "QQQ": price_rows("QQQ", [100, 101, 102, 103, 104, 105]),
                "SMH": price_rows("SMH", [100, 102, 104, 106, 108, 110]),
            },
            metadata={"category": "Semiconductors"},
        )

        self.assertEqual(row["benchmark_symbol"], "SMH")
        self.assertEqual(row["benchmark_return_pct"], 10.0)

    def test_tech_core_selection_uses_qqq_when_available(self) -> None:
        row = self.compare(
            outcome(symbol="MSFT", percent_change=7.0),
            {
                "QQQ": price_rows("QQQ", [100, 101, 102, 103, 104, 105]),
                "SPY": price_rows("SPY", [100, 100.5, 101, 101.5, 102, 102.5]),
            },
            metadata={"category": "Mega-cap AI/platform"},
        )

        self.assertEqual(row["benchmark_symbol"], "QQQ")
        self.assertEqual(row["excess_return_pct"], 2.0)

    def test_fallback_benchmark_used_when_configured_and_available(self) -> None:
        row = self.compare(
            outcome(symbol="MDB", percent_change=4.0),
            {"VGT": price_rows("VGT", [100, 101, 102, 103, 104, 105])},
            metadata={"category": "database software"},
            fallback_benchmark="VGT",
        )

        self.assertEqual(row["benchmark_symbol"], "VGT")
        self.assertEqual(row["data_status"], "ok")

    def test_tactical_outcome_can_use_same_window_comparison(self) -> None:
        row = self.compare(
            tactical_outcome(),
            {"QQQ": price_rows("QQQ", [100, 101])},
            metadata={"sleeve": "tactical", "tactical_horizon": "same_week"},
        )

        self.assertEqual(row["window"], 1)
        self.assertEqual(row["benchmark_symbol"], "QQQ")
        self.assertEqual(row["excess_return_pct"], 2.0)

    def test_fixture_rows_are_supported(self) -> None:
        rows = json.loads(FIXTURE.read_text())
        comparisons = subject.benchmark_comparison_rows(
            rows,
            {
                "QQQ": price_rows("QQQ", [100, 101, 102, 103, 104, 105]),
                "SMH": price_rows("SMH", [100, 102, 104, 106, 108, 110]),
            },
            metadata_by_symbol={
                "MSFT": {"category": "Mega-cap AI/platform"},
                "AMD": {"category": "Semiconductors"},
            },
        )

        self.assertEqual([row["symbol"] for row in comparisons], ["AMD", "MSFT"])
        self.assertEqual(comparisons[0]["benchmark_symbol"], "SMH")
        self.assertEqual(comparisons[1]["benchmark_symbol"], "QQQ")

    def test_no_recommendation_mutation_or_model_tuning(self) -> None:
        rec = outcome()
        before = copy.deepcopy(rec)

        row = self.compare(rec)

        self.assertEqual(rec, before)
        self.assertEqual(row["model_tuning_impact"], "none")
        self.assertEqual(row["recommendation_impact"], "none")
        self.assertIn("Review-only benchmark comparison", row["notes"])

    def test_no_provider_storage_or_model_imports(self) -> None:
        tree = ast.parse((ROOT / "stock_trading" / "benchmark_comparison.py").read_text())
        imports = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imports.update(
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        )

        forbidden = {
            "urllib",
            "requests",
            "stock_trading.provider_client",
            "stock_trading.storage.provider_repository",
            "stock_trading.analysis_engine",
            "stock_trading.recommendation_outcomes",
            "stock_trading.tactical_outcomes",
        }
        self.assertFalse(imports & forbidden)


if __name__ == "__main__":
    unittest.main()
