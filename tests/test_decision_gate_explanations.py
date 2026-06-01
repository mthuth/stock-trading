#!/usr/bin/env python3
"""Tests for plain-English decision-gate explanations."""

from __future__ import annotations

import copy
import unittest

from stock_trading.decision_gate_explanations import explain_decision_gate


def explanation(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "action": "Add",
        "candidate_action": "Add",
        "decision_gate_status": "Blocked",
        "safe_to_buy": False,
        "blocked_reasons": [],
        "target_confidence": "Medium",
        "data_status": "Blended",
        "provider_gaps": [],
        "watchlist_policy": {"blocked": False},
        "current_price": 100.0,
        "allocation_safety": {},
    }
    row.update(overrides)
    return explain_decision_gate(row)


def group_names(result: dict[str, object]) -> set[str]:
    return {str(group.get("group")) for group in result["blocker_groups"]}


class DecisionGateExplanationTests(unittest.TestCase):
    def test_watch_action_blocked(self) -> None:
        result = explanation(
            action="Watch",
            candidate_action="Watch",
            blocked_reasons=["Watch action is not a buy action"],
        )

        self.assertEqual(result["plain_status"], "Not buy-ready yet")
        self.assertIn("action_not_buy_ready", group_names(result))
        self.assertIn("current model action is Watch", result["buyer_friendly_explanation"])
        self.assertIn("official action would need to upgrade", " ".join(result["what_would_make_buy_ready"]))

    def test_verification_open(self) -> None:
        result = explanation(blocked_reasons=["Verification check is still open"])

        self.assertIn("verification_open", group_names(result))
        self.assertIn("verification check still needs to clear", result["buyer_friendly_explanation"])
        self.assertIn("verification check would need to clear", " ".join(result["what_would_make_buy_ready"]))

    def test_missing_price(self) -> None:
        result = explanation(
            current_price=0,
            data_status="Needs price refresh",
            blocked_reasons=["Missing current price"],
        )

        self.assertIn("missing_price", group_names(result))
        self.assertEqual(result["missing_data_note"], "Data is incomplete, so confidence/readiness is reduced.")
        self.assertIn("not a bearish thesis", result["not_bearish_note"])
        self.assertIn("price data would need to refresh", " ".join(result["what_would_make_buy_ready"]))

    def test_provider_gap(self) -> None:
        result = explanation(
            blocked_reasons=["Required data gap is still open"],
            provider_gaps=[{"provider": "finnhub", "endpoint": "price_target", "status": "blocked"}],
        )

        self.assertIn("provider_gap", group_names(result))
        self.assertIn("Provider/source data gaps are reducing trust", result["buyer_friendly_explanation"])
        self.assertIn("provider/data gaps would need to resolve", " ".join(result["what_would_make_buy_ready"]))

    def test_low_target_confidence(self) -> None:
        result = explanation(target_confidence="Low", blocked_reasons=["Low target confidence"])

        self.assertIn("low_target_confidence", group_names(result))
        self.assertIn("Target confidence is too low", result["plain_summary"])
        self.assertIn("Target confidence would need to improve", " ".join(result["what_would_make_buy_ready"]))

    def test_watchlist_only(self) -> None:
        result = explanation(
            blocked_reasons=["Speculative AI watchlist-only block"],
            watchlist_policy={"blocked": True, "reason": "Speculative AI watchlist-only block"},
        )

        self.assertIn("watchlist_only", group_names(result))
        self.assertIn("watchlist policy blocks", result["buyer_friendly_explanation"])
        self.assertIn("watchlist-only policy would need to clear", " ".join(result["what_would_make_buy_ready"]))

    def test_allocation_blocked(self) -> None:
        result = explanation(
            blocked_reasons=["Allocation cap leaves no buy capacity"],
            allocation_safety={"applied_limit": "allocation_cap", "suggested_amount": 0},
        )

        self.assertIn("allocation_blocked", group_names(result))
        self.assertIn("allocation limits or buy capacity", result["buyer_friendly_explanation"])
        self.assertIn("Allocation capacity would need to be available", " ".join(result["what_would_make_buy_ready"]))

    def test_no_safe_buy(self) -> None:
        result = explanation(blocked_reasons=["No ranked candidates available"])

        self.assertIn("no_decision_safe_buy", group_names(result))
        self.assertIn("not buy-ready yet", result["buyer_friendly_explanation"])
        self.assertIn("decision gate would need to move to Ready", " ".join(result["what_would_make_buy_ready"]))

    def test_missing_data_not_treated_as_bearish_thesis(self) -> None:
        result = explanation(
            current_price=0,
            data_status="Needs price refresh",
            blocked_reasons=["Missing current price", "Required data gap is still open"],
        )

        text = " ".join(
            [
                result["plain_summary"],
                result["buyer_friendly_explanation"],
                result["missing_data_note"],
                result["not_bearish_note"],
            ]
        ).lower()
        self.assertIn("data is incomplete", text)
        self.assertIn("not a bearish thesis", text)
        self.assertNotIn("bad company", text)
        self.assertNotIn("bearish by itself", text.replace("not a bearish thesis by itself", ""))

    def test_decision_safe_buy(self) -> None:
        result = explanation(
            decision_gate_status="Ready",
            safe_to_buy=True,
            blocked_reasons=[],
            action="Add",
            candidate_action="Add",
        )

        self.assertEqual(result["plain_status"], "Decision-safe buy/add candidate")
        self.assertEqual(result["blocker_groups"], [])
        self.assertEqual(result["what_would_make_buy_ready"], [])

    def test_no_input_mutation(self) -> None:
        inputs = {
            "action": "Watch",
            "safe_to_buy": False,
            "blocked_reasons": ["Watch action is not a buy action"],
            "watchlist_policy": {"blocked": False},
        }
        before = copy.deepcopy(inputs)

        explain_decision_gate(inputs)

        self.assertEqual(inputs, before)


if __name__ == "__main__":
    unittest.main()
