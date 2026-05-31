#!/usr/bin/env python3
"""Tests for review-only alert artifact exports."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from stock_trading.alert_artifacts import (
    GUARDRAIL_TEXT,
    build_alert_artifact,
    render_alert_markdown,
    write_alert_artifacts,
)


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "tests" / "fixtures" / "alerts" / "sample_alerts.json"
EMPTY = ROOT / "tests" / "fixtures" / "alerts" / "empty_alerts.json"
FORBIDDEN_MARKDOWN_TERMS = ("place trade", "execute trade", "order", "broker")


class AlertArtifactTests(unittest.TestCase):
    def load_sample(self) -> dict[str, object]:
        return json.loads(SAMPLE.read_text())

    def test_json_export_shape_and_summaries(self) -> None:
        artifact = build_alert_artifact(self.load_sample())

        self.assertEqual(artifact["metadata"]["report_date"], "2026-05-31")
        self.assertEqual(artifact["metadata"]["alert_count"], 6)
        self.assertEqual(artifact["active_alert_summary"]["active_count"], 4)
        self.assertEqual(artifact["alerts_by_severity"], {"critical": 1, "high": 2, "medium": 1})
        self.assertEqual(artifact["alerts_by_review_area"]["provider_gaps"], 1)
        self.assertEqual(artifact["dismissed_resolved_counts"]["dismissed"], 1)
        self.assertEqual(artifact["dismissed_resolved_counts"]["resolved"], 1)
        self.assertEqual(artifact["top_priority_alerts"][0]["alert_id"], "provider-gap-panw")
        self.assertTrue(all(row["review_only"] for row in artifact["alerts"]))
        self.assertTrue(all(row["recommendation_only"] for row in artifact["alerts"]))

    def test_markdown_export_contains_summary_without_execution_language(self) -> None:
        artifact = build_alert_artifact(self.load_sample())
        markdown = render_alert_markdown(artifact)
        lower = markdown.lower()

        self.assertIn("# Alert Review Summary", markdown)
        self.assertIn(GUARDRAIL_TEXT, markdown)
        self.assertIn("Provider gap worsened", markdown)
        self.assertIn("## Alerts By Severity", markdown)
        for forbidden in FORBIDDEN_MARKDOWN_TERMS:
            self.assertNotIn(forbidden, lower)

    def test_empty_alert_set_exports_cleanly(self) -> None:
        artifact = build_alert_artifact(json.loads(EMPTY.read_text()))
        markdown = render_alert_markdown(artifact)

        self.assertEqual(artifact["metadata"]["alert_count"], 0)
        self.assertEqual(artifact["active_alert_summary"]["active_count"], 0)
        self.assertEqual(artifact["alerts_by_severity"], {})
        self.assertIn("No active alerts.", markdown)
        self.assertIn(GUARDRAIL_TEXT, markdown)

    def test_guardrail_text_present_in_json_and_markdown(self) -> None:
        artifact = build_alert_artifact(self.load_sample())
        markdown = render_alert_markdown(artifact)

        self.assertEqual(artifact["metadata"]["guardrail"], GUARDRAIL_TEXT)
        self.assertEqual(artifact["guardrails"]["text"], GUARDRAIL_TEXT)
        self.assertTrue(artifact["guardrails"]["no_live_notifications"])
        self.assertTrue(artifact["guardrails"]["no_recommendation_changes"])
        self.assertIn(GUARDRAIL_TEXT, markdown)

    def test_write_alert_artifacts_outputs_json_and_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = write_alert_artifacts(self.load_sample(), tmp, basename="review-alerts")
            json_path = Path(result["json_path"])
            markdown_path = Path(result["markdown_path"])

            self.assertTrue(json_path.exists())
            self.assertTrue(markdown_path.exists())
            self.assertEqual(json.loads(json_path.read_text())["metadata"]["alert_count"], 6)
            self.assertIn("# Alert Review Summary", markdown_path.read_text())
            self.assertTrue(result["review_only"])
            self.assertTrue(result["recommendation_only"])

    def test_output_is_deterministic_and_does_not_mutate_input(self) -> None:
        source = self.load_sample()
        original = copy.deepcopy(source)

        first = build_alert_artifact(source, generated_at="2026-05-31T09:30:00Z")
        second = build_alert_artifact(source, generated_at="2026-05-31T09:30:00Z")

        self.assertEqual(source, original)
        self.assertEqual(first, second)

    def test_cli_help(self) -> None:
        result = subprocess.run(
            [sys.executable, "scripts/export_alerts.py", "--help"],
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=True,
        )

        self.assertIn("--fixture", result.stdout)
        self.assertIn("--output-dir", result.stdout)

    def test_cli_exports_fixture_only_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/export_alerts.py",
                    "--fixture",
                    str(SAMPLE),
                    "--output-dir",
                    tmp,
                    "--basename",
                    "fixture-alerts",
                    "--generated-at",
                    "2026-05-31T09:30:00Z",
                ],
                cwd=ROOT,
                check=True,
                text=True,
                capture_output=True,
            )

            self.assertIn("fixture-alerts.json", result.stdout)
            self.assertTrue((Path(tmp) / "fixture-alerts.json").exists())
            self.assertTrue((Path(tmp) / "fixture-alerts.md").exists())


if __name__ == "__main__":
    unittest.main()
