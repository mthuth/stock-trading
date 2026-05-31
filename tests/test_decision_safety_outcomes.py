#!/usr/bin/env python3
"""Regression tests for review-only decision-safety effectiveness metrics."""

from __future__ import annotations

import unittest
from datetime import date, timedelta

from stock_trading import decision_safety_outcomes as subject


WATCHLIST_REASON = "Speculative/watchlist-only policy blocks buy-readiness until observation is complete."


def recommendation(
    *,
    symbol: str = "MSFT",
    report_date: str = "2026-05-01",
    action: str = "Add",
    candidate_action: str = "Add",
    decision_gate_status: str = "Ready",
    reasons: list[str] | None = None,
    rank: int = 2,
    watchlist_only_blocked: bool = False,
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "report_date": report_date,
        "action": action,
        "candidate_action": candidate_action,
        "score": 82.0,
        "current_price": 100.0,
        "target_price": 140.0,
        "decision_gate_status": decision_gate_status,
        "decision_gate_reasons": reasons or [],
        "rank": rank,
        "watchlist_only_blocked": watchlist_only_blocked,
    }


def price_rows(symbol: str, closes: list[float]) -> list[dict[str, object]]:
    return [
        {
            "symbol": symbol,
            "price_date": (date(2026, 5, 1) + timedelta(days=index)).isoformat(),
            "close": close,
            "adjusted_close": close,
            "provider": "Unit",
        }
        for index, close in enumerate(closes)
    ]


def review_row(rec: dict[str, object], closes: list[float], window: int = 1) -> dict[str, object]:
    rows = subject.decision_safety_effectiveness_rows(
        [rec],
        {str(rec["symbol"]): price_rows(str(rec["symbol"]), closes)},
        windows=(window,),
    )
    return rows[0]


class DecisionSafetyOutcomeTests(unittest.TestCase):
    def test_blocked_candidate_later_declined_likely_avoided_risk(self) -> None:
        rec = recommendation(
            symbol="NVDA",
            decision_gate_status="Blocked",
            reasons=["Wide target range"],
        )

        row = review_row(rec, [100, 96])

        self.assertEqual(row["review_bucket"], "blocked_buy_candidate")
        self.assertTrue(row["block_likely_avoided_risk"])
        self.assertFalse(row["block_may_have_missed_upside"])
        self.assertEqual(row["later_price_movement_pct"], -4.0)

    def test_blocked_candidate_later_rose_may_have_missed_upside(self) -> None:
        rec = recommendation(
            symbol="NVDA",
            decision_gate_status="Blocked",
            reasons=["Verification check is still open"],
            rank=1,
        )

        row = review_row(rec, [100, 106])

        self.assertEqual(row["review_bucket"], "top_ranked_blocked")
        self.assertTrue(row["block_may_have_missed_upside"])
        self.assertFalse(row["block_likely_avoided_risk"])
        self.assertEqual(row["later_price_movement_pct"], 6.0)

    def test_ready_candidate_later_rose(self) -> None:
        row = review_row(recommendation(), [100, 105])

        self.assertEqual(row["review_bucket"], "decision_safe_candidate")
        self.assertEqual(row["assessment"], "Ready candidate later rose.")
        self.assertFalse(row["block_likely_avoided_risk"])
        self.assertFalse(row["block_may_have_missed_upside"])

    def test_ready_candidate_later_declined(self) -> None:
        row = review_row(recommendation(), [100, 94])

        self.assertEqual(row["review_bucket"], "decision_safe_candidate")
        self.assertEqual(row["assessment"], "Ready candidate later declined.")
        self.assertFalse(row["block_likely_avoided_risk"])
        self.assertFalse(row["block_may_have_missed_upside"])

    def test_missing_outcome_history_is_marked_review_only(self) -> None:
        row = review_row(recommendation(), [100], window=5)

        self.assertTrue(row["not_enough_history"])
        self.assertEqual(row["outcome_status"], "not_enough_history")
        self.assertTrue(row["review_only"])
        self.assertIn("Review-only", row["notes"])

    def test_watchlist_only_blocked_case_is_separate_bucket(self) -> None:
        rec = recommendation(
            symbol="SOUN",
            action="Watch",
            candidate_action="Watch",
            decision_gate_status="Blocked",
            reasons=[WATCHLIST_REASON],
            watchlist_only_blocked=True,
        )

        row = review_row(rec, [100, 103])

        self.assertEqual(row["review_bucket"], "watchlist_only_blocked")
        self.assertEqual(row["blocked_reasons"], [WATCHLIST_REASON])
        self.assertTrue(row["block_may_have_missed_upside"])

    def test_summary_counts_review_buckets(self) -> None:
        recs = [
            recommendation(symbol="MSFT", decision_gate_status="Ready"),
            recommendation(symbol="NVDA", decision_gate_status="Blocked", reasons=["Wide target range"]),
            recommendation(symbol="SOUN", action="Watch", candidate_action="Watch", decision_gate_status="Blocked", reasons=[WATCHLIST_REASON]),
        ]
        rows = subject.decision_safety_effectiveness_rows(
            recs,
            {
                "MSFT": price_rows("MSFT", [100, 104]),
                "NVDA": price_rows("NVDA", [100, 96]),
                "SOUN": price_rows("SOUN", [100, 102]),
            },
            windows=(1,),
        )

        summary = subject.summarize_effectiveness(rows)

        self.assertTrue(summary["review_only"])
        self.assertEqual(summary["decision_safe_candidates"], 1)
        self.assertEqual(summary["blocked_buy_candidates"], 1)
        self.assertEqual(summary["watchlist_only_blocked_candidates"], 1)
        self.assertEqual(summary["blocks_likely_avoided_risk"], 1)
        self.assertEqual(summary["blocks_may_have_missed_upside"], 1)


if __name__ == "__main__":
    unittest.main()
