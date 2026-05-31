#!/usr/bin/env python3
"""Wave 8 earnings-review fixture contracts."""

from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "earnings"


EXPECTED_SCENARIOS = {
    "upcoming_strong_long_term_candidate": "Upcoming earnings with strong long-term candidate",
    "upcoming_decision_gate_blocked": "Upcoming earnings but decision gate blocked",
    "recent_positive_reaction": "Recent earnings positive reaction",
    "recent_negative_reaction_thesis_intact": "Recent earnings negative reaction but thesis intact",
    "recent_thesis_weakened": "Recent earnings thesis weakened",
    "missing_earnings_date": "Missing earnings date",
    "etf_not_applicable": "ETF not applicable",
    "foreign_issuer_different_filing_pattern": "Foreign issuer / different filing pattern",
    "provider_gap_blocks_earnings_confidence": "Provider gap blocks earnings confidence",
}

REQUIRED_GUARDRAILS = {
    "no_automatic_trading",
    "no_broker_write",
    "no_order_preview",
    "no_short_selling",
    "no_full_tactical_same_day_engine",
    "no_automatic_scoring_changes",
    "no_automatic_target_changes",
    "no_automatic_decision_safety_changes_from_ai",
    "no_automatic_model_tuning",
}

SIGNAL_FIELDS = {
    "guidance",
    "estimates",
    "margins",
    "revenue",
    "eps",
    "ai_capex_commentary",
    "risk_language",
    "market_reaction",
    "thesis_impact",
}

SIGNAL_DIRECTIONS = {"improved", "weakened", "mixed", "neutral", "missing", "not_applicable"}
CONTROLLED_ACTIONS = {"Strong Buy", "Buy", "Add", "Hold", "Watch", "Trim", "Avoid"}
EVENT_PHASES = {"pre_earnings", "post_earnings", "not_applicable"}
EVENT_STATUSES = {"upcoming", "recent", "missing_date", "not_applicable"}
EARNINGS_CONFIDENCE = {"high", "medium", "low", "not_applicable"}
PRE_REVIEW_DECISIONS = {
    "buy_before_earnings",
    "wait_for_earnings",
    "avoid_earnings_setup",
    "keep_watching",
    "not_applicable",
}
POST_REVIEW_DECISIONS = {
    "buy_after_earnings",
    "keep_watching",
    "avoid_earnings_setup",
    "not_applicable",
}


def load_fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURE_DIR / f"{name}.json").read_text())


