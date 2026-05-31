#!/usr/bin/env python3
"""Watchlist-only policy regression tests."""

from __future__ import annotations

import unittest

from scripts import generate_daily_report as subject
from stock_trading.watchlist_policy import evaluate_watchlist_policy


CONTROLLED_LABELS = {"Strong Buy", "Buy", "Add", "Hold", "Watch", "Trim", "Avoid"}
WATCHLIST_REASON = (
    "Speculative AI names remain watchlist-only until observation time, "
    "evidence quality, and target confidence are strong enough for buy-readiness."
)


def watchlist_targets() -> dict[str, object]:
    return {
        "speculative_ai": {
            "watchlist_only_days": 21,
            "allow_buy_recommendations": False,
            "symbols": ["SOUN", "AEHR", "BBAI", "ALAB", "PLAB"],
            "eligibility_reason": WATCHLIST_REASON,
            "eligibility_requirements": [
                "Complete the configured observation period.",
                "Refresh primary-source and company evidence.",
            ],
            "confidence_requirements": [
                "Medium or High target confidence.",
                "No decision-safety blocking insight.",
            ],
        }
    }


def research_input(symbol: str = "SOUN", sleeve: str = "speculative_ai") -> subject.ResearchInput:
    return subject.ResearchInput(
        symbol=symbol,
        company=f"{symbol} Corp",
        category="Speculative AI/small-mid cap" if sleeve == "speculative_ai" else "Mega-cap AI/platform",
        sleeve=sleeve,
        trade_type="tactical_2_4_week" if sleeve == "speculative_ai" else "long_term",
        current_price=10.0,
        target_price=25.0,
        quality_score=98.0,
        momentum_score=98.0,
        catalyst_score=98.0,
        risk_score=90.0,
        confidence="High",
        notes="High-score test fixture.",
        price_source="fixture",
        target_source="fixture",
        estimate_source="",
        sentiment_source="",
        eps_estimate="",
        revenue_estimate="",
        news_sentiment="",
        provider_notes="",
    )


def blended_target(symbol: str = "SOUN", upside: float = 150.0) -> subject.BlendedTarget:
    return subject.BlendedTarget(
        symbol=symbol,
        target_price=25.0,
        target_low=22.0,
        target_high=28.0,
        current_price=10.0,
        upside_pct=upside,
        confidence="high",
        source_count=3,
        blend_status="Analyst + fundamental + technical",
        sources_label="Fixture blend",
        notes="Fixture target",
    )


def score_breakdown(total: float = 95.0) -> subject.ScoreBreakdown:
    return subject.ScoreBreakdown(
        total=total,
        upside=20.0,
        quality=25.0,
        momentum=20.0,
        catalyst=15.0,
        risk=15.0,
        owned_penalty=0.0,
        speculative_penalty=0.0,
        model="Long-term",
    )


def decision_row(action: str = "Add", item: subject.ResearchInput | None = None) -> dict[str, object]:
    row_item = item or research_input()
    return {
        "input": row_item,
        "target": blended_target(row_item.symbol),
        "action": action,
        "score": 95.0,
        "breakdown": score_breakdown(),
        "position_after_buy_pct": 2.0,
    }


class WatchlistPolicyTests(unittest.TestCase):
    def test_watchlist_only_symbol_with_high_score_does_not_become_buy_label(self) -> None:
        item = research_input("SOUN", "speculative_ai")

        action = subject.action_for(item, 99.0, 2.0, watchlist_targets())

        self.assertEqual(action, "Watch")
        self.assertIn(action, CONTROLLED_LABELS)

    def test_watchlist_only_symbol_with_strong_upside_keeps_score_math_but_blocks_buy_label(self) -> None:
        item = research_input("ALAB", "speculative_ai")
        target = blended_target("ALAB", upside=180.0)
        before = subject.score_stock(item, {}, target)
        policy = evaluate_watchlist_policy(item.symbol, item.sleeve, watchlist_targets())
        after = subject.score_stock(item, {}, target)

        action = subject.action_for(item, after.total, 2.0, watchlist_targets())

        self.assertEqual(before, after)
        self.assertTrue(policy["blocked"])
        self.assertEqual(action, "Watch")

    def test_watchlist_only_symbol_is_blocked_by_decision_safety(self) -> None:
        gate = subject.decision_safety_gate(decision_row("Add"), targets=watchlist_targets())

        self.assertFalse(gate["safe_to_buy"])
        self.assertEqual(gate["status"], "Blocked")
        self.assertIn(WATCHLIST_REASON, gate["reasons"])
        self.assertTrue(gate["watchlist_policy"]["blocked"])

    def test_non_watchlist_symbol_is_unaffected(self) -> None:
        item = research_input("MSFT", "long_term")

        action = subject.action_for(item, 92.0, 2.0, watchlist_targets())
        gate = subject.decision_safety_gate(decision_row(action, item), targets=watchlist_targets())

        self.assertEqual(action, "Add")
        self.assertTrue(gate["safe_to_buy"])
        self.assertFalse(gate["watchlist_policy"]["blocked"])

    def test_missing_watchlist_policy_does_not_block_non_watchlist_candidate(self) -> None:
        item = research_input("MSFT", "long_term")

        action = subject.action_for(item, 92.0, 2.0, {})
        gate = subject.decision_safety_gate(decision_row(action, item), targets={})

        self.assertEqual(action, "Add")
        self.assertTrue(gate["safe_to_buy"])
        self.assertFalse(gate["watchlist_policy"]["blocked"])

    def test_configured_reason_is_available_for_report_context_decision_gate(self) -> None:
        item = research_input("BBAI", "speculative_ai")
        action = subject.action_for(item, 96.0, 2.0, watchlist_targets())

        gate = subject.decision_safety_gate(decision_row(action, item), targets=watchlist_targets())

        self.assertEqual(action, "Watch")
        self.assertEqual(gate["candidate_action"], "Watch")
        self.assertEqual(gate["watchlist_policy"]["reason"], WATCHLIST_REASON)
        self.assertIn(WATCHLIST_REASON, gate["summary"])

    def test_legacy_speculative_config_without_symbols_still_blocks_speculative_ai(self) -> None:
        item = research_input("SOUN", "speculative_ai")

        action = subject.action_for(item, 95.0, 2.0, {"speculative_ai": {"allow_buy_recommendations": False}})

        self.assertEqual(action, "Watch")


if __name__ == "__main__":
    unittest.main()
