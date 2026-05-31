#!/usr/bin/env python3
"""Regression tests for review-only tactical outcome tracking."""

from __future__ import annotations

import copy
import json
import unittest
from datetime import date, timedelta
from pathlib import Path

from stock_trading import tactical_outcomes as subject


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "tactical" / "setups.json"


def setup(
    *,
    symbol: str = "MSFT",
    setup_date: str = "2026-05-01",
    setup_label: str = "breakout",
    tactical_horizon: str = "5_trading_days",
    review_action: str = "tactical_buy_review",
    setup_confidence: str = "medium",
    original_price: float = 100.0,
    invalidation_price: float = 96.0,
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "setup_date": setup_date,
        "report_date": setup_date,
        "setup_label": setup_label,
        "tactical_horizon": tactical_horizon,
        "review_action": review_action,
        "setup_confidence": setup_confidence,
        "original_price": original_price,
        "invalidation_price": invalidation_price,
        "current_recommendation": {"action": "Add", "score": 82.0},
    }


def price_rows(
    symbol: str,
    closes: list[float],
    *,
    highs: list[float] | None = None,
    lows: list[float] | None = None,
    start_day: int = 1,
) -> list[dict[str, object]]:
    highs = highs or closes
    lows = lows or closes
    return [
        {
            "symbol": symbol,
            "price_date": (date(2026, 5, start_day) + timedelta(days=index)).isoformat(),
            "open": close,
            "high": highs[index],
            "low": lows[index],
            "close": close,
            "adjusted_close": close,
            "volume": 1000 + index,
            "provider": "Unit",
        }
        for index, close in enumerate(closes)
    ]


class TacticalOutcomeTests(unittest.TestCase):
    def row_for(
        self,
        closes: list[float],
        *,
        highs: list[float] | None = None,
        lows: list[float] | None = None,
        tactical_setup: dict[str, object] | None = None,
        window: int = 5,
    ) -> dict[str, object]:
        tactical_setup = tactical_setup or setup()
        rows = subject.tactical_outcome_rows(
            [tactical_setup],
            {str(tactical_setup["symbol"]): price_rows(str(tactical_setup["symbol"]), closes, highs=highs, lows=lows)},
            windows=(window,),
        )
        return rows[0]

    def test_default_windows_include_tactical_review_periods(self) -> None:
        rows = subject.tactical_outcome_rows(
            [setup()],
            {"MSFT": price_rows("MSFT", [100 + index for index in range(61)])},
        )

        self.assertEqual([row["window_trading_days"] for row in rows], [1, 5, 20, 60])
        self.assertTrue(all(row["review_only"] for row in rows))

    def test_positive_follow_through(self) -> None:
        row = self.row_for([100, 101, 102, 103, 104, 105], window=5)

        self.assertEqual(row["outcome_status"], "positive_follow_through")
        self.assertEqual(row["later_price"], 105)
        self.assertEqual(row["percent_change"], 5.0)
        self.assertEqual(row["directional_return_pct"], 5.0)

    def test_negative_follow_through(self) -> None:
        row = self.row_for(
            [100, 99, 98, 97, 96, 95],
            tactical_setup=setup(invalidation_price=90.0),
            window=5,
        )

        self.assertEqual(row["outcome_status"], "negative_follow_through")
        self.assertEqual(row["percent_change"], -5.0)

    def test_flat_outcome(self) -> None:
        row = self.row_for([100, 100.2], window=1)

        self.assertEqual(row["outcome_status"], "flat")

    def test_not_enough_history(self) -> None:
        row = self.row_for([100, 101], window=5)

        self.assertEqual(row["outcome_status"], "not_enough_history")
        self.assertIsNone(row["later_price"])
        self.assertIsNone(row["percent_change"])

    def test_invalidated_setup(self) -> None:
        row = self.row_for([100, 101, 102], lows=[100, 95.5, 101], window=2)

        self.assertTrue(row["invalidation_hit"])
        self.assertEqual(row["outcome_status"], "invalidated")
        self.assertEqual(row["invalidation_price"], 96.0)

    def test_volatile_but_favorable(self) -> None:
        row = self.row_for(
            [100, 101, 105],
            highs=[100, 104, 106],
            lows=[100, 95, 101],
            tactical_setup=setup(invalidation_price=90.0),
            window=2,
        )

        self.assertEqual(row["outcome_status"], "favorable_but_choppy")
        self.assertEqual(row["max_favorable_move_pct"], 6.0)
        self.assertEqual(row["max_adverse_move_pct"], -5.0)

    def test_volatile_inconclusive(self) -> None:
        row = self.row_for(
            [100, 99, 100.5],
            highs=[100, 104, 105],
            lows=[100, 95, 96],
            tactical_setup=setup(invalidation_price=90.0),
            window=2,
        )

        self.assertEqual(row["outcome_status"], "volatile_inconclusive")

    def test_tactical_sell_review_is_directional_but_not_execution(self) -> None:
        sell_setup = setup(review_action="tactical_sell_review", original_price=100.0, invalidation_price=104.0)
        row = self.row_for([100, 99, 96], tactical_setup=sell_setup, window=2)

        self.assertEqual(row["percent_change"], -4.0)
        self.assertEqual(row["directional_return_pct"], 4.0)
        self.assertEqual(row["outcome_status"], "positive_follow_through")
        self.assertEqual(row["recommendation_impact"], "none")

    def test_fixture_rows_are_supported(self) -> None:
        setups = json.loads(FIXTURE.read_text())
        rows = subject.tactical_outcome_rows(
            setups,
            {
                "MSFT": price_rows("MSFT", [100, 101, 102, 103, 104, 105]),
                "NVDA": price_rows("NVDA", [200, 201, 202]),
            },
            windows=(1,),
        )

        self.assertEqual([row["symbol"] for row in rows], ["MSFT", "NVDA"])
        self.assertEqual(rows[0]["setup_label"], "breakout")
        self.assertEqual(rows[1]["setup_label"], "post_earnings_reaction")

    def test_no_recommendation_mutation_or_model_tuning(self) -> None:
        tactical_setup = setup()
        before = copy.deepcopy(tactical_setup)

        rows = subject.tactical_outcome_rows(
            [tactical_setup],
            {"MSFT": price_rows("MSFT", [100, 102])},
            windows=(1,),
        )
        summary = subject.summarize_tactical_outcomes(rows)

        self.assertEqual(tactical_setup, before)
        self.assertEqual(rows[0]["model_tuning_impact"], "none")
        self.assertEqual(rows[0]["recommendation_impact"], "none")
        self.assertEqual(summary["model_tuning_impact"], "none")
        self.assertEqual(summary["recommendation_impact"], "none")

    def test_output_status_vocabulary_is_controlled(self) -> None:
        self.assertEqual(
            subject.OUTCOME_STATUSES,
            {
                "not_enough_history",
                "positive_follow_through",
                "negative_follow_through",
                "flat",
                "invalidated",
                "volatile_inconclusive",
                "favorable_but_choppy",
            },
        )


if __name__ == "__main__":
    unittest.main()
