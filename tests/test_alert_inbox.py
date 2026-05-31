#!/usr/bin/env python3
"""Tests for the review-only alert inbox view model."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from stock_trading.alert_inbox import RECOMMENDATION_ONLY_NOTE, build_alert_inbox


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "alerts" / "alert_rows.json"


class AlertInboxTests(unittest.TestCase):
    def setUp(self) -> None:
        self.alerts = json.loads(FIXTURE.read_text())

    def inbox(self, rows: list[dict[str, object]] | None = None, **kwargs: object) -> dict[str, object]:
        return build_alert_inbox(rows if rows is not None else self.alerts, current_date="2026-05-31", **kwargs)

    def test_empty_inbox_returns_useful_empty_state(self) -> None:
        inbox = self.inbox([])

        self.assertTrue(inbox["review_only"])
        self.assertEqual(inbox["metadata"]["input_count"], 0)
        self.assertEqual(inbox["summary"]["active_alerts"], 0)
        self.assertTrue(inbox["summary"]["empty_state"]["is_empty"])
        self.assertIn("No active review alerts", inbox["summary"]["empty_state"]["message"])
        self.assertEqual(inbox["recommendation_only_note"], RECOMMENDATION_ONLY_NOTE)

    def test_grouping_by_severity(self) -> None:
        inbox = self.inbox()

        severity_groups = inbox["grouped_alerts"]["by_severity"]
        self.assertEqual([row["alert_id"] for row in severity_groups["high"]], ["gate-nvda", "earn-msft"])
        self.assertEqual(inbox["summary"]["by_severity"], {"high": 2, "info": 1, "medium": 2})

    def test_grouping_by_type(self) -> None:
        inbox = self.inbox()

        type_groups = inbox["grouped_alerts"]["by_alert_type"]
        self.assertEqual(type_groups["decision_gate_changed"][0]["symbol"], "NVDA")
        self.assertEqual(type_groups["provider_gap_worsened"][0]["symbol"], "AMD")

    def test_grouping_by_symbol(self) -> None:
        inbox = self.inbox()

        symbol_groups = inbox["grouped_alerts"]["by_symbol"]
        self.assertEqual(symbol_groups["NVDA"][0]["alert_id"], "gate-nvda")
        self.assertEqual(symbol_groups["SPY"][0]["alert_type"], "benchmark_underperformance")
        self.assertNotIn("unknown", symbol_groups)

    def test_sorting_prioritizes_severity_status_newest_symbol(self) -> None:
        inbox = self.inbox()

        self.assertEqual(
            [row["alert_id"] for row in inbox["top_priority_alerts"]],
            ["gate-nvda", "model-spy", "gap-amd", "console-artifact"],
        )

    def test_status_filter_includes_matching_statuses(self) -> None:
        inbox = self.inbox(status_filter="resolved")

        self.assertEqual(inbox["metadata"]["status_filter"], ["resolved"])
        self.assertEqual(inbox["summary"]["visible_alerts"], 1)
        self.assertEqual(inbox["grouped_alerts"]["by_status"]["resolved"][0]["alert_id"], "brief-meta")

    def test_severity_filter_limits_visible_alerts(self) -> None:
        inbox = self.inbox(severity_filter=["high"])

        self.assertEqual(inbox["metadata"]["severity_filter"], ["high"])
        self.assertEqual(inbox["summary"]["visible_alerts"], 2)
        self.assertEqual(set(inbox["grouped_alerts"]["by_severity"]), {"high"})

    def test_dismissed_and_resolved_excluded_from_active_by_default(self) -> None:
        inbox = self.inbox()

        visible_ids = {
            row["alert_id"]
            for rows in inbox["grouped_alerts"]["by_status"].values()
            for row in rows
        }
        self.assertNotIn("brief-meta", visible_ids)
        self.assertNotIn("tactical-net", visible_ids)
        self.assertEqual(inbox["dismissed_resolved_counts"], {"dismissed": 1, "resolved": 1})
        self.assertEqual(inbox["summary"]["active_alerts"], 4)

    def test_review_area_grouping(self) -> None:
        inbox = self.inbox()

        area_groups = inbox["grouped_alerts"]["by_review_area"]
        self.assertEqual(area_groups["capital_deployment"][0]["alert_id"], "gate-nvda")
        self.assertEqual(area_groups["earnings_review"][0]["alert_id"], "earn-msft")
        self.assertEqual(area_groups["provider_data"][0]["alert_id"], "gap-amd")
        self.assertEqual(area_groups["ai_briefs"], [])

    def test_stale_and_deferred_alerts_are_separate(self) -> None:
        inbox = self.inbox()

        self.assertEqual(
            [row["alert_id"] for row in inbox["stale_deferred_alerts"]],
            ["earn-msft", "console-artifact"],
        )
        self.assertEqual(inbox["summary"]["stale_deferred_alerts"], 2)

    def test_output_is_deterministic_and_does_not_mutate_input(self) -> None:
        alerts = copy.deepcopy(self.alerts)
        original = copy.deepcopy(alerts)

        first = self.inbox(alerts)
        second = self.inbox(alerts)

        self.assertEqual(alerts, original)
        self.assertEqual(first, second)
        self.assertNotIn("trade", " ".join(row["title"].lower() for row in first["top_priority_alerts"]))

    def test_recommendation_and_trading_behavior_are_not_returned(self) -> None:
        inbox = self.inbox()

        self.assertTrue(inbox["metadata"]["recommendation_only"])
        self.assertTrue(inbox["metadata"]["review_only"])
        self.assertIn("Alerts do not change scores", inbox["metadata"]["note"])
        for row in inbox["top_priority_alerts"]:
            self.assertEqual(row["recommendation_impact"], "none")
            self.assertEqual(row["trading_impact"], "none")
            self.assertTrue(row["review_only"])
            self.assertNotIn("suggested_amount", row)
            self.assertNotIn("order", row)


if __name__ == "__main__":
    unittest.main()
