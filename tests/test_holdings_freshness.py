#!/usr/bin/env python3
"""Tests for holdings and broker snapshot freshness summaries."""

from __future__ import annotations

import json
import unittest
from datetime import datetime

from stock_trading.holdings_freshness import (
    READ_ONLY_GUARDRAIL,
    build_holdings_freshness,
    freshness_contains_restricted_language,
)


class HoldingsFreshnessTests(unittest.TestCase):
    def test_fresh_broker_snapshot(self) -> None:
        summary = build_holdings_freshness(
            {
                "source": "broker_readonly",
                "as_of": "2026-06-01T08:00:00",
                "last_pulled_at": "2026-06-01T08:10:00",
                "accounts": [{"account_id": "acct-****-001", "positions": [{"symbol": "NVDA"}]}],
            },
            today=datetime(2026, 6, 1, 12, 0, 0),
            stale_after_hours=24,
        )

        self.assertEqual(summary["source"], "broker_readonly")
        self.assertEqual(summary["as_of"], "2026-06-01T08:00:00")
        self.assertEqual(summary["last_pulled_at"], "2026-06-01T08:10:00")
        self.assertEqual(summary["freshness_label"], "fresh")
        self.assertEqual(summary["age_hours"], 4)
        self.assertEqual(summary["age_days"], 0)
        self.assertEqual(summary["account_count"], 1)
        self.assertEqual(summary["position_count"], 1)
        self.assertEqual(summary["warnings"], [])
        self.assertTrue(summary["read_only"])
        self.assertTrue(summary["no_order_capability"])

    def test_stale_broker_snapshot(self) -> None:
        summary = build_holdings_freshness(
            {
                "source": "broker_readonly",
                "as_of": "2026-05-30T08:00:00",
                "accounts": [{"account_id": "acct-****-001", "positions": [{"symbol": "MSFT"}]}],
            },
            today=datetime(2026, 6, 1, 12, 0, 0),
            stale_after_hours=24,
        )

        self.assertEqual(summary["freshness_label"], "stale")
        self.assertEqual(summary["age_hours"], 52)
        self.assertTrue(any("stale" in warning.lower() for warning in summary["warnings"]))
        self.assertIn("do not treat holdings or cash as current", summary["warning"])

    def test_missing_snapshot(self) -> None:
        summary = build_holdings_freshness(None, today=datetime(2026, 6, 1, 12, 0, 0))

        self.assertEqual(summary["source"], "unknown")
        self.assertEqual(summary["freshness_label"], "missing")
        self.assertIsNone(summary["age_hours"])
        self.assertEqual(summary["account_count"], 0)
        self.assertEqual(summary["position_count"], 0)
        self.assertTrue(any("missing" in warning.lower() for warning in summary["warnings"]))

    def test_manual_config_source(self) -> None:
        summary = build_holdings_freshness(
            {
                "source": "manual",
                "as_of": "2026-06-01T07:30:00",
                "accounts": [{"account_id": "manual-review", "positions": []}],
            },
            today=datetime(2026, 6, 1, 12, 0, 0),
        )

        self.assertEqual(summary["source"], "manual")
        self.assertEqual(summary["freshness_label"], "fresh")
        self.assertEqual(summary["account_count"], 1)
        self.assertEqual(summary["position_count"], 0)
        self.assertTrue(any("no position data" in warning.lower() for warning in summary["warnings"]))

        configured = build_holdings_freshness(
            {"source": "config", "as_of": "2026-06-01T07:30:00"},
            today=datetime(2026, 6, 1, 12, 0, 0),
        )
        self.assertEqual(configured["source"], "config")

    def test_unknown_as_of_date(self) -> None:
        summary = build_holdings_freshness(
            {
                "source": "broker_readonly",
                "accounts": [{"account_id": "acct-****-001", "positions": [{"symbol": "NVDA"}]}],
            },
            today=datetime(2026, 6, 1, 12, 0, 0),
        )

        self.assertEqual(summary["freshness_label"], "unknown")
        self.assertEqual(summary["as_of"], "")
        self.assertIsNone(summary["age_hours"])
        self.assertTrue(any("no usable as-of timestamp" in warning for warning in summary["warnings"]))

    def test_no_account_or_position_data(self) -> None:
        summary = build_holdings_freshness(
            {"source": "broker_readonly", "as_of": "2026-06-01T08:00:00"},
            today=datetime(2026, 6, 1, 12, 0, 0),
        )

        self.assertEqual(summary["freshness_label"], "fresh")
        self.assertEqual(summary["account_count"], 0)
        self.assertEqual(summary["position_count"], 0)
        self.assertTrue(any("no account data" in warning.lower() for warning in summary["warnings"]))
        self.assertTrue(any("no position data" in warning.lower() for warning in summary["warnings"]))

    def test_read_only_guardrail_and_display_labels(self) -> None:
        summary = build_holdings_freshness(
            {"source": "fixture_broker_snapshot", "as_of": "2026-06-01T08:00:00"},
            today=datetime(2026, 6, 1, 12, 0, 0),
        )
        labels = [row["label"] for row in summary["display_rows"]]

        self.assertEqual(summary["source"], "fixture")
        self.assertEqual(summary["guardrail"], READ_ONLY_GUARDRAIL)
        self.assertIn("Holdings source", labels)
        self.assertIn("As of", labels)
        self.assertIn("Last pulled", labels)
        self.assertIn("Freshness", labels)
        self.assertIn("Read-only snapshot", labels)
        self.assertFalse(freshness_contains_restricted_language(summary))

    def test_no_order_or_trade_action_language(self) -> None:
        summary = build_holdings_freshness(
            {"source": "broker_readonly", "as_of": "2026-06-01T08:00:00"},
            today=datetime(2026, 6, 1, 12, 0, 0),
        )
        rendered = json.dumps(summary, sort_keys=True).lower()

        for phrase in ("place order", "preview order", "execute trade", "execute order", "buy now", "sell now"):
            self.assertNotIn(phrase, rendered)


if __name__ == "__main__":
    unittest.main()
