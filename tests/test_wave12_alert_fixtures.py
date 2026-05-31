#!/usr/bin/env python3
"""Wave 12 alert/review-trigger fixture contracts."""

from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "alerts"


EXPECTED_SCENARIOS = {
    "decision_gate_blocked_to_ready": "Decision gate changed from blocked to ready",
    "target_confidence_degraded": "Target confidence degraded",
    "provider_gap_resolved": "Provider gap resolved",
    "provider_gap_worsened": "Provider gap worsened",
    "price_move_above_threshold": "Price moved above threshold",
    "earnings_pre_window_entered": "Upcoming earnings entered pre-earnings window",
    "post_earnings_review_due": "Post-earnings review due",
    "source_catalyst_event": "New source/catalyst event",
    "ai_brief_ready": "AI brief ready",
    "ai_brief_guardrail_failed": "AI brief guardrail failed",
    "recommendation_outcome_threshold": "Recommendation outcome crossed review threshold",
    "tactical_setup_appeared": "Tactical setup appeared",
    "model_trust_changed": "Model trust changed",
    "capital_deployment_review": "Capital deployment review",
    "watchlist_readiness_changed": "Watchlist readiness changed",
    "duplicate_alerts_need_deduping": "Duplicate alerts need deduping",
    "alert_lifecycle_acknowledged_dismissed": "Alert acknowledged/dismissed lifecycle",
    "no_alerts": "No alerts",
}

ALERT_TYPES = {
    "decision_gate_changed",
    "target_confidence_changed",
    "provider_gap_resolved",
    "provider_gap_worsened",
    "price_move_review",
    "earnings_window_entered",
    "post_earnings_review_due",
    "source_event_review",
    "ai_brief_ready",
    "ai_brief_guardrail_failed",
    "recommendation_outcome_review",
    "tactical_setup_review",
    "model_trust_changed",
    "capital_deployment_review",
    "watchlist_readiness_changed",
}
ALERT_STATUSES = {"new", "seen", "acknowledged", "deferred", "dismissed", "resolved"}
SEVERITIES = {"critical_review", "high_review", "medium_review", "low_review", "informational"}
REQUIRED_GUARDRAILS = {
    "no_automatic_trading",
    "no_broker_write",
    "no_order_preview",
    "no_margin_account_trading_logic",
    "no_automatic_scoring_changes",
    "no_automatic_target_changes",
    "no_automatic_decision_safety_changes",
    "no_automatic_source_weight_changes",
    "no_model_tuning",
    "no_live_external_notifications",
    "no_automatic_recommendation_changes_from_alerts",
}
ALERT_FIELDS = {
    "alert_id",
    "alert_type",
    "status",
    "severity",
    "priority",
    "created_at",
    "symbol",
    "company",
    "decision_mode",
    "source",
    "event_summary",
    "why_review",
    "review_action",
    "prior_state",
    "current_state",
    "dedupe_key",
    "dedupe_group",
    "duplicate_of",
    "related_artifacts",
    "review_only_note",
}


def load_fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURE_DIR / f"{name}.json").read_text())


class Wave12AlertFixtureTests(unittest.TestCase):
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
                self.assertEqual(fixture["alert_layer"], "review_triggers")
                self.assertIs(fixture["review_only"], True)
                self.assertIs(fixture["recommendation_only"], True)
                self.assertIsInstance(fixture["alerts"], list)

                expected = fixture["expected_behavior"]
                self.assertIn("inbox_state", expected)
                self.assertIsInstance(expected["scenario_assertions"], list)
                self.assertIn("official_recommendation_unchanged", expected["scenario_assertions"])

                guardrails = fixture["guardrails"]
                self.assertEqual(set(guardrails), REQUIRED_GUARDRAILS)
                for value in guardrails.values():
                    self.assertIs(value, True)

                for alert in fixture["alerts"]:
                    self.assertEqual(set(alert), ALERT_FIELDS)
                    self.assertIn(alert["alert_type"], ALERT_TYPES)
                    self.assertIn(alert["status"], ALERT_STATUSES)
                    self.assertIn(alert["severity"], SEVERITIES)
                    self.assertIsInstance(alert["priority"], int)
                    self.assertIsInstance(alert["prior_state"], dict)
                    self.assertIsInstance(alert["current_state"], dict)
                    self.assertIsInstance(alert["related_artifacts"], list)
                    self.assertNotEqual(alert["dedupe_key"], "")
                    self.assertNotEqual(alert["review_only_note"], "")

    def test_alert_types_cover_required_taxonomy(self) -> None:
        found_types = {
            alert["alert_type"]
            for scenario_id in EXPECTED_SCENARIOS
            for alert in load_fixture(scenario_id)["alerts"]
        }

        self.assertEqual(found_types, ALERT_TYPES)

    def test_statuses_and_severities_cover_required_values(self) -> None:
        statuses = {
            alert["status"]
            for scenario_id in EXPECTED_SCENARIOS
            for alert in load_fixture(scenario_id)["alerts"]
        }
        severities = {
            alert["severity"]
            for scenario_id in EXPECTED_SCENARIOS
            for alert in load_fixture(scenario_id)["alerts"]
        }

        self.assertTrue(statuses.issubset(ALERT_STATUSES))
        self.assertIn("new", statuses)
        self.assertIn("acknowledged", statuses)
        self.assertIn("dismissed", statuses)
        self.assertEqual(severities, SEVERITIES)

    def test_deduplication_fixture_marks_duplicate_alerts(self) -> None:
        fixture = load_fixture("duplicate_alerts_need_deduping")
        alerts = fixture["alerts"]

        self.assertEqual(len(alerts), 2)
        self.assertEqual(alerts[0]["dedupe_key"], alerts[1]["dedupe_key"])
        self.assertEqual(alerts[1]["duplicate_of"], alerts[0]["alert_id"])
        self.assertIn("duplicate_of_set", fixture["expected_behavior"]["scenario_assertions"])

    def test_lifecycle_fixture_uses_local_status_metadata(self) -> None:
        fixture = load_fixture("alert_lifecycle_acknowledged_dismissed")
        statuses = {alert["status"] for alert in fixture["alerts"]}

        self.assertEqual(statuses, {"acknowledged", "dismissed"})
        self.assertIn("acknowledged_status_visible", fixture["expected_behavior"]["scenario_assertions"])
        self.assertIn("dismissed_status_visible", fixture["expected_behavior"]["scenario_assertions"])

    def test_no_alerts_fixture_does_not_invent_alerts(self) -> None:
        fixture = load_fixture("no_alerts")

        self.assertEqual(fixture["alerts"], [])
        self.assertEqual(fixture["expected_behavior"]["inbox_state"], "empty")
        self.assertIn("no_alerts_invented", fixture["expected_behavior"]["scenario_assertions"])

    def test_no_fixture_enables_trading_or_external_notifications(self) -> None:
        forbidden_phrases = ("execute trade", "send sms", "send email", "send slack")
        for scenario_id in EXPECTED_SCENARIOS:
            with self.subTest(scenario_id=scenario_id):
                fixture = load_fixture(scenario_id)
                serialized = json.dumps(fixture).lower()

                for phrase in forbidden_phrases:
                    self.assertNotIn(phrase, serialized)
                self.assertTrue(fixture["guardrails"]["no_live_external_notifications"])
                self.assertTrue(fixture["guardrails"]["no_automatic_recommendation_changes_from_alerts"])


if __name__ == "__main__":
    unittest.main()
