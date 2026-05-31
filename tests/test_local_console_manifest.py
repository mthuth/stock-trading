#!/usr/bin/env python3
"""Tests for the read-only local console manifest builder."""

from __future__ import annotations

import ast
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from stock_trading.local_console_manifest import (
    MANIFEST_VERSION,
    RECOMMENDATION_ONLY_NOTE,
    build_local_console_manifest,
    write_local_console_manifest,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_CONTEXT = ROOT / "tests" / "fixtures" / "report_context.json"


class LocalConsoleManifestTests(unittest.TestCase):
    def write_fixture_reports(self, reports_dir: Path) -> Path:
        reports_dir.mkdir(parents=True, exist_ok=True)
        context_path = reports_dir / "report-context-2026-05-28.json"
        shutil.copyfile(FIXTURE_CONTEXT, context_path)
        for name in (
            "dashboard-2026-05-28.html",
            "daily-recommendation-2026-05-28.md",
            "daily-recommendation-2026-05-28.csv",
            "ai-analysis-context-2026-05-28.json",
            "ai-insight-briefs-2026-05-28.md",
            "ai-insight-briefs-2026-05-28.json",
            "ai-insight-briefs-2026-05-28.html",
            "provider-gap-action-plan.md",
        ):
            (reports_dir / name).write_text("fixture artifact\n")
        return context_path

    def test_manifest_builds_from_fixture_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            reports_dir = Path(temp_dir) / "reports"
            context_path = self.write_fixture_reports(reports_dir)

            manifest = build_local_console_manifest(
                reports_dir,
                report_context_path=context_path,
                generated_at="2026-05-31T12:00:00Z",
            )

        self.assertEqual(manifest["manifest_version"], MANIFEST_VERSION)
        self.assertEqual(manifest["generated_at"], "2026-05-31T12:00:00Z")
        self.assertEqual(manifest["report_date"], "2026-05-28")
        self.assertTrue(manifest["read_only"])
        self.assertIn("recommendation-only", manifest["recommendation_only_note"].lower())
        self.assertIn("does not place trades", manifest["recommendation_only_note"])
        self.assertEqual(manifest["missing_artifacts"], [])
        self.assertTrue(manifest["latest_report_context_path"].endswith("report-context-2026-05-28.json"))
        self.assertTrue(manifest["latest_dashboard_path"].endswith("dashboard-2026-05-28.html"))
        self.assertTrue(manifest["latest_markdown_report_path"].endswith("daily-recommendation-2026-05-28.md"))
        self.assertTrue(manifest["latest_csv_path"].endswith("daily-recommendation-2026-05-28.csv"))
        self.assertTrue(manifest["latest_ai_context_path"].endswith("ai-analysis-context-2026-05-28.json"))
        self.assertTrue(manifest["latest_ai_briefs_paths"]["markdown"].endswith("ai-insight-briefs-2026-05-28.md"))
        self.assertTrue(
            manifest["latest_provider_gap_paths"]["provider_gap_action_plan"].endswith("provider-gap-action-plan.md")
        )
        self.assertEqual(manifest["capital_deployment_summary"]["status"], "deployable")
        self.assertEqual(manifest["capital_deployment_summary"]["primary_candidate"]["symbol"], "NVDA")
        self.assertEqual(manifest["earnings_review_summary"]["upcoming_count"], 2)
        self.assertEqual(manifest["earnings_review_summary"]["recent_count"], 1)
        self.assertEqual(manifest["decision_safety_summary"]["status"], "Ready")
        self.assertEqual(manifest["provider_gap_summary"]["provider_blocker_count"], 3)
        self.assertEqual(manifest["source_usefulness_summary"]["row_count"], 3)
        self.assertEqual(manifest["run_history_summary"]["analysis_run_id"], 202)

    def test_missing_artifacts_warn_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            reports_dir = Path(temp_dir) / "reports"
            reports_dir.mkdir()
            context_path = reports_dir / "report-context-2026-05-28.json"
            shutil.copyfile(FIXTURE_CONTEXT, context_path)

            manifest = build_local_console_manifest(reports_dir, report_context_path=context_path)

        missing_names = {item["artifact"] for item in manifest["missing_artifacts"]}
        self.assertIn("dashboard", missing_names)
        self.assertIn("markdown", missing_names)
        self.assertIn("csv", missing_names)
        self.assertIn("ai_context", missing_names)
        self.assertIn("ai_briefs_markdown", missing_names)
        self.assertTrue(manifest["warnings"])
        self.assertEqual(manifest["latest_dashboard_path"], "")
        self.assertTrue(manifest["read_only"])

    def test_manifest_does_not_mutate_report_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            reports_dir = Path(temp_dir) / "reports"
            context_path = self.write_fixture_reports(reports_dir)
            before = json.loads(context_path.read_text())

            build_local_console_manifest(reports_dir, report_context_path=context_path)

            after = json.loads(context_path.read_text())
        self.assertEqual(after, before)

    def test_manifest_json_is_serializable_and_writer_outputs_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            reports_dir = Path(temp_dir) / "reports"
            context_path = self.write_fixture_reports(reports_dir)
            output_path = Path(temp_dir) / "local-console-manifest.json"

            written = write_local_console_manifest(output_path, reports_dir=reports_dir, report_context_path=context_path)
            manifest = json.loads(written.read_text())

        self.assertEqual(manifest["manifest_version"], MANIFEST_VERSION)
        self.assertTrue(manifest["read_only"])
        json.dumps(manifest, sort_keys=True)

    def test_cli_helper_writes_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            reports_dir = Path(temp_dir) / "reports"
            self.write_fixture_reports(reports_dir)
            output_path = Path(temp_dir) / "manifest.json"

            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/build_local_console_manifest.py",
                    "--reports-dir",
                    str(reports_dir),
                    "--output",
                    str(output_path),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            manifest = json.loads(output_path.read_text())

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Wrote", result.stdout)
        self.assertEqual(manifest["manifest_version"], MANIFEST_VERSION)
        self.assertTrue(manifest["read_only"])

    def test_builder_has_no_execution_or_provider_imports(self) -> None:
        source_path = ROOT / "stock_trading" / "local_console_manifest.py"
        tree = ast.parse(source_path.read_text(), filename=str(source_path))
        imports: set[str] = set()
        calls: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    calls.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    calls.add(node.func.attr)

        banned_import_roots = (
            "stock_trading.analysis_engine",
            "stock_trading.provider_client",
            "stock_trading.storage",
            "stock_trading.workflows",
            "stock_trading.ai_briefs",
            "stock_trading.llm_research_briefs",
            "scripts",
        )
        for imported in imports:
            self.assertFalse(
                any(imported == banned or imported.startswith(f"{banned}.") for banned in banned_import_roots),
                f"Manifest builder must stay read-only; imported {imported}",
            )
        self.assertFalse({"run_analysis", "run_daily", "render_report_context", "write_ai_brief_artifacts"} & calls)
        self.assertIn("does not place trades", RECOMMENDATION_ONLY_NOTE)


if __name__ == "__main__":
    unittest.main()
