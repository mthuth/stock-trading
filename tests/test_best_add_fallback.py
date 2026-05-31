#!/usr/bin/env python3
"""Regression tests for review-only best-add fallback selection."""

from __future__ import annotations

import copy
import unittest

from stock_trading import best_add_fallback as subject


WATCHLIST_REASON = "Speculative AI names remain watchlist-only until evidence and observation time improve."


def gate(*, safe: bool = True, reasons: list[str] | None = None) -> dict[str, object]:
    return {
        "safe_to_buy": safe,
        "status": "Ready" if safe else "Blocked",
        "reasons": reasons or [],
        "summary": "Decision-safe buy candidate." if safe else "; ".join(reasons or ["Blocked"]),
    }


def row(
    symbol: str,
    *,
    action: str = "Add",
    score: float = 90.0,
    sleeve: str = "long_term",
    confidence: str = "Medium",
    data_status: str = "Blended",
    decision_gate: dict[str, object] | None = None,
    suggested_amount: float | None = 2500.0,
    watchlist_blocked: bool = False,
) -> dict[str, object]:
    return {
        "rank": 0,
        "symbol": symbol,
        "company": f"{symbol} Corp",
        "sleeve": sleeve,
        "trade_type": "long_term",
        "action": action,
        "score": score,
        "target_confidence": confidence,
        "data_status": data_status,
        "decision_gate": decision_gate if decision_gate is not None else gate(),
        "suggested_amount": suggested_amount,
        "watchlist_policy": {
            "blocked": watchlist_blocked,
            "reason": WATCHLIST_REASON if watchlist_blocked else "",
        },
        "rationale": f"{symbol} fixture rationale",
    }


