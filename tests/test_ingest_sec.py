#!/usr/bin/env python3
"""SEC ingestion coverage checks."""

from __future__ import annotations

from datetime import date
import unittest
from unittest.mock import patch

from scripts import ingest_sec as subject
from stock_trading.sec_coverage import (
    CikMapping,
    SecCoverageSubject,
    SecEndpointResult,
    normalize_sec_ticker_map,
    provider_status_rows,
    summarize_sec_coverage,
)


def submissions_payload(filing_date: str = "2026-05-01") -> dict[str, object]:
    return {
        "filings": {
            "recent": {
                "form": ["10-Q"],
                "filingDate": [filing_date],
                "reportDate": [filing_date],
                "accessionNumber": ["0000000000-26-000001"],
                "primaryDocument": ["form10q.htm"],
            }
        }
    }


def companyfacts_payload() -> dict[str, object]:
    return {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            {
                                "val": 130497000000,
                                "end": "2026-01-31",
                                "form": "10-K",
                            }
                        ]
                    }
                }
            }
        }
    }


def summarize_one(
    subject_row: SecCoverageSubject,
    ticker_map: dict[str, CikMapping],
    submissions: SecEndpointResult | None = None,
    companyfacts: SecEndpointResult | None = None,
):
    return summarize_sec_coverage(
        [subject_row],
        ticker_map,
        submissions_by_symbol={subject_row.symbol: submissions} if submissions else {},
        companyfacts_by_symbol={subject_row.symbol: companyfacts} if companyfacts else {},
        fact_concepts=tuple(subject.FACT_CONCEPTS),
        latest_successful_sec_refresh="2026-05-30T12:00:00",
        as_of=date(2026, 5, 31),
    )[0]


