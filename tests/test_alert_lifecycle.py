#!/usr/bin/env python3
"""Tests for review-only alert deduplication and lifecycle helpers."""

from __future__ import annotations

import copy
import unittest

from stock_trading import alert_lifecycle as subject


def alert(
    *,
    alert_type: str = "decision_gate_changed",
    symbol: str = "MSFT",
    report_date: str = "2026-05-31",
    reason_codes: list[str] | None = None,
    source_refs: list[str] | None = None,
    severity: str = "medium",
    status: str = "new",
    created_at: str = "2026-05-31T09:00:00Z",
    updated_at: str = "",
    dedupe_key: str = "",
) -> dict[str, object]:
    return {
        "alert_type": alert_type,
        "symbol": symbol,
        "report_date": report_date,
        "reason_codes": reason_codes or ["decision_gate_blocked"],
        "source_refs": source_refs or ["report-context-2026-05-31.json#MSFT"],
        "severity": severity,
        "status": status,
        "created_at": created_at,
        "updated_at": updated_at,
        "summary": "Decision gate changed for MSFT.",
        **({"dedupe_key": dedupe_key} if dedupe_key else {}),
    }


class AlertLifecycleTests(unittest.TestCase):
    def test_duplicate_collapse_uses_same_dedupe_key(self) -> None:
        rows = [
            alert(dedupe_key="manual-key", created_at="2026-05-31T09:00:00Z"),
            alert(dedupe_key="manual-key", created_at="2026-05-31T10:00:00Z", source_refs=["dashboard.html#MSFT"]),
        ]

        result = subject.dedupe_alerts(rows)

        self.assertEqual(result["duplicate_count"], 1)
        self.assertEqual(len(result["alerts"]), 1)
        item = result["alerts"][0]
        self.assertEqual(item["dedupe_key"], "manual-key")
        self.assertEqual(item["occurrence_count"], 2)
        self.assertEqual(item["created_at"], "2026-05-31T10:00:00Z")
        self.assertEqual(item["updated_at"], "2026-05-31T10:00:00Z")
        self.assertEqual(item["source_refs"], ["dashboard.html#MSFT", "report-context-2026-05-31.json#MSFT"])

    def test_duplicate_without_key_uses_stable_alert_inputs(self) -> None:
        first = alert(reason_codes=["provider_gap", "target_confidence_low"], source_refs=["a", "b"])
        second = alert(reason_codes=["target_confidence_low", "provider_gap"], source_refs=["b", "a"])

        self.assertEqual(subject.dedupe_key_for(first), subject.dedupe_key_for(second))

    def test_severity_escalation_preserves_highest_severity(self) -> None:
        result = subject.dedupe_alerts(
            [
                alert(dedupe_key="gap", severity="low", created_at="2026-05-31T09:00:00Z"),
                alert(dedupe_key="gap", severity="high", created_at="2026-05-31T10:00:00Z"),
            ]
        )

        item = result["alerts"][0]
        self.assertEqual(item["severity"], "high")
        self.assertEqual(item["status"], "new")
        self.assertEqual(item["lifecycle_event"], "renewed")

    def test_acknowledged_alert_preserved_for_same_or_lower_severity_duplicate(self) -> None:
        result = subject.dedupe_alerts(
            [
                alert(dedupe_key="known", severity="high", status="acknowledged", created_at="2026-05-31T09:00:00Z"),
                alert(dedupe_key="known", severity="medium", status="new", created_at="2026-05-31T10:00:00Z"),
            ]
        )

        item = result["alerts"][0]
        self.assertEqual(item["status"], "acknowledged")
        self.assertEqual(item["severity"], "high")
        self.assertEqual(item["lifecycle_event"], "preserved")

    def test_dismissed_alert_not_revived_by_low_severity_duplicate(self) -> None:
        result = subject.dedupe_alerts(
            [
                alert(dedupe_key="dismissed-gap", severity="high", status="dismissed", created_at="2026-05-31T09:00:00Z"),
                alert(dedupe_key="dismissed-gap", severity="low", status="new", created_at="2026-05-31T10:00:00Z"),
            ]
        )

        item = result["alerts"][0]
        self.assertEqual(item["status"], "dismissed")
        self.assertEqual(item["lifecycle_event"], "preserved")

    def test_high_severity_duplicate_renews_dismissed_review_item(self) -> None:
        result = subject.dedupe_alerts(
            [
                alert(dedupe_key="dismissed-gap", severity="medium", status="dismissed", created_at="2026-05-31T09:00:00Z"),
                alert(dedupe_key="dismissed-gap", severity="critical", status="new", created_at="2026-05-31T10:00:00Z"),
            ]
        )

        item = result["alerts"][0]
        self.assertEqual(item["status"], "new")
        self.assertEqual(item["severity"], "critical")
        self.assertEqual(item["lifecycle_event"], "renewed")

    def test_valid_lifecycle_transitions(self) -> None:
        seen = subject.transition_alert_status(alert(), "seen", changed_at="2026-05-31T10:00:00Z")
        acknowledged = subject.transition_alert_status(seen["alert"], "acknowledged", changed_at="2026-05-31T10:05:00Z")
        deferred = subject.transition_alert_status(
            acknowledged["alert"],
            "deferred",
            changed_at="2026-05-31T10:10:00Z",
            deferred_until="2026-06-03",
        )
        resolved = subject.transition_alert_status(deferred["alert"], "resolved", changed_at="2026-05-31T10:15:00Z")

        self.assertTrue(seen["ok"])
        self.assertEqual(seen["alert"]["status"], "seen")
        self.assertEqual(seen["alert"]["last_seen_at"], "2026-05-31T10:00:00Z")
        self.assertTrue(acknowledged["ok"])
        self.assertTrue(deferred["ok"])
        self.assertEqual(deferred["alert"]["deferred_until"], "2026-06-03")
        self.assertTrue(resolved["ok"])
        self.assertEqual(resolved["alert"]["status"], "resolved")

    def test_invalid_lifecycle_transition_returns_structured_error(self) -> None:
        result = subject.transition_alert_status(
            alert(status="dismissed"),
            "acknowledged",
            changed_at="2026-05-31T10:00:00Z",
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["alert"]["status"], "dismissed")
        self.assertTrue(any("Invalid alert transition" in error for error in result["errors"]))

    def test_invalid_status_returns_structured_error(self) -> None:
        result = subject.transition_alert_status(alert(), "reopened")

        self.assertFalse(result["ok"])
        self.assertTrue(any("Invalid alert status" in error for error in result["errors"]))

    def test_deferred_without_date_returns_warning(self) -> None:
        result = subject.transition_alert_status(alert(), "deferred", changed_at="2026-05-31T10:00:00Z")

        self.assertTrue(result["ok"])
        self.assertTrue(any("no deferred_until" in warning for warning in result["warnings"]))

    def test_no_input_mutation(self) -> None:
        rows = [alert(), alert(dedupe_key="other", symbol="NVDA")]
        before = copy.deepcopy(rows)

        subject.dedupe_alerts(rows)
        subject.transition_alert_status(rows[0], "seen", changed_at="2026-05-31T10:00:00Z")

        self.assertEqual(rows, before)

    def test_output_is_review_only(self) -> None:
        result = subject.dedupe_alerts([alert()])

        item = result["alerts"][0]
        self.assertTrue(result["review_only"])
        self.assertTrue(item["review_only"])
        self.assertIn("must not automatically change scores", item["notes"])


if __name__ == "__main__":
    unittest.main()
