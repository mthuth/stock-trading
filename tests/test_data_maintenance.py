#!/usr/bin/env python3
"""Regression tests for review-only data maintenance backlog generation."""

from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from stock_trading.data_maintenance import (
    generate_data_maintenance_backlog,
    render_work_requests_markdown,
    write_backlog_docs,
)


def by_root(backlog: dict[str, object], root_cause: str) -> list[dict[str, object]]:
    rows = backlog["work_requests"]
    assert isinstance(rows, list)
    return [dict(row) for row in rows if row.get("root_cause") == root_cause]


class DataMaintenanceBacklogTests(unittest.TestCase):
    def test_missing_current_price_becomes_high_priority_work_request(self) -> None:
        backlog = generate_data_maintenance_backlog(
            provider_gaps=[
                {
                    "symbol": "BBAI",
                    "provider": "FMP/Alpha Vantage",
                    "field_name": "current_price",
                    "status": "missing",
                    "message": "No current price returned",
                    "top_5": True,
                }
            ]
        )

        request = by_root(backlog, "missing_current_price")[0]
        self.assertEqual(request["priority"], "P0 blocker")
        self.assertEqual(request["recommended_action"], "fix_config")
        self.assertEqual(request["affected_symbols"], ["BBAI"])
        self.assertTrue(request["review_only"])

    def test_not_implemented_source_becomes_work_request(self) -> None:
        backlog = generate_data_maintenance_backlog(
            research_source_rows=[
                {
                    "source_name": "Unusual Whales options flow",
                    "access_model": "paid_api_candidate",
                    "implementation_status": "not_implemented",
                    "next_step": "Evaluate API token cost and endpoint fit.",
                }
            ]
        )

        request = by_root(backlog, "not_implemented_source")[0]
        self.assertEqual(request["recommended_action"], "paid_provider_decision")
        self.assertEqual(request["priority"], "P2 medium")
        self.assertIn("Unusual Whales options flow", request["affected_sources"])

    def test_zero_record_source_becomes_work_request(self) -> None:
        backlog = generate_data_maintenance_backlog(
            source_health_rows=[
                {
                    "source_name": "NVIDIA official RSS",
                    "quality_label": "not_enough_data",
                    "total_evidence": "0",
                    "source_tier": "tier_1_official",
                }
            ]
        )

        request = by_root(backlog, "zero_record_source")[0]
        self.assertEqual(request["recommended_action"], "implement_source")
        self.assertEqual(request["priority"], "P2 medium")

    def test_etf_expected_gap_becomes_mark_expected_gap(self) -> None:
        backlog = generate_data_maintenance_backlog(
            provider_gaps=[
                {
                    "symbol": "QQQM",
                    "provider": "SEC EDGAR",
                    "field_name": "companyfacts",
                    "status": "missing",
                    "message": "ETF has no SEC companyfacts coverage",
                }
            ]
        )

        request = by_root(backlog, "etf_expected_gap")[0]
        self.assertEqual(request["recommended_action"], "mark_expected_gap")
        self.assertEqual(request["priority"], "P3 low")
        self.assertEqual(request["affected_symbols"], ["QQQM"])

    def test_etf_missing_current_price_remains_real_gap(self) -> None:
        backlog = generate_data_maintenance_backlog(
            provider_gaps=[
                {
                    "symbol": "QQQM",
                    "provider": "Alpha Vantage",
                    "field_name": "current_price",
                    "status": "missing",
                    "message": "No current price returned",
                }
            ]
        )

        self.assertFalse(by_root(backlog, "etf_expected_gap"))
        request = by_root(backlog, "missing_current_price")[0]
        self.assertEqual(request["recommended_action"], "fix_config")
        self.assertEqual(request["priority"], "P1 high")

    def test_parser_failure_becomes_improve_parser(self) -> None:
        backlog = generate_data_maintenance_backlog(
            provider_gaps=[
                {
                    "symbol": "NVDA",
                    "provider": "Company investor relations",
                    "field_name": "official_ir_page",
                    "status": "error",
                    "message": "parser failed to parse release links",
                }
            ]
        )

        request = by_root(backlog, "parser_failure")[0]
        self.assertEqual(request["recommended_action"], "improve_parser")
        self.assertEqual(request["priority"], "P2 medium")

    def test_paid_provider_gap_becomes_paid_provider_decision(self) -> None:
        backlog = generate_data_maintenance_backlog(
            provider_gaps=[
                {
                    "symbol": "SNOW",
                    "provider": "Paid analyst provider",
                    "field_name": "analyst_target",
                    "status": "missing",
                    "message": "Needs paid target provider",
                    "target_confidence": "needs_review",
                }
            ]
        )

        request = by_root(backlog, "missing_analyst_target_breadth")[0]
        self.assertEqual(request["recommended_action"], "paid_provider_decision")
        self.assertEqual(request["priority"], "P1 high")

    def test_duplicate_gaps_are_grouped(self) -> None:
        backlog = generate_data_maintenance_backlog(
            provider_gaps=[
                {
                    "symbol": "BBAI",
                    "provider": "FMP",
                    "field_name": "current_price",
                    "status": "missing",
                    "source_ref": "gap:1",
                },
                {
                    "symbol": "ALAB",
                    "provider": "FMP",
                    "field_name": "current_price",
                    "status": "missing",
                    "source_ref": "gap:2",
                },
            ]
        )

        requests = by_root(backlog, "missing_current_price")
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0]["affected_symbols"], ["ALAB", "BBAI"])
        self.assertEqual(requests[0]["source_refs"], ["gap:1", "gap:2"])

    def test_docs_output_contains_codex_ready_work_requests(self) -> None:
        backlog = generate_data_maintenance_backlog(
            provider_gaps=[
                {
                    "symbol": "BBAI",
                    "provider": "FMP",
                    "field_name": "current_price",
                    "status": "missing",
                }
            ]
        )

        markdown = render_work_requests_markdown(backlog)
        self.assertIn("Codex-ready work requests", markdown)
        self.assertIn("Codex prompt seed", markdown)
        self.assertIn("codex/data-maintenance-", markdown)
        self.assertIn("no GitHub issues were created", markdown)

        with tempfile.TemporaryDirectory() as tmpdir:
            paths = write_backlog_docs(backlog, tmpdir)
            self.assertEqual([path.name for path in paths], ["DATA_MAINTENANCE_BACKLOG.md", "DATA_GAP_WORK_REQUESTS.md"])
            self.assertTrue((Path(tmpdir) / "DATA_MAINTENANCE_BACKLOG.md").exists())

    def test_no_github_issue_creation_and_no_input_mutation(self) -> None:
        provider_gaps = [
            {
                "symbol": "ALAB",
                "provider": "FMP",
                "field_name": "current_price",
                "status": "missing",
            }
        ]
        original = copy.deepcopy(provider_gaps)

        backlog = generate_data_maintenance_backlog(provider_gaps=provider_gaps)

        self.assertFalse(backlog["github_issues_created"])
        self.assertEqual(provider_gaps, original)
        for request in backlog["work_requests"]:
            self.assertNotIn("github_issue", request)
            self.assertTrue(request["review_only"])


if __name__ == "__main__":
    unittest.main()
