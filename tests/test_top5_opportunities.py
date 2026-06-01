#!/usr/bin/env python3
"""Tests for the review-only Top 5 opportunity view."""

from __future__ import annotations

import copy
import unittest

from stock_trading.top5_opportunities import (
    RELIABILITY_BLOCKER_NOTE,
    build_top5_opportunities,
)


class Top5OpportunitiesTests(unittest.TestCase):
    def candidate(self, symbol: str, **overrides: object) -> dict[str, object]:
        row: dict[str, object] = {
            "rank": overrides.pop("rank", 1),
            "symbol": symbol,
            "company": f"{symbol} Corp.",
            "sleeve": "long_term",
            "trade_type": "long_term",
            "action": "Add",
            "score": 80.0,
            "safe_to_buy": True,
            "decision_gate_status": "Ready",
            "blocked_reasons": [],
            "target_confidence": "Medium",
            "data_status": "Blended",
            "suggested_amount": 500.0,
            "rationale": "Existing recommendation rationale.",
        }
        row.update(overrides)
        return row

    def test_selects_top_5_from_existing_ranked_recommendations(self) -> None:
        rows = [
            self.candidate("MSFT", rank=1),
            self.candidate("NVDA", rank=2),
            self.candidate("META", rank=3),
            self.candidate("AMZN", rank=4),
            self.candidate("GOOGL", rank=5),
            self.candidate("CRM", rank=6),
        ]

        result = build_top5_opportunities(rows)

        self.assertEqual([row["symbol"] for row in result["rows"]], ["MSFT", "NVDA", "META", "AMZN", "GOOGL"])
        self.assertEqual(result["summary"]["count"], 5)

    def test_distinguishes_core_mega_cap_and_higher_upside_candidates(self) -> None:
        rows = [
            self.candidate("MSFT", rank=1),
            self.candidate("NVDA", rank=2),
            self.candidate("META", rank=3),
            self.candidate("AMZN", rank=4),
            self.candidate("GOOGL", rank=5),
            self.candidate("SOUN", rank=6, sleeve="speculative_ai"),
        ]

        result = build_top5_opportunities(rows)
        buckets = {row["symbol"]: row["opportunity_bucket"] for row in result["rows"]}

        self.assertEqual(buckets["MSFT"], "core_mega_cap")
        self.assertEqual(buckets["SOUN"], "speculative_watchlist")
        self.assertTrue(result["summary"]["has_core_mega_cap"])
        self.assertTrue(result["summary"]["has_higher_upside"])

    def test_avoids_duplicate_symbols(self) -> None:
        rows = [
            self.candidate("MSFT", rank=1, score=90),
            self.candidate("MSFT", rank=2, score=89),
            self.candidate("NVDA", rank=3),
            self.candidate("META", rank=4),
            self.candidate("AMZN", rank=5),
            self.candidate("SOUN", rank=6, sleeve="speculative_ai"),
        ]

        result = build_top5_opportunities(rows)

        symbols = [row["symbol"] for row in result["rows"]]
        self.assertEqual(len(symbols), len(set(symbols)))
        self.assertEqual(symbols.count("MSFT"), 1)

    def test_blocked_top_candidate_keeps_reasons_visible(self) -> None:
        rows = [
            self.candidate(
                "MSFT",
                rank=1,
                safe_to_buy=False,
                decision_gate_status="Blocked",
                blocked_reasons=["Verification check still open."],
            ),
            self.candidate("NVDA", rank=2),
            self.candidate("SOUN", rank=3, sleeve="speculative_ai"),
        ]

        result = build_top5_opportunities(rows)
        top = result["rows"][0]

        self.assertEqual(top["symbol"], "MSFT")
        self.assertFalse(top["safe_to_buy"])
        self.assertEqual(top["capital_action"], "blocked")
        self.assertIn("Verification check still open.", top["blocked_reasons"])

    def test_decision_safe_candidate_is_clear_and_deployable(self) -> None:
        result = build_top5_opportunities([self.candidate("MSFT", rank=1, suggested_amount=750.0)])
        row = result["rows"][0]

        self.assertTrue(row["safe_to_buy"])
        self.assertEqual(row["decision_gate_status"], "Ready")
        self.assertEqual(row["capital_action"], "deploy")
        self.assertEqual(row["suggested_amount"], 750.0)

    def test_no_safe_add_holds_capacity(self) -> None:
        rows = [
            self.candidate("MSFT", rank=1, action="Watch", safe_to_buy=False, decision_gate_status="Blocked"),
            self.candidate("SOUN", rank=2, sleeve="speculative_ai", safe_to_buy=False, decision_gate_status="Blocked"),
        ]

        result = build_top5_opportunities(rows)

        self.assertEqual(result["capital_action"], "hold_capacity")
        self.assertIn("Hold buy capacity", result["hold_capacity_message"])
        self.assertEqual(result["summary"]["safe_to_buy_count"], 0)

    def test_missing_data_is_confidence_blocker_not_bearish_thesis(self) -> None:
        result = build_top5_opportunities(
            [
                self.candidate(
                    "ALAB",
                    rank=1,
                    data_status="Needs price",
                    provider_gaps=["Current price unavailable"],
                )
            ]
        )
        row = result["rows"][0]

        self.assertEqual(row["top_blocker"], RELIABILITY_BLOCKER_NOTE)
        self.assertIn("Current price unavailable", row["data_gap_summary"])
        self.assertNotIn("bearish", row["top_reason"].lower())

    def test_does_not_mutate_recommendation_input(self) -> None:
        rows = [
            self.candidate("MSFT", rank=1),
            self.candidate("SOUN", rank=2, sleeve="speculative_ai"),
        ]
        original = copy.deepcopy(rows)

        build_top5_opportunities(rows)

        self.assertEqual(rows, original)


if __name__ == "__main__":
    unittest.main()
