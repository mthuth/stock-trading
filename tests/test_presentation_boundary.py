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
            self.assertIn("Daily Decision Review", dashboard_text)
            self.assertIn("Decision safety", dashboard_text)
            self.assertIn("Score explainability", dashboard_text)
            self.assertIn("Target source drilldown", dashboard_text)
            self.assertIn("Product Review Path", dashboard_text)
            self.assertIn("Provider gap review", dashboard_text)
            self.assertIn("Data Reliability Review", dashboard_text)
            self.assertIn("Missing data", dashboard_text)
            self.assertIn("Stale data", dashboard_text)
            self.assertIn("Blocked or rate-limited", dashboard_text)
            self.assertIn("SEC coverage", dashboard_text)
            self.assertIn("Official IR coverage", dashboard_text)
            self.assertIn("Refresh plan", dashboard_text)
            self.assertIn("Reliability", dashboard_text)
            self.assertIn("Source Health", dashboard_text)
            self.assertIn("Data Ingestion", dashboard_text)
            self.assertIn("Decision Briefs", dashboard_text)
            self.assertIn("AI synthesis explanatory", dashboard_text)
            self.assertIn("Learning Review", dashboard_text)
            self.assertIn("Review-only learning", dashboard_text)
            self.assertIn("Wave 7 Capital Deployment Prep", dashboard_text)
            self.assertIn("No broker orders or previews", dashboard_text)
            self.assertIn("Feedback", dashboard_text)
            self.assertIn("Print Review", dashboard_text)
            self.assertIn("window.print()", dashboard_text)
            self.assertIn('class="print-review"', dashboard_text)
            self.assertIn("@media print", dashboard_text)
            self.assertIn("Ranked Data Gaps", dashboard_text)
            self.assertIn("Next-Day Watchlist", dashboard_text)
            self.assertLess(dashboard_text.index("Daily Decision Review"), dashboard_text.index("Product Review Path"))
            self.assertLess(dashboard_text.index("Product Review Path"), dashboard_text.index("Data Reliability Review"))
            self.assertLess(dashboard_text.index("Data Reliability Review"), dashboard_text.index("Learning Review"))
            markdown_text = markdown.read_text()
            self.assertIn("Daily Decision Review", markdown_text)
            self.assertIn("Product Review Path", markdown_text)
            self.assertIn("Data Reliability Review", markdown_text)
            self.assertIn("Learning Review", markdown_text)
            self.assertIn("Review-only", markdown_text)
            self.assertIn("Wave 7 Capital Deployment Prep", markdown_text)
            self.assertIn("Score drivers", markdown_text)
            self.assertIn("Target Source Drilldown", markdown_text)
            self.assertIn("SEC Coverage", markdown_text)
            self.assertIn("Official IR Coverage", markdown_text)
            self.assertIn("Refresh Plan", markdown_text)
            self.assertIn("Provider gap review", markdown_text)
            self.assertIn("NVDA", markdown_text)
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
        self.assertIn("Daily Decision Review", dashboard_text)
        self.assertIn("Score explainability", dashboard_text)
        self.assertIn("Target confidence", dashboard_text)
        self.assertIn("Provider gaps", dashboard_text)
        self.assertIn("Data Reliability Review", dashboard_text)
        self.assertIn("Provider gap status", dashboard_text)
        self.assertIn("Source health rollups", dashboard_text)
        self.assertIn("What should refresh next", dashboard_text)
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

    def test_2026_05_29_nvda_context_is_not_rendered_as_recommended_next_buy(self) -> None:
        context = {section: {} for section in subject.REQUIRED_CONTEXT_SECTIONS}
        context["metadata"] = {"report_date": "2026-05-29", "generated_at": "2026-05-29T18:00:00"}
        context["summary"] = {
            "top_symbol": "NVDA",
            "top_company": "NVIDIA",
            "top_action": "Add",
            "top_score": 82.0,
            "confidence": "Low",
            "decision_gate": {
                "safe_to_buy": False,
                "status": "Blocked",
                "candidate_action": "Add",
                "reasons": [
                    "Low target confidence",
                    "Wide target range",
                    "Verification check is still open",
                ],
            },
        }
        context["reliability"] = {"mode": "Fixture", "price_counts": {"fresh": 1, "missing": 0}}
        context["source_health"] = {"summary": {"needs_attention": 0, "healthy": 1, "stale": 0, "not_implemented": 0}}

        markdown = subject.render_markdown(context)
        dashboard = subject.render_dashboard_html(context)

        self.assertIn("No decision-safe buy: **NVDA - NVIDIA**", markdown)
        self.assertIn("- Decision safety gate: **Blocked**", markdown)
        self.assertIn("Low target confidence", markdown)
        self.assertIn("Wide target range", markdown)
        self.assertNotIn("Recommended next buy: **NVDA - NVIDIA**", markdown)
        self.assertIn("No decision-safe buy", dashboard)
        self.assertIn("Daily Decision Review", dashboard)
        self.assertIn("Decision safety", dashboard)
        self.assertIn("Decision Gate", dashboard)
        self.assertIn("Add blocked", dashboard)
        self.assertNotIn(">Recommended next buy<", dashboard)

    def test_provider_gap_review_context_renders_in_dashboard_and_markdown(self) -> None:
        context = {section: {} for section in subject.REQUIRED_CONTEXT_SECTIONS}
        context["metadata"] = {"report_date": "2026-05-31", "generated_at": "2026-05-31T08:00:00"}
        context["summary"] = {"top_symbol": "NVDA", "top_action": "Add", "top_score": 82.0}
        context["reliability"] = {"mode": "ok_with_warnings", "price_counts": {"fresh": 1, "missing": 0}}
        context["source_health"] = {"summary": {"needs_attention": 1, "healthy": 0, "stale": 0, "not_implemented": 0}}
        context["provider_gap_review"] = {
            "summary": {
                "total": 1,
                "blocker": 1,
                "review_needed": 0,
                "stale_missing": 0,
                "informational": 0,
                "top_candidate": "NVDA",
                "top_candidate_affected": True,
                "top_candidate_gap_count": 1,
                "status_note": "Provider gaps remain visible even when report generation succeeds or a workflow finishes ok_with_warnings.",
            },
            "headers": ["Severity", "Top Candidate", "Provider", "Symbol", "Endpoint/Field", "Status", "Last Attempted", "Latest Issue", "Next Action"],
            "rows": [["blocker", "Yes", "Finnhub", "NVDA", "quote", "rate_limited", "2026-05-31", "HTTP 429 quota exceeded", "Wait for quota reset"]],
            "provider_groups": [{"provider": "Finnhub", "count": 1, "highest_severity": "blocker"}],
            "symbol_groups": [{"symbol": "NVDA", "count": 1, "highest_severity": "blocker"}],
        }

        dashboard = subject.render_dashboard_html(context)
        markdown = subject.render_markdown(context)

        self.assertIn("Provider Gap Review", dashboard)
        self.assertIn("provider-gap-count-blocker", dashboard)
        self.assertIn("NVDA affected by 1 active gap", dashboard)
        self.assertIn("Provider Gap Review", markdown)
        self.assertIn("Top candidate affected: **Yes**", markdown)
        self.assertIn("ok_with_warnings", markdown)


if __name__ == "__main__":
    unittest.main()
