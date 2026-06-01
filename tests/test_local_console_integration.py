#!/usr/bin/env python3
"""Wave 9 local decision console integration tests."""

from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from stock_trading.local_console import render_local_console
from stock_trading.local_console_manifest import build_local_console_manifest


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_CONTEXT = ROOT / "tests" / "fixtures" / "local_console" / "report-context-2026-05-31.json"


class LocalConsoleIntegrationTests(unittest.TestCase):
    def make_reports_dir(self, tmpdir: Path) -> Path:
        reports = tmpdir / "reports"
        reports.mkdir()
        shutil.copy(FIXTURE_CONTEXT, reports / "report-context-2026-05-31.json")
        (reports / "dashboard-2026-05-31.html").write_text("<html><body>Fixture dashboard</body></html>")
        (reports / "daily-recommendation-2026-05-31.md").write_text("# Fixture daily report\n")
        (reports / "daily-recommendation-2026-05-31.csv").write_text("symbol,action\nNVDA,Add\n")
        (reports / "ai-insight-briefs-2026-05-31.md").write_text("# Fixture AI briefs\n")
        return reports

    def make_db(self, tmpdir: Path) -> Path:
        db_path = tmpdir / "stock_trading.sqlite"
        conn = sqlite3.connect(db_path)
        with conn:
            conn.execute(
                """
                CREATE TABLE workflow_runs (
                    id INTEGER PRIMARY KEY,
                    started_at TEXT,
                    finished_at TEXT,
                    trigger TEXT,
                    command TEXT,
                    status TEXT,
                    summary TEXT,
                    message TEXT,
                    artifacts_json TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE recommendation_runs (
                    id INTEGER PRIMARY KEY,
                    generated_at TEXT,
                    report_date TEXT,
                    report_path TEXT,
                    dashboard_path TEXT,
                    csv_path TEXT,
                    email_path TEXT,
                    workflow_run_id INTEGER
                )
                """
            )
            conn.execute(
                "INSERT INTO workflow_runs VALUES (1, '2026-05-31T08:00:00', '2026-05-31T08:01:00', 'manual', 'python3 scripts/run_daily.py --skip-refresh', 'ok', 'Generated fixture report', '', '[]')"
            )
            conn.execute(
                "INSERT INTO recommendation_runs VALUES (2, '2026-05-31T08:01:00', '2026-05-31', 'reports/daily-recommendation-2026-05-31.md', 'reports/dashboard-2026-05-31.html', 'reports/daily-recommendation-2026-05-31.csv', 'reports/email-summary-2026-05-31.txt', 1)"
            )
        conn.close()
        return db_path

    def test_manifest_and_render_connect_console_sections(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmpdir = Path(raw_tmp)
            reports = self.make_reports_dir(tmpdir)
            db_path = self.make_db(tmpdir)

            manifest = build_local_console_manifest(reports_dir=reports, db_path=db_path, root=tmpdir)
            html = render_local_console(manifest)

            self.assertTrue(manifest["recommendation_only"])
            self.assertEqual(manifest["report_context"]["report_date"], "2026-05-31")
            self.assertIn("latest_recommendation", manifest["panels"])
            self.assertIn("decision_quality", manifest["panels"])
            self.assertIn("capital_deployment", manifest["panels"])
            self.assertIn("earnings_review", manifest["panels"])
            self.assertIn("tactical_review", manifest["panels"])
            self.assertIn("provider_reliability", manifest["panels"])
            self.assertIn("ai_brief_status", manifest["panels"])
            self.assertIn("learning_review", manifest["panels"])
            self.assertIn("manual_journal_outcomes", manifest["panels"])
            self.assertIn("run_history", manifest["panels"])
            self.assertIn("strategy_roadmap", manifest["panels"])

            self.assertIn("Local Decision Console", html)
            self.assertIn("Latest Recommendation", html)
            self.assertIn("Decision Quality Review", html)
            self.assertIn("Long-Term Capital Deployment", html)
            self.assertIn("Earnings Review", html)
            self.assertIn("Tactical Review", html)
            self.assertIn("Provider/Data Reliability", html)
            self.assertIn("AI Brief Status", html)
            self.assertIn("Learning Review", html)
            self.assertIn("Manual Journal And Outcomes", html)
            self.assertIn("Artifact Index", html)
            self.assertIn("Run History", html)
            self.assertIn("No automatic trading", html)
            self.assertIn("No order preview", html)
            self.assertLess(html.index("Decision Quality Review"), html.index("Long-Term Capital Deployment"))
            self.assertNotIn("<button", html.lower())
            self.assertNotIn("place trade", html.lower())
            self.assertNotIn("preview order", html.lower())

    def test_missing_artifacts_render_gracefully(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmpdir = Path(raw_tmp)
            reports = tmpdir / "empty-reports"
            reports.mkdir()

            manifest = build_local_console_manifest(reports_dir=reports, db_path=tmpdir / "missing.sqlite", root=tmpdir)
            html = render_local_console(manifest)

            self.assertFalse(manifest["report_context"]["available"])
            self.assertIn("No report context artifact found", manifest["report_context"]["empty_state"])
            self.assertIn("No local report artifacts found yet", html)
            self.assertIn("No local SQLite run history is available yet", html)

    def test_cli_workflow_writes_manifest_and_console(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmpdir = Path(raw_tmp)
            reports = self.make_reports_dir(tmpdir)
            db_path = self.make_db(tmpdir)
            manifest_path = tmpdir / "local-console-manifest.json"
            html_path = tmpdir / "local-console.html"

            build = subprocess.run(
                [
                    sys.executable,
                    "scripts/build_local_console_manifest.py",
                    "--reports-dir",
                    str(reports),
                    "--db-path",
                    str(db_path),
                    "--output",
                    str(manifest_path),
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            render = subprocess.run(
                [
                    sys.executable,
                    "scripts/render_local_console.py",
                    "--manifest",
                    str(manifest_path),
                    "--output",
                    str(html_path),
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )

            self.assertIn("Wrote", build.stdout)
            self.assertIn("Wrote", render.stdout)
            self.assertTrue(manifest_path.exists())
            self.assertTrue(html_path.exists())
            payload = json.loads(manifest_path.read_text())
            self.assertIn("python3 scripts/build_local_console_manifest.py", payload["workflow"]["build_manifest"])
            self.assertIn("Local Decision Console", html_path.read_text())


if __name__ == "__main__":
    unittest.main()
