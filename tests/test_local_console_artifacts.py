#!/usr/bin/env python3
"""Tests for read-only local console artifact indexing."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from stock_trading import local_console_artifacts as subject


def write_artifact(root: Path, relative_path: str, body: str = "fixture") -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    return path


class LocalConsoleArtifactTests(unittest.TestCase):
    def test_artifacts_present_are_summarized(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            reports = root / "reports"
            write_artifact(root, "reports/daily-recommendation-2026-05-31.md")
            write_artifact(root, "reports/daily-recommendation-2026-05-31.csv")
            write_artifact(root, "reports/dashboard-2026-05-31.html")
            write_artifact(root, "reports/report-context-2026-05-31.json", "{}")
            write_artifact(root, "reports/ai-analysis-context-2026-05-31.json", "{}")
            write_artifact(root, "reports/ai-insight-briefs-2026-05-31.md")
            write_artifact(root, "reports/ai-insight-briefs-2026-05-31.json", "{}")
            write_artifact(root, "reports/synthesis-packets-2026-05-31.json", "{}")
            write_artifact(root, "reports/provider-coverage-audit.md")
            write_artifact(root, "reports/provider-gap-action-plan.md")
            write_artifact(root, "reports/local-console-manifest.json", "{}")

            model = subject.artifact_index_view_model(reports, root=root, as_of="2026-05-31")

        types = {row["artifact_type"] for row in model["artifacts"] if row["exists"]}
        self.assertIn("daily_markdown_report", types)
        self.assertIn("csv_recommendation_export", types)
        self.assertIn("dashboard_html", types)
        self.assertIn("report_context_json", types)
        self.assertIn("ai_analysis_context", types)
        self.assertIn("ai_brief", types)
        self.assertIn("synthesis_packets", types)
        self.assertIn("provider_coverage_audit", types)
        self.assertIn("provider_gap_action_plan", types)
        self.assertIn("local_console_manifest", types)
        self.assertTrue(model["review_only"])
        self.assertEqual(model["metadata"]["existing_count"], 11)

    def test_missing_artifacts_remain_visible(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            reports = root / "reports"
            write_artifact(root, "reports/dashboard-2026-05-31.html")

            model = subject.artifact_index_view_model(reports, root=root, as_of="2026-05-31")

        missing_types = {row["artifact_type"] for row in model["missing"]}
        self.assertIn("daily_markdown_report", missing_types)
        self.assertIn("report_context_json", missing_types)
        self.assertIn("local_console_manifest", missing_types)
        self.assertTrue(all(row["status"] == "missing" for row in model["missing"]))

    def test_latest_artifact_selection_uses_report_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            reports = root / "reports"
            write_artifact(root, "reports/dashboard-2026-05-29.html")
            write_artifact(root, "reports/dashboard-2026-05-31.html")

            rows = subject.artifact_index(reports, root=root, as_of="2026-05-31")
            latest = subject.latest_artifacts(rows)

        self.assertEqual(latest["dashboard_html"]["report_date"], "2026-05-31")
        self.assertEqual(latest["dashboard_html"]["path"], "reports/dashboard-2026-05-31.html")

    def test_stale_artifact_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            reports = root / "reports"
            write_artifact(root, "reports/report-context-2026-05-20.json", "{}")

            model = subject.artifact_index_view_model(
                reports,
                root=root,
                as_of="2026-05-31",
                stale_after_days=2,
            )

        stale_rows = [row for row in model["artifacts"] if row["artifact_type"] == "report_context_json"]
        self.assertEqual(stale_rows[0]["freshness"], "stale")
        self.assertIn("11 day(s) old", stale_rows[0]["notes"])
        self.assertEqual(model["metadata"]["stale_count"], 1)

    def test_no_reports_directory_does_not_create_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            reports = root / "missing-reports"

            model = subject.artifact_index_view_model(reports, root=root, as_of="2026-05-31")

            self.assertFalse(reports.exists())

        self.assertEqual(model["metadata"]["existing_count"], 0)
        self.assertGreaterEqual(model["metadata"]["missing_count"], 1)
        self.assertTrue(all(not row["exists"] for row in model["artifacts"]))

    def test_artifact_index_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            reports = root / "reports"
            write_artifact(root, "reports/daily-recommendation-2026-05-31.md")
            before = sorted(path.relative_to(root) for path in root.rglob("*"))

            subject.artifact_index_view_model(reports, root=root, as_of="2026-05-31")

            after = sorted(path.relative_to(root) for path in root.rglob("*"))

        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
