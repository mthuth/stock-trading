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

        self.assertEqual(rows[0]["quality_label"], "high_signal")
        self.assertEqual(rows[0]["records_inserted"], 3)
        self.assertEqual(rows[0]["tagged_evidence"], 3)
        self.assertEqual(rows[0]["tag_rate"], 1.0)
        self.assertEqual(inserted, 1)
        self.assertEqual(stored[0], "high_signal")
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

        self.assertEqual(rows["Noisy Source"]["quality_label"], "needs_review")
        self.assertEqual(rows["Noisy Source"]["tag_rate"], 0.0)
        self.assertEqual(rows["Blocked Source"]["quality_label"], "blocked")


if __name__ == "__main__":
    unittest.main()
