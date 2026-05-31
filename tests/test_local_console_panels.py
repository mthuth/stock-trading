#!/usr/bin/env python3
"""Tests for read-only local decision-console panel helpers."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from stock_trading.local_console_panels import (
    GUARDRAIL_TEXT,
    build_ai_briefs_panel,
    build_artifacts_run_history_panel,
    build_capital_deployment_panel,
    build_current_decision_panel,
    build_earnings_review_panel,
    build_learning_review_panel,
    build_local_console_panels,
    build_manual_journal_outcomes_panel,
    build_provider_gaps_panel,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "local_console" / "panels_context.json"


class LocalConsolePanelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.context = json.loads(FIXTURE.read_text())

    def assert_guardrails(self, panel: dict[str, object]) -> None:
        self.assertIs(panel["review_only"], True)
        self.assertIs(panel["recommendation_only"], True)
        self.assertIn("No trades", str(panel["guardrail"]))
        self.assertIn("order previews", str(panel["guardrail"]))
        self.assertIn("broker writes", str(panel["guardrail"]))
        self.assertEqual(panel["guardrail"], GUARDRAIL_TEXT)

    def test_current_decision_panel_with_data(self) -> None:
        panel = build_current_decision_panel(self.context["summary"])

        self.assertEqual(panel["id"], "current_decision")
        self.assertEqual(panel["status"], "passed")
        self.assertEqual(panel["items"][0]["top_symbol"], "NVDA")
        self.assertEqual(panel["items"][0]["top_action"], "Add")
        self.assertEqual(panel["items"][0]["suggested_amount_text"], "$2,500.00")
        self.assertIs(panel["items"][0]["safe_to_buy"], True)
        self.assert_guardrails(panel)

    def test_current_decision_panel_with_blocked_candidate(self) -> None:
        summary = copy.deepcopy(self.context["summary"])
        summary["decision_gate"] = {
            "status": "blocked",
            "safe_to_buy": False,
            "reasons": ["Target confidence is too low"],
        }

        panel = build_current_decision_panel(summary)

        self.assertEqual(panel["status"], "blocked")
        self.assertEqual(panel["warnings"], ["Target confidence is too low"])
        self.assertIs(panel["items"][0]["safe_to_buy"], False)
        self.assert_guardrails(panel)

    def test_capital_deployment_panel_with_data(self) -> None:
        panel = build_capital_deployment_panel(self.context["long_term_capital_deployment"])

        self.assertEqual(panel["id"], "capital_deployment")
        self.assertEqual(panel["status"], "deployable")
        self.assertEqual(panel["items"][0]["primary_symbol"], "NVDA")
        self.assertEqual(panel["items"][0]["fallback_symbol"], "MSFT")
        self.assertEqual(panel["items"][0]["deployable_amount_text"], "$2,500.00")
        self.assert_guardrails(panel)

    def test_earnings_review_panel_with_warning_state(self) -> None:
        panel = build_earnings_review_panel(self.context["earnings_review"])

        self.assertEqual(panel["id"], "earnings_review")
        self.assertEqual(panel["status"], "warning")
        self.assertEqual(panel["items"][0]["upcoming_count"], 1)
        self.assertEqual(panel["items"][0]["recent_count"], 1)
        self.assertEqual(panel["items"][0]["provider_gap_count"], 1)
        self.assertIn("PANW: Calendar provider blocked", panel["warnings"])
        self.assert_guardrails(panel)

    def test_provider_gaps_panel_with_stale_and_warning_state(self) -> None:
        panel = build_provider_gaps_panel(self.context["source_health"])

        self.assertEqual(panel["id"], "provider_gaps")
        self.assertEqual(panel["status"], "warning")
        self.assertIs(panel["stale"], True)
        self.assertTrue(any("Provider plan/access blocker" in warning for warning in panel["warnings"]))
        self.assert_guardrails(panel)

    def test_provider_gaps_panel_with_stale_only_state(self) -> None:
        source_health = {
            "summary": {"stale": 2},
            "provider_blockers": {"headers": [], "rows": []},
            "alerts": {"headers": [], "rows": []},
        }

        panel = build_provider_gaps_panel(source_health)

        self.assertEqual(panel["status"], "stale")
        self.assertIs(panel["stale"], True)
        self.assert_guardrails(panel)

    def test_ai_briefs_panel_with_data(self) -> None:
        panel = build_ai_briefs_panel(self.context["ai_briefs"])

        self.assertEqual(panel["id"], "ai_briefs")
        self.assertEqual(panel["status"], "passed")
        self.assertEqual(panel["items"][0]["symbol"], "NVDA")
        self.assertEqual(panel["items"][0]["guardrail_status"], "passed")
        self.assert_guardrails(panel)

    def test_ai_briefs_panel_accepts_string_warnings(self) -> None:
        brief_data = copy.deepcopy(self.context["ai_briefs"])
        brief_data["guardrails"]["status"] = "warning"
        brief_data["guardrails"]["warnings"] = ["Company-only evidence needs review"]

        panel = build_ai_briefs_panel(brief_data)

        self.assertEqual(panel["status"], "warning")
        self.assertEqual(panel["warnings"], ["Company-only evidence needs review"])
        self.assert_guardrails(panel)

    def test_learning_review_panel_with_data(self) -> None:
        panel = build_learning_review_panel(self.context["learning_review"])

        self.assertEqual(panel["id"], "learning_review")
        self.assertEqual(panel["status"], "ready")
        self.assertEqual(len(panel["items"]), 5)
        self.assertIn("do not tune recommendations", panel["summary"])
        self.assert_guardrails(panel)

    def test_manual_journal_outcomes_panel_with_data(self) -> None:
        panel = build_manual_journal_outcomes_panel(
            {
                "manual_journal": self.context["manual_journal"],
                "recommendation_outcomes": self.context["recommendation_outcomes"],
            }
        )

        self.assertEqual(panel["id"], "manual_journal_outcomes")
        self.assertEqual(panel["status"], "ready")
        self.assertEqual(panel["items"][0]["manual_journal_count"], 2)
        self.assertEqual(panel["items"][0]["recommendation_outcome_count"], 1)
        self.assert_guardrails(panel)

    def test_artifacts_run_history_panel_with_stale_artifact(self) -> None:
        panel = build_artifacts_run_history_panel(
            {
                "artifacts": self.context["artifacts"],
                "run_history": self.context["run_history"],
            }
        )

        self.assertEqual(panel["id"], "artifacts_run_history")
        self.assertEqual(panel["status"], "stale")
        self.assertIs(panel["stale"], True)
        self.assertTrue(any("context" in warning for warning in panel["warnings"]))
        self.assertTrue(any("run" in item for item in panel["items"]))
        self.assert_guardrails(panel)

    def test_missing_data_for_each_panel(self) -> None:
        builders = (
            build_current_decision_panel,
            build_capital_deployment_panel,
            build_earnings_review_panel,
            build_provider_gaps_panel,
            build_ai_briefs_panel,
            build_learning_review_panel,
            build_manual_journal_outcomes_panel,
            build_artifacts_run_history_panel,
        )

        for builder in builders:
            with self.subTest(builder=builder.__name__):
                panel = builder({})
                self.assertEqual(panel["status"], "missing")
                self.assertIs(panel["missing_data"], True)
                self.assert_guardrails(panel)

    def test_composed_panels_are_deterministic_and_do_not_mutate_input(self) -> None:
        original = copy.deepcopy(self.context)

        first = build_local_console_panels(self.context)
        second = build_local_console_panels(self.context)

        self.assertEqual(self.context, original)
        self.assertEqual(first, second)
        self.assertEqual(
            set(first),
            {
                "current_decision",
                "capital_deployment",
                "earnings_review",
                "provider_gaps",
                "ai_briefs",
                "learning_review",
                "manual_journal_outcomes",
                "artifacts_run_history",
            },
        )
        for panel in first.values():
            self.assert_guardrails(panel)


if __name__ == "__main__":
    unittest.main()
