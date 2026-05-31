#!/usr/bin/env python3
"""Official company investor-relations coverage tests."""

from __future__ import annotations

import unittest
from unittest import mock

from stock_trading.official_ir_coverage import (
    build_official_ir_coverage,
    classify_ir_evidence_type,
    coverage_gap_status_rows,
)

import scripts.ingest_official_ir as ingest_official_ir


def approved_row(symbol: str, company: str, category: str = "Mega-cap AI/platform") -> dict[str, str]:
    return {
        "symbol": symbol,
        "company": company,
        "category": category,
        "sleeve": "long_term",
        "trade_type": "long_term",
    }


class OfficialIRCoverageTests(unittest.TestCase):
    def test_configured_ir_source_reports_latest_success_and_evidence_types(self) -> None:
        coverage = build_official_ir_coverage(
            [approved_row("MSFT", "Microsoft")],
            [
                {
                    "symbol": "MSFT",
                    "company_name": "Microsoft",
                    "ir_url": "https://www.microsoft.com/en-us/Investor",
                    "source_focus": "investor relations home",
                }
            ],
            [
                {
                    "symbol": "MSFT",
                    "status": "ok",
                    "message": "",
                    "run_id": 7,
                    "refreshed_at": "2026-05-31 08:00:00",
                }
            ],
            [
                {
                    "symbol": "MSFT",
                    "provider_endpoint": "official_ir_earnings_release",
                    "title": "Quarterly earnings release",
                    "source_url": "https://example.test/earnings",
                }
            ],
        )

        self.assertEqual(coverage[0]["configured_ir_url"], "https://www.microsoft.com/en-us/Investor")
        self.assertEqual(coverage[0]["ir_source_status"], "ok")
        self.assertEqual(coverage[0]["latest_successful_fetch"], "2026-05-31 08:00:00")
        self.assertEqual(coverage[0]["evidence_types_found"], ["earnings_release"])

    def test_missing_ir_source_is_an_explicit_gap(self) -> None:
        coverage = build_official_ir_coverage([approved_row("NVDA", "NVIDIA")], [])

        self.assertEqual(coverage[0]["ir_source_status"], "missing_source")
        self.assertIn("No official company IR source", str(coverage[0]["latest_issue"]))
        self.assertEqual(
            coverage_gap_status_rows(coverage),
            [
                {
                    "symbol": "NVDA",
                    "provider": "Company investor relations",
                    "field_name": "official_ir_page",
                    "status": "missing_source",
                    "message": "No official company IR source is configured.",
                }
            ],
        )

    def test_blocked_ir_source_reports_latest_issue(self) -> None:
        coverage = build_official_ir_coverage(
            [approved_row("META", "Meta Platforms")],
            [{"symbol": "META", "company_name": "Meta Platforms", "ir_url": "https://investor.example.test"}],
            [
                {
                    "symbol": "META",
                    "status": "blocked",
                    "message": "HTTP 403",
                    "run_id": 10,
                    "refreshed_at": "2026-05-31 08:30:00",
                }
            ],
        )

        self.assertEqual(coverage[0]["ir_source_status"], "blocked")
        self.assertEqual(coverage[0]["latest_issue"], "HTTP 403")

    def test_parser_gap_is_visible_as_source_gap(self) -> None:
        coverage = build_official_ir_coverage(
            [approved_row("AMZN", "Amazon")],
            [{"symbol": "AMZN", "company_name": "Amazon", "ir_url": "https://ir.example.test"}],
            [
                {
                    "symbol": "AMZN",
                    "status": "parser_gap",
                    "message": "Fetched page but parser found no relevant IR links.",
                    "run_id": 11,
                    "refreshed_at": "2026-05-31 08:45:00",
                }
            ],
        )

        self.assertEqual(coverage[0]["ir_source_status"], "parser_gap")
        self.assertEqual(coverage_gap_status_rows(coverage)[0]["status"], "parser_gap")

    def test_earnings_release_link_classification(self) -> None:
        self.assertEqual(
            classify_ir_evidence_type("Fiscal Q3 2026 financial results press release", "/news/quarterly-results"),
            "earnings_release",
        )

    def test_investor_presentation_link_classification(self) -> None:
        self.assertEqual(
            classify_ir_evidence_type("Investor presentation slides", "/events/presentation.pdf"),
            "investor_presentation",
        )

    def test_official_company_evidence_is_primary_company_framed_context(self) -> None:
        source = {
            "symbol": "MSFT",
            "company_name": "Microsoft",
            "ir_url": "https://www.microsoft.com/en-us/Investor",
            "source_focus": "investor relations home",
        }
        parsed = ingest_official_ir.InvestorPageParser(source["ir_url"])
        parsed.title = "Microsoft Investor Relations"
        rows = ingest_official_ir.page_evidence(
            source,
            parsed,
            [
                {
                    "text": "Quarterly earnings release",
                    "href": "https://example.test/earnings",
                    "ir_evidence_type": "earnings_release",
                }
            ],
            "abc123",
        )

        page_row = rows[0]
        link_row = rows[1]
        self.assertEqual(page_row["corroboration_status"], "primary_source")
        self.assertEqual(page_row["source_type"], "company release")
        self.assertIn("company-framed primary-source context", str(page_row["summary"]))
        self.assertEqual(link_row["evidence_type"], "official_ir_link")
        self.assertEqual(link_row["provider_endpoint"], "official_ir_earnings_release")
        self.assertIn("not independent confirmation", str(link_row["summary"]))

    def test_ingest_source_records_parser_gap_without_live_call(self) -> None:
        source = {
            "symbol": "MSFT",
            "company_name": "Microsoft",
            "ir_url": "https://www.microsoft.com/en-us/Investor",
            "source_focus": "investor relations home",
        }
        payload_calls: list[dict[str, object]] = []
        evidence_calls: list[list[dict[str, object]]] = []

        def fake_payload(*args: object, **kwargs: object) -> int:
            payload_calls.append({"args": args, "kwargs": kwargs})
            return 1

        def fake_evidence(rows: list[dict[str, object]]) -> int:
            evidence_calls.append(rows)
            return len(rows)

        with mock.patch.object(ingest_official_ir, "fetch_page", return_value=("ok", b"<html></html>", "text/html", "")):
            with mock.patch.object(ingest_official_ir, "record_provider_payload", side_effect=fake_payload):
                with mock.patch.object(ingest_official_ir, "record_research_evidence", side_effect=fake_evidence):
                    inserted, status = ingest_official_ir.ingest_source(source, "test-agent", link_limit=4)

        self.assertEqual(inserted, 0)
        self.assertEqual(status["status"], "parser_gap")
        self.assertIn("parser found no readable", str(status["message"]))
        self.assertEqual(evidence_calls, [[]])
        self.assertEqual(payload_calls[0]["args"][3], "parser_gap")


if __name__ == "__main__":
    unittest.main()
