#!/usr/bin/env python3
"""Regression tests for the data-ingestion boundary module."""

from __future__ import annotations

import unittest
from unittest.mock import patch


from stock_trading import ingestion as subject


class IngestionBoundaryTests(unittest.TestCase):
    def test_refresh_prices_returns_standard_result_without_rendering(self) -> None:
        commands: list[list[str]] = []

        def fake_runner(command: list[str]) -> int:
            commands.append(command)
            return 0

        result = subject.refresh_prices(fake_runner)

        self.assertEqual(result.provider, "multi-provider")
        self.assertEqual(result.endpoint, "market_data")
        self.assertEqual(result.status, "ok")
        self.assertIn("refresh_market_data.py", result.command)
        self.assertNotIn("generate_daily_report.py", result.command)
        self.assertEqual(len(commands), 1)

    def test_provider_health_snapshot_uses_gap_view_contract(self) -> None:
        class FakeRow(dict):
            def __getitem__(self, key: str) -> object:
                return dict.__getitem__(self, key)

        with patch.object(
            subject,
            "latest_provider_gaps",
            return_value=[
                FakeRow(
                    refreshed_at="2026-05-28 18:00:00",
                    symbol="NVDA",
                    provider="FMP",
                    field_name="target_price",
                    status="missing",
                    message="No target returned",
                )
            ],
        ):
            snapshot = subject.provider_health_snapshot()

        self.assertEqual(snapshot[0]["symbol"], "NVDA")
        self.assertEqual(snapshot[0]["status"], "missing")
        self.assertEqual(snapshot[0]["field_name"], "target_price")

    def test_ingestion_status_normalization_uses_shared_labels(self) -> None:
        self.assertEqual(subject.normalize_status("success"), "ok")
        self.assertEqual(subject.normalize_status("error", "HTTP 429 rate limit"), "rate_limited")
        self.assertEqual(subject.normalize_status("error", "HTTP 403 forbidden"), "blocked")
        self.assertEqual(subject.normalize_status("error", "missing target"), "missing")
        self.assertEqual(subject.normalize_status("error", "stale price"), "stale")
        self.assertEqual(subject.status_for_exit(2), "error")


if __name__ == "__main__":
    unittest.main()
