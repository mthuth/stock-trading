#!/usr/bin/env python3
"""Tests for local broker read-only snapshot imports."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from datetime import date
from pathlib import Path

from stock_trading.broker_snapshot_importer import import_broker_snapshot, mask_account_id, write_snapshot


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "broker_readonly"


class BrokerSnapshotImporterTests(unittest.TestCase):
    def test_json_import_normalizes_read_only_snapshot(self) -> None:
        snapshot = import_broker_snapshot(FIXTURES / "sample_snapshot.json", today=date(2026, 6, 1))

        self.assertTrue(snapshot["read_only"])
        self.assertTrue(snapshot["no_order_capability"])
        self.assertFalse(snapshot["broker_api_called"])
        self.assertEqual(snapshot["summary"]["account_count"], 2)
        self.assertEqual(snapshot["summary"]["position_count"], 3)
        self.assertEqual(snapshot["summary"]["total_buying_capacity"], 2250.25)
        symbols = {
            position["symbol"]
            for account in snapshot["accounts"]
            for position in account["positions"]
        }
        self.assertEqual(symbols, {"MSFT", "NVDA", "QQQM"})

    def test_csv_import_normalizes_accounts_and_positions(self) -> None:
        snapshot = import_broker_snapshot(FIXTURES / "csv_snapshot", today=date(2026, 6, 1))

        self.assertEqual(snapshot["source"], "manual_csv")
        self.assertEqual(snapshot["summary"]["account_count"], 2)
        self.assertEqual(snapshot["summary"]["position_count"], 2)
        self.assertEqual(snapshot["summary"]["total_market_value"], 1150.0)

    def test_unmasked_account_id_redacted(self) -> None:
        self.assertEqual(mask_account_id("FAKE-IRA-123456789"), "****6789")
        snapshot = import_broker_snapshot(FIXTURES / "sample_snapshot.json", today=date(2026, 6, 1))

        account_ids = [account["account_id_masked"] for account in snapshot["accounts"]]
        self.assertIn("****6789", account_ids)
        self.assertIn("****4321", account_ids)
        self.assertNotIn("FAKE-IRA-123456789", json.dumps(snapshot))

    def test_token_secret_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "bad.json"
            path.write_text(json.dumps({"source": "manual", "oauth_token": "secret", "accounts": []}), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "secret/token/order"):
                import_broker_snapshot(path)

    def test_order_field_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "bad.json"
            path.write_text(
                json.dumps(
                    {
                        "source": "manual",
                        "as_of": "2026-06-01",
                        "accounts": [
                            {
                                "account_id": "FAKE-1234",
                                "cash": 100,
                                "order_preview": {"symbol": "MSFT"},
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "order"):
                import_broker_snapshot(path)

    def test_missing_cash_handled_with_warning(self) -> None:
        snapshot = import_broker_snapshot(FIXTURES / "sample_snapshot.json", today=date(2026, 6, 1))

        warnings = snapshot["validation"]["warnings"]
        self.assertTrue(any("missing cash" in warning for warning in warnings))
        self.assertTrue(snapshot["validation"]["ok"])

    def test_zero_cash_is_valid_amount(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "zero_cash.json"
            path.write_text(
                json.dumps(
                    {
                        "source": "manual",
                        "as_of": "2026-06-01",
                        "no_order_capability": True,
                        "accounts": [
                            {
                                "account_id": "FAKE-0000",
                                "cash": 0,
                                "buying_capacity": 0,
                                "positions": [],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            snapshot = import_broker_snapshot(path, today=date(2026, 6, 1))

        self.assertEqual(snapshot["accounts"][0]["cash"], 0.0)
        self.assertEqual(snapshot["accounts"][0]["buying_capacity"], 0.0)
        self.assertFalse(any("missing cash" in warning for warning in snapshot["validation"]["warnings"]))

    def test_multiple_accounts(self) -> None:
        snapshot = import_broker_snapshot(FIXTURES / "sample_snapshot.json", today=date(2026, 6, 1))

        self.assertEqual(len(snapshot["accounts"]), 2)
        self.assertEqual({account["account_type"] for account in snapshot["accounts"]}, {"IRA_ROLLOVER", "BROKERAGE"})

    def test_stale_snapshot_warning(self) -> None:
        snapshot = import_broker_snapshot(FIXTURES / "sample_snapshot.json", today=date(2026, 6, 20), stale_after_days=7)

        self.assertTrue(any("stale" in warning for warning in snapshot["validation"]["warnings"]))

    def test_cli_help(self) -> None:
        completed = subprocess.run(
            ["python3", "scripts/import_broker_snapshot.py", "--help"],
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=True,
        )

        self.assertIn("--input", completed.stdout)
        self.assertIn("--output", completed.stdout)

    def test_cli_writes_normalized_snapshot_without_live_broker_calls(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "broker-readonly-snapshot.json"
            completed = subprocess.run(
                [
                    "python3",
                    "scripts/import_broker_snapshot.py",
                    "--input",
                    str(FIXTURES / "sample_snapshot.json"),
                    "--output",
                    str(output),
                    "--stale-after-days",
                    "30",
                ],
                cwd=ROOT,
                check=True,
                text=True,
                capture_output=True,
            )
            payload = json.loads(output.read_text(encoding="utf-8"))

        self.assertIn("Wrote read-only broker snapshot", completed.stdout)
        self.assertTrue(payload["read_only"])
        self.assertTrue(payload["no_order_capability"])
        self.assertFalse(payload["broker_api_called"])

    def test_write_snapshot_is_file_only(self) -> None:
        snapshot = import_broker_snapshot(FIXTURES / "sample_snapshot.json", today=date(2026, 6, 1))
        with tempfile.TemporaryDirectory() as tmpdir:
            output = write_snapshot(snapshot, Path(tmpdir) / "snapshot.json")
            payload = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(payload["schema_version"], "broker_readonly_snapshot_v1")
        self.assertTrue(payload["read_only"])


if __name__ == "__main__":
    unittest.main()
