#!/usr/bin/env python3
"""Regression tests for daily workflow command ordering."""

from __future__ import annotations

import sys
import unittest
from argparse import Namespace
from unittest.mock import patch


from stock_trading.cli import daily as subject
from stock_trading.workflows import daily as workflow_subject


def workflow_args(**overrides: bool) -> Namespace:
    values = {name: False for name in workflow_subject.FLAG_LABELS}
    values.update(overrides)
    return Namespace(**values)


def plan_names(plan: list[workflow_subject.WorkflowStep]) -> list[str]:
    return [step.name for step in plan]


def plan_by_name(plan: list[workflow_subject.WorkflowStep]) -> dict[str, workflow_subject.WorkflowStep]:
    return {step.name: step for step in plan}


def required_by_name(plan: list[workflow_subject.WorkflowStep]) -> dict[str, bool]:
    return {step.name: step.required for step in plan}


class DailyWorkflowPlanTests(unittest.TestCase):
    def test_default_daily_plan_refreshes_report_only(self) -> None:
        plan = workflow_subject.build_daily_workflow_plan(workflow_args())

        self.assertEqual(plan_names(plan), ["generate_daily_report"])
        report = plan[0]
        self.assertTrue(report.required)
        self.assertEqual(report.callable_name, "generate_daily_report_step")
        self.assertEqual(report.command[1:], ("scripts/generate_daily_report.py", "--refresh"))
        self.assertEqual(report.reason, "always enabled; report refresh planned")

    def test_skip_refresh_plan_disables_report_refresh(self) -> None:
        plan = workflow_subject.build_daily_workflow_plan(workflow_args(skip_refresh=True))

        self.assertEqual(plan_names(plan), ["generate_daily_report"])
        report = plan[0]
        self.assertTrue(report.required)
        self.assertEqual(report.callable_name, "generate_daily_report_step")
        self.assertEqual(report.command[1:], ("scripts/generate_daily_report.py",))
        self.assertEqual(report.reason, "always enabled; refresh disabled by --skip-refresh")

    def test_ingest_evidence_plan_covers_required_optional_paths_and_reasons(self) -> None:
        plan = workflow_subject.build_daily_workflow_plan(workflow_args(ingest_evidence=True))

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
        self.assertEqual(
            required_by_name(plan),
            {
                "refresh_market_data": True,
                "ingest_finnhub": False,
                "ingest_research_depth": False,
                "ingest_sec": False,
                "ingest_official_ir": False,
                "ingest_public_research_feeds": False,
                "tag_research_evidence": False,
                "curate_source_depth": False,
                "cluster_evidence_events": False,
                "prepare_synthesis_packets": False,
                "score_source_quality": False,
                "plan_ingestion_runs": False,
                "curate_score_signals": False,
                "generate_daily_report": True,
            },
        )

        steps = plan_by_name(plan)
        self.assertEqual(steps["refresh_market_data"].callable_name, "")
        self.assertEqual(steps["refresh_market_data"].command[1:], ("scripts/refresh_market_data.py",))
        self.assertEqual(steps["refresh_market_data"].reason, "enabled by --ingest-evidence")
        self.assertEqual(steps["ingest_finnhub"].callable_name, "")
        self.assertEqual(steps["ingest_finnhub"].reason, "enabled by --ingest-evidence")
        self.assertEqual(steps["ingest_research_depth"].callable_name, "")
        self.assertEqual(steps["ingest_research_depth"].reason, "enabled by --ingest-evidence")
        self.assertEqual(steps["ingest_sec"].reason, "enabled by --ingest-evidence")
        self.assertEqual(steps["ingest_official_ir"].reason, "enabled by --ingest-evidence")
        self.assertEqual(steps["ingest_public_research_feeds"].callable_name, "ingest_public_research_feeds_step")
        self.assertEqual(steps["tag_research_evidence"].callable_name, "tag_research_evidence_step")
        self.assertEqual(steps["curate_source_depth"].callable_name, "curate_source_depth_step")
        self.assertEqual(steps["cluster_evidence_events"].callable_name, "cluster_evidence_events_step")
        self.assertEqual(steps["cluster_evidence_events"].command[1:], ("scripts/cluster_evidence_events.py", "--rebuild"))
        self.assertEqual(steps["prepare_synthesis_packets"].callable_name, "prepare_synthesis_packets_step")
        self.assertEqual(steps["score_source_quality"].callable_name, "score_source_quality_step")
        self.assertEqual(steps["plan_ingestion_runs"].callable_name, "plan_ingestion_runs_step")
        self.assertEqual(steps["curate_score_signals"].callable_name, "")
        self.assertEqual(steps["curate_score_signals"].command[1:], ("scripts/curate_score_signals.py", "--rebuild"))
        self.assertEqual(steps["generate_daily_report"].command[1:], ("scripts/generate_daily_report.py",))
        self.assertEqual(steps["generate_daily_report"].reason, "always enabled; prior market refresh step supplies fresh data")

    def test_ingest_free_data_plan_uses_free_bundle_without_market_refresh(self) -> None:
        plan = workflow_subject.build_daily_workflow_plan(workflow_args(ingest_free_data=True))

        self.assertEqual(
            plan_names(plan),
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
        self.assertNotIn("refresh_market_data", plan_names(plan))

        steps = plan_by_name(plan)
        self.assertTrue(steps["generate_daily_report"].required)
        self.assertEqual(steps["generate_daily_report"].command[1:], ("scripts/generate_daily_report.py", "--refresh"))
        self.assertEqual(steps["generate_daily_report"].reason, "always enabled; report refresh planned")
        for step_name in plan_names(plan)[:-1]:
            self.assertFalse(steps[step_name].required, step_name)
            self.assertIn("--ingest-free-data", steps[step_name].reason)
        self.assertEqual(steps["ingest_price_history"].callable_name, "ingest_price_history_step")
        self.assertEqual(steps["ingest_research_depth"].callable_name, "")
        self.assertEqual(steps["ingest_public_research_feeds"].callable_name, "ingest_public_research_feeds_step")
        self.assertEqual(steps["curate_score_signals"].callable_name, "")

    def test_ingest_public_sources_plan_runs_public_bundle_without_market_refresh(self) -> None:
        plan = workflow_subject.build_daily_workflow_plan(workflow_args(ingest_public_sources=True))

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

        steps = plan_by_name(plan)
        self.assertEqual(steps["generate_daily_report"].command[1:], ("scripts/generate_daily_report.py", "--refresh"))
        for step_name in plan_names(plan)[:-1]:
            self.assertFalse(steps[step_name].required, step_name)
            self.assertIn("--ingest-public-sources", steps[step_name].reason)
        self.assertEqual(steps["ingest_public_research_feeds"].callable_name, "ingest_public_research_feeds_step")
        self.assertEqual(steps["tag_research_evidence"].callable_name, "tag_research_evidence_step")
        self.assertEqual(steps["curate_source_depth"].callable_name, "curate_source_depth_step")
        self.assertEqual(steps["curate_score_signals"].callable_name, "")

    def test_verify_insights_plan_adds_optional_subprocess_before_report(self) -> None:
        plan = workflow_subject.build_daily_workflow_plan(workflow_args(verify_insights=True))

        self.assertEqual(plan_names(plan), ["run_verification_queue", "generate_daily_report"])
        verification, report = plan
        self.assertFalse(verification.required)
        self.assertEqual(verification.callable_name, "")
        self.assertEqual(verification.command[1:], ("scripts/run_verification_queue.py", "--execute"))
        self.assertEqual(verification.reason, "enabled by --verify-insights")
        self.assertTrue(report.required)
        self.assertEqual(report.callable_name, "generate_daily_report_step")
        self.assertEqual(report.command[1:], ("scripts/generate_daily_report.py", "--refresh"))
        self.assertEqual(report.reason, "always enabled; report refresh planned")

    def test_show_gaps_plan_adds_optional_subprocess_after_report(self) -> None:
        plan = workflow_subject.build_daily_workflow_plan(workflow_args(show_gaps=True))

        self.assertEqual(plan_names(plan), ["generate_daily_report", "show_provider_gaps"])
        report, gaps = plan
        self.assertTrue(report.required)
        self.assertEqual(report.callable_name, "generate_daily_report_step")
        self.assertEqual(report.command[1:], ("scripts/generate_daily_report.py", "--refresh"))
        self.assertEqual(gaps.required, False)
        self.assertEqual(gaps.callable_name, "")
        self.assertEqual(gaps.command[1:], ("scripts/show_provider_gaps.py",))
        self.assertEqual(gaps.reason, "enabled by --show-gaps")


class RunDailyTests(unittest.TestCase):
    def test_cli_uses_package_report_step_without_run_monkeypatch(self) -> None:
        with (
            patch.object(sys, "argv", ["run_daily.py", "--skip-refresh"]),
            patch.object(subject, "generate_daily_report_step", return_value=0) as report_step,
            patch.object(subject, "start_workflow_run", return_value=42),
            patch.object(subject, "finish_workflow_run"),
        ):
            self.assertEqual(subject.main(), 0)

        report_step.assert_called_once_with(42, True, refresh=False)

    def test_cli_uses_package_public_feed_step_without_run_monkeypatch(self) -> None:
        with (
            patch.object(sys, "argv", ["run_daily.py", "--skip-refresh", "--ingest-public-feeds"]),
            patch.object(subject, "ingest_public_research_feeds_step", return_value=0) as public_feed_step,
            patch.object(subject, "generate_daily_report_step", return_value=0) as report_step,
            patch.object(subject, "start_workflow_run", return_value=42),
            patch.object(subject, "finish_workflow_run"),
        ):
            self.assertEqual(subject.main(), 0)

        public_feed_step.assert_called_once_with(42, False)
        report_step.assert_called_once_with(42, True, refresh=False)

    def test_ingest_evidence_refreshes_analyst_targets_before_fmp_depth_checks(self) -> None:
        commands: list[list[str]] = []

        def fake_run(command: list[str], *_args: object, **_kwargs: object) -> int:
            commands.append(command)
            return 0

        with (
            patch.object(sys, "argv", ["run_daily.py", "--ingest-evidence"]),
            patch.object(subject, "run", side_effect=fake_run),
            patch.object(subject, "start_workflow_run", return_value=42),
            patch.object(subject, "finish_workflow_run"),
        ):
            self.assertEqual(subject.main(), 0)

        command_names = [command[1] for command in commands]
        self.assertLess(
            command_names.index("scripts/refresh_market_data.py"),
            command_names.index("scripts/ingest_research_depth.py"),
        )
        self.assertIn("scripts/curate_score_signals.py", command_names)
        self.assertEqual(commands[-1][1], "scripts/generate_daily_report.py")
        self.assertNotIn("--refresh", commands[-1])

    def test_ingest_free_data_runs_free_bundle_without_market_refresh(self) -> None:
        commands: list[list[str]] = []

        def fake_run(command: list[str], *_args: object, **_kwargs: object) -> int:
            commands.append(command)
            return 0

        with (
            patch.object(sys, "argv", ["run_daily.py", "--ingest-free-data", "--score-shadow"]),
            patch.object(subject, "run", side_effect=fake_run),
            patch.object(subject, "start_workflow_run", return_value=42),
            patch.object(subject, "finish_workflow_run"),
        ):
            self.assertEqual(subject.main(), 0)

        command_names = [command[1] for command in commands]
        self.assertIn("scripts/ingest_price_history.py", command_names)
        self.assertIn("scripts/ingest_sec.py", command_names)
        self.assertIn("scripts/ingest_official_ir.py", command_names)
        self.assertIn("scripts/ingest_public_research_feeds.py", command_names)
        self.assertIn("scripts/tag_research_evidence.py", command_names)
        self.assertIn("scripts/curate_source_depth.py", command_names)
        self.assertIn("scripts/cluster_evidence_events.py", command_names)
        self.assertIn("scripts/prepare_synthesis_packets.py", command_names)
        self.assertIn("scripts/score_source_quality.py", command_names)
        self.assertIn("scripts/plan_ingestion_runs.py", command_names)
        self.assertIn("scripts/curate_score_signals.py", command_names)
        self.assertLess(
            command_names.index("scripts/tag_research_evidence.py"),
            command_names.index("scripts/curate_source_depth.py"),
        )
        self.assertLess(
            command_names.index("scripts/curate_source_depth.py"),
            command_names.index("scripts/cluster_evidence_events.py"),
        )
        self.assertLess(
            command_names.index("scripts/cluster_evidence_events.py"),
            command_names.index("scripts/prepare_synthesis_packets.py"),
        )
        self.assertLess(
            command_names.index("scripts/prepare_synthesis_packets.py"),
            command_names.index("scripts/score_source_quality.py"),
        )
        self.assertLess(
            command_names.index("scripts/score_source_quality.py"),
            command_names.index("scripts/plan_ingestion_runs.py"),
        )
        self.assertNotIn("scripts/refresh_market_data.py", command_names)
        self.assertEqual(commands[-1][1], "scripts/generate_daily_report.py")

    def test_ingest_public_sources_alias_runs_public_source_ingestion(self) -> None:
        commands: list[list[str]] = []

        def fake_run(command: list[str], *_args: object, **_kwargs: object) -> int:
            commands.append(command)
            return 0

        with (
            patch.object(sys, "argv", ["run_daily.py", "--skip-refresh", "--ingest-public-sources"]),
            patch.object(subject, "run", side_effect=fake_run),
            patch.object(subject, "start_workflow_run", return_value=42),
            patch.object(subject, "finish_workflow_run"),
        ):
            self.assertEqual(subject.main(), 0)

        command_names = [command[1] for command in commands]
        self.assertIn("scripts/ingest_public_research_feeds.py", command_names)
        self.assertIn("scripts/curate_source_depth.py", command_names)
        self.assertIn("scripts/cluster_evidence_events.py", command_names)
        self.assertIn("scripts/prepare_synthesis_packets.py", command_names)
        self.assertIn("scripts/score_source_quality.py", command_names)
        self.assertIn("scripts/plan_ingestion_runs.py", command_names)
        self.assertIn("scripts/curate_score_signals.py", command_names)
        self.assertEqual(commands[-1][1], "scripts/generate_daily_report.py")

    def test_curate_source_depth_can_run_without_other_ingestion(self) -> None:
        commands: list[list[str]] = []

        def fake_run(command: list[str], *_args: object, **_kwargs: object) -> int:
            commands.append(command)
            return 0

        with (
            patch.object(sys, "argv", ["run_daily.py", "--skip-refresh", "--curate-source-depth"]),
            patch.object(subject, "run", side_effect=fake_run),
            patch.object(subject, "start_workflow_run", return_value=42),
            patch.object(subject, "finish_workflow_run"),
        ):
            self.assertEqual(subject.main(), 0)

        command_names = [command[1] for command in commands]
        self.assertIn("scripts/curate_source_depth.py", command_names)
        self.assertNotIn("scripts/refresh_market_data.py", command_names)
        self.assertEqual(commands[-1][1], "scripts/generate_daily_report.py")

    def test_plan_ingestion_can_run_without_other_ingestion(self) -> None:
        commands: list[list[str]] = []

        def fake_run(command: list[str], *_args: object, **_kwargs: object) -> int:
            commands.append(command)
            return 0

        with (
            patch.object(sys, "argv", ["run_daily.py", "--skip-refresh", "--plan-ingestion"]),
            patch.object(subject, "run", side_effect=fake_run),
            patch.object(subject, "start_workflow_run", return_value=42),
            patch.object(subject, "finish_workflow_run"),
        ):
            self.assertEqual(subject.main(), 0)

        command_names = [command[1] for command in commands]
        self.assertIn("scripts/plan_ingestion_runs.py", command_names)
        self.assertNotIn("scripts/refresh_market_data.py", command_names)
        self.assertEqual(commands[-1][1], "scripts/generate_daily_report.py")

    def test_cluster_evidence_can_run_without_other_ingestion(self) -> None:
        commands: list[list[str]] = []

        def fake_run(command: list[str], *_args: object, **_kwargs: object) -> int:
            commands.append(command)
            return 0

        with (
            patch.object(sys, "argv", ["run_daily.py", "--skip-refresh", "--cluster-evidence"]),
            patch.object(subject, "run", side_effect=fake_run),
            patch.object(subject, "start_workflow_run", return_value=42),
            patch.object(subject, "finish_workflow_run"),
        ):
            self.assertEqual(subject.main(), 0)

        command_names = [command[1] for command in commands]
        self.assertIn("scripts/cluster_evidence_events.py", command_names)
        self.assertNotIn("scripts/refresh_market_data.py", command_names)
        self.assertEqual(commands[-1][1], "scripts/generate_daily_report.py")

    def test_prepare_synthesis_can_run_without_other_ingestion(self) -> None:
        commands: list[list[str]] = []

        def fake_run(command: list[str], *_args: object, **_kwargs: object) -> int:
            commands.append(command)
            return 0

        with (
            patch.object(sys, "argv", ["run_daily.py", "--skip-refresh", "--prepare-synthesis"]),
            patch.object(subject, "run", side_effect=fake_run),
            patch.object(subject, "start_workflow_run", return_value=42),
            patch.object(subject, "finish_workflow_run"),
        ):
            self.assertEqual(subject.main(), 0)

        command_names = [command[1] for command in commands]
        self.assertIn("scripts/prepare_synthesis_packets.py", command_names)
        self.assertNotIn("scripts/refresh_market_data.py", command_names)
        self.assertEqual(commands[-1][1], "scripts/generate_daily_report.py")

    def test_plain_daily_run_keeps_report_refresh(self) -> None:
        commands: list[list[str]] = []

        def fake_run(command: list[str], *_args: object, **_kwargs: object) -> int:
            commands.append(command)
            return 0

        with (
            patch.object(sys, "argv", ["run_daily.py"]),
            patch.object(subject, "run", side_effect=fake_run),
            patch.object(subject, "start_workflow_run", return_value=42),
            patch.object(subject, "finish_workflow_run"),
        ):
            self.assertEqual(subject.main(), 0)

        self.assertEqual(len(commands), 1)
        self.assertEqual(commands[0][1], "scripts/generate_daily_report.py")
        self.assertIn("--refresh", commands[0])

    def test_verify_insights_runs_queue_before_report(self) -> None:
        commands: list[list[str]] = []

        def fake_run(command: list[str], *_args: object, **_kwargs: object) -> int:
            commands.append(command)
            return 0

        with (
            patch.object(sys, "argv", ["run_daily.py", "--skip-refresh", "--verify-insights"]),
            patch.object(subject, "run", side_effect=fake_run),
            patch.object(subject, "start_workflow_run", return_value=42),
            patch.object(subject, "finish_workflow_run"),
        ):
            self.assertEqual(subject.main(), 0)

        command_names = [command[1] for command in commands]
        self.assertLess(
            command_names.index("scripts/run_verification_queue.py"),
            command_names.index("scripts/generate_daily_report.py"),
        )
        self.assertIn("--execute", commands[0])

    def test_verify_insights_failure_is_nonfatal_warning(self) -> None:
        commands: list[list[str]] = []

        def fake_run(command: list[str], *_args: object, **_kwargs: object) -> int:
            commands.append(command)
            if command[1] == "scripts/run_verification_queue.py":
                return 1
            return 0

        with (
            patch.object(sys, "argv", ["run_daily.py", "--skip-refresh", "--verify-insights"]),
            patch.object(subject, "run", side_effect=fake_run),
            patch.object(subject, "start_workflow_run", return_value=42),
            patch.object(subject, "finish_workflow_run") as finish_workflow_run,
        ):
            self.assertEqual(subject.main(), 0)

        command_names = [command[1] for command in commands]
        self.assertIn("scripts/run_verification_queue.py", command_names)
        self.assertIn("scripts/generate_daily_report.py", command_names)
        self.assertEqual(finish_workflow_run.call_args.args[1], "ok_with_warnings")

    def test_optional_evidence_failure_continues_to_report(self) -> None:
        commands: list[list[str]] = []

        def fake_run(command: list[str], *_args: object, **_kwargs: object) -> int:
            commands.append(command)
            if command[1] == "scripts/ingest_finnhub.py":
                return 1
            return 0

        with (
            patch.object(sys, "argv", ["run_daily.py", "--skip-refresh", "--ingest-finnhub"]),
            patch.object(subject, "run", side_effect=fake_run),
            patch.object(subject, "start_workflow_run", return_value=42),
            patch.object(subject, "finish_workflow_run") as finish_workflow_run,
        ):
            self.assertEqual(subject.main(), 0)

        command_names = [command[1] for command in commands]
        self.assertIn("scripts/ingest_finnhub.py", command_names)
        self.assertIn("scripts/generate_daily_report.py", command_names)
        finish_workflow_run.assert_called()
        self.assertEqual(finish_workflow_run.call_args.args[1], "ok_with_warnings")

    def test_optional_package_ingestion_failure_continues_to_report(self) -> None:
        with (
            patch.object(sys, "argv", ["run_daily.py", "--skip-refresh", "--ingest-public-feeds"]),
            patch.object(subject, "ingest_public_research_feeds_step", return_value=1),
            patch.object(subject, "generate_daily_report_step", return_value=0) as report_step,
            patch.object(subject, "start_workflow_run", return_value=42),
            patch.object(subject, "finish_workflow_run") as finish_workflow_run,
        ):
            self.assertEqual(subject.main(), 0)

        report_step.assert_called_once_with(42, True, refresh=False)
        finish_workflow_run.assert_called()
        self.assertEqual(finish_workflow_run.call_args.args[1], "ok_with_warnings")

    def test_required_report_failure_fails_workflow(self) -> None:
        with (
            patch.object(sys, "argv", ["run_daily.py", "--skip-refresh"]),
            patch.object(subject, "generate_daily_report_step", return_value=1),
            patch.object(subject, "start_workflow_run", return_value=42),
            patch.object(subject, "finish_workflow_run") as finish_workflow_run,
        ):
            self.assertEqual(subject.main(), 1)

        finish_workflow_run.assert_called_with(
            42,
            "failed",
            message="Report generation failed.",
            summary="",
            error_class="report_generation_failed",
        )

    def test_refresh_failure_stops_when_no_core_price_data_exists(self) -> None:
        commands: list[list[str]] = []

        def fake_run(command: list[str], *_args: object, **_kwargs: object) -> int:
            commands.append(command)
            if command[1] == "scripts/refresh_market_data.py":
                return 1
            return 0

        with (
            patch.object(sys, "argv", ["run_daily.py", "--ingest-evidence"]),
            patch.object(subject, "run", side_effect=fake_run),
            patch.object(subject, "has_any_core_price_data", return_value=False),
            patch.object(subject, "start_workflow_run", return_value=42),
            patch.object(subject, "finish_workflow_run") as finish_workflow_run,
        ):
            self.assertEqual(subject.main(), 1)

        command_names = [command[1] for command in commands]
        self.assertIn("scripts/refresh_market_data.py", command_names)
        self.assertNotIn("scripts/generate_daily_report.py", command_names)
        finish_workflow_run.assert_called_with(
            42,
            "failed",
            message="Market-data refresh failed and no usable price data exists.",
            summary="",
            error_class="missing_core_price_data",
        )


if __name__ == "__main__":
    unittest.main()