class Wave8EarningsFixtureTests(unittest.TestCase):
    maxDiff = None

    def test_expected_fixture_set_exists(self) -> None:
        fixture_ids = {
            path.stem
            for path in FIXTURE_DIR.glob("*.json")
            if path.stem in EXPECTED_SCENARIOS
        }

        self.assertEqual(fixture_ids, set(EXPECTED_SCENARIOS))

    def test_common_fixture_contract(self) -> None:
        for scenario_id, scenario_label in EXPECTED_SCENARIOS.items():
            with self.subTest(scenario_id=scenario_id):
                fixture = load_fixture(scenario_id)

                self.assertEqual(fixture["scenario_id"], scenario_id)
                self.assertEqual(fixture["scenario_label"], scenario_label)
                self.assertEqual(fixture["decision_mode"], "earnings_event")
                self.assertIs(fixture["recommendation_only"], True)
                self.assertIn(fixture["scope"], {"owned", "watchlist", "approved_universe"})
                self.assertIn(fixture["event_phase"], EVENT_PHASES)

                event = fixture["earnings_event"]
                self.assertIsInstance(event, dict)
                for field in (
                    "earnings_date",
                    "time_of_day",
                    "fiscal_period",
                    "days_to_or_since_earnings",
                    "event_status",
                    "source",
                    "source_status",
                    "earnings_confidence",
                    "provider_gaps",
                    "filing_pattern",
                ):
                    self.assertIn(field, event)
                self.assertIn(event["event_status"], EVENT_STATUSES)
                self.assertIn(event["earnings_confidence"], EARNINGS_CONFIDENCE)
                self.assertIsInstance(event["provider_gaps"], list)

                recommendation = fixture["current_recommendation"]
                self.assertIn(recommendation["action"], CONTROLLED_ACTIONS)
                self.assertIn(recommendation["decision_gate_status"], {"Ready", "Blocked"})
                self.assertIsInstance(recommendation["safe_to_buy"], bool)

                review = fixture["review_decision"]
                self.assertIn(review["pre_earnings"], PRE_REVIEW_DECISIONS)
                self.assertIn(review["post_earnings"], POST_REVIEW_DECISIONS)
                self.assertEqual(review["official_recommendation_impact"], "none_review_only")

                self.assertEqual(set(fixture["earnings_signals"]), SIGNAL_FIELDS)
                for direction in fixture["earnings_signals"].values():
                    self.assertIn(direction, SIGNAL_DIRECTIONS)

                guardrails = fixture["guardrails"]
                self.assertEqual(REQUIRED_GUARDRAILS, set(guardrails))
                for value in guardrails.values():
                    self.assertIs(value, True)

                expected = fixture["expected_behavior"]
                self.assertIn("queue_status", expected)
                self.assertIn("review_label", expected)
                self.assertIsInstance(expected["scenario_assertions"], list)

    def test_pre_earnings_scenarios_have_upcoming_or_gap_status(self) -> None:
        for scenario_id in ("upcoming_strong_long_term_candidate", "upcoming_decision_gate_blocked", "missing_earnings_date"):
            with self.subTest(scenario_id=scenario_id):
                fixture = load_fixture(scenario_id)

                self.assertEqual(fixture["event_phase"], "pre_earnings")
                self.assertIn(fixture["earnings_event"]["event_status"], {"upcoming", "missing_date"})
                self.assertEqual(fixture["review_decision"]["post_earnings"], "not_applicable")

    def test_blocked_decision_gate_is_not_overridden(self) -> None:
        fixture = load_fixture("upcoming_decision_gate_blocked")

        self.assertEqual(fixture["current_recommendation"]["decision_gate_status"], "Blocked")
        self.assertIs(fixture["current_recommendation"]["safe_to_buy"], False)
        self.assertEqual(fixture["review_decision"]["pre_earnings"], "avoid_earnings_setup")
        self.assertIn("no_gate_override", fixture["expected_behavior"]["scenario_assertions"])

    def test_post_earnings_scenarios_capture_thesis_direction(self) -> None:
        expected_impacts = {
            "recent_positive_reaction": "improved",
            "recent_negative_reaction_thesis_intact": "neutral",
            "recent_thesis_weakened": "weakened",
        }
        for scenario_id, thesis_impact in expected_impacts.items():
            with self.subTest(scenario_id=scenario_id):
                fixture = load_fixture(scenario_id)

                self.assertEqual(fixture["event_phase"], "post_earnings")
                self.assertEqual(fixture["earnings_event"]["event_status"], "recent")
                self.assertEqual(fixture["earnings_signals"]["thesis_impact"], thesis_impact)
                self.assertEqual(fixture["review_decision"]["pre_earnings"], "not_applicable")

    def test_missing_earnings_date_keeps_provider_gap_visible(self) -> None:
        fixture = load_fixture("missing_earnings_date")
        event = fixture["earnings_event"]

        self.assertIsNone(event["earnings_date"])
        self.assertEqual(event["source_status"], "missing")
        self.assertEqual(event["earnings_confidence"], "low")
        self.assertIn("missing_earnings_date", event["provider_gaps"])
        self.assertIn("provider_gap_visible", fixture["expected_behavior"]["scenario_assertions"])

    def test_etf_is_not_applicable_not_provider_failure(self) -> None:
        fixture = load_fixture("etf_not_applicable")

        self.assertEqual(fixture["sleeve"], "etf_context")
        self.assertEqual(fixture["event_phase"], "not_applicable")
        self.assertEqual(fixture["earnings_event"]["source_status"], "not_applicable")
        self.assertEqual(fixture["earnings_event"]["provider_gaps"], [])
        self.assertTrue(all(value == "not_applicable" for value in fixture["earnings_signals"].values()))
        self.assertIn("not_provider_failure", fixture["expected_behavior"]["scenario_assertions"])

    def test_foreign_issuer_fixture_uses_different_filing_pattern(self) -> None:
        fixture = load_fixture("foreign_issuer_different_filing_pattern")
        event = fixture["earnings_event"]

        self.assertEqual(fixture["symbol"], "TSM")
        self.assertEqual(event["source_status"], "foreign_issuer_fallback")
        self.assertEqual(event["filing_pattern"], "foreign_issuer_20f_6k_ir")
        self.assertIn("sec_companyfacts_equivalent_needed", event["provider_gaps"])

    def test_provider_gap_can_block_earnings_confidence_only(self) -> None:
        fixture = load_fixture("provider_gap_blocks_earnings_confidence")
        event = fixture["earnings_event"]

        self.assertEqual(event["source_status"], "provider_gap")
        self.assertEqual(event["earnings_confidence"], "low")
        self.assertGreaterEqual(len(event["provider_gaps"]), 1)
        self.assertEqual(fixture["review_decision"]["official_recommendation_impact"], "none_review_only")
        self.assertIn("provider_gap_blocks_confidence", fixture["expected_behavior"]["scenario_assertions"])


if __name__ == "__main__":
    unittest.main()