class SecCoverageTests(unittest.TestCase):
    def test_mapped_operating_company_has_current_submissions_and_companyfacts(self) -> None:
        record = summarize_one(
            SecCoverageSubject("NVDA", "NVIDIA", "Mega-cap AI/platform", "long_term", "long_term"),
            {"NVDA": CikMapping("0001045810", "NVIDIA CORP")},
            SecEndpointResult("ok", "", submissions_payload()),
            SecEndpointResult("ok", "", companyfacts_payload()),
        )

        self.assertEqual(record.coverage_status, "covered")
        self.assertEqual(record.cik, "0001045810")
        self.assertEqual(record.submissions_status, "ok")
        self.assertEqual(record.companyfacts_status, "ok")
        self.assertEqual(record.latest_filing_date, "2026-05-01")
        self.assertEqual(record.latest_successful_sec_refresh, "2026-05-30T12:00:00")
        self.assertFalse(record.needs_attention)

    def test_missing_cik_is_recorded_as_provider_gap(self) -> None:
        record = summarize_one(
            SecCoverageSubject("SNOW", "Snowflake", "Cybersecurity/cloud/software", "long_term", "long_term"),
            {},
        )

        rows = provider_status_rows(record)
        self.assertEqual(record.coverage_status, "missing_cik")
        self.assertEqual(rows[0]["field_name"], "cik_mapping")
        self.assertEqual(rows[0]["status"], "missing")
        self.assertIn("No SEC ticker CIK mapping", rows[0]["message"])

    def test_etf_non_operating_symbol_is_not_sec_failure(self) -> None:
        record = summarize_one(
            SecCoverageSubject("QQQM", "Invesco NASDAQ 100 ETF", "ETF/ballast", "etf", "etf"),
            {},
        )

        rows = provider_status_rows(record)
        self.assertEqual(record.coverage_status, "not_applicable")
        self.assertEqual(record.submissions_status, "expected")
        self.assertEqual(record.companyfacts_status, "expected")
        self.assertFalse(record.needs_attention)
        self.assertEqual(
            [(row["field_name"], row["status"]) for row in rows],
            [
                ("cik_mapping", "expected"),
                ("submissions", "expected"),
                ("companyfacts", "expected"),
            ],
        )
        self.assertIn("not required", rows[0]["message"])

    def test_stale_sec_data_is_visible_as_provider_gap(self) -> None:
        record = summarize_one(
            SecCoverageSubject("MSFT", "Microsoft", "Mega-cap AI/platform", "long_term", "long_term"),
            {"MSFT": CikMapping("0000789019", "MICROSOFT CORP")},
            SecEndpointResult("ok", "", submissions_payload("2025-01-15")),
            SecEndpointResult("ok", "", companyfacts_payload()),
        )

        rows = provider_status_rows(record)
        self.assertEqual(record.submissions_status, "stale")
        self.assertEqual(rows[0]["field_name"], "submissions")
        self.assertEqual(rows[0]["status"], "stale")
        self.assertIn("2025-01-15", rows[0]["message"])

    def test_companyfacts_missing_is_visible_as_provider_gap(self) -> None:
        record = summarize_one(
            SecCoverageSubject("META", "Meta Platforms", "Mega-cap AI/platform", "long_term", "long_term"),
            {"META": CikMapping("0001326801", "META PLATFORMS INC")},
            SecEndpointResult("ok", "", submissions_payload()),
            SecEndpointResult("ok", "", {"facts": {"us-gaap": {}}}),
        )

        rows = provider_status_rows(record)
        self.assertEqual(record.companyfacts_status, "missing")
        self.assertEqual(rows[1]["field_name"], "companyfacts")
        self.assertEqual(rows[1]["status"], "missing")
        self.assertIn("companyfacts", rows[1]["message"])

    def test_submissions_missing_is_visible_as_provider_gap(self) -> None:
        record = summarize_one(
            SecCoverageSubject("AMZN", "Amazon", "Mega-cap AI/platform", "long_term", "long_term"),
            {"AMZN": CikMapping("0001018724", "AMAZON COM INC")},
            SecEndpointResult("ok", "", {"filings": {"recent": {"form": [], "filingDate": []}}}),
            SecEndpointResult("ok", "", companyfacts_payload()),
        )

        rows = provider_status_rows(record)
        self.assertEqual(record.submissions_status, "missing")
        self.assertEqual(rows[0]["field_name"], "submissions")
        self.assertEqual(rows[0]["status"], "missing")
        self.assertIn("No recent SEC submissions", rows[0]["message"])

    def test_rate_limited_sec_endpoint_is_visible_as_provider_gap(self) -> None:
        record = summarize_one(
            SecCoverageSubject("AMZN", "Amazon", "Mega-cap AI/platform", "long_term", "long_term"),
            {"AMZN": CikMapping("0001018724", "AMAZON COM INC")},
            SecEndpointResult("error", "HTTP 429: too many requests", {}),
            SecEndpointResult("ok", "", companyfacts_payload()),
        )

        rows = provider_status_rows(record)
        self.assertEqual(record.submissions_status, "rate_limited")
        self.assertEqual(rows[0]["status"], "rate_limited")
        self.assertIn("429", rows[0]["message"])

    def test_foreign_or_adr_missing_cik_gets_clear_status(self) -> None:
        record = summarize_one(
            SecCoverageSubject("TSM", "Taiwan Semiconductor", "Semiconductors", "long_term", "long_term"),
            {},
        )

        self.assertEqual(record.coverage_status, "foreign_or_adr_unmapped")
        self.assertIn("Foreign/ADR", record.issue)
        self.assertEqual(provider_status_rows(record)[0]["status"], "missing")

    def test_ambiguous_cik_mapping_is_provider_gap(self) -> None:
        ticker_map = normalize_sec_ticker_map(
            {
                "0": {"ticker": "TEST", "cik_str": 1, "title": "Test A"},
                "1": {"ticker": "TEST", "cik_str": 2, "title": "Test B"},
            }
        )
        record = summarize_one(
            SecCoverageSubject("TEST", "Test Company", "Mega-cap AI/platform", "long_term", "long_term"),
            ticker_map,
        )

        self.assertEqual(record.coverage_status, "ambiguous_cik")
        self.assertEqual(provider_status_rows(record)[0]["status"], "ambiguous")

    def test_ingest_symbol_uses_coverage_rows_without_live_network(self) -> None:
        responses = [
            ("ok", submissions_payload(), ""),
            ("ok", {"facts": {"us-gaap": {}}}, ""),
        ]

        with (
            patch.object(subject, "sec_get_json", side_effect=responses),
            patch.object(subject, "record_provider_payload", return_value=1),
            patch.object(subject, "record_research_evidence", return_value=1),
            patch.object(subject, "upsert_company_identifier") as upsert_identifier,
            patch.object(subject.time, "sleep"),
        ):
            inserted, rows = subject.ingest_symbol(
                "NVDA",
                {"NVDA": CikMapping("0001045810", "NVIDIA CORP")},
                "test-agent",
                subject=SecCoverageSubject("NVDA", "NVIDIA", "Mega-cap AI/platform", "long_term", "long_term"),
            )

        self.assertEqual(inserted, 1)
        self.assertEqual(rows[0]["field_name"], "submissions")
        self.assertEqual(rows[0]["status"], "ok")
        self.assertEqual(rows[1]["field_name"], "companyfacts")
        self.assertEqual(rows[1]["status"], "missing")
        upsert_identifier.assert_called_once_with("NVDA", "0001045810", "NVIDIA CORP")


if __name__ == "__main__":
    unittest.main()
