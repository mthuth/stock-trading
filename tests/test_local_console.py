#!/usr/bin/env python3
"""Regression tests for the static local decision console shell."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from stock_trading.local_console import (
    SECTION_ORDER,
    load_local_console_manifest,
    render_local_console,
    write_local_console,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "local_console" / "manifest.json"


class LocalConsoleTests(unittest.TestCase):
    def test_renders_fixture_manifest_sections_and_guardrails(self) -> None:
        manifest = load_local_console_manifest(FIXTURE)

        html = render_local_console(manifest, source_path=FIXTURE)

        for _section_id, title in SECTION_ORDER:
            self.assertIn(title, html)
        self.assertIn("Current Decision", html)
        self.assertIn("Long-Term Capital Deployment", html)
        self.assertIn("Earnings Review", html)
        self.assertIn("Data Reliability / Provider Gaps", html)
        self.assertIn("AI Briefs", html)
        self.assertIn("Learning Review", html)
        self.assertIn("Manual Journal", html)
        self.assertIn("Outcomes", html)
        self.assertIn("Artifacts / Run History", html)
        self.assertIn("Strategy / Roadmap Links", html)
        self.assertIn("Recommendation-only decision support", html)
        self.assertIn("No automatic trading", html)
        self.assertIn("No order preview", html)
        self.assertIn("No broker writes", html)

    def test_missing_manifest_renders_helpful_empty_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            missing = Path(tmpdir) / "missing-manifest.json"
            output = Path(tmpdir) / "local-console.html"

            write_local_console(manifest_path=missing, output_path=output)
            html = output.read_text()

        self.assertIn("Missing manifest", html)
        self.assertIn("No local console manifest was found", html)
        self.assertIn("reports/local-console-manifest.json", html)
        self.assertIn("Recommendation-only decision support", html)

    def test_cli_renders_fixture_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "console.html"
            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/render_local_console.py",
                    "--manifest",
                    str(FIXTURE),
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(output.exists())
            html = output.read_text()

        self.assertIn("Rendered local decision console", result.stdout)
        self.assertIn("Local Decision Console", html)
        self.assertIn("Daily dashboard", html)

    def test_shell_has_navigation_but_no_run_controls_or_broker_actions(self) -> None:
        html = render_local_console(load_local_console_manifest(FIXTURE), source_path=FIXTURE)
        lowered = html.lower()

        self.assertIn("<nav", lowered)
        self.assertNotIn("<button", lowered)
        self.assertNotIn("<form", lowered)
        self.assertNotIn("place order", lowered)
        self.assertNotIn("preview order", lowered)
        self.assertNotIn("broker write action", lowered)
        self.assertNotIn("execute trade", lowered)
        self.assertIn("no order preview", lowered)
        self.assertIn("no broker writes", lowered)


if __name__ == "__main__":
    unittest.main()
