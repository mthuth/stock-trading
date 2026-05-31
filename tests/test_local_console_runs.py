#!/usr/bin/env python3
"""Tests for read-only local console run-history view models."""

from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from stock_trading import local_console_runs as subject


def create_workflow_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    with conn:
        conn.execute(
            """
            CREATE TABLE workflow_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT,
                finished_at TEXT,
                trigger TEXT,
                command TEXT,
                status TEXT,
                summary TEXT,
                error_class TEXT,
                message TEXT,
                artifacts_json TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE workflow_step_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workflow_run_id INTEGER,
                step_name TEXT,
                command TEXT,
                started_at TEXT,
                finished_at TEXT,
                status TEXT,
                required INTEGER,
                retry_count INTEGER,
                exit_code INTEGER,
                error_class TEXT,
                message TEXT,
                artifacts_json TEXT
            )
            """
        )
    conn.close()


def insert_run(
    path: Path,
    *,
    status: str = "ok_with_warnings",
    summary: str = "Provider gap display failed; SEC ingestion skipped",
    message: str = "",
    error_class: str = "",
    artifacts: list[str] | None = None,
) -> int:
    conn = sqlite3.connect(path)
    with conn:
        cursor = conn.execute(
            """
            INSERT INTO workflow_runs (
                started_at, finished_at, trigger, command, status, summary,
                error_class, message, artifacts_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-05-31 08:00:00",
                "2026-05-31 08:03:00",
                "daily",
                "python3 scripts/run_daily.py --skip-refresh --show-gaps",
                status,
                summary,
                error_class,
                message,
                json.dumps(artifacts or ["reports/dashboard-2026-05-31.html"]),
            ),
        )
        run_id = int(cursor.lastrowid)
    conn.close()
    return run_id


def insert_step(path: Path, run_id: int) -> None:
    conn = sqlite3.connect(path)
    with conn:
        conn.execute(
            """
            INSERT INTO workflow_step_runs (
                workflow_run_id, step_name, command, started_at, finished_at,
                status, required, retry_count, exit_code, error_class, message,
                artifacts_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                "show_provider_gaps",
                "python3 scripts/show_provider_gaps.py",
                "2026-05-31 08:02:00",
                "2026-05-31 08:03:00",
                "failed",
                0,
                0,
                1,
                "ProviderGapError",
                "fixture warning",
                json.dumps(["reports/provider-gap-action-plan.md"]),
            ),
        )
    conn.close()


class LocalConsoleRunTests(unittest.TestCase):
    def test_run_history_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "stock_trading.sqlite"
            create_workflow_db(db_path)
            run_id = insert_run(db_path)
            insert_step(db_path, run_id)

            model = subject.run_history_view_model(db_path)

        self.assertTrue(model["metadata"]["available"])
        self.assertEqual(model["metadata"]["run_count"], 1)
        latest = model["latest_run"]
        self.assertEqual(latest["run_id"], run_id)
        self.assertEqual(latest["workflow_name"], "daily")
        self.assertEqual(latest["status"], "ok_with_warnings")
        self.assertIn("Provider gap display failed", latest["warnings"])
        self.assertTrue(any("show_provider_gaps" in error for error in latest["errors"]))
        self.assertIn("reports/dashboard-2026-05-31.html", latest["artifact_references"])
        self.assertIn("reports/provider-gap-action-plan.md", latest["artifact_references"])
        self.assertTrue(latest["review_only"])

    def test_run_history_unavailable_without_database(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "missing.sqlite"

            model = subject.run_history_view_model(db_path)

            self.assertFalse(db_path.exists())

        self.assertFalse(model["metadata"]["available"])
        self.assertEqual(model["runs"], [])
        self.assertTrue(model["review_only"])

    def test_run_history_unavailable_without_tables(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "empty.sqlite"
            sqlite3.connect(db_path).close()

            model = subject.run_history_view_model(db_path)

        self.assertFalse(model["metadata"]["available"])
        self.assertEqual(model["runs"], [])

    def test_failed_run_surfaces_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "stock_trading.sqlite"
            create_workflow_db(db_path)
            run_id = insert_run(
                db_path,
                status="failed",
                summary="",
                message="Report generation failed.",
                error_class="report_generation_failed",
                artifacts=[],
            )

            rows = subject.workflow_run_rows(db_path)

        self.assertEqual(rows[0]["run_id"], run_id)
        self.assertEqual(rows[0]["status"], "failed")
        self.assertEqual(rows[0]["errors"], ["report_generation_failed: Report generation failed."])

    def test_limit_orders_latest_runs_first(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "stock_trading.sqlite"
            create_workflow_db(db_path)
            first = insert_run(db_path, artifacts=["reports/dashboard-2026-05-30.html"])
            second = insert_run(db_path, artifacts=["reports/dashboard-2026-05-31.html"])

            rows = subject.workflow_run_rows(db_path, limit=1)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["run_id"], second)
        self.assertNotEqual(rows[0]["run_id"], first)

    def test_run_history_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "stock_trading.sqlite"
            create_workflow_db(db_path)
            insert_run(db_path)
            before = db_path.stat().st_mtime_ns

            subject.run_history_view_model(db_path)

            after = db_path.stat().st_mtime_ns

        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
