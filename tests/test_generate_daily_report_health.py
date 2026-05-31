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


def score_breakdown() -> subject.ScoreBreakdown:
    return subject.ScoreBreakdown(
        total=75.0,
        upside=10.0,
        quality=20.0,
        momentum=15.0,
        catalyst=12.0,
        risk=18.0,
        owned_penalty=0.0,
        speculative_penalty=0.0,
        model="Long-term",
    )


def next_day_row(
    item: subject.ResearchInput | None = None,
    target: subject.BlendedTarget | None = None,
    include_rationale: bool = True,
) -> dict[str, object]:
    row: dict[str, object] = {
        "input": item or research_input(),
        "target": blended_target() if target is None else target,
        "action": "Watch",
        "score": 75.0,
    }
    if include_rationale:
        row["breakdown"] = score_breakdown()
        row["position_after_buy_pct"] = 0.0
    return row


def decision_insight(symbol: str = "NVDA", insight_type: str = "Conviction Builder") -> subject.DecisionInsight:
    return subject.DecisionInsight(
        symbol=symbol,
        headline="Test insight",
        insight_type=insight_type,
        why_it_matters="Test why",
        supporting_data="Test data",
        risk_or_uncertainty="Test risk",
        next_check="Test next check",
        what_would_change_the_view="Test change",
    )


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

    def test_provider_blocker_review_names_blocked_field_and_fix(self) -> None:
        rows = subject.provider_blocker_review_rows(
            [
                {
                    "symbol": "NVDA",
                    "provider": "Official Investor Relations",
                    "field_name": "official_ir_page",
                    "status": "blocked",
                    "message": "IR endpoint blocked by provider access",
                }
            ],
            [
                {
                    "input": type("Input", (), {"symbol": "NVDA"})(),
                    "action": "Add",
                    "score": 80.7,
                }
            ],
        )

        self.assertEqual(rows[0][0], "High")
        self.assertEqual(rows[0][1], "NVDA")
        self.assertEqual(rows[0][4], "Primary-source evidence")
        self.assertEqual(rows[0][5], "Provider plan/access blocker")
        self.assertIn("Rank 1 / Add / 80.7", rows[0][6])
        self.assertIn("scripts/ingest_official_ir.py --symbols NVDA", rows[0][8])

    def test_provider_blocker_review_prioritizes_ranked_symbols(self) -> None:
        provider_rows = [
            {
                "symbol": "LOWRANK",
                "provider": "Financial Modeling Prep",
                "field_name": "analyst_targets",
                "status": "blocked",
                "message": "HTTP 403 blocked by plan",
            },
            {
                "symbol": "TOP",
                "provider": "Financial Modeling Prep",
                "field_name": "analyst_targets",
                "status": "blocked",
                "message": "HTTP 403 blocked by plan",
            },
        ]
        ranked = [
            {"input": type("Input", (), {"symbol": "TOP"})(), "action": "Watch", "score": 77.0},
            {"input": type("Input", (), {"symbol": "LOWRANK"})(), "action": "Watch", "score": 65.0},
        ]

        rows = subject.provider_blocker_review_rows(provider_rows, ranked)

        self.assertEqual(rows[0][1], "TOP")
        self.assertEqual(rows[0][4], "Analyst target breadth")
        self.assertIn("scripts/refresh_market_data.py --symbol TOP", rows[0][8])

    def test_provider_blocker_review_classifies_network_retry(self) -> None:
        rows = subject.provider_blocker_review_rows(
            [
                {
                    "symbol": "META",
                    "provider": "SEC EDGAR",
                    "field_name": "companyfacts",
                    "status": "failed",
                    "message": "urlopen error nodename nor servname provided",
                }
            ]
        )

        self.assertEqual(rows[0][0], "Medium")
        self.assertEqual(rows[0][4], "Primary-source evidence")
        self.assertEqual(rows[0][5], "Network / DNS")
        self.assertIn("scripts/show_provider_gaps.py --symbol META", rows[0][8])

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

    def test_next_day_readiness_empty_watchlist_needs_attention(self) -> None:
        status = subject.next_day_readiness([], {"stale": 0, "not_implemented": 0}, [])

        self.assertEqual(status["item"]["status"], "Needs attention")
        self.assertIsNone(status["preview"])

    def test_next_day_readiness_missing_price_target_or_rationale_needs_attention(self) -> None:
        missing_data = subject.next_day_readiness(
            [next_day_row(research_input(current_price=0.0, target_price=0.0), None)],
            {"stale": 0, "not_implemented": 0},
            [],
        )
        missing_rationale = subject.next_day_readiness(
            [next_day_row(include_rationale=False)],
            {"stale": 0, "not_implemented": 0},
            [],
        )

        self.assertEqual(missing_data["item"]["status"], "Needs attention")
        self.assertEqual(missing_rationale["item"]["status"], "Needs attention")

    def test_next_day_readiness_valid_candidate_is_ready(self) -> None:
        status = subject.next_day_readiness([next_day_row()], {"stale": 0, "not_implemented": 0}, [])

        self.assertEqual(status["item"]["status"], "Ready")
        self.assertEqual(status["preview"]["symbol"], "NVDA")
        self.assertEqual(status["preview"]["data_status"], "Blended")

    def test_next_day_readiness_weak_target_or_source_context_requires_review(self) -> None:
        weak_target = subject.next_day_readiness(
            [next_day_row(target=blended_target(confidence="low", blend_status="Analyst + fundamental + technical; wide target range"))],
            {"stale": 0, "not_implemented": 0},
            [],
        )
        stale_context = subject.next_day_readiness(
            [next_day_row()],
            {"stale": 1, "not_implemented": 0},
            [],
        )
        health_alert = subject.next_day_readiness(
            [next_day_row()],
            {"stale": 0, "not_implemented": 0},
            [["Medium", "Stale feed", "Stale", 1, "old", "", "Refresh"]],
        )

        self.assertEqual(weak_target["item"]["status"], "Review")
        self.assertEqual(stale_context["item"]["status"], "Review")
        self.assertEqual(health_alert["item"]["status"], "Review")

    def test_decision_safety_gate_blocks_current_nvda_low_confidence_case(self) -> None:
        row = next_day_row(
            target=blended_target(
                confidence="low",
                blend_status="Analyst + fundamental + technical; wide target range",
            )
        )
        row["action"] = "Add"

        gate = subject.decision_safety_gate(row, decision_insight(insight_type="Verification Needed"))

        self.assertFalse(gate["safe_to_buy"])
        self.assertEqual(gate["status"], "Blocked")
        self.assertIn("Low target confidence", gate["reasons"])
        self.assertIn("Wide target range", gate["reasons"])
        self.assertIn("Verification check is still open", gate["reasons"])

    def test_decision_summary_candidate_skips_blocked_add_for_safe_add(self) -> None:
        blocked = next_day_row(target=blended_target(confidence="low", blend_status="Analyst + fundamental + technical; wide target range"))
        blocked["action"] = "Add"
        blocked["score"] = 82.0
        safe_item = research_input()
        safe_item.symbol = "MSFT"
        safe_item.company = "Microsoft"
        safe_target = blended_target()
        safe_target.symbol = "MSFT"
        safe = next_day_row(item=safe_item, target=safe_target)
        safe["action"] = "Add"
        safe["score"] = 80.0

        selected, gate = subject.decision_summary_candidate(
            [blocked, safe],
            {
                "NVDA": decision_insight("NVDA", "Verification Needed"),
                "MSFT": decision_insight("MSFT", "Conviction Builder"),
            },
        )

        self.assertEqual(selected["input"].symbol, "MSFT")
        self.assertTrue(gate["safe_to_buy"])

    def test_decision_summary_candidate_holds_buy_capacity_when_no_safe_add_exists(self) -> None:
        blocked = next_day_row(target=blended_target(confidence="low", blend_status="Analyst + fundamental + technical; wide target range"))
        blocked["action"] = "Add"

        selected, gate = subject.decision_summary_candidate(
            [blocked],
            {"NVDA": decision_insight("NVDA", "Verification Needed")},
        )

        self.assertEqual(selected["input"].symbol, "NVDA")
        self.assertFalse(gate["safe_to_buy"])
        self.assertEqual(gate["candidate_action"], "Add")

    def test_pre_market_readiness_all_checks_ready(self) -> None:
        next_day_status = subject.next_day_readiness([next_day_row()], {"stale": 0, "not_implemented": 0}, [])
        items = readiness_by_label(
            subject.pre_market_readiness_items(
                {"input": research_input(), "target": blended_target()},
                [["NVDA", "etrade_production", "1", "$100.00", "$100.00", "1.0%"]],
                {"healthy": 4, "needs_attention": 0, "stale": 0, "not_implemented": 0},
                [],
                2,
                next_day_status["item"],
            )
        )

        self.assertEqual(items["Price data"]["status"], "Ready")
        self.assertEqual(items["Target trust"]["status"], "Ready")
        self.assertEqual(items["Source health"]["status"], "Ready")
        self.assertEqual(items["Holdings context"]["status"], "Ready")
        self.assertEqual(items["Feedback review"]["status"], "Ready")
        self.assertEqual(items["Next-day setup"]["status"], "Ready")

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
