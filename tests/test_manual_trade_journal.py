#!/usr/bin/env python3
"""Tests for the manual decision/trade journal."""

from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import add_trade_journal_entry
from stock_trading import storage
from stock_trading.manual_trade_journal import (
    ACTION_TAKEN_VALUES,
    list_manual_journal_entries,
    record_manual_journal_entry,
)


class ManualTradeJournalTests(unittest.TestCase):
    def test_record_manual_buy_decision_persists_locally(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "journal.sqlite"
            with patch("stock_trading.storage.DB_FILE", db_path):
                result = record_manual_journal_entry(
                    {
                        "decision_date": "2026-05-31",
                        "symbol": "msft",
                        "action_taken": "bought",
                        "amount": "1250.50",
                        "shares": "2.5",
                        "price": "500.20",
                        "rationale": "Manual buy after reviewing report.",
                        "recommendation_run_id": "",
                        "report_date": "2026-05-31",
                        "notes": "Retirement account manual action.",
                    }
                )
                rows = list_manual_journal_entries(symbol="MSFT", report_date="2026-05-31")

        self.assertEqual(result["kind"], "manual_trade_journal")
        self.assertEqual(result["symbol"], "MSFT")
        self.assertEqual(rows[0]["id"], result["id"])
        self.assertEqual(rows[0]["action_taken"], "bought")
        self.assertEqual(rows[0]["amount"], 1250.50)
        self.assertEqual(rows[0]["shares"], 2.5)
        self.assertEqual(rows[0]["price"], 500.20)
        self.assertEqual(rows[0]["rationale"], "Manual buy after reviewing report.")

    def test_supported_action_types_are_recordable(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "journal.sqlite"
            with patch("stock_trading.storage.DB_FILE", db_path):
                for index, action in enumerate(sorted(ACTION_TAKEN_VALUES), start=1):
                    record_manual_journal_entry(
                        {
                            "decision_date": "2026-05-31",
                            "symbol": f"T{index}",
                            "action_taken": action,
                            "report_date": "2026-05-31",
                        }
                    )
                rows = list_manual_journal_entries(report_date="2026-05-31", limit=20)

        self.assertEqual({row["action_taken"] for row in rows}, ACTION_TAKEN_VALUES)

    def test_query_by_symbol_and_report_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "journal.sqlite"
            with patch("stock_trading.storage.DB_FILE", db_path):
                record_manual_journal_entry(
                    {
                        "decision_date": "2026-05-30",
                        "symbol": "NVDA",
                        "action_taken": "watched",
                        "report_date": "2026-05-30",
                    }
                )
                record_manual_journal_entry(
                    {
                        "decision_date": "2026-05-31",
                        "symbol": "NVDA",
                        "action_taken": "skipped",
                        "report_date": "2026-05-31",
                    }
                )
                rows = list_manual_journal_entries(symbol="NVDA", report_date="2026-05-31")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["action_taken"], "skipped")
        self.assertEqual(rows[0]["report_date"], "2026-05-31")

    def test_invalid_action_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "action_taken must be one of"):
            record_manual_journal_entry({"symbol": "MSFT", "action_taken": "buy"})

    def test_journal_entries_do_not_alter_recommendation_scores(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "journal.sqlite"
            with patch("stock_trading.storage.DB_FILE", db_path):
                run_id = storage.record_recommendation_run(
                    "2026-05-31",
                    Path("reports/daily.md"),
                    Path("reports/dashboard.html"),
                    Path("reports/daily.csv"),
                    Path("reports/email.txt"),
                    50000,
                    2500,
                )
                storage.record_recommendation_scores(
                    run_id,
                    [
                        {
                            "run_id": run_id,
                            "report_date": "2026-05-31",
                            "symbol": "MSFT",
                            "company": "Microsoft",
                            "sleeve": "long_term",
                            "trade_type": "long_term",
                            "action": "Add",
                            "score": 84.2,
                            "current_price": 500.0,
                            "target_price": 560.0,
                            "upside_pct": 12.0,
                            "target_confidence": "Medium",
                            "data_status": "Blended",
                            "score_breakdown": "Fixture",
                            "rationale": "Fixture recommendation",
                        }
                    ],
                )
                conn = storage.init_db()
                before = conn.execute("SELECT action, score FROM recommendation_scores WHERE symbol = 'MSFT'").fetchall()
                conn.close()
                record_manual_journal_entry(
                    {
                        "decision_date": "2026-05-31",
                        "symbol": "MSFT",
                        "action_taken": "skipped",
                        "recommendation_run_id": run_id,
                        "report_date": "2026-05-31",
                        "rationale": "Waited for a pullback.",
                    }
                )
                conn = storage.init_db()
                after = conn.execute("SELECT action, score FROM recommendation_scores WHERE symbol = 'MSFT'").fetchall()
                journal_count = conn.execute("SELECT COUNT(*) FROM manual_trade_journal").fetchone()[0]
                conn.close()

        self.assertEqual(before, after)
        self.assertEqual(journal_count, 1)

    def test_cli_records_manual_entry_without_broker_access(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "journal.sqlite"
            with (
                patch("stock_trading.storage.DB_FILE", db_path),
                patch(
                    "sys.argv",
                    [
                        "add_trade_journal_entry.py",
                        "AMZN",
                        "reviewed_only",
                        "--decision-date",
                        "2026-05-31",
                        "--report-date",
                        "2026-05-31",
                        "--notes",
                        "Reviewed outside the app.",
                    ],
                ),
                patch("sys.stdout", new_callable=io.StringIO) as stdout,
            ):
                exit_code = add_trade_journal_entry.main()
                rows = list_manual_journal_entries(symbol="AMZN", report_date="2026-05-31")

        self.assertEqual(exit_code, 0)
        self.assertIn("Recorded manual journal entry", stdout.getvalue())
        self.assertEqual(rows[0]["action_taken"], "reviewed_only")


if __name__ == "__main__":
    unittest.main()
