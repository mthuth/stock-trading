#!/usr/bin/env python3
"""Regression tests for the review-only long-term add queue."""

from __future__ import annotations

import copy
import unittest

from stock_trading import analysis_engine
from stock_trading.long_term_add_queue import build_long_term_add_queue


def candidate(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "rank": 1,
        "symbol": "MSFT",
        "company": "Microsoft",
        "sleeve": "long_term",
        "trade_type": "long_term",
        "action": "Add",
        "score": 84.5,
        "decision_gate": {"safe_to_buy": True, "status": "Ready", "reasons": []},
        "confidence": "Medium",
        "data_status": "Blended",
        "suggested_amount": 2500.0,
        "allocation_safety": {
            "suggested_amount": 2500.0,
            "buy_capacity": 2500.0,
            "applied_limit": "buy_capacity",
            "reason": "Full buy capacity is available under allocation rules.",
        },
        "score_breakdown": "quality + momentum + target confidence",
    }
    base.update(overrides)
    return base


class LongTermAddQueueTests(unittest.TestCase):
    def test_clear_decision_safe_long_term_add(self) -> None:
        queue = build_long_term_add_queue([candidate()])

        self.assertEqual(queue["result"], "decision_safe_add_available")
        self.assertEqual(queue["best_decision_safe_symbol"], "MSFT")
        self.assertTrue(queue["should_deploy_buy_capacity"])
        self.assertTrue(queue["rows"][0]["safe_to_buy"])
        self.assertIn("decision safety", queue["rows"][0]["why_this_is_in_queue"])

    def test_top_ranked_candidate_blocked_uses_backup_safe_add(self) -> None:
        rows = [
            candidate(
                rank=1,
                symbol="NVDA",
                decision_gate={
                    "safe_to_buy": False,
                    "status": "Blocked",
                    "reasons": ["Verification check is still open"],
                },
                suggested_amount=0.0,
            ),
            candidate(rank=2, symbol="MSFT", score=82.0),
        ]

        queue = build_long_term_add_queue(rows)

        self.assertEqual(queue["top_candidate_symbol"], "NVDA")
        self.assertEqual(queue["best_decision_safe_symbol"], "MSFT")
        self.assertFalse(queue["rows"][0]["safe_to_buy"])
        self.assertIn("Verification check is still open", queue["rows"][0]["blocked_reasons"])

    def test_watchlist_only_candidate_excluded_from_decision_safe_buy(self) -> None:
        queue = build_long_term_add_queue(
            [
                candidate(
                    symbol="SOUN",
                    watchlist_policy={"blocked": True, "reason": "Speculative AI watchlist-only block"},
                )
            ]
        )

        self.assertEqual(queue["result"], "hold_buy_capacity")
        self.assertEqual(queue["best_decision_safe_symbol"], "")
        self.assertFalse(queue["rows"][0]["safe_to_buy"])
        self.assertIn("Speculative AI watchlist-only block", queue["rows"][0]["blocked_reasons"])

    def test_no_safe_add_exists_holds_buy_capacity(self) -> None:
        queue = build_long_term_add_queue(
            [
                candidate(
                    decision_gate={"safe_to_buy": False, "status": "Blocked", "reasons": ["Low target confidence"]},
                    confidence="Low",
                    suggested_amount=0.0,
                )
            ]
        )

        self.assertEqual(queue["result"], "hold_buy_capacity")
        self.assertFalse(queue["should_deploy_buy_capacity"])
        self.assertIn("Hold buy capacity", queue["hold_buy_capacity_reason"])

    def test_low_target_confidence_is_visible_as_blocker(self) -> None:
        queue = build_long_term_add_queue(
            [
                candidate(
                    confidence="Low",
                    decision_gate={"safe_to_buy": False, "status": "Blocked", "reasons": ["Low target confidence"]},
                    suggested_amount=0.0,
                )
            ]
        )

        self.assertIn("Low target confidence", queue["rows"][0]["blocked_reasons"])
        self.assertIn("Target confidence is Low.", queue["rows"][0]["blocked_reasons"])
        self.assertEqual(queue["rows"][0]["target_confidence"], "Low")

    def test_missing_current_price_is_visible_as_data_blocker(self) -> None:
        queue = build_long_term_add_queue(
            [
                candidate(
                    current_price=None,
                    data_status="Needs price",
                    decision_gate={"safe_to_buy": False, "status": "Blocked", "reasons": ["Needs price"]},
                    suggested_amount=0.0,
                )
            ]
        )

        self.assertIn("Needs price", queue["rows"][0]["blocked_reasons"])
        self.assertIn("Needs price", queue["rows"][0]["provider_data_blockers"])

    def test_provider_gap_blocker_is_visible(self) -> None:
        queue = build_long_term_add_queue(
            [
                candidate(
                    provider_blockers=["Provider verification is blocked"],
                    decision_gate={
                        "safe_to_buy": False,
                        "status": "Blocked",
                        "reasons": ["Provider verification is blocked"],
                    },
                    suggested_amount=0.0,
                )
            ]
        )

        self.assertIn("Provider verification is blocked", queue["rows"][0]["blocked_reasons"])
        self.assertIn("Provider verification is blocked", queue["rows"][0]["provider_data_blockers"])

    def test_allocation_cap_reduces_amount_without_changing_action(self) -> None:
        queue = build_long_term_add_queue(
            [
                candidate(
                    action="Add",
                    suggested_amount=500.0,
                    allocation_safety={
                        "suggested_amount": 500.0,
                        "buy_capacity": 2500.0,
                        "applied_limit": "sleeve_cap",
                        "reason": "Suggested amount reduced by sleeve cap.",
                    },
                )
            ]
        )

        row = queue["rows"][0]
        self.assertEqual(row["action"], "Add")
        self.assertEqual(row["suggested_amount"], 500.0)
        self.assertTrue(any("sleeve_cap" in note for note in row["allocation_notes"]))

    def test_ai_synthesis_readiness_is_explanatory_only(self) -> None:
        queue = build_long_term_add_queue(
            [
                candidate(
                    ai_synthesis_readiness={
                        "status": "partially_ready",
                        "data_gaps": ["No recent IR evidence"],
                    }
                )
            ]
        )

        readiness = queue["rows"][0]["ai_synthesis_readiness"]
        self.assertTrue(readiness["review_only"])
        self.assertEqual(readiness["status"], "partially_ready")
        self.assertIn("explanatory only", readiness["note"])

    def test_input_recommendations_are_not_mutated(self) -> None:
        rows = [candidate()]
        before = copy.deepcopy(rows)

        build_long_term_add_queue(rows)

        self.assertEqual(rows, before)

    def test_analysis_report_context_includes_review_only_queue(self) -> None:
        context = analysis_engine.run_analysis(persist=False, write_context=False)
        queue = context["long_term_add_queue"]

        self.assertTrue(queue["review_only"])
        self.assertTrue(queue["recommendation_only"])
        self.assertEqual(queue["decision_mode"], "long_term_buy_add")
        self.assertIn(queue["result"], {"decision_safe_add_available", "hold_buy_capacity"})
        self.assertIn("does not change scores", queue["note"])
        self.assertIn("rows", queue)
        self.assertIn("hold_buy_capacity_reason", queue)
        self.assertEqual(context["metadata"]["recommendation_only"], True)


if __name__ == "__main__":
    unittest.main()
