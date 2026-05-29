#!/usr/bin/env python3
"""Regression tests for rendering UX artifacts from report context only."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import presentation as subject  # noqa: E402


class PresentationBoundaryTests(unittest.TestCase):
    def test_render_report_context_from_fixture_writes_artifacts(self) -> None:
        context = subject.load_report_context(ROOT / "tests" / "fixtures" / "report_context.json")
        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch("provider_client.fetch_json_url") as fetch_json_url,
                patch("generate_daily_report.score_stock") as score_stock,
            ):
                paths = subject.render_report_context(context, Path(tmpdir))

            dashboard = Path(tmpdir) / "dashboard-2026-05-28.html"
            markdown = Path(tmpdir) / "daily-recommendation-2026-05-28.md"

            self.assertIn(dashboard, paths)
            self.assertIn(markdown, paths)
            self.assertIn("Report Context", dashboard.read_text())
            self.assertIn("Recommendation-only", dashboard.read_text())
            self.assertIn("Reliability", dashboard.read_text())
            self.assertIn("NVDA", markdown.read_text())
            fetch_json_url.assert_not_called()
            score_stock.assert_not_called()


if __name__ == "__main__":
    unittest.main()

