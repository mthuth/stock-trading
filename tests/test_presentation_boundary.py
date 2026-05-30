#!/usr/bin/env python3
"""Regression tests for rendering UX artifacts from report context only."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]

from stock_trading import presentation as subject


class PresentationBoundaryTests(unittest.TestCase):
    def test_render_report_context_from_fixture_writes_artifacts(self) -> None:
        context = subject.load_report_context(ROOT / "tests" / "fixtures" / "report_context.json")
        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch("stock_trading.provider_client.fetch_json_url") as fetch_json_url,
                patch("scripts.generate_daily_report.score_stock") as score_stock,
            ):
                paths = subject.render_report_context(context, Path(tmpdir))

            dashboard = Path(tmpdir) / "dashboard-2026-05-28.html"
            markdown = Path(tmpdir) / "daily-recommendation-2026-05-28.md"
            end_of_day = Path(tmpdir) / "end-of-day-2026-05-28.md"
            context_path = Path(tmpdir) / "report-context-2026-05-28.json"

            self.assertIn(dashboard, paths)
            self.assertIn(markdown, paths)
            self.assertIn(end_of_day, paths)
            self.assertIn(context_path, paths)
            dashboard_text = dashboard.read_text()
            self.assertIn("Report Context", dashboard_text)
            self.assertIn("Recommendation-only", dashboard_text)
            self.assertIn("Action Queue", dashboard_text)
            self.assertIn("Reliability", dashboard_text)
            self.assertIn("Source Health", dashboard_text)
            self.assertIn("Data Ingestion", dashboard_text)
            self.assertIn("Decision Briefs", dashboard_text)
            self.assertIn("Feedback", dashboard_text)
            self.assertIn("Print Review", dashboard_text)
            self.assertIn("window.print()", dashboard_text)
            self.assertIn('class="print-review"', dashboard_text)
            self.assertIn("@media print", dashboard_text)
            self.assertIn("Ranked Data Gaps", dashboard_text)
            self.assertIn("Next-Day Watchlist", dashboard_text)
            self.assertIn("NVDA", markdown.read_text())
            json.loads(context_path.read_text())
            fetch_json_url.assert_not_called()
            score_stock.assert_not_called()

    def test_enriched_report_context_contract_is_json_native(self) -> None:
        context = {section: {} for section in subject.REQUIRED_CONTEXT_SECTIONS}
        context["metadata"] = {"report_date": "2026-05-28", "recommendation_only": True}
        context["summary"] = {"top_symbol": "NVDA", "top_action": "Add", "top_score": 84.2}
        context["reliability"] = {"mode": "Fixture", "price_counts": {"fresh": 1}}
        context["recommendations"] = [{"symbol": "NVDA", "action": "Add", "score": 84.2}]

        self.assertEqual(subject.validate_report_context(context), [])
        json.dumps(context)

    def test_action_queue_renders_compact_scan_with_audit_table(self) -> None:
        context = {section: {} for section in subject.REQUIRED_CONTEXT_SECTIONS}
        context["metadata"] = {"report_date": "2026-05-29", "generated_at": "2026-05-29T08:00:00"}
        context["summary"] = {"top_symbol": "NVDA", "top_action": "Add", "top_score": 80.7}
        context["reliability"] = {"mode": "Fixture", "price_counts": {"fresh": 1}}
        context["source_health"] = {
            "summary": {"needs_attention": 0, "healthy": 1, "stale": 0, "not_implemented": 0},
            "alerts": {
                "headers": ["Severity", "Source", "Status", "Records", "Last Run", "Latest Issue", "Next Action"],
                "rows": [
                    ["High", "Alpha Vantage", "Needs attention", 1, "2026-05-29", "DNS failure", "Check network"],
                    ["Medium", "Public feed", "Review", 2, "2026-05-29", "Stale feed", "Review setup"],
                    ["Low", "Manual source", "Info", 3, "2026-05-29", "No issue", "Monitor"],
                ],
            },
            "issue_groups": {"headers": [], "rows": []},
        }
        context["queues"] = {
            "action_queue": {
                "headers": [
                    "Rank",
                    "Symbol",
                    "Action",
                    "Score",
                    "Change",
                    "Today",
                    "Target",
                    "Upside",
                    "Confidence",
                    "Status",
                    "Type",
                    "Rationale",
                ],
                "rows": [
                    [
                        1,
                        "NVDA",
                        '<span class="action-hover" tabindex="0"><span class="pill add">Add</span></span>',
                        "80.7",
                        '<span class="change-badge change-none" title="No action, score, or target movement crossed the display threshold.">No material change</span>',
                        "$212.60",
                        "$285.01",
                        "34.1%",
                        "Low",
                        "Wide range",
                        "Long term",
                        "Score is high enough to add and the proposed buy stays within position caps.",
                    ]
                ],
                "raw_columns": [2, 4],
            },
            "data_gaps": {"headers": ["Rank", "Symbol"], "rows": []},
            "next_day": {"headers": ["Rank", "Symbol"], "rows": []},
        }

        dashboard_text = subject.render_dashboard_html(context)

        self.assertIn('class="action-queue-list"', dashboard_text)
        self.assertIn('class="action-card"', dashboard_text)
        self.assertIn("NVDA", dashboard_text)
        self.assertIn("No material change", dashboard_text)
        self.assertIn("Wide range", dashboard_text)
        self.assertIn("Score is high enough to add", dashboard_text)
        self.assertIn("Full Action Queue Audit", dashboard_text)
        self.assertIn('<table class="decision-table">', dashboard_text)
        self.assertIn("Print Review", dashboard_text)
        self.assertIn("Feedback", dashboard_text)
        self.assertIn("Ranked Data Gaps", dashboard_text)
        self.assertIn("feedbackStatus", dashboard_text)
        self.assertIn("Recent Feedback", dashboard_text)
        self.assertIn("fetch('/feedback'", dashboard_text)
        self.assertIn("fetch('/feedback/recent'", dashboard_text)
        self.assertIn("Command fallback", dashboard_text)
        self.assertIn('class="source-health-filter"', dashboard_text)
        self.assertIn('data-source-health-filter="blocker"', dashboard_text)
        self.assertIn('data-source-health-filter="review"', dashboard_text)
        self.assertIn('data-source-health-filter="info"', dashboard_text)
        self.assertIn("Blockers <span>1</span>", dashboard_text)
        self.assertIn("Review <span>1</span>", dashboard_text)
        self.assertIn("Info <span>1</span>", dashboard_text)
        self.assertIn("applySourceHealthFilter", dashboard_text)


if __name__ == "__main__":
    unittest.main()