class BestAddFallbackTests(unittest.TestCase):
    def test_top_candidate_safe_returns_primary_add(self) -> None:
        review = subject.build_best_add_fallback_review(
            [
                row("MSFT", score=95.0),
                row("NVDA", score=92.0),
            ]
        )

        self.assertEqual(review["mode"], "primary_add")
        self.assertEqual(review["primary_add"]["symbol"], "MSFT")
        self.assertIsNone(review["fallback_add"])
        self.assertFalse(review["hold_capacity"]["recommended"])
        self.assertIsNone(review["blocked_top_candidate"])

    def test_blocked_top_candidate_returns_second_safe_candidate(self) -> None:
        review = subject.build_best_add_fallback_review(
            [
                row("MSFT", score=95.0, decision_gate=gate(safe=False, reasons=["Wide target range"])),
                row("NVDA", score=92.0),
            ]
        )

        self.assertEqual(review["mode"], "fallback_add")
        self.assertEqual(review["blocked_top_candidate"]["symbol"], "MSFT")
        self.assertIn("Wide target range", review["blocked_top_candidate"]["blocked_reasons"])
        self.assertEqual(review["fallback_add"]["symbol"], "NVDA")
        self.assertFalse(review["hold_capacity"]["recommended"])

    def test_multiple_blocked_candidates_before_safe_candidate(self) -> None:
        review = subject.build_best_add_fallback_review(
            [
                row("MSFT", decision_gate=gate(safe=False, reasons=["Provider verification is blocked"])),
                row("NVDA", decision_gate=gate(safe=False, reasons=["Partial target blend"])),
                row("AVGO"),
            ]
        )

        self.assertEqual(review["mode"], "fallback_add")
        self.assertEqual(review["fallback_add"]["symbol"], "AVGO")
        self.assertEqual([candidate["symbol"] for candidate in review["skipped_candidates"]], ["MSFT", "NVDA"])

    def test_all_candidates_blocked_recommends_holding_capacity(self) -> None:
        review = subject.build_best_add_fallback_review(
            [
                row("MSFT", decision_gate=gate(safe=False, reasons=["Missing current price"])),
                row("NVDA", decision_gate=gate(safe=False, reasons=["Low target confidence"])),
            ]
        )

        self.assertEqual(review["mode"], "hold_capacity")
        self.assertTrue(review["hold_capacity"]["recommended"])
        self.assertEqual(review["blocked_top_candidate"]["symbol"], "MSFT")
        self.assertIsNone(review["fallback_add"])

    def test_watchlist_only_candidate_is_skipped(self) -> None:
        review = subject.build_best_add_fallback_review(
            [
                row("SOUN", score=96.0, watchlist_blocked=True),
                row("MSFT", score=90.0),
            ]
        )

        self.assertEqual(review["mode"], "fallback_add")
        self.assertEqual(review["blocked_top_candidate"]["symbol"], "SOUN")
        self.assertIn(WATCHLIST_REASON, review["blocked_top_candidate"]["blocked_reasons"])
        self.assertEqual(review["fallback_add"]["symbol"], "MSFT")

    def test_low_target_confidence_candidate_is_skipped(self) -> None:
        review = subject.build_best_add_fallback_review(
            [
                row("MSFT", confidence="Low"),
                row("NVDA", confidence="High"),
            ]
        )

        self.assertEqual(review["mode"], "fallback_add")
        self.assertIn("Low target confidence", review["blocked_top_candidate"]["blocked_reasons"])
        self.assertEqual(review["fallback_add"]["symbol"], "NVDA")

    def test_no_long_term_candidates_holds_capacity(self) -> None:
        review = subject.build_best_add_fallback_review(
            [
                row("QQQM", sleeve="etf"),
                row("SOUN", sleeve="speculative_ai", action="Watch"),
            ]
        )

        self.assertEqual(review["mode"], "hold_capacity")
        self.assertEqual(review["candidate_count"], 0)
        self.assertTrue(review["hold_capacity"]["recommended"])
        self.assertIsNone(review["blocked_top_candidate"])

    def test_provider_blocker_prevents_fallback_selection(self) -> None:
        review = subject.build_best_add_fallback_review(
            [
                row("MSFT", decision_gate=gate(safe=False, reasons=["Missing current price"])),
                row("NVDA"),
                row("AVGO"),
            ],
            provider_gap_records=[
                {
                    "symbol": "NVDA",
                    "provider": "SEC EDGAR",
                    "field_name": "companyfacts",
                    "status": "blocked",
                    "latest_issue": "HTTP 403",
                    "severity": "blocker",
                }
            ],
        )

        self.assertEqual(review["mode"], "fallback_add")
        self.assertEqual(review["fallback_add"]["symbol"], "AVGO")
        self.assertIn("Provider blocker", " ".join(review["skipped_candidates"][1]["blocked_reasons"]))

    def test_zero_allocation_capacity_skips_candidate(self) -> None:
        review = subject.build_best_add_fallback_review(
            [
                {
                    **row("MSFT", suggested_amount=0.0),
                    "allocation_safety": {
                        "suggested_amount": 0.0,
                        "reduction_reasons": ["single-stock cap reduced capacity to $0.00"],
                    },
                },
                row("NVDA"),
            ]
        )

        self.assertEqual(review["mode"], "fallback_add")
        self.assertEqual(review["fallback_add"]["symbol"], "NVDA")
        self.assertIn("single-stock cap", " ".join(review["blocked_top_candidate"]["blocked_reasons"]))

    def test_recommendation_input_not_mutated(self) -> None:
        rows = [
            row("MSFT", decision_gate=gate(safe=False, reasons=["Wide target range"])),
            row("NVDA"),
        ]
        gaps = [{"symbol": "MSFT", "status": "blocked", "severity": "blocker"}]
        before_rows = copy.deepcopy(rows)
        before_gaps = copy.deepcopy(gaps)

        review = subject.build_best_add_fallback_review(rows, provider_gap_records=gaps)

        self.assertEqual(rows, before_rows)
        self.assertEqual(gaps, before_gaps)
        self.assertTrue(review["review_only"])
        self.assertIn("must not change scores", review["notes"])


if __name__ == "__main__":
    unittest.main()
