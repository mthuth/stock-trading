#!/usr/bin/env python3
"""Regression tests for source-health summaries in the daily report."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

from scripts import generate_daily_report as subject


def research_input(current_price: float = 100.0, target_price: float = 120.0) -> subject.ResearchInput:
    return subject.ResearchInput(
        symbol="NVDA",
        company="NVIDIA",
        category="Mega-cap AI/platform",
        sleeve="long_term",
        trade_type="long_term",
        current_price=current_price,
        target_price=target_price,
        quality_score=90.0,
        momentum_score=88.0,
        catalyst_score=86.0,
        risk_score=80.0,
        confidence="medium",
        notes="Test note",
        price_source="test",
        target_source="test",
        estimate_source="",
        sentiment_source="",
        eps_estimate="",
        revenue_estimate="",
        news_sentiment="",
        provider_notes="",
    )


def blended_target(
    confidence: str = "medium",
    blend_status: str = "Analyst + fundamental + technical",
) -> subject.BlendedTarget:
    return subject.BlendedTarget(
        symbol="NVDA",
        target_price=125.0,
        target_low=115.0,
        target_high=130.0,
        current_price=100.0,
        upside_pct=25.0,
        confidence=confidence,
        source_count=3,
        blend_status=blend_status,
        sources_label="Analyst, Fundamental, Technical",
        notes="Test blend",
    )


def readiness_by_label(items: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    return {item["label"]: item for item in items}


def marker_row(action: str = "Watch", score: float = 75.0, target_price: float = 125.0) -> dict[str, object]:
    return {
        "input": research_input(),
        "target": blended_target(),
        "action": action,
        "score": score,
    }


class GenerateDailyReportHealthTests(unittest.TestCase):
    def test_source_health_summary_counts_each_status_bucket(self) -> None:
        source_rows = [
            {"source_name": "Source A", "operations": {"status": "Implemented"}},
            {"source_name": "Source B", "operations": {"status": "Needs attention", "latest_issue": "API blocked", "records": 10, "last_run": "2026-05-28 22:00:00", "next_action": "Retry"}},
            {"source_name": "Source C", "operations": {"status": "Stale", "records": 4, "last_run": "2026-05-25 10:00:00", "next_action": "Refresh"}},
            {"source_name": "Source D", "operations": {"status": "Not implemented", "records": 0, "last_run": "", "next_action": "Build it"}},
        ]

        summary = subject.source_health_summary(source_rows)

        self.assertEqual(summary["implemented"], 3)
        self.assertEqual(summary["healthy"], 1)
        self.assertEqual(summary["needs_attention"], 1)
        self.assertEqual(summary["stale"], 1)
        self.assertEqual(summary["not_implemented"], 1)
        self.assertEqual(len(summary["top_alerts"]), 3)

    def test_source_health_alert_rows_prioritize_latest_issues(self) -> None:
        source_rows = [
            {
                "source_name": "Blocked feed",
                "operations": {
                    "status": "Needs attention",
                    "latest_issue": "DNS failure",
                    "records": 12,
                    "last_run": "2026-05-28 22:00:00",
                    "next_action": "Retry provider",
                },
            },
            {
                "source_name": "Stale source",
                "operations": {
                    "status": "Stale",
                    "latest_issue": "",
                    "records": 5,
                    "last_run": "2026-05-20 10:00:00",
                    "next_action": "Refresh source",
                },
            },
            {
                "source_name": "Healthy source",
                "operations": {
                    "status": "Implemented",
                    "latest_issue": "",
                    "records": 25,
                    "last_run": "2026-05-28 21:00:00",
                    "next_action": "None",
                },
            },
        ]

        rows = subject.source_health_alert_rows(source_rows)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][0], "High")
        self.assertEqual(rows[0][1], "Blocked feed")
        self.assertEqual(rows[1][0], "Medium")
        self.assertEqual(rows[1][1], "Stale source")

    def test_source_issue_groups_collapse_network_alerts(self) -> None:
        alerts = [
            ["High", "Alpha Vantage", "Needs attention", 3, "now", "<urlopen error [Errno 8] nodename nor servname provided, or not known>", "Retry"],
            ["High", "SEC EDGAR", "Needs attention", 3, "now", "DNS failure", "Retry"],
        ]

        rows = subject.source_issue_group_rows(alerts)

        self.assertEqual(rows, [["Network / DNS", "Needs attention", 2, "Network or DNS failures affected provider refreshes.", "Check network/API availability."]])

    def test_source_issue_groups_classify_provider_access(self) -> None:
        alerts = [
            ["High", "FMP stock news", "Needs attention", 2, "now", "HTTP 403: blocked by plan", "Upgrade plan"],
            ["High", "Alpha Vantage", "Needs attention", 2, "now", "rate limit exceeded for API key", "Wait"],
        ]

        rows = subject.source_issue_group_rows(alerts)

        self.assertEqual(rows, [["Provider access", "Needs attention", 2, "Access, plan, credential, or quota limits affected sources.", "Review provider access."]])

    def test_source_issue_groups_classify_missing_data(self) -> None:
        alerts = [
            ["Medium", "The Batch", "Not implemented", 0, "Not run", "No records captured yet", "Build it"],
            ["Medium", "Newsletter", "Stale", 2, "old", "missing feed", "Refresh"],
        ]

        rows = subject.source_issue_group_rows(alerts)

        self.assertEqual(rows, [["Missing data", "Review", 2, "Configured sources have missing, stale, or unimplemented data.", "Review source setup."]])

    def test_source_issue_groups_classify_provider_error_and_other(self) -> None:
        rows = subject.source_issue_group_rows(
            [
                ["High", "Provider A", "Needs attention", 1, "now", "HTTP 503 service unavailable", "Retry"],
                ["Low", "Provider B", "Planned", 1, "now", "Unexpected parser state", "Inspect"],
            ]
        )

        self.assertEqual(rows[0], ["Provider error", "Needs attention", 1, "Provider-side errors affected source refreshes.", "Retry after provider recovery."])
        self.assertEqual(rows[1], ["Other", "Info", 1, "Unclassified source issue needs review.", "Review detailed source alerts."])

    def test_source_issue_groups_do_not_change_detailed_alert_rows(self) -> None:
        source_rows = [
            {
                "source_name": "Blocked feed",
                "operations": {
                    "status": "Needs attention",
                    "latest_issue": "DNS failure",
                    "records": 12,
                    "last_run": "2026-05-28 22:00:00",
                    "next_action": "Retry provider",
                },
            }
        ]

        detail_rows = subject.source_health_alert_rows(source_rows)
        _ = subject.source_issue_group_rows(detail_rows)

        self.assertEqual(
            detail_rows,
            [["High", "Blocked feed", "Needs attention", 12, "2026-05-28 22:00:00", "DNS failure", "Retry provider"]],
        )

    def test_change_marker_new_without_two_history_points(self) -> None:
        marker = subject.change_marker_for_row(marker_row(), {"NVDA": [{"action": "Watch", "score": 75.0, "target_price": 125.0}]})

        self.assertEqual(marker["label"], "New")

    def test_change_marker_action_change_takes_priority(self) -> None:
        marker = subject.change_marker_for_row(
            marker_row(action="Watch", score=80.0),
            {
                "NVDA": [
                    {"action": "Avoid", "score": 70.0, "target_price": 110.0},
                    {"action": "Avoid", "score": 70.0, "target_price": 110.0},
                ]
            },
        )

        self.assertEqual(marker["label"], "Action changed")
        self.assertIn("Avoid to Watch", marker["note"])

    def test_change_marker_score_movement_threshold(self) -> None:
        marker = subject.change_marker_for_row(
            marker_row(score=76.2),
            {
                "NVDA": [
                    {"action": "Watch", "score": 74.9, "target_price": 125.0},
                    {"action": "Watch", "score": 74.9, "target_price": 125.0},
                ]
            },
        )

        self.assertEqual(marker["label"], "Score +1.3")
        self.assertEqual(marker["class"], "change-up")

    def test_change_marker_target_movement_threshold(self) -> None:
        marker = subject.change_marker_for_row(
            marker_row(score=75.1),
            {
                "NVDA": [
                    {"action": "Watch", "score": 75.0, "target_price": 120.0},
                    {"action": "Watch", "score": 75.0, "target_price": 120.0},
                ]
            },
        )

        self.assertEqual(marker["label"], "Target +4.2%")
        self.assertEqual(marker["class"], "change-up")

    def test_change_marker_small_movements_are_not_material(self) -> None:
        marker = subject.change_marker_for_row(
            marker_row(score=75.5),
            {
                "NVDA": [
                    {"action": "Watch", "score": 75.0, "target_price": 124.0},
                    {"action": "Watch", "score": 75.0, "target_price": 124.0},
                ]
            },
        )

        self.assertEqual(marker["label"], "No material change")
        self.assertEqual(marker["class"], "change-none")

    def test_pre_market_readiness_all_checks_ready(self) -> None:
        items = readiness_by_label(
            subject.pre_market_readiness_items(
                {"input": research_input(), "target": blended_target()},
                [["NVDA", "etrade_production", "1", "$100.00", "$100.00", "1.0%"]],
                {"healthy": 4, "needs_attention": 0, "stale": 0, "not_implemented": 0},
                [],
                2,
            )
        )

        self.assertEqual(items["Price data"]["status"], "Ready")
        self.assertEqual(items["Target trust"]["status"], "Ready")
        self.assertEqual(items["Source health"]["status"], "Ready")
        self.assertEqual(items["Holdings context"]["status"], "Ready")
        self.assertEqual(items["Feedback review"]["status"], "Ready")

    def test_pre_market_readiness_missing_price_and_target_need_attention(self) -> None:
        items = readiness_by_label(
            subject.pre_market_readiness_items(
                {"input": research_input(current_price=0.0, target_price=0.0), "target": None},
                [["NVDA", "etrade_production", "1", "$100.00", "$100.00", "1.0%"]],
                {"healthy": 4, "needs_attention": 0, "stale": 0, "not_implemented": 0},
                [],
                1,
            )
        )

        self.assertEqual(items["Price data"]["status"], "Needs attention")
        self.assertEqual(items["Target trust"]["status"], "Needs attention")

    def test_pre_market_readiness_low_confidence_wide_range_requires_review(self) -> None:
        items = readiness_by_label(
            subject.pre_market_readiness_items(
                {
                    "input": research_input(),
                    "target": blended_target(
                        confidence="low",
                        blend_status="Analyst + fundamental + technical; wide target range",
                    ),
                },
                [["NVDA", "etrade_production", "1", "$100.00", "$100.00", "1.0%"]],
                {"healthy": 4, "needs_attention": 0, "stale": 0, "not_implemented": 0},
                [],
                1,
            )
        )

        self.assertEqual(items["Target trust"]["status"], "Review")
        self.assertIn("Wide range", items["Target trust"]["reason"])

    def test_pre_market_readiness_source_alerts_escalate_status(self) -> None:
        high_alert_items = readiness_by_label(
            subject.pre_market_readiness_items(
                {"input": research_input(), "target": blended_target()},
                [["NVDA", "etrade_production", "1", "$100.00", "$100.00", "1.0%"]],
                {"healthy": 3, "needs_attention": 1, "stale": 0, "not_implemented": 0},
                [["High", "Blocked feed", "Needs attention", 1, "now", "DNS failure", "Retry"]],
                1,
            )
        )
        review_items = readiness_by_label(
            subject.pre_market_readiness_items(
                {"input": research_input(), "target": blended_target()},
                [["NVDA", "etrade_production", "1", "$100.00", "$100.00", "1.0%"]],
                {"healthy": 3, "needs_attention": 0, "stale": 1, "not_implemented": 1},
                [["Medium", "Stale feed", "Stale", 1, "old", "", "Refresh"]],
                1,
            )
        )

        self.assertEqual(high_alert_items["Source health"]["status"], "Needs attention")
        self.assertEqual(review_items["Source health"]["status"], "Review")

    def test_pre_market_readiness_missing_holdings_and_feedback_are_advisory(self) -> None:
        items = readiness_by_label(
            subject.pre_market_readiness_items(
                {"input": research_input(), "target": blended_target()},
                [],
                {"healthy": 4, "needs_attention": 0, "stale": 0, "not_implemented": 0},
                [],
                0,
            )
        )

        self.assertEqual(items["Holdings context"]["status"], "Review")
        self.assertEqual(items["Feedback review"]["status"], "Review")
        self.assertNotEqual(items["Holdings context"]["status"], "Needs attention")
        self.assertNotEqual(items["Feedback review"]["status"], "Needs attention")


if __name__ == "__main__":
    unittest.main()
