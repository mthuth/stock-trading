#!/usr/bin/env python3
"""Regression tests for review-only recommendation outcome tracking."""

from __future__ import annotations

import copy
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from stock_trading import recommendation_outcomes as subject
from stock_trading.storage import connection
from stock_trading.storage import provider_repository, recommendation_repository


def recommendation(
    *,
    symbol: str = "MSFT",
    report_date: str = "2026-05-01",
    action: str = "Add",
    score: float = 82.0,
    current_price: float = 100.0,
    target_price: float = 140.0,
    decision_gate_status: str = "Ready",
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "report_date": report_date,
        "action": action,
        "score": score,
        "current_price": current_price,
        "target_price": target_price,
        "decision_gate_status": decision_gate_status,
        "decision_gate_reasons": ["fixture reason"] if decision_gate_status == "Blocked" else [],
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


class RecommendationOutcomeTests(unittest.TestCase):
    def row_for(self, closes: list[float], rec: dict[str, object] | None = None, window: int = 5) -> dict[str, object]:
        rec = rec or recommendation()
        rows = subject.recommendation_outcome_rows(
            [rec],
            {str(rec["symbol"]): price_rows(str(rec["symbol"]), closes)},
            windows=(window,),
        )
        return rows[0]

    def test_enough_price_history_calculates_window_metrics(self) -> None:
        row = self.row_for([100, 102, 103, 104, 106, 108], window=5)

        self.assertEqual(row["later_price_date"], "2026-05-06")
        self.assertEqual(row["later_price"], 108)
        self.assertEqual(row["percent_change"], 8.0)
        self.assertEqual(row["target_progress"], 20.0)
        self.assertEqual(row["review_only"], True)

    def test_default_windows_include_required_review_periods(self) -> None:
        rows = subject.recommendation_outcome_rows(
            [recommendation()],
            {"MSFT": price_rows("MSFT", [100 + index for index in range(61)])},
        )

        self.assertEqual([row["window_trading_days"] for row in rows], [1, 5, 20, 60])
        self.assertEqual(rows[-1]["later_price_date"], "2026-06-30")
        self.assertEqual(rows[-1]["outcome_status"], "target_progress")

    def test_missing_later_price_is_not_enough_history(self) -> None:
        row = self.row_for([100, 102], window=5)

        self.assertEqual(row["outcome_status"], "not_enough_history")
        self.assertIsNone(row["later_price"])
        self.assertIsNone(row["percent_change"])

    def test_positive_follow_through(self) -> None:
        row = self.row_for([100, 101, 102], window=2)

        self.assertEqual(row["outcome_status"], "positive_follow_through")

    def test_negative_follow_through(self) -> None:
        row = self.row_for([100, 99, 97], window=2)

        self.assertEqual(row["outcome_status"], "negative_follow_through")

    def test_flat_outcome(self) -> None:
        row = self.row_for([100, 100.4], window=1)

        self.assertEqual(row["outcome_status"], "flat")

    def test_target_progress_and_drawdown_statuses(self) -> None:
        progress = self.row_for([100, 125], window=1)
        drawdown = self.row_for([100, 90], window=1)

        self.assertEqual(progress["outcome_status"], "target_progress")
        self.assertEqual(drawdown["outcome_status"], "drawdown_warning")

    def test_blocked_recommendation_outcome_preserves_gate_context(self) -> None:
        rec = recommendation(symbol="NVDA", decision_gate_status="Blocked")
        row = self.row_for([100, 98], rec=rec, window=1)

        self.assertEqual(row["decision_gate_status"], "Blocked")
        self.assertEqual(row["decision_gate_reasons"], ["fixture reason"])
        self.assertEqual(row["outcome_status"], "negative_follow_through")

    def test_no_mutation_of_recommendation_behavior(self) -> None:
        rec = recommendation(action="Add", score=82.0, current_price=100.0, target_price=140.0)
        before = copy.deepcopy(rec)

        subject.recommendation_outcome_rows([rec], {"MSFT": price_rows("MSFT", [100, 101])}, windows=(1,))

        self.assertEqual(rec, before)

    def test_local_review_output_loads_existing_storage_without_schema_change(self) -> None:
        original_db_file = connection.DB_FILE
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                connection.DB_FILE = Path(tmpdir) / "outcomes.sqlite"
                provider_repository.record_price_history(
                    price_rows("MSFT", [100, 102, 104], start_day=1)
                )
                recommendation_repository.record_recommendation_scores(
                    1,
                    [
                        {
                            "run_id": 1,
                            "report_date": "2026-05-01",
                            "symbol": "MSFT",
                            "company": "Microsoft",
                            "sleeve": "long_term",
                            "trade_type": "long_term",
                            "action": "Add",
                            "score": 82.0,
                            "current_price": 100.0,
                            "target_price": 140.0,
                            "upside_pct": 40.0,
                            "target_confidence": "medium",
                            "data_status": "Blended",
                            "score_breakdown": "fixture",
                            "rationale": "fixture",
                        }
                    ],
                )

                review = subject.build_recommendation_outcome_review(windows=(1,))
        finally:
            connection.DB_FILE = original_db_file

        self.assertTrue(review["metadata"]["review_only"])
        self.assertEqual(review["metadata"]["windows"], [1])
        self.assertEqual(review["outcomes"][0]["symbol"], "MSFT")
        self.assertEqual(review["outcomes"][0]["outcome_status"], "positive_follow_through")


if __name__ == "__main__":
    unittest.main()
