#!/usr/bin/env python3
"""Regression tests for provider-gap status normalization."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from stock_trading import ingestion
from stock_trading import provider_gap_status as subject
from stock_trading.storage import connection
from stock_trading.storage import provider_repository


class ProviderGapStatusTests(unittest.TestCase):
    def test_controlled_status_vocabulary(self) -> None:
        self.assertEqual(
            subject.PROVIDER_STATUSES,
            {
                "ok",
                "missing",
                "stale",
                "blocked",
                "rate_limited",
                "parser_gap",
                "not_implemented",
                "error",
            },
        )

    def test_normalizes_ok(self) -> None:
        self.assertEqual(subject.normalize_provider_status("ok"), "ok")
        self.assertEqual(subject.normalize_provider_status("success"), "ok")

    def test_normalizes_blocked(self) -> None:
        self.assertEqual(subject.normalize_provider_status("error", "HTTP 403 forbidden"), "blocked")
        self.assertEqual(subject.normalize_provider_status("failed", "auth token rejected"), "blocked")

    def test_normalizes_rate_limited(self) -> None:
        self.assertEqual(subject.normalize_provider_status("error", "HTTP 429 too many requests"), "rate_limited")
        self.assertEqual(subject.normalize_provider_status("blocked", "quota rate limit reached for API key"), "rate_limited")

    def test_normalizes_missing(self) -> None:
        self.assertEqual(subject.normalize_provider_status("error", "missing field target_price"), "missing")
        self.assertEqual(subject.normalize_provider_status("failed", "no data found for symbol"), "missing")

    def test_normalizes_stale(self) -> None:
        self.assertEqual(subject.normalize_provider_status("error", "old timestamp returned by provider"), "stale")
        self.assertEqual(subject.normalize_provider_status("failed", "stale cached price"), "stale")

    def test_normalizes_parser_gap(self) -> None:
        self.assertEqual(subject.normalize_provider_status("error", "parse failure in payload"), "parser_gap")
        self.assertEqual(subject.normalize_provider_status("failed", "no parseable items found"), "parser_gap")

    def test_normalizes_not_implemented(self) -> None:
        self.assertEqual(subject.normalize_provider_status("error", "not configured"), "not_implemented")
        self.assertEqual(subject.normalize_provider_status("failed", "source not implemented"), "not_implemented")

    def test_normalizes_unknown_error(self) -> None:
        self.assertEqual(subject.normalize_provider_status("failed", "unexpected provider failure"), "error")

    def test_ingestion_boundary_uses_shared_normalization(self) -> None:
        self.assertEqual(ingestion.normalize_status("failed", "no parseable items"), "parser_gap")
        self.assertEqual(ingestion.status_for_exit(2, "not built yet"), "not_implemented")
        summary = ingestion.summarize_results(
            [
                ingestion.IngestionResult("Provider", "endpoint", "NVDA", "success"),
                ingestion.IngestionResult("Provider", "endpoint", "MSFT", "error", "HTTP 429 rate limit"),
            ]
        )

        self.assertEqual(summary["ok"], 1)
        self.assertEqual(summary["rate_limited"], 1)

    def test_storage_records_normalized_provider_gap_statuses(self) -> None:
        original_db_file = connection.DB_FILE
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                connection.DB_FILE = Path(tmpdir) / "provider-status.sqlite"
                provider_repository.record_provider_run(
                    "Fixture Provider",
                    "failed",
                    "HTTP 429 quota exhausted",
                    [
                        {
                            "symbol": "NVDA",
                            "provider": "Fixture Provider",
                            "field_name": "analyst_targets",
                            "status": "failed",
                            "message": "HTTP 403 forbidden",
                        },
                        {
                            "symbol": "MSFT",
                            "provider": "Fixture Provider",
                            "field_name": "news",
                            "status": "failed",
                            "message": "no parseable items",
                        },
                    ],
                )

                rows = provider_repository.latest_provider_gaps()
        finally:
            connection.DB_FILE = original_db_file

        statuses = {(row["symbol"], row["field_name"]): row["status"] for row in rows}
        self.assertEqual(statuses[("NVDA", "analyst_targets")], "blocked")
        self.assertEqual(statuses[("MSFT", "news")], "parser_gap")


if __name__ == "__main__":
    unittest.main()
