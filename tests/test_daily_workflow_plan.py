#!/usr/bin/env python3
"""Pure daily workflow plan tests."""

from __future__ import annotations

import sys
import unittest
from unittest.mock import patch

from stock_trading.cli.daily import parse_args
from stock_trading.workflows.daily import WorkflowStep, build_daily_workflow_plan


def args_for(*flags: str):
    with patch.object(sys, "argv", ["run_daily.py", *flags]):
        return parse_args()


def plan_names(plan: list[WorkflowStep]) -> list[str]:
    return [step.name for step in plan]


def find_step(plan: list[WorkflowStep], name: str) -> WorkflowStep:
    for step in plan:
        if step.name == name:
            return step
    raise AssertionError(f"Missing workflow step: {name}")


class DailyWorkflowPlanTests(unittest.TestCase):
    def test_default_run_plans_report_refresh_only(self) -> None:
        plan = build_daily_workflow_plan(args_for())

        self.assertEqual(plan_names(plan), ["generate_daily_report"])
        report = find_step(plan, "generate_daily_report")
        self.assertTrue(report.required)
        self.assertEqual(report.callable_name, "generate_daily_report_step")
        self.assertIn("--refresh", report.command)
        self.assertIn("report refresh planned", report.reason)

    def test_skip_refresh_plans_report_without_refresh(self) -> None:
        plan = build_daily_workflow_plan(args_for("--skip-refresh"))

        self.assertEqual(plan_names(plan), ["generate_daily_report"])
        report = find_step(plan, "generate_daily_report")
        self.assertNotIn("--refresh", report.command)
        self.assertIn("--skip-refresh", report.reason)

    def test_ingest_evidence_plans_full_evidence_chain(self) -> None:
        plan = build_daily_workflow_plan(args_for("--ingest-evidence"))

        self.assertEqual(
            plan_names(plan),
            [
                "refresh_market_data",
                "ingest_finnhub",
                "ingest_research_depth",
                "ingest_sec",
                "ingest_official_ir",
                "ingest_public_research_feeds",
                "tag_research_evidence",
                "curate_source_depth",
                "cluster_evidence_events",
                "prepare_synthesis_packets",
                "score_source_quality",
                "plan_ingestion_runs",
                "curate_score_signals",
                "generate_daily_report",
            ],
        )
        refresh = find_step(plan, "refresh_market_data")
        self.assertTrue(refresh.required)
        self.assertIn("--ingest-evidence", refresh.reason)
        self.assertFalse(find_step(plan, "ingest_finnhub").required)
        self.assertNotIn("--refresh", find_step(plan, "generate_daily_report").command)

    def test_ingest_free_data_plans_free_bundle_without_market_refresh_step(self) -> None:
        plan = build_daily_workflow_plan(args_for("--ingest-free-data"))

        names = plan_names(plan)
        self.assertNotIn("refresh_market_data", names)
        self.assertNotIn("ingest_finnhub", names)
        self.assertEqual(
            names,
            [
                "ingest_price_history",
                "ingest_research_depth",
                "ingest_sec",
                "ingest_official_ir",
                "ingest_public_research_feeds",
                "tag_research_evidence",
                "curate_source_depth",
                "cluster_evidence_events",
                "prepare_synthesis_packets",
                "score_source_quality",
                "plan_ingestion_runs",
                "curate_score_signals",
                "generate_daily_report",
            ],
        )
        self.assertEqual(find_step(plan, "ingest_price_history").callable_name, "ingest_price_history_step")
        self.assertIn("--ingest-free-data", find_step(plan, "score_source_quality").reason)
        self.assertIn("--refresh", find_step(plan, "generate_daily_report").command)

    def test_ingest_public_sources_plans_public_source_chain_only(self) -> None:
        plan = build_daily_workflow_plan(args_for("--ingest-public-sources"))

        self.assertEqual(
            plan_names(plan),
            [
                "ingest_public_research_feeds",
                "tag_research_evidence",
                "curate_source_depth",
                "cluster_evidence_events",
                "prepare_synthesis_packets",
                "score_source_quality",
                "plan_ingestion_runs",
                "curate_score_signals",
                "generate_daily_report",
            ],
        )
        self.assertNotIn("refresh_market_data", plan_names(plan))
        self.assertNotIn("ingest_sec", plan_names(plan))
        self.assertEqual(
            find_step(plan, "ingest_public_research_feeds").callable_name,
            "ingest_public_research_feeds_step",
        )
        self.assertIn("--ingest-public-sources", find_step(plan, "curate_score_signals").reason)

    def test_verify_insights_plans_queue_before_report(self) -> None:
        plan = build_daily_workflow_plan(args_for("--verify-insights"))

        self.assertEqual(plan_names(plan), ["run_verification_queue", "generate_daily_report"])
        verify = find_step(plan, "run_verification_queue")
        self.assertFalse(verify.required)
        self.assertIn("--execute", verify.command)
        self.assertIn("--verify-insights", verify.reason)

    def test_show_gaps_plans_gap_display_after_report(self) -> None:
        plan = build_daily_workflow_plan(args_for("--show-gaps"))

        self.assertEqual(plan_names(plan), ["generate_daily_report", "show_provider_gaps"])
        show_gaps = find_step(plan, "show_provider_gaps")
        self.assertFalse(show_gaps.required)
        self.assertEqual(show_gaps.command[1], "scripts/show_provider_gaps.py")
        self.assertIn("--show-gaps", show_gaps.reason)


if __name__ == "__main__":
    unittest.main()
