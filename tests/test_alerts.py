import copy
import unittest

from stock_trading.alerts import (
    ALERT_TYPES,
    RECOMMENDATION_ONLY_NOTE,
    SEVERITIES,
    STATUSES,
    ai_brief_alerts,
    build_alert,
    build_review_alerts,
    decision_gate_alerts,
    earnings_window_alerts,
    model_trust_alerts,
    provider_gap_alerts,
    recommendation_outcome_alerts,
    tactical_setup_alerts,
    validate_alert,
)


REPORT_DATE = "2026-05-31"
CREATED_AT = "2026-05-31T08:00:00"


class AlertModelTests(unittest.TestCase):
    def test_alert_row_creation_is_deterministic_and_review_only(self) -> None:
        first = build_alert(
            report_date=REPORT_DATE,
            created_at=CREATED_AT,
            symbol="msft",
            alert_type="price_move_review",
            severity="medium_review",
            title="MSFT price move needs review",
            summary="MSFT moved enough to review manually.",
            reason_codes=["price_move_review"],
            source_refs=["price_history:MSFT"],
            recommended_review_action="review_price_move",
        )
        second = build_alert(
            report_date=REPORT_DATE,
            created_at=CREATED_AT,
            symbol="MSFT",
            alert_type="price_move_review",
            severity="medium_review",
            title="MSFT price move needs review",
            summary="MSFT moved enough to review manually.",
            reason_codes=["price_move_review"],
            source_refs=["price_history:MSFT"],
            recommended_review_action="review_price_move",
        )

        self.assertEqual(first, second)
        self.assertTrue(first["alert_id"].startswith("alert_"))
        self.assertEqual(first["symbol"], "MSFT")
        self.assertEqual(first["status"], "new")
        self.assertTrue(first["review_only"])
        self.assertEqual(first["recommendation_only_note"], RECOMMENDATION_ONLY_NOTE)
        self.assertTrue(validate_alert(first)["ok"])
        for field in (
            "alert_id",
            "created_at",
            "report_date",
            "symbol",
            "alert_type",
            "severity",
            "status",
            "title",
            "summary",
            "reason_codes",
            "source_refs",
            "related_artifacts",
            "recommended_review_action",
            "dedupe_key",
            "expires_at",
            "review_only",
            "recommendation_only_note",
        ):
            self.assertIn(field, first)

    def test_alert_constants_include_required_contract_values(self) -> None:
        self.assertIn("decision_gate_changed", ALERT_TYPES)
        self.assertIn("ai_brief_guardrail_failed", ALERT_TYPES)
        self.assertIn("watchlist_readiness_changed", ALERT_TYPES)
        self.assertIn("critical_review", SEVERITIES)
        self.assertIn("informational", SEVERITIES)
        self.assertIn("acknowledged", STATUSES)
        self.assertIn("resolved", STATUSES)

    def test_invalid_alert_type_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_alert(
                report_date=REPORT_DATE,
                created_at=CREATED_AT,
                alert_type="trade_now",
                severity="medium_review",
                title="Invalid",
                summary="Invalid alert type.",
            )

    def test_invalid_severity_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_alert(
                report_date=REPORT_DATE,
                created_at=CREATED_AT,
                alert_type="price_move_review",
                severity="urgent_trade",
                title="Invalid",
                summary="Invalid severity.",
            )

    def test_review_only_guardrail_detects_missing_flag(self) -> None:
        alert = build_alert(
            report_date=REPORT_DATE,
            created_at=CREATED_AT,
            alert_type="price_move_review",
            severity="low_review",
            title="Review",
            summary="Manual review only.",
        )
        broken = dict(alert)
        broken["review_only"] = False

        result = validate_alert(broken)

        self.assertFalse(result["ok"])
        self.assertIn("review_only_required", result["errors"])


