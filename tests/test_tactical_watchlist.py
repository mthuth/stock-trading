#!/usr/bin/env python3
"""Tests for review-only tactical watchlist queue helpers."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from stock_trading.tactical_watchlist import (
    RECOMMENDATION_ONLY_NOTE,
    TACTICAL_REVIEW_ACTIONS,
    build_tactical_watchlist_queue,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "tactical" / "watchlist_setups.json"
OFFICIAL_RECOMMENDATION_LABELS = {"Strong Buy", "Buy", "Add", "Hold", "Watch", "Trim", "Avoid"}


class TacticalWatchlistTests(unittest.TestCase):
    def setUp(self) -> None:
        self.setups = json.loads(FIXTURE.read_text())

    def row(self, queue: dict[str, object], symbol: str) -> dict[str, object]:
        for row in queue["rows"]:
            if row["symbol"] == symbol:
                return row
        self.fail(f"Missing row for {symbol}")

    def assert_review_only_row(self, row: dict[str, object]) -> None:
        self.assertTrue(row["review_only"])
        self.assertTrue(row["recommendation_only"])
        self.assertTrue(row["does_not_override_long_term"])
        self.assertEqual(row["decision_mode"], "tactical_trade")
        self.assertIn(row["review_action"], TACTICAL_REVIEW_ACTIONS)
        self.assertNotIn(row["review_action"], OFFICIAL_RECOMMENDATION_LABELS)
        self.assertEqual(row["note"], RECOMMENDATION_ONLY_NOTE)
        self.assertNotIn("action", row)

    def test_high_confidence_tactical_setup_ranks_first(self) -> None:
        queue = build_tactical_watchlist_queue(self.setups, as_of_date="2026-05-31")

        top = queue["rows"][0]

        self.assertEqual(top["symbol"], "NVDA")
        self.assertEqual(top["setup_label"], "breakout")
        self.assertEqual(top["review_action"], "tactical_buy_review")
        self.assertEqual(top["priority_rank"], 1)
        self.assertEqual(top["setup_confidence"], "high")
        self.assert_review_only_row(top)

    def test_lower_priority_setup_due_to_data_gap(self) -> None:
        queue = build_tactical_watchlist_queue(self.setups, as_of_date="2026-05-31")
        panw = self.row(queue, "PANW")
        nvda = self.row(queue, "NVDA")

        self.assertEqual(panw["review_action"], "data_gap_review")
        self.assertGreater(panw["priority_rank"], nvda["priority_rank"])
        self.assertEqual(panw["data_quality_label"], "data_gap")
        self.assertIn("Recent tactical price history is unavailable.", panw["provider_data_gaps"][0])
        self.assert_review_only_row(panw)

    def test_earnings_proximity_setup_gets_context_and_priority(self) -> None:
        queue = build_tactical_watchlist_queue(self.setups, as_of_date="2026-05-31")
        msft = self.row(queue, "MSFT")

        self.assertEqual(msft["setup_label"], "pre_earnings_setup")
        self.assertEqual(msft["review_action"], "tactical_buy_review")
        self.assertEqual(msft["earnings_event_context"]["event_proximity_days"], 3)
        self.assertGreater(msft["priority_components"]["event_proximity"], 0)
        self.assert_review_only_row(msft)

    def test_tactical_sell_review_label_stays_review_only(self) -> None:
        queue = build_tactical_watchlist_queue(self.setups, as_of_date="2026-05-31")
        amzn = self.row(queue, "AMZN")

        self.assertEqual(amzn["review_action"], "tactical_sell_review")
        self.assertNotIn(amzn["review_action"], OFFICIAL_RECOMMENDATION_LABELS)
        self.assertEqual(amzn["long_term_context"]["action"], "Hold")
        self.assert_review_only_row(amzn)

    def test_long_term_add_is_not_overridden(self) -> None:
        queue = build_tactical_watchlist_queue(self.setups, as_of_date="2026-05-31")
        nvda = self.row(queue, "NVDA")

        self.assertEqual(nvda["long_term_context"]["action"], "Add")
        self.assertEqual(queue["decision_mode"], "tactical_trade")
        self.assertTrue(queue["does_not_override_long_term"])
        self.assertTrue(queue["review_only"])
        self.assertTrue(queue["recommendation_only"])

    def test_no_setup_is_included_and_marked_low_priority(self) -> None:
        queue = build_tactical_watchlist_queue(self.setups, as_of_date="2026-05-31")
        avgo = self.row(queue, "AVGO")

        self.assertEqual(queue["excluded"], [])
        self.assertEqual(len(queue["rows"]), len(self.setups))
        self.assertEqual(avgo["setup_label"], "no_setup")
        self.assertEqual(avgo["review_action"], "avoid_for_now")
        self.assertEqual(avgo["priority_rank"], len(queue["rows"]))
        self.assertIn("No actionable setup", avgo["invalidation_condition"])
        self.assert_review_only_row(avgo)

    def test_queue_does_not_mutate_input_and_is_deterministic(self) -> None:
        original = copy.deepcopy(self.setups)

        first = build_tactical_watchlist_queue(self.setups, as_of_date="2026-05-31")
        second = build_tactical_watchlist_queue(self.setups, as_of_date="2026-05-31")

        self.assertEqual(self.setups, original)
        self.assertEqual(first, second)

    def test_missing_optional_fields_are_handled_gracefully(self) -> None:
        queue = build_tactical_watchlist_queue([{"symbol": "TSLA"}], as_of_date="2026-05-31")
        row = queue["rows"][0]

        self.assertEqual(row["symbol"], "TSLA")
        self.assertEqual(row["setup_label"], "no_setup")
        self.assertEqual(row["review_action"], "avoid_for_now")
        self.assertEqual(row["priority_rank"], 1)
        self.assert_review_only_row(row)


if __name__ == "__main__":
    unittest.main()
