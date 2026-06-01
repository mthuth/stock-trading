#!/usr/bin/env python3
"""Tests for broker read-only snapshot contracts."""

from __future__ import annotations

import copy
import json
import unittest
from datetime import date
from pathlib import Path

from stock_trading import broker_readonly as subject


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "broker_readonly"
TODAY = date(2026, 6, 1)


def load_valid_snapshot() -> dict[str, object]:
    return json.loads((FIXTURE_DIR / "valid_snapshot.json").read_text())


class BrokerReadonlySnapshotTests(unittest.TestCase):
    def test_valid_snapshot(self) -> None:
        snapshot = load_valid_snapshot()
        result = subject.validate_broker_snapshot(snapshot, today=TODAY)
        normalized = result["normalized_snapshot"]

        self.assertTrue(result["valid"], result)
        self.assertTrue(normalized["snapshot_id"].startswith("broker_snapshot_"))
        self.assertEqual(normalized["source"], "fixture")
        self.assertTrue(normalized["read_only"])
        self.assertTrue(normalized["no_order_capability"])
        self.assertEqual(normalized["cash_summary"]["cash_available"], 2500.0)
        self.assertEqual(normalized["positions"][0]["symbol"], "MSFT")
        self.assertIn("does not enable orders", normalized["recommendation_only_note"])

    def test_missing_account_id_is_invalid(self) -> None:
        snapshot = load_valid_snapshot()
        snapshot["accounts"][0]["account_id_masked"] = ""

        result = subject.validate_broker_snapshot(snapshot, today=TODAY)

        self.assertFalse(result["valid"])
        self.assertIn("accounts[0].account_id_masked", {error["path"] for error in result["errors"]})

    def test_unmasked_account_id_rejected_when_claimed_masked(self) -> None:
        snapshot = load_valid_snapshot()
        snapshot["accounts"][0]["account_id_masked"] = "123456789"

        result = subject.validate_broker_snapshot(snapshot, today=TODAY)

        self.assertFalse(result["valid"])
        self.assertIn("accounts[0].account_id_masked", {error["path"] for error in result["errors"]})

    def test_raw_account_id_is_redacted_with_warning(self) -> None:
        snapshot = load_valid_snapshot()
        snapshot["accounts"][0].pop("account_id_masked")
        snapshot["accounts"][0]["account_id"] = "123456789"

        result = subject.validate_broker_snapshot(snapshot, today=TODAY)
        normalized = result["normalized_snapshot"]

        self.assertTrue(result["valid"], result)
        self.assertEqual(normalized["accounts"][0]["account_id_masked"], "acct_****6789")
        self.assertIn("accounts[0].account_id", {warning["path"] for warning in result["warnings"]})

    def test_buying_power_marked_context_only(self) -> None:
        normalized = subject.normalize_broker_snapshot(load_valid_snapshot())
        account = normalized["accounts"][0]

        self.assertEqual(account["buying_power"], 2500.0)
        self.assertTrue(account["buying_power_context_only"])

    def test_margin_field_marked_context_only(self) -> None:
        normalized = subject.normalize_broker_snapshot(load_valid_snapshot())
        account = normalized["accounts"][0]

        self.assertFalse(account["margin_enabled"])
        self.assertTrue(account["margin_enabled_context_only"])

    def test_token_or_secret_field_rejected(self) -> None:
        snapshot = load_valid_snapshot()
        snapshot["oauth_token"] = "not-a-real-token"

        result = subject.validate_broker_snapshot(snapshot, today=TODAY)

        self.assertFalse(result["valid"])
        self.assertIn("oauth_token", {error["path"] for error in result["errors"]})

    def test_order_or_order_preview_field_rejected(self) -> None:
        snapshot = load_valid_snapshot()
        snapshot["order_preview"] = {"symbol": "MSFT"}

        result = subject.validate_broker_snapshot(snapshot, today=TODAY)

        self.assertFalse(result["valid"])
        self.assertIn("order_preview", {error["path"] for error in result["errors"]})

    def test_read_only_and_no_order_flags_required(self) -> None:
        snapshot = load_valid_snapshot()
        snapshot["read_only"] = False
        snapshot["no_order_capability"] = False

        result = subject.validate_broker_snapshot(snapshot, today=TODAY)

        self.assertFalse(result["valid"])
        paths = {error["path"] for error in result["errors"]}
        self.assertIn("read_only", paths)
        self.assertIn("no_order_capability", paths)

    def test_multiple_accounts(self) -> None:
        snapshot = load_valid_snapshot()
        snapshot["accounts"].append(
            {
                "account_id_masked": "acct_****2222",
                "account_type": "BROKERAGE",
                "display_name": "Fixture Brokerage",
                "currency": "USD",
                "cash_available": 1000,
                "total_market_value": 9000,
                "total_equity": 10000,
                "sync_status": "ok",
                "as_of": "2026-06-01T08:00:00",
            }
        )
        snapshot["positions"].append(
            {
                "account_id_masked": "acct_****2222",
                "symbol": "QQQM",
                "quantity": 20,
                "market_value": 4000,
                "price": 200,
                "sleeve": "etf_context",
                "as_of": "2026-06-01T08:00:00",
                "source": "fixture",
            }
        )

        result = subject.validate_broker_snapshot(snapshot, today=TODAY)
        normalized = result["normalized_snapshot"]

        self.assertTrue(result["valid"], result)
        self.assertEqual(len(normalized["accounts"]), 2)
        self.assertEqual(normalized["cash_summary"]["cash_available"], 3500.0)
        self.assertEqual([account["account_id_masked"] for account in normalized["accounts"]], ["acct_****1111", "acct_****2222"])

    def test_missing_cash_warns(self) -> None:
        snapshot = load_valid_snapshot()
        snapshot["accounts"][0]["cash_available"] = None
        snapshot.pop("cash_summary", None)

        result = subject.validate_broker_snapshot(snapshot, today=TODAY)

        self.assertTrue(result["valid"], result)
        warning_paths = {warning["path"] for warning in result["warnings"]}
        self.assertIn("accounts[0].cash_available", warning_paths)
        self.assertIn("cash_summary.cash_available", warning_paths)

    def test_zero_cash_is_valid_available_cash(self) -> None:
        snapshot = load_valid_snapshot()
        snapshot["accounts"][0]["cash_available"] = 0

        result = subject.validate_broker_snapshot(snapshot, today=TODAY)

        self.assertTrue(result["valid"], result)
        self.assertEqual(result["normalized_snapshot"]["cash_summary"]["cash_available"], 0.0)

    def test_stale_snapshot_warning(self) -> None:
        snapshot = load_valid_snapshot()
        snapshot["as_of"] = "2026-05-20T08:00:00"

        result = subject.validate_broker_snapshot(snapshot, today=TODAY, stale_after_days=3)

        self.assertTrue(result["valid"], result)
        self.assertIn("as_of", {warning["path"] for warning in result["warnings"]})

    def test_no_input_mutation(self) -> None:
        snapshot = load_valid_snapshot()
        before = copy.deepcopy(snapshot)

        subject.normalize_broker_snapshot(snapshot)
        subject.validate_broker_snapshot(snapshot, today=TODAY)

        self.assertEqual(snapshot, before)

    def test_redact_account_id(self) -> None:
        self.assertEqual(subject.redact_account_id("123456789"), "acct_****6789")
        self.assertEqual(subject.redact_account_id("acct_****1111"), "acct_****1111")


if __name__ == "__main__":
    unittest.main()