class AlertRuleEngineTests(unittest.TestCase):
    def test_decision_gate_alert(self) -> None:
        alerts = decision_gate_alerts(
            [
                {
                    "symbol": "NVDA",
                    "previous_status": "ready",
                    "current_status": "blocked",
                    "source_refs": ["decision_safety:NVDA"],
                }
            ],
            report_date=REPORT_DATE,
            created_at=CREATED_AT,
        )

        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["alert_type"], "decision_gate_changed")
        self.assertEqual(alerts[0]["severity"], "high_review")
        self.assertEqual(alerts[0]["recommended_review_action"], "review_decision_gate")
        self.assertIn("from_ready", alerts[0]["reason_codes"])
        self.assertIn("to_blocked", alerts[0]["reason_codes"])

    def test_provider_gap_alerts_for_resolved_and_worsened_gap(self) -> None:
        alerts = provider_gap_alerts(
            [
                {
                    "symbol": "AMD",
                    "provider": "finnhub",
                    "endpoint": "analyst_targets",
                    "previous_status": "blocked",
                    "current_status": "ok",
                },
                {
                    "symbol": "TSM",
                    "provider": "sec",
                    "field": "companyfacts",
                    "previous_status": "ok",
                    "current_status": "rate_limited",
                    "message": "Provider returned 429.",
                },
            ],
            report_date=REPORT_DATE,
            created_at=CREATED_AT,
        )

        self.assertEqual([alert["alert_type"] for alert in alerts], ["provider_gap_resolved", "provider_gap_worsened"])
        self.assertEqual(alerts[0]["severity"], "informational")
        self.assertEqual(alerts[1]["severity"], "high_review")
        self.assertIn("rate_limited", alerts[1]["reason_codes"])
        self.assertIn("Provider returned 429.", alerts[1]["summary"])

    def test_earnings_window_alert(self) -> None:
        alerts = earnings_window_alerts(
            [
                {
                    "symbol": "AAPL",
                    "earnings_date": "2026-06-06",
                    "event_type": "upcoming_earnings",
                    "days_until_earnings": 6,
                    "review_window": "pre_earnings",
                    "source": "fixture",
                }
            ],
            report_date=REPORT_DATE,
            created_at=CREATED_AT,
        )

        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["alert_type"], "earnings_window_entered")
        self.assertEqual(alerts[0]["recommended_review_action"], "review_pre_earnings_setup")

    def test_ai_guardrail_alert(self) -> None:
        alerts = ai_brief_alerts(
            [
                {
                    "symbol": "META",
                    "guardrail_result": {
                        "passed": False,
                        "failures": [{"category": "order_or_execution_language"}],
                    },
                    "audit_refs": ["brief:META"],
                }
            ],
            report_date=REPORT_DATE,
            created_at=CREATED_AT,
        )

        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["alert_type"], "ai_brief_guardrail_failed")
        self.assertEqual(alerts[0]["severity"], "high_review")
        self.assertIn("order_or_execution_language", alerts[0]["reason_codes"])

    def test_recommendation_outcome_alert(self) -> None:
        alerts = recommendation_outcome_alerts(
            [
                {
                    "symbol": "AVGO",
                    "window_trading_days": 20,
                    "outcome_status": "drawdown_warning",
                    "percent_change": -9.4,
                    "target_progress": -20.0,
                }
            ],
            report_date=REPORT_DATE,
            created_at=CREATED_AT,
        )

        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["alert_type"], "recommendation_outcome_review")
        self.assertEqual(alerts[0]["severity"], "high_review")
        self.assertIn("drawdown_warning", alerts[0]["reason_codes"])

    def test_tactical_setup_alert(self) -> None:
        alerts = tactical_setup_alerts(
            [
                {
                    "symbol": "CRM",
                    "setup_label": "breakout_review",
                    "review_action": "tactical_buy_review",
                    "setup_confidence": "medium",
                },
                {"symbol": "ORCL", "setup_label": "no_tactical_setup", "review_action": "hold_existing"},
            ],
            report_date=REPORT_DATE,
            created_at=CREATED_AT,
        )

        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["symbol"], "CRM")
        self.assertEqual(alerts[0]["alert_type"], "tactical_setup_review")
        self.assertEqual(alerts[0]["recommended_review_action"], "tactical_buy_review")

    def test_model_trust_alert(self) -> None:
        alerts = model_trust_alerts(
            [
                {
                    "model_name": "official_v1",
                    "previous_trust_level": "observe",
                    "current_trust_level": "assist",
                    "previous_trust_score": 42.0,
                    "current_trust_score": 57.0,
                }
            ],
            report_date=REPORT_DATE,
            created_at=CREATED_AT,
        )

        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["alert_type"], "model_trust_changed")
        self.assertEqual(alerts[0]["recommended_review_action"], "review_model_trust")

    def test_build_review_alerts_dedupes_and_marks_inbox_review_only(self) -> None:
        inbox = build_review_alerts(
            {
                "decision_gates": [
                    {"symbol": "NVDA", "previous_status": "ready", "current_status": "blocked"},
                    {"symbol": "NVDA", "previous_status": "ready", "current_status": "blocked"},
                ],
                "provider_gaps": [
                    {"symbol": "TSM", "provider": "sec", "field": "companyfacts", "current_status": "blocked"}
                ],
                "earnings_events": [
                    {"symbol": "AAPL", "event_type": "upcoming_earnings", "days_until_earnings": 2}
                ],
                "ai_briefs": [
                    {"symbol": "META", "guardrail_result": {"passed": False, "failures": [{"category": "missing_source_references"}]}}
                ],
                "recommendation_outcomes": [
                    {"symbol": "AVGO", "outcome_status": "target_progress", "percent_change": 7.0, "target_progress": 62}
                ],
                "tactical_setups": [
                    {"symbol": "CRM", "setup_label": "momentum_review", "review_action": "watch_intraday"}
                ],
                "model_trust": [
                    {"model_name": "official_v1", "previous_trust_score": 60, "current_trust_score": 50}
                ],
            },
            report_date=REPORT_DATE,
            created_at=CREATED_AT,
        )

        self.assertTrue(inbox["review_only"])
        self.assertTrue(inbox["recommendation_only"])
        self.assertEqual(inbox["alert_count"], 7)
        self.assertTrue(all(alert["review_only"] for alert in inbox["alerts"]))
        self.assertEqual(len({alert["dedupe_key"] for alert in inbox["alerts"]}), 7)

    def test_no_input_mutation(self) -> None:
        signals = {
            "decision_gates": [{"symbol": "NVDA", "previous_status": "ready", "current_status": "blocked"}],
            "provider_gaps": [{"symbol": "TSM", "provider": "sec", "field": "companyfacts", "current_status": "blocked"}],
            "earnings_events": [{"symbol": "AAPL", "event_type": "upcoming_earnings", "days_until_earnings": 2}],
            "ai_briefs": [{"symbol": "META", "guardrail_result": {"passed": False, "failures": [{"category": "missing_source_references"}]}}],
            "recommendation_outcomes": [{"symbol": "AVGO", "outcome_status": "target_progress", "percent_change": 7.0}],
            "tactical_setups": [{"symbol": "CRM", "setup_label": "momentum_review", "review_action": "watch_intraday"}],
            "model_trust": [{"model_name": "official_v1", "previous_trust_score": 60, "current_trust_score": 50}],
        }
        before = copy.deepcopy(signals)

        build_review_alerts(signals, report_date=REPORT_DATE, created_at=CREATED_AT)

        self.assertEqual(signals, before)


if __name__ == "__main__":
    unittest.main()
