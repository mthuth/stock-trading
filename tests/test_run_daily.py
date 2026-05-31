#!/usr/bin/env python3
"""Regression tests for daily workflow command ordering."""

from __future__ import annotations

import sys
import unittest
from unittest.mock import patch


from stock_trading.cli import daily as subject


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
