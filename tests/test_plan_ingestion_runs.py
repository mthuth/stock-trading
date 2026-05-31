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


NOW = datetime(2026, 5, 29, 12, 0, tzinfo=timezone.utc)


def source_config(
    name: str,
    category: str,
    tier: str = "tier_2_independent",
    access_model: str = "free_public",
    implementation_status: str = "configured_public_source",
) -> dict[str, str]:
    return {
        "source_name": name,
        "source_category": category,
        "source_tier": tier,
        "access_model": access_model,
        "implementation_status": implementation_status,
    }


class PlannerFixture:
    def __init__(self, testcase: unittest.TestCase, configs: dict[str, dict[str, str]]) -> None:
        self.testcase = testcase
        self.configs = configs
        self.tmpdir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.tmpdir.name)
        self.db_file = self.data_dir / "stock_trading.sqlite"
        self.patches = [
            patch.object(storage, "DATA_DIR", self.data_dir),
            patch.object(storage, "DB_FILE", self.db_file),
            patch.object(subject, "load_source_configs", return_value=configs),
            patch.object(subject, "utc_now", return_value=NOW),
        ]

    def __enter__(self) -> "PlannerFixture":
        for active_patch in self.patches:
            active_patch.start()
        self.testcase.addCleanup(self.cleanup)
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def cleanup(self) -> None:
        for active_patch in reversed(self.patches):
            active_patch.stop()
        self.tmpdir.cleanup()

    def connect(self):
        return storage.init_db()

    def build(self) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        return subject.build_plan()


def insert_evidence(
    conn,
    source_name: str,
    category: str,
    fetched_at: str,
    source_timestamp: str | None = None,
    symbol: str = "NVDA",
) -> None:
    conn.execute(
        """
        INSERT INTO research_evidence (
            symbol, evidence_type, source_name, source_type,
            source_timestamp, fetched_at, title, summary
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            symbol,
            f"{category}_public_feed",
            source_name,
            category,
            source_timestamp or fetched_at,
            fetched_at,
            f"{source_name} item",
            "",
        ),
    )


def insert_quality(
    conn,
    source_name: str,
    category: str,
    quality_label: str,
    *,
    total_evidence: int = 0,
    latest_success: str = "",
    latest_issue: str = "",
    blocked_runs: int = 0,
    error_runs: int = 0,
) -> None:
    conn.execute(
        """
        INSERT INTO source_quality_metrics (
            metric_date, source_name, source_category, total_evidence,
            latest_success, latest_issue, blocked_runs, error_runs, quality_label
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "2026-05-29",
            source_name,
            category,
            total_evidence,
            latest_success,
            latest_issue,
            blocked_runs,
            error_runs,
            quality_label,
        ),
    )


