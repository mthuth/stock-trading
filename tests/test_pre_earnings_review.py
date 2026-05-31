#!/usr/bin/env python3
"""Tests for review-only pre-earnings setup review."""

from __future__ import annotations

import copy
import unittest

from stock_trading.pre_earnings_review import (
    REVIEW_ACTIONS,
    SETUP_LABELS,
    review_pre_earnings_setup,
    review_pre_earnings_setups,
)


def event(symbol: str = "MSFT", earnings_date: str = "2026-06-07") -> dict[str, object]:
    return {
        "symbol": symbol,
        "company": "Microsoft",
        "earnings_date": earnings_date,
    }


def recommendation(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "symbol": "MSFT",
        "company": "Microsoft",
        "action": "Add",
        "score": 84.0,
        "confidence": "Medium",
        "decision_gate": {
            "safe_to_buy": True,
            "status": "Ready",
            "reasons": [],
        },
    }
    row.update(overrides)
    return row


def ready_gate() -> dict[str, object]:
    return {"safe_to_buy": True, "status": "Ready", "reasons": []}


def blocked_gate() -> dict[str, object]:
    return {
        "safe_to_buy": False,
        "status": "Blocked",
        "reasons": ["Low target confidence"],
    }


class PreEarningsReviewTests(unittest.TestCase):
    def test_attractive_long_term_candidate_before_earnings(self) -> None:
        result = review_pre_earnings_setup(
            earnings_event=event(),
            recommendation=recommendation(),
            decision_safety=ready_gate(),
            target_confidence="Medium",
            price_history_summary={"status": "available", "history_days": 60, "max_daily_move_pct": 2.5},
            ai_synthesis_readiness={"status": "ready_for_ai_synthesis", "eligible_for_ai_synthesis": True},
            as_of_date="2026-05-31",
        )

        self.assertEqual(result["symbol"], "MSFT")
        self.assertEqual(result["earnings_date"], "2026-06-07")
        self.assertEqual(result["days_until_earnings"], 7)
        self.assertEqual(result["setup_label"], "attractive_pre_earnings_review")
        self.assertEqual(result["recommended_review_action"], "consider_small_review_only_add")
        self.assertTrue(result["review_only"])
        self.assertIn("Recommendation-only", result["recommendation_only_note"])

    def test_attractive_candidate_but_decision_gate_blocked(self) -> None:
        result = review_pre_earnings_setup(
            earnings_event=event("NVDA"),
            recommendation=recommendation(symbol="NVDA", confidence="High"),
            decision_safety=blocked_gate(),
            target_confidence="High",
            price_history_summary={"status": "available", "history_days": 80},
            as_of_date="2026-05-31",
        )

        self.assertEqual(result["setup_label"], "avoid_pre_earnings_add")
        self.assertEqual(result["recommended_review_action"], "hold_buy_capacity")
        self.assertIn("Decision safety is not ready before earnings.", result["blockers"])
        self.assertIn("Low target confidence", result["blockers"])

    def test_low_target_confidence_before_earnings_waits(self) -> None:
        result = review_pre_earnings_setup(
            earnings_event=event("AMD"),
            recommendation=recommendation(symbol="AMD", confidence="Low"),
            decision_safety=ready_gate(),
            target_confidence="Low",
            price_history_summary={"status": "available", "history_days": 40},
            as_of_date="2026-05-31",
        )

        self.assertEqual(result["setup_label"], "wait_for_earnings")
        self.assertEqual(result["recommended_review_action"], "wait_until_after_report")
        self.assertIn("Target confidence is Low before earnings.", result["blockers"])

    def test_missing_earnings_date_is_data_insufficient(self) -> None:
        result = review_pre_earnings_setup(
            earnings_event={"symbol": "MSFT", "company": "Microsoft"},
            recommendation=recommendation(),
            as_of_date="2026-05-31",
        )

        self.assertEqual(result["setup_label"], "data_insufficient")
        self.assertEqual(result["recommended_review_action"], "verify_data_first")
        self.assertIsNone(result["days_until_earnings"])
        self.assertIn("earnings_date", result["data_gaps"])

    def test_high_volatility_or_insufficient_price_history_blocks_review(self) -> None:
        result = review_pre_earnings_setup(
            earnings_event=event("META"),
            recommendation=recommendation(symbol="META", confidence="Medium"),
            decision_safety=ready_gate(),
            target_confidence="Medium",
            price_history_summary={"status": "insufficient", "history_days": 8, "max_daily_move_pct": 11},
            as_of_date="2026-05-31",
        )

        self.assertEqual(result["setup_label"], "data_insufficient")
        self.assertEqual(result["recommended_review_action"], "verify_data_first")
        self.assertIn("Price history is insufficient for earnings-timing review.", result["blockers"])
        self.assertTrue(any("volatility" in reason.lower() for reason in result["reasons"]))

    def test_provider_gap_blocks_confidence(self) -> None:
        result = review_pre_earnings_setup(
            earnings_event=event("GOOGL"),
            recommendation=recommendation(symbol="GOOGL", confidence="Medium"),
            decision_safety=ready_gate(),
            target_confidence="Medium",
            provider_gaps=[
                {
                    "severity": "blocker",
                    "provider": "Finnhub",
                    "field": "earnings_calendar",
                    "status": "blocked",
                    "latest_issue": "HTTP 429",
                }
            ],
            as_of_date="2026-05-31",
        )

        self.assertEqual(result["setup_label"], "data_insufficient")
        self.assertEqual(result["recommended_review_action"], "verify_data_first")
        self.assertTrue(any("Provider gap blocks confidence" in blocker for blocker in result["blockers"]))
        self.assertTrue(any("Finnhub" in gap for gap in result["data_gaps"]))

    def test_outside_pre_earnings_window_is_ignored_for_now(self) -> None:
        result = review_pre_earnings_setup(
            earnings_event=event("AMZN", earnings_date="2026-07-15"),
            recommendation=recommendation(symbol="AMZN"),
            as_of_date="2026-05-31",
            pre_earnings_window_days=14,
        )

        self.assertEqual(result["setup_label"], "not_in_pre_earnings_window")
        self.assertEqual(result["recommended_review_action"], "ignore_for_now")
        self.assertEqual(result["days_until_earnings"], 45)

    def test_weak_ai_source_and_prior_follow_through_reduce_but_do_not_mutate(self) -> None:
        rec = recommendation(symbol="AVGO", confidence="Medium")
        before = copy.deepcopy(rec)

        result = review_pre_earnings_setup(
            earnings_event=event("AVGO"),
            recommendation=rec,
            decision_safety=ready_gate(),
            target_confidence="Medium",
            source_usefulness={"label": "noisy"},
            ai_synthesis_readiness={"status": "partially_ready"},
            prior_follow_through={"outcome_label": "likely_noisy"},
            as_of_date="2026-05-31",
        )

        self.assertIn(result["setup_label"], SETUP_LABELS)
        self.assertIn(result["recommended_review_action"], REVIEW_ACTIONS)
        self.assertTrue(result["review_only"])
        self.assertEqual(rec, before)

    def test_no_recommendation_mutation(self) -> None:
        rec = recommendation()
        add = {"symbol": "MSFT", "safe_to_buy": True, "suggested_amount": 2500}
        gate = ready_gate()
        before = (copy.deepcopy(rec), copy.deepcopy(add), copy.deepcopy(gate))

        review_pre_earnings_setup(
            earnings_event=event(),
            recommendation=rec,
            long_term_add=add,
            decision_safety=gate,
            target_confidence="Medium",
            as_of_date="2026-05-31",
        )

        self.assertEqual((rec, add, gate), before)

    def test_batch_review_is_deterministic_and_review_only(self) -> None:
        review = review_pre_earnings_setups(
            [
                event("NVDA", "2026-06-10"),
                event("MSFT", "2026-06-03"),
            ],
            recommendations_by_symbol={
                "MSFT": recommendation(symbol="MSFT"),
                "NVDA": recommendation(symbol="NVDA"),
            },
            as_of_date="2026-05-31",
        )

        self.assertTrue(review["review_only"])
        self.assertTrue(review["recommendation_only"])
        self.assertEqual([row["symbol"] for row in review["rows"]], ["MSFT", "NVDA"])


if __name__ == "__main__":
    unittest.main()
