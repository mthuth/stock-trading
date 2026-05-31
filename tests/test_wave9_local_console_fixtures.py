#!/usr/bin/env python3
"""Wave 9 local decision-console fixture contracts."""

from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "local_console"


EXPECTED_SCENARIOS = {
    "latest_long_term_capital_deployment_available": "Latest long-term capital deployment available",
    "no_safe_add_hold_capital": "No safe add / hold capital",
    "earnings_review_pending": "Earnings review pending",
    "ai_brief_draft_reviewed_rejected_states": "AI brief draft/reviewed/rejected states",
    "provider_gaps_present": "Provider gaps present",
    "learning_review_with_outcomes_journal": "Learning review with outcomes/journal",
    "no_learning_history_yet": "No learning history yet",
    "missing_latest_report_context": "Missing latest report context",
    "no_generated_artifacts": "No generated artifacts",
}

REQUIRED_GUARDRAILS = {
    "no_automatic_trading",
    "no_broker_write",
    "no_order_preview",
    "no_real_time_market_monitoring",
    "no_run_control_execution_yet",
    "no_live_provider_refresh_from_console",
    "no_score_target_decision_safety_changes",
    "no_automatic_source_weight_changes",
    "no_automatic_recommendation_changes_from_feedback_or_outcomes",
    "no_future_short_candidate_in_buy_add",
}

REQUIRED_PANELS = {
    "latest_recommendation",
    "long_term_add",
    "capital_deployment",
    "earnings_review",
    "provider_gaps",
    "ai_briefs",
    "manual_journal",
    "learning_review",
    "run_history",
    "artifacts",
}

PANEL_STATES = {"available", "empty", "missing", "pending", "review_needed", "not_applicable"}
RUN_STATUSES = {"success", "ok_with_warnings", "failed", "missing", "not_run"}
ARTIFACT_STATUSES = {"available", "missing", "stale", "not_applicable"}
AI_BRIEF_STATUSES = {"draft", "reviewed", "rejected"}
AI_GUARDRAIL_STATUSES = {"pending_review", "passed", "failed"}


def load_fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURE_DIR / f"{name}.json").read_text())


def panel_map(fixture: dict[str, object]) -> dict[str, dict[str, object]]:
    panels = fixture["panels"]
    assert isinstance(panels, list)
    return {str(panel["panel_id"]): panel for panel in panels}


