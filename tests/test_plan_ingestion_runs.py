#!/usr/bin/env python3
"""Regression tests for ingestion freshness and backfill planning."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from scripts import plan_ingestion_runs as subject
from stock_trading import storage


class PlanIngestionRunsTests(unittest.TestCase):
    def test_due_plan_prioritizes_stale_high_signal_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            db_file = data_dir / "stock_trading.sqlite"
            with (
                patch.object(storage, "DATA_DIR", data_dir),
                patch.object(storage, "DB_FILE", db_file),
                patch.object(
                    subject,
                    "load_source_configs",
                    return_value={
                        "AWS News Blog": {
                            "source_name": "AWS News Blog",
                            "source_category": "company_blog",
                            "source_tier": "tier_1_official",
                            "access_model": "free_public",
                            "implementation_status": "configured_public_source",
                        }
                    },
                ),
                patch.object(
                    subject,
                    "utc_now",
                    return_value=datetime(2026, 5, 29, 12, 0, tzinfo=timezone.utc),
                ),
            ):
                conn = storage.init_db()
                with conn:
                    conn.execute(
                        """
                        INSERT INTO research_evidence (
                            symbol, evidence_type, source_name, source_type,
                            source_timestamp, fetched_at, title, summary
                        )
                        VALUES (
                            'AMZN', 'company_blog_public_feed', 'AWS News Blog',
                            'company_blog', '2026-05-20T12:00:00+00:00',
                            '2026-05-20T12:00:00+00:00', 'AWS item', ''
                        )
                        """
                    )
                    conn.execute(
                        """
                        INSERT INTO source_quality_metrics (
                            metric_date, source_name, source_category, quality_label
                        )
                        VALUES ('2026-05-29', 'AWS News Blog', 'company_blog', 'high_signal')
                        """
                    )
                conn.close()

                plan_rows, backfill_rows = subject.build_plan()

        self.assertEqual(plan_rows[0]["source_name"], "AWS News Blog")
        self.assertEqual(plan_rows[0]["due_status"], "due")
        self.assertEqual(plan_rows[0]["cadence_days"], 1)
        self.assertIn("Cadence elapsed", plan_rows[0]["reason"])
        self.assertEqual(backfill_rows[0]["source_name"], "AWS News Blog")
        self.assertEqual(backfill_rows[0]["status"], "queued")

    def test_blocked_source_enters_cooldown(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            db_file = data_dir / "stock_trading.sqlite"
            with (
                patch.object(storage, "DATA_DIR", data_dir),
                patch.object(storage, "DB_FILE", db_file),
                patch.object(
                    subject,
                    "load_source_configs",
                    return_value={
                        "VentureBeat AI": {
                            "source_name": "VentureBeat AI",
                            "source_category": "tech_news",
                            "access_model": "free_public",
                            "implementation_status": "configured_public_source",
                        }
                    },
                ),
                patch.object(
                    subject,
                    "utc_now",
                    return_value=datetime(2026, 5, 29, 12, 0, tzinfo=timezone.utc),
                ),
            ):
                conn = storage.init_db()
                with conn:
                    conn.execute(
                        """
                        INSERT INTO provider_payloads (
                            provider, endpoint, symbol, status, message, created_at
                        )
                        VALUES (
                            'VentureBeat AI', 'public_feed', 'MARKET', 'blocked',
                            'blocked by upstream', '2026-05-29T10:00:00+00:00'
                        )
                        """
                    )
                conn.close()

                plan_rows, backfill_rows = subject.build_plan()

        self.assertEqual(plan_rows[0]["due_status"], "cooldown")
        self.assertIn("blocked", plan_rows[0]["reason"].lower())
        self.assertEqual(backfill_rows[0]["status"], "cooldown")

    def test_records_plan_and_backfill_queue(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            db_file = data_dir / "stock_trading.sqlite"
            with (
                patch.object(storage, "DATA_DIR", data_dir),
                patch.object(storage, "DB_FILE", db_file),
                patch.object(
                    subject,
                    "load_source_configs",
                    return_value={
                        "Micron Newsroom": {
                            "source_name": "Micron Newsroom",
                            "source_category": "company_newsroom",
                            "source_tier": "tier_1_official",
                            "access_model": "free_public",
                        }
                    },
                ),
                patch.object(subject, "direct_symbol_for_source", return_value="MU"),
                patch.object(
                    subject,
                    "utc_now",
                    return_value=datetime(2026, 5, 29, 12, 0, tzinfo=timezone.utc),
                ),
            ):
                plan_rows, backfill_rows = subject.build_plan()
                storage.record_ingestion_run_plan(plan_rows, rebuild=True)
                storage.record_ingestion_backfill_queue(backfill_rows, rebuild=True)
                conn = storage.init_db()
                stored_plan = conn.execute(
                    "SELECT due_status, priority_rank FROM ingestion_run_plan WHERE source_name = 'Micron Newsroom'"
                ).fetchone()
                stored_backfill = conn.execute(
                    "SELECT symbol, status FROM ingestion_backfill_queue WHERE source_name = 'Micron Newsroom'"
                ).fetchone()
                conn.close()

        self.assertEqual(stored_plan[0], "due")
        self.assertEqual(stored_plan[1], 1)
        self.assertEqual(stored_backfill[0], "MU")
        self.assertEqual(stored_backfill[1], "queued")


if __name__ == "__main__":
    unittest.main()