def insert_payload(conn, source_name: str, status: str, created_at: str, message: str = "") -> None:
    conn.execute(
        """
        INSERT INTO provider_payloads (
            provider, endpoint, symbol, status, message, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (source_name, "public_feed", "MARKET", status, message, created_at),
    )


class PlanIngestionRunsTests(unittest.TestCase):
    def test_due_source_has_no_success_recorded(self) -> None:
        with PlannerFixture(
            self,
            {"Micron Newsroom": source_config("Micron Newsroom", "company_newsroom", "tier_1_official")},
        ):
            plan_rows, backfill_rows = subject.build_plan()

        self.assertEqual(plan_rows[0]["source_name"], "Micron Newsroom")
        self.assertEqual(plan_rows[0]["due_status"], "due")
        self.assertIn("No successful source run", plan_rows[0]["reason"])
        self.assertEqual(backfill_rows[0]["status"], "queued")

    def test_cooldown_source_waits_after_recent_block(self) -> None:
        with PlannerFixture(
            self,
            {"VentureBeat AI": source_config("VentureBeat AI", "tech_news")},
        ) as fixture:
            conn = fixture.connect()
            with conn:
                insert_payload(conn, "VentureBeat AI", "blocked", "2026-05-29T10:00:00+00:00", "blocked by upstream")
            conn.close()

            plan_rows, backfill_rows = fixture.build()

        self.assertEqual(plan_rows[0]["due_status"], "cooldown")
        self.assertIn("blocked", plan_rows[0]["reason"].lower())
        self.assertTrue(plan_rows[0]["cooldown_until"])
        self.assertEqual(backfill_rows[0]["status"], "cooldown")

    def test_blocked_source_shows_review_after_cooldown_expires(self) -> None:
        with PlannerFixture(
            self,
            {"Public RSS": source_config("Public RSS", "tech_news")},
        ) as fixture:
            conn = fixture.connect()
            with conn:
                insert_payload(conn, "Public RSS", "blocked", "2026-05-10T10:00:00+00:00", "HTTP 403")
            conn.close()

            plan_rows, _ = fixture.build()

        self.assertEqual(plan_rows[0]["due_status"], "blocked")
        self.assertIn("HTTP 403", plan_rows[0]["latest_issue"])
        self.assertIn("HTTP 403", plan_rows[0]["reason"])

    def test_stale_source_is_due_after_cadence_elapsed(self) -> None:
        with PlannerFixture(
            self,
            {"AWS News Blog": source_config("AWS News Blog", "company_blog", "tier_1_official")},
        ) as fixture:
            conn = fixture.connect()
            with conn:
                insert_evidence(
                    conn,
                    "AWS News Blog",
                    "company_blog",
                    "2026-05-20T12:00:00+00:00",
                )
                insert_quality(conn, "AWS News Blog", "company_blog", "high_signal")
            conn.close()

            plan_rows, backfill_rows = fixture.build()

        self.assertEqual(plan_rows[0]["source_name"], "AWS News Blog")
        self.assertEqual(plan_rows[0]["due_status"], "stale")
        self.assertEqual(plan_rows[0]["cadence_days"], 1)
        self.assertIn("stale", plan_rows[0]["reason"])
        self.assertEqual(backfill_rows[0]["status"], "queued")

    def test_not_implemented_source_is_visible_but_low_priority(self) -> None:
        with PlannerFixture(
            self,
            {
                "Paid Analyst Feed": source_config(
                    "Paid Analyst Feed",
                    "analyst_research",
                    access_model="paid_api_candidate",
                    implementation_status="not_implemented",
                )
            },
        ):
            plan_rows, backfill_rows = subject.build_plan()

        self.assertEqual(plan_rows[0]["due_status"], "not_implemented")
        self.assertIn("not implemented", plan_rows[0]["reason"])
        self.assertEqual(backfill_rows, [])

    def test_backfill_needed_source_stays_visible_when_recently_refreshed(self) -> None:
        with PlannerFixture(
            self,
            {"NVIDIA Blog": source_config("NVIDIA Blog", "company_blog", "tier_1_official")},
        ) as fixture:
            conn = fixture.connect()
            with conn:
                insert_evidence(
                    conn,
                    "NVIDIA Blog",
                    "company_blog",
                    "2026-05-29T09:00:00+00:00",
                )
                insert_evidence(
                    conn,
                    "NVIDIA Blog",
                    "company_blog",
                    "2026-05-29T10:00:00+00:00",
                )
            conn.close()

            plan_rows, backfill_rows = fixture.build()

        self.assertEqual(plan_rows[0]["due_status"], "backfill_needed")
        self.assertIn("backfill", plan_rows[0]["reason"])
        self.assertEqual(backfill_rows[0]["source_name"], "NVIDIA Blog")
        self.assertEqual(backfill_rows[0]["reason"], "Too few records for source history.")

    def test_high_priority_official_sources_sort_above_news_and_context_sources(self) -> None:
        with PlannerFixture(
            self,
            {
                "Company investor relations": source_config("Company investor relations", "company_ir", "tier_1_official"),
                "TechCrunch AI": source_config("TechCrunch AI", "tech_news"),
                "Weekly AI Podcast": source_config("Weekly AI Podcast", "podcast"),
            },
        ):
            plan_rows, _ = subject.build_plan()

        self.assertEqual([row["source_name"] for row in plan_rows], [
            "Company investor relations",
            "TechCrunch AI",
            "Weekly AI Podcast",
        ])

    def test_low_priority_context_sources_sort_below_same_status_news_sources(self) -> None:
        with PlannerFixture(
            self,
            {
                "Semiconductor Daily": source_config("Semiconductor Daily", "semiconductor_news"),
                "Industry Podcast": source_config("Industry Podcast", "podcast"),
            },
        ):
            plan_rows, _ = subject.build_plan()

        self.assertEqual(plan_rows[-1]["source_name"], "Industry Podcast")
        self.assertGreater(plan_rows[-1]["priority_rank"], plan_rows[0]["priority_rank"])

    def test_records_plan_and_backfill_queue(self) -> None:
        with (
            PlannerFixture(
                self,
                {"Micron Newsroom": source_config("Micron Newsroom", "company_newsroom", "tier_1_official")},
            ) as fixture,
            patch.object(subject, "direct_symbol_for_source", return_value="MU"),
        ):
            plan_rows, backfill_rows = fixture.build()
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