class Wave9LocalConsoleFixtureTests(unittest.TestCase):
    maxDiff = None

    def test_expected_fixture_set_exists(self) -> None:
        fixture_ids = {path.stem for path in FIXTURE_DIR.glob("*.json")}

        self.assertEqual(fixture_ids, set(EXPECTED_SCENARIOS))

    def test_common_fixture_contract(self) -> None:
        for scenario_id, scenario_label in EXPECTED_SCENARIOS.items():
            with self.subTest(scenario_id=scenario_id):
                fixture = load_fixture(scenario_id)

                self.assertEqual(fixture["scenario_id"], scenario_id)
                self.assertEqual(fixture["scenario_label"], scenario_label)
                self.assertEqual(fixture["console_mode"], "local_decision_console")
                self.assertIs(fixture["recommendation_only"], True)
                self.assertIs(fixture["read_only"], True)
                self.assertIn("report_date", fixture)

                run = fixture["latest_run"]
                self.assertIn(run["status"], RUN_STATUSES)
                for field in ("run_id", "run_type", "commands", "artifacts", "warnings", "errors"):
                    self.assertIn(field, run)
                self.assertIsInstance(run["commands"], list)
                self.assertIsInstance(run["artifacts"], list)
                self.assertIsInstance(run["warnings"], list)
                self.assertIsInstance(run["errors"], list)

                artifacts = fixture["latest_artifacts"]
                self.assertIsInstance(artifacts["items"], list)
                self.assertIsInstance(artifacts["missing"], list)
                for artifact in artifacts["items"]:
                    for field in ("artifact_id", "artifact_type", "path", "report_date", "status", "source", "notes"):
                        self.assertIn(field, artifact)
                    self.assertIn(artifact["status"], ARTIFACT_STATUSES)
                    self.assertIsInstance(artifact["notes"], list)

                snapshot = fixture["latest_decision_snapshot"]
                for field in (
                    "status",
                    "latest_recommendation_review",
                    "top_recommendation",
                    "best_long_term_add",
                    "capital_deployment_status",
                    "earnings_review_status",
                    "provider_gap_status",
                    "ai_brief_status",
                    "learning_review_status",
                ):
                    self.assertIn(field, snapshot)

                panels = panel_map(fixture)
                self.assertEqual(set(panels), REQUIRED_PANELS)
                for panel in panels.values():
                    for field in ("panel_id", "title", "state", "source", "read_only", "empty_state", "last_updated"):
                        self.assertIn(field, panel)
                    self.assertIn(panel["state"], PANEL_STATES)
                    self.assertIs(panel["read_only"], True)

                expected = fixture["expected_behavior"]
                self.assertIn("primary_console_state", expected)
                self.assertIn("scenario_assertions", expected)
                self.assertIsInstance(expected["scenario_assertions"], list)

                boundaries = fixture["future_boundaries"]
                self.assertEqual(boundaries["run_control"], "not_in_scope_view_only")
                self.assertEqual(boundaries["intraday"], "not_in_scope_not_real_time")
                self.assertEqual(boundaries["broker_read_only"], "future_optional_read_only")

                guardrails = fixture["guardrails"]
                self.assertEqual(REQUIRED_GUARDRAILS, set(guardrails))
                for value in guardrails.values():
                    self.assertIs(value, True)

    def test_latest_long_term_deployment_is_decision_ready(self) -> None:
        fixture = load_fixture("latest_long_term_capital_deployment_available")
        snapshot = fixture["latest_decision_snapshot"]

        self.assertEqual(snapshot["status"], "available")
        self.assertEqual(snapshot["best_long_term_add"]["symbol"], "MSFT")
        self.assertTrue(snapshot["best_long_term_add"]["safe_to_buy"])
        self.assertEqual(snapshot["capital_deployment_status"], "deploy_review")
        self.assertIn("best_long_term_add_visible", fixture["expected_behavior"]["scenario_assertions"])

    def test_no_safe_add_holds_buy_capacity(self) -> None:
        fixture = load_fixture("no_safe_add_hold_capital")
        snapshot = fixture["latest_decision_snapshot"]
        panels = panel_map(fixture)

        self.assertIsNone(snapshot["best_long_term_add"])
        self.assertEqual(snapshot["capital_deployment_status"], "hold_buy_capacity")
        self.assertEqual(panels["long_term_add"]["state"], "review_needed")
        self.assertIn("buy_capacity_held", fixture["expected_behavior"]["scenario_assertions"])

    def test_earnings_review_pending_routes_attention(self) -> None:
        fixture = load_fixture("earnings_review_pending")
        panels = panel_map(fixture)

        self.assertEqual(fixture["earnings_review"]["status"], "review_needed")
        self.assertEqual(fixture["earnings_review"]["recommended_review_action"], "review_pre_earnings")
        self.assertEqual(panels["earnings_review"]["state"], "review_needed")
        self.assertIn("recommendation_unchanged", fixture["expected_behavior"]["scenario_assertions"])

    def test_ai_brief_states_are_visible_and_explanatory_only(self) -> None:
        fixture = load_fixture("ai_brief_draft_reviewed_rejected_states")
        statuses = {brief["status"] for brief in fixture["ai_briefs"]}
        guardrail_statuses = {brief["guardrail_status"] for brief in fixture["ai_briefs"]}

        self.assertEqual(statuses, AI_BRIEF_STATUSES)
        self.assertEqual(guardrail_statuses, AI_GUARDRAIL_STATUSES)
        self.assertIn("ai_explanatory_only", fixture["expected_behavior"]["scenario_assertions"])

    def test_provider_gaps_are_visible_without_live_refresh(self) -> None:
        fixture = load_fixture("provider_gaps_present")
        panels = panel_map(fixture)
        statuses = {gap["status"] for gap in fixture["provider_gaps"]}

        self.assertEqual(panels["provider_gaps"]["state"], "review_needed")
        self.assertEqual(statuses, {"blocked", "missing", "stale"})
        self.assertIn("no_live_refresh", fixture["expected_behavior"]["scenario_assertions"])

    def test_learning_review_handles_present_and_missing_history(self) -> None:
        with_history = load_fixture("learning_review_with_outcomes_journal")
        no_history = load_fixture("no_learning_history_yet")

        self.assertTrue(with_history["learning_review"]["outcomes_available"])
        self.assertGreater(len(with_history["manual_journal"]), 0)
        self.assertEqual(no_history["learning_review"]["status"], "not_enough_history")
        self.assertEqual(no_history["manual_journal"], [])
        self.assertIn("learning_empty_state_visible", no_history["expected_behavior"]["scenario_assertions"])

    def test_missing_context_and_no_artifacts_do_not_invent_recommendations(self) -> None:
        for scenario_id in ("missing_latest_report_context", "no_generated_artifacts"):
            with self.subTest(scenario_id=scenario_id):
                fixture = load_fixture(scenario_id)
                snapshot = fixture["latest_decision_snapshot"]

                self.assertEqual(snapshot["status"], "missing")
                self.assertIsNone(snapshot["top_recommendation"])
                self.assertIsNone(snapshot["best_long_term_add"])
                self.assertIn("no_recommendation_invented", fixture["expected_behavior"]["scenario_assertions"])

    def test_wave9_fixtures_do_not_enable_console_execution(self) -> None:
        for scenario_id in EXPECTED_SCENARIOS:
            with self.subTest(scenario_id=scenario_id):
                fixture = load_fixture(scenario_id)
                run = fixture["latest_run"]

                self.assertNotIn("commands_enabled", fixture)
                self.assertIsInstance(run["commands"], list)
                self.assertEqual(fixture["future_boundaries"]["run_control"], "not_in_scope_view_only")
                self.assertTrue(fixture["guardrails"]["no_run_control_execution_yet"])
                self.assertTrue(fixture["guardrails"]["no_live_provider_refresh_from_console"])


if __name__ == "__main__":
    unittest.main()
