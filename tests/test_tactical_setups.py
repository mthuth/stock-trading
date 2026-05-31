#!/usr/bin/env python3
"""Tests for deterministic, review-only tactical setup classification."""

from __future__ import annotations

import copy
import unittest
from datetime import date, timedelta

from stock_trading import tactical_setups as subject


def price_rows(
    closes: list[float],
    *,
    start: date = date(2026, 4, 1),
    symbol: str = "NVDA",
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index, close in enumerate(closes):
        rows.append(
            {
                "symbol": symbol,
                "date": (start + timedelta(days=index)).isoformat(),
                "close": close,
                "high": close * 1.01,
                "low": close * 0.99,
                "volume": 1_000_000 + index,
            }
        )
    return rows


def flat_rows(value: float = 100.0, days: int = 30) -> list[dict[str, object]]:
    return price_rows([value for _ in range(days)])


class TacticalSetupTests(unittest.TestCase):
    def classify(self, **kwargs: object) -> dict[str, object]:
        kwargs.setdefault("symbol", "NVDA")
        kwargs.setdefault("as_of_date", "2026-05-31")
        return subject.classify_tactical_setup(**kwargs)

    def assert_review_only(self, row: dict[str, object]) -> None:
        self.assertTrue(row["review_only"])
        self.assertIn("Recommendation-only", row["recommendation_only_note"])
        self.assertIn("does not place trades", row["recommendation_only_note"])
        self.assertNotIn("Strong Buy", str(row))

    def test_breakout_setup(self) -> None:
        history = price_rows([95, 96, 97, 98, 99, 100, 100, 101, 100, 99, 100, 101, 100, 102, 103, 102, 103, 104, 105, 106, 110])

        row = self.classify(price_history=history)

        self.assertEqual(row["setup_label"], "breakout_review")
        self.assertEqual(row["review_action"], "tactical_buy_review")
        self.assertEqual(row["tactical_horizon"], "same_week")
        self.assertGreater(row["resistance_level"], 0)
        self.assertIn("resistance", " ".join(row["reasons"]))
        self.assert_review_only(row)

    def test_pullback_setup(self) -> None:
        closes = [90, 91, 92, 93, 94, 95, 96, 98, 100, 102, 104, 103, 101, 99, 97, 96, 96, 96, 96, 97]
        row = self.classify(
            price_history=price_rows(closes),
            technical_context={"support_level": 94, "resistance_level": 105},
        )

        self.assertEqual(row["setup_label"], "pullback_review")
        self.assertEqual(row["review_action"], "tactical_buy_review")
        self.assertEqual(row["support_level"], 94)
        self.assertIn("support", row["invalidation_condition"])
        self.assert_review_only(row)

    def test_momentum_setup(self) -> None:
        closes = [100 + index * 0.4 for index in range(20)] + [110, 112, 114, 116, 118, 120]
        row = self.classify(price_history=price_rows(closes))

        self.assertEqual(row["setup_label"], "momentum_review")
        self.assertIn(row["review_action"], {"tactical_buy_review", "watch_intraday"})
        self.assertIn(row["tactical_horizon"], {"same_day", "same_week"})
        self.assert_review_only(row)

    def test_reversal_setup(self) -> None:
        closes = [130 - index for index in range(50)] + [78, 77, 76, 77, 78, 82]
        row = self.classify(
            price_history=price_rows(closes),
            technical_context={"support_level": 76, "resistance_level": 95},
        )

        self.assertEqual(row["setup_label"], "reversal_review")
        self.assertEqual(row["review_action"], "wait_for_confirmation")
        self.assertEqual(row["tactical_horizon"], "same_month")
        self.assert_review_only(row)

    def test_post_earnings_reaction_setup(self) -> None:
        row = self.classify(
            price_history=flat_rows(),
            post_earnings_review={
                "symbol": "NVDA",
                "earnings_date": "2026-05-28",
                "days_since_earnings": 3,
                "reaction_label": "market_confirmation",
                "evidence_summary": ["Revenue and guidance improved after earnings."],
                "data_gaps": [],
            },
        )

        self.assertEqual(row["setup_label"], "post_earnings_reaction_review")
        self.assertEqual(row["review_action"], "tactical_buy_review")
        self.assertEqual(row["tactical_horizon"], "same_week")
        self.assertIn("Post-earnings", row["reasons"][0])
        self.assert_review_only(row)

    def test_pre_earnings_setup(self) -> None:
        row = self.classify(
            price_history=flat_rows(),
            pre_earnings_review={
                "symbol": "NVDA",
                "earnings_date": "2026-06-04",
                "days_until_earnings": 4,
                "setup_label": "attractive_pre_earnings_review",
                "reasons": ["Strong candidate, but earnings timing needs manual review."],
                "blockers": [],
                "data_gaps": [],
            },
        )

        self.assertEqual(row["setup_label"], "pre_earnings_setup_review")
        self.assertEqual(row["review_action"], "tactical_buy_review")
        self.assertEqual(row["tactical_horizon"], "same_week")
        self.assert_review_only(row)

    def test_news_catalyst_setup(self) -> None:
        row = self.classify(
            price_history=flat_rows(),
            catalyst_events=[
                {
                    "symbol": "NVDA",
                    "event_date": "2026-05-30",
                    "event_type": "product_launch",
                    "headline": "New AI platform launch drives momentum",
                    "corroboration_label": "independent_confirmed",
                }
            ],
        )

        self.assertEqual(row["setup_label"], "news_catalyst_review")
        self.assertEqual(row["review_action"], "tactical_buy_review")
        self.assertEqual(row["tactical_horizon"], "same_week")
        self.assertIn("Recent catalyst/news event", row["reasons"][0])
        self.assert_review_only(row)

    def test_no_setup(self) -> None:
        row = self.classify(price_history=flat_rows())

        self.assertEqual(row["setup_label"], "no_tactical_setup")
        self.assertEqual(row["review_action"], "hold_existing")
        self.assertEqual(row["tactical_horizon"], "none")
        self.assertIn("No deterministic tactical setup", row["reasons"][0])
        self.assert_review_only(row)

    def test_missing_price_history(self) -> None:
        row = self.classify(price_history=[])

        self.assertEqual(row["setup_label"], "data_insufficient")
        self.assertEqual(row["review_action"], "data_gap_review")
        self.assertEqual(row["setup_confidence"], "needs_review")
        self.assertIn("missing_price_history", row["data_gaps"])
        self.assert_review_only(row)

    def test_provider_gap_lowers_confidence(self) -> None:
        history = price_rows([95, 96, 97, 98, 99, 100, 100, 101, 100, 99, 100, 101, 100, 102, 103, 102, 103, 104, 105, 106, 110])

        row = self.classify(
            price_history=history,
            provider_gaps=[
                {
                    "symbol": "NVDA",
                    "provider": "Yahoo",
                    "field": "price_history",
                    "status": "stale",
                    "latest_issue": "Price history is stale.",
                }
            ],
        )

        self.assertEqual(row["setup_label"], "breakout_review")
        self.assertEqual(row["review_action"], "data_gap_review")
        self.assertEqual(row["setup_confidence"], "low")
        self.assertIn("Provider gaps lower tactical setup confidence.", row["reasons"])
        self.assertIn("Yahoo price_history: Price history is stale.", row["blockers"])
        self.assert_review_only(row)

    def test_long_term_recommendation_not_mutated(self) -> None:
        recommendation = {
            "symbol": "NVDA",
            "action": "Add",
            "score": 84.2,
            "decision_gate_status": "Ready",
            "nested": {"target_confidence": "Medium"},
        }
        before = copy.deepcopy(recommendation)

        row = self.classify(
            price_history=flat_rows(),
            recommendation=recommendation,
        )

        self.assertEqual(recommendation, before)
        self.assertEqual(row["setup_label"], "no_tactical_setup")
        self.assertEqual(row["symbol"], "NVDA")
        self.assert_review_only(row)

    def test_batch_output_is_review_only_and_sorted(self) -> None:
        review = subject.classify_tactical_setups(
            [
                {"symbol": "MSFT", "price_history": []},
                {"symbol": "NVDA", "price_history": flat_rows()},
            ],
            as_of_date="2026-05-31",
        )

        self.assertTrue(review["review_only"])
        self.assertTrue(review["recommendation_only"])
        self.assertEqual(review["row_count"], 2)
        self.assertEqual([row["setup_label"] for row in review["rows"]], ["data_insufficient", "no_tactical_setup"])


if __name__ == "__main__":
    unittest.main()
