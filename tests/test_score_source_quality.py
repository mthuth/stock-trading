#!/usr/bin/env python3
"""Regression tests for V1.9 source-quality scoring."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import score_source_quality as subject
from stock_trading import storage as engine_common


class SourceQualityTests(unittest.TestCase):
    def test_high_signal_source_rolls_up_tags_and_confidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            db_file = data_dir / "stock_trading.sqlite"
            with (
                patch.object(engine_common, "DATA_DIR", data_dir),
                patch.object(engine_common, "DB_FILE", db_file),
                patch.object(subject, "DB_FILE", db_file),
            ):
                conn = engine_common.init_db()
                with conn:
                    for index in range(3):
                        cursor = conn.execute(
                            """
                            INSERT INTO research_evidence (
                                symbol, evidence_type, source_name, source_type, title,
                                summary, confidence, corroboration_status
                            )
                            VALUES ('MARKET', 'public_feed', 'Unit Source', 'tech_news', ?, '', 'medium', 'pending')
                            """,
                            (f"NVIDIA item {index}",),
                        )
                        conn.execute(
                            """
                            INSERT INTO evidence_symbol_tags (
                                evidence_id, symbol, match_type, matched_text, confidence,
                                confidence_bucket, match_reason
                            )
                            VALUES (?, 'NVDA', 'company_alias', 'NVIDIA', 0.95, 'high', 'company_alias')
                            """,
                            (cursor.lastrowid,),
                        )
                    conn.execute(
                        """
                        INSERT INTO provider_payloads (provider, endpoint, symbol, status, message)
                        VALUES ('Unit Source', 'public_feed', 'MARKET', 'ok', 'seen=3 inserted=3')
                        """
                    )
                conn.close()

                rows = subject.load_metrics(source_filter="Unit Source")
                inserted = engine_common.record_source_quality_metrics(rows, rebuild=True)

                conn = engine_common.init_db()
                stored = conn.execute(
                    "SELECT quality_label, tag_rate, avg_tag_confidence, confidence_bucket_summary FROM source_quality_metrics WHERE source_name = 'Unit Source'"
                ).fetchone()
                conn.close()

        self.assertEqual(rows[0]["quality_label"], "useful_source")
        self.assertEqual(rows[0]["records_inserted"], 3)
        self.assertEqual(rows[0]["tagged_evidence"], 3)
        self.assertEqual(rows[0]["tag_rate"], 1.0)
        self.assertEqual(inserted, 1)
        self.assertEqual(stored[0], "useful_source")
        self.assertEqual(stored[1], 1.0)
        self.assertEqual(stored[2], 0.95)
        self.assertEqual(stored[3], "high: 3")

    def test_noisy_and_blocked_sources_get_review_labels(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            db_file = data_dir / "stock_trading.sqlite"
            with (
                patch.object(engine_common, "DATA_DIR", data_dir),
                patch.object(engine_common, "DB_FILE", db_file),
                patch.object(subject, "DB_FILE", db_file),
            ):
                conn = engine_common.init_db()
                with conn:
                    for index in range(5):
                        conn.execute(
                            """
                            INSERT INTO research_evidence (
                                symbol, evidence_type, source_name, source_type, title,
                                summary, confidence, corroboration_status
                            )
                            VALUES ('MARKET', 'public_feed', 'Noisy Source', 'tech_news', ?, '', 'medium', 'pending')
                            """,
                            (f"General AI item {index}",),
                        )
                    conn.execute(
                        """
                        INSERT INTO provider_payloads (provider, endpoint, symbol, status, message)
                        VALUES ('Blocked Source', 'public_feed', 'MARKET', 'blocked', 'HTTP 403 blocked')
                        """
                    )
                    conn.execute(
                        """
                        INSERT INTO raw_ingestion_payloads (provider, endpoint, symbol, status, message)
                        VALUES ('Blocked Source', 'public_feed', 'MARKET', 'blocked', 'HTTP 403 blocked')
                        """
                    )
                conn.close()

                rows = {row["source_name"]: row for row in subject.load_metrics()}

        self.assertEqual(rows["Noisy Source"]["quality_label"], "noisy_source")
        self.assertEqual(rows["Noisy Source"]["tag_rate"], 0.0)
        self.assertEqual(rows["Blocked Source"]["quality_label"], "blocked_source")
        self.assertEqual(rows["Blocked Source"]["blocked_count"], 2)

    def test_context_not_enough_parser_gap_and_stale_labels_are_distinct(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            db_file = data_dir / "stock_trading.sqlite"
            with (
                patch.object(engine_common, "DATA_DIR", data_dir),
                patch.object(engine_common, "DB_FILE", db_file),
                patch.object(subject, "DB_FILE", db_file),
            ):
                conn = engine_common.init_db()
                with conn:
                    for index in range(3):
                        conn.execute(
                            """
                            INSERT INTO research_evidence (
                                symbol, evidence_type, source_name, source_type, title,
                                summary, confidence, corroboration_status
                            )
                            VALUES ('MARKET', 'public_feed', 'Context Source', 'tech_news', ?, '', 'medium', 'pending')
                            """,
                            (f"Context item {index}",),
                        )
                    conn.execute(
                        """
                        INSERT INTO research_evidence (
                            symbol, evidence_type, source_name, source_type, title,
                            summary, confidence, corroboration_status
                        )
                        VALUES ('MARKET', 'public_feed', 'Thin Source', 'tech_news', 'Only one item', '', 'medium', 'pending')
                        """
                    )
                    conn.execute(
                        """
                        INSERT INTO provider_payloads (provider, endpoint, symbol, status, message)
                        VALUES ('Parser Gap Source', 'public_feed', 'MARKET', 'parser_gap', 'parser_gap: no parseable items')
                        """
                    )
                    conn.execute(
                        """
                        INSERT INTO raw_ingestion_payloads (provider, endpoint, symbol, status, message)
                        VALUES ('Parser Gap Source', 'public_feed', 'MARKET', 'parser_gap', 'parser_gap: no parseable items')
                        """
                    )
                    conn.execute(
                        """
                        INSERT INTO research_evidence (
                            symbol, evidence_type, source_name, source_type, title,
                            summary, confidence, corroboration_status, fetched_at
                        )
                        VALUES ('NVDA', 'public_feed', 'Stale Source', 'tech_news', 'Old item', '', 'medium', 'pending', '2020-01-01 00:00:00')
                        """
                    )
                conn.close()

                rows = {row["source_name"]: row for row in subject.load_metrics()}

        self.assertEqual(rows["Context Source"]["quality_label"], "useful_context")
        self.assertEqual(rows["Thin Source"]["quality_label"], "not_enough_data")
        self.assertEqual(rows["Parser Gap Source"]["quality_label"], "parser_gap")
        self.assertEqual(rows["Parser Gap Source"]["parser_gap_count"], 2)
        self.assertIn("parser", rows["Parser Gap Source"]["notes"].lower())
        self.assertEqual(rows["Stale Source"]["quality_label"], "stale_source")

    def test_low_confidence_matches_make_noisy_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            db_file = data_dir / "stock_trading.sqlite"
            with (
                patch.object(engine_common, "DATA_DIR", data_dir),
                patch.object(engine_common, "DB_FILE", db_file),
                patch.object(subject, "DB_FILE", db_file),
            ):
                conn = engine_common.init_db()
                with conn:
                    for index in range(6):
                        cursor = conn.execute(
                            """
                            INSERT INTO research_evidence (
                                symbol, evidence_type, source_name, source_type, title,
                                summary, confidence, corroboration_status
                            )
                            VALUES ('MARKET', 'public_feed', 'Low Confidence Source', 'tech_news', ?, '', 'medium', 'pending')
                            """,
                            (f"Broad AI item {index}",),
                        )
                        conn.execute(
                            """
                            INSERT INTO evidence_symbol_tags (
                                evidence_id, symbol, match_type, matched_text, confidence,
                                confidence_bucket, match_reason
                            )
                            VALUES (?, 'NVDA', 'sector_context', 'AI', 0.40, 'needs_review', 'sector_context')
                            """,
                            (cursor.lastrowid,),
                        )
                conn.close()

                row = subject.load_metrics(source_filter="Low Confidence Source")[0]

        self.assertEqual(row["quality_label"], "noisy_source")
        self.assertEqual(row["low_confidence_matches"], 6)
        self.assertEqual(row["tagged_evidence"], 0)

    def test_local_source_depth_rows_do_not_create_source_quality(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            db_file = data_dir / "stock_trading.sqlite"
            with (
                patch.object(engine_common, "DATA_DIR", data_dir),
                patch.object(engine_common, "DB_FILE", db_file),
                patch.object(subject, "DB_FILE", db_file),
            ):
                conn = engine_common.init_db()
                with conn:
                    for index in range(5):
                        conn.execute(
                            """
                            INSERT INTO research_evidence (
                                symbol, evidence_type, source_name, source_type, title,
                                summary, confidence, corroboration_status
                            )
                            VALUES ('NVDA', 'official_source_depth_signal', 'Local source depth curator', 'curated_source_depth', ?, '', 'high', 'corroborated')
                            """,
                            (f"Derived source-depth item {index}",),
                        )
                    conn.execute(
                        """
                        INSERT INTO provider_payloads (provider, endpoint, symbol, status, message)
                        VALUES ('Local source depth curator', 'source_depth_curator', 'ALL', 'ok', 'inserted=5')
                        """
                    )
                conn.close()

                rows = subject.load_metrics(source_filter="Local source depth curator")

        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
