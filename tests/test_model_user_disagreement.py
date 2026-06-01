#!/usr/bin/env python3
"""Tests for review-only model/user disagreement tracking."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from stock_trading.model_user_disagreement import (
    build_model_user_disagreement_review,
    disagreement_type_for,
    model_user_disagreement_rows,
)


FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "model_user_disagreement"
    / "msft_watch_user_bought.json"
)


def rec(
    symbol: str,
    action: str,
    *,
    report_date: str = "2026-06-01",
    decision_gate_status: str = "Ready",
    blocked_reasons: list[str] | None = None,
) -> dict[str, object]:
    return {
        "report_date": report_date,
        "symbol": symbol,
        "company": f"{symbol} Company",
        "action": action,
        "score": 80.0,
        "decision_gate_status": decision_gate_status,
        "decision_gate_reasons": list(blocked_reasons or []),
    }


def journal(
    symbol: str,
    action_taken: str,
    *,
    report_date: str = "2026-06-01",
    rationale: str = "Fixture user rationale.",
) -> dict[str, object]:
    return {
        "decision_date": report_date,
        "report_date": report_date,
        "symbol": symbol,
        "action_taken": action_taken,
        "rationale": rationale,
    }


class ModelUserDisagreementTests(unittest.TestCase):
    def only_row(
        self,
        recommendations: list[dict[str, object]],
        journal_entries: list[dict[str, object]],
        outcomes: list[dict[str, object]] | None = None,
    ) -> dict[str, object]:
        rows = model_user_disagreement_rows(journal_entries, recommendations, outcomes or [])
        self.assertEqual(len(rows), 1)
        return rows[0]

    def test_model_watch_user_bought_from_fixture(self) -> None:
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        row = self.only_row(
            fixture["recommendations"],
            fixture["manual_journal_entries"],
            fixture["outcomes"],
        )

        self.assertEqual(row["symbol"], "MSFT")
        self.assertEqual(row["model_action"], "Watch")
        self.assertEqual(row["user_action"], "bought")
        self.assertEqual(row["disagreement_type"], "model_watch_user_bought")
        self.assertIn("Matt likes MSFT", row["user_rationale"])
        self.assertEqual(row["later_outcome"][0]["outcome_status"], "positive_follow_through")

    def test_model_blocked_user_bought(self) -> None:
        row = self.only_row(
            [rec("NVDA", "Watch", decision_gate_status="Blocked", blocked_reasons=["verification open"])],
            [journal("NVDA", "added")],
        )

        self.assertEqual(row["disagreement_type"], "model_blocked_user_bought")
        self.assertEqual(row["blocked_reasons"], ["verification open"])
        self.assertIn("over-blocked", row["learning_note"])

    def test_model_buy_user_skipped(self) -> None:
        row = self.only_row([rec("AMZN", "Buy")], [journal("AMZN", "skipped")])

        self.assertEqual(row["disagreement_type"], "model_buy_user_skipped")
        self.assertEqual(row["user_action"], "skipped")

    def test_model_add_user_held(self) -> None:
        row = self.only_row([rec("GOOGL", "Add")], [journal("GOOGL", "held")])

        self.assertEqual(row["disagreement_type"], "model_add_user_held")
        self.assertIn("sizing", row["learning_note"])

    def test_model_avoid_user_bought(self) -> None:
        row = self.only_row([rec("PLAB", "Avoid")], [journal("PLAB", "bought")])

        self.assertEqual(row["disagreement_type"], "model_avoid_user_bought")

    def test_model_buy_user_avoided(self) -> None:
        row = self.only_row([rec("META", "Strong Buy")], [journal("META", "avoided")])

        self.assertEqual(row["disagreement_type"], "model_buy_user_avoided")

    def test_model_and_user_agreed(self) -> None:
        row = self.only_row([rec("AVGO", "Add")], [journal("AVGO", "bought")])

        self.assertEqual(row["disagreement_type"], "model_and_user_agreed")
        self.assertTrue(row["review_only"])
        self.assertTrue(row["no_model_change"])

    def test_missing_journal_entry(self) -> None:
        row = self.only_row([rec("AMD", "Watch")], [])

        self.assertEqual(row["disagreement_type"], "no_user_action_recorded")
        self.assertEqual(row["user_action"], "")
        self.assertEqual(row["manual_journal_entries"], 0)

    def test_missing_recommendation(self) -> None:
        row = self.only_row([], [journal("MSFT", "bought")])

        self.assertEqual(row["disagreement_type"], "missing_recommendation")
        self.assertEqual(row["model_action"], "")
        self.assertIn("no matching recommendation", row["learning_note"])

    def test_later_outcome_present(self) -> None:
        row = self.only_row(
            [rec("MSFT", "Watch")],
            [journal("MSFT", "bought")],
            [
                {
                    "report_date": "2026-06-01",
                    "symbol": "MSFT",
                    "window_trading_days": 20,
                    "outcome_status": "target_progress",
                    "percent_change": 8.2,
                }
            ],
        )

        self.assertEqual(row["later_outcome"][0]["window_trading_days"], 20)
        self.assertEqual(row["later_outcome"][0]["outcome_status"], "target_progress")

    def test_review_summary_counts_disagreements(self) -> None:
        review = build_model_user_disagreement_review(
            [journal("MSFT", "bought"), journal("AVGO", "bought")],
            [rec("MSFT", "Watch"), rec("AVGO", "Add")],
        )

        self.assertEqual(review["metadata"]["row_count"], 2)
        self.assertEqual(review["summary"]["disagreement_count"], 1)
        self.assertEqual(review["summary"]["agreement_count"], 1)
        self.assertEqual(review["summary"]["by_type"]["model_watch_user_bought"], 1)
        self.assertTrue(review["summary"]["no_model_change"])

    def test_no_model_or_recommendation_mutation(self) -> None:
        recommendations = [rec("MSFT", "Watch")]
        journal_entries = [journal("MSFT", "bought")]
        before_recommendations = copy.deepcopy(recommendations)
        before_journal = copy.deepcopy(journal_entries)

        rows = model_user_disagreement_rows(journal_entries, recommendations)

        self.assertEqual(recommendations, before_recommendations)
        self.assertEqual(journal_entries, before_journal)
        self.assertTrue(rows[0]["review_only"])
        self.assertTrue(rows[0]["no_model_change"])
        self.assertIn("do not tune models", rows[0]["notes"])

    def test_classifier_direct_cases_are_deterministic(self) -> None:
        self.assertEqual(
            disagreement_type_for(
                action="Watch",
                user="bought",
                gate_status="Ready",
                reasons=[],
            ),
            "model_watch_user_bought",
        )
        self.assertEqual(
            disagreement_type_for(
                action="Buy",
                user="skipped",
                gate_status="Ready",
                reasons=[],
            ),
            "model_buy_user_skipped",
        )


if __name__ == "__main__":
    unittest.main()
