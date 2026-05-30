#!/usr/bin/env python3
"""Regression tests for the V1.8 verification queue runner."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from stock_trading import storage
from stock_trading import verification_queue as subject


def queue_row(symbol: str, next_check: str, status: str = "queued") -> dict[str, object]:
    return {
        "run_id": 1,
        "report_date": "2026-05-29",
        "symbol": symbol,
        "priority_rank": 1,
        "insight_type": "Verification Needed",
        "reason": "unit reason",
        "expected_score_impact": 1.0,
        "next_check": next_check,
        "command_mapping": next_check,
        "automation_mode": "auto",
        "status": status,
        "result_summary": "",
        "workflow_step_id": None,
        "started_at": None,
        "completed_at": None,
    }


class VerificationQueueTests(unittest.TestCase):
    def test_sec_ir_next_check_maps_to_two_commands(self) -> None:
        plan = subject.command_plan("scripts/ingest_sec.py + scripts/ingest_official_ir.py", "NVDA")

        self.assertEqual(len(plan.commands), 2)
        self.assertIn("scripts/ingest_sec.py", plan.commands[0])
        self.assertIn("scripts/ingest_official_ir.py", plan.commands[1])

    def test_price_history_next_check_maps_to_one_command(self) -> None:
        plan = subject.command_plan("scripts/ingest_price_history.py", "MSFT")

        self.assertEqual(len(plan.commands), 1)
        self.assertIn("--symbols", plan.commands[0])
        self.assertIn("MSFT", plan.commands[0])

    def test_benzinga_runs_only_when_key_is_present(self) -> None:
        no_key = subject.command_plan(
            "scripts/ingest_benzinga_analyst_targets.py or config/manual_analyst_targets.csv",
            "MU",
            env={},
        )
        with_key = subject.command_plan(
            "scripts/ingest_benzinga_analyst_targets.py or config/manual_analyst_targets.csv",
            "MU",
            env={"BENZINGA_API_KEY": "unit"},
        )

        self.assertEqual(no_key.blocked_status, "manual_required")
        self.assertEqual(len(with_key.commands), 1)
        self.assertIn("scripts/ingest_benzinga_analyst_targets.py", with_key.commands[0])

    def test_manual_and_provider_gap_items_are_not_executed(self) -> None:
        manual = subject.command_plan("config/manual_analyst_targets.csv", "AVGO")
        provider = subject.command_plan("scripts/show_provider_gaps.py", "NVDA")

        self.assertEqual(manual.blocked_status, "manual_required")
        self.assertEqual(provider.blocked_status, "blocked_provider_fix_needed")

    def test_runner_updates_failures_without_stopping_other_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            db_file = data_dir / "stock_trading.sqlite"
            rows = [
                queue_row("NVDA", "scripts/ingest_sec.py + scripts/ingest_official_ir.py"),
                queue_row("MSFT", "scripts/ingest_price_history.py"),
            ]
            with patch.object(storage, "DATA_DIR", data_dir), patch.object(storage, "DB_FILE", db_file):
                storage.record_verification_queue_items(rows)
                commands: list[list[str]] = []

                def fake_runner(command: list[str]) -> int:
                    commands.append(command)
                    return 1 if "scripts/ingest_sec.py" in command else 0

                status = subject.run_queue(execute=True, limit=10, runner=fake_runner)
                latest = storage.latest_verification_queue()

        statuses = {row["symbol"]: row["status"] for row in latest}
        self.assertEqual(status, 1)
        self.assertGreaterEqual(len(commands), 3)
        self.assertEqual(statuses["NVDA"], "failed")
        self.assertEqual(statuses["MSFT"], "completed")


if __name__ == "__main__":
    unittest.main()
