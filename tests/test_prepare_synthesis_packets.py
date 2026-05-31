#!/usr/bin/env python3
"""Regression tests for deterministic synthesis readiness preparation."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import prepare_synthesis_packets as subject
from stock_trading import storage


class PrepareSynthesisPacketsTests(unittest.TestCase):
    def test_ready_and_company_only_events_are_classified(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            db_file = data_dir / "stock_trading.sqlite"
            output_dir = data_dir / "reports"
            with patch.object(storage, "DATA_DIR", data_dir), patch.object(storage, "DB_FILE", db_file):
                conn = storage.init_db()
                with conn:
                    conn.execute(
                        """
                        INSERT INTO evidence_event_clusters (
                            event_date, symbol, event_key, event_type, headline,
                            summary, corroboration_label, source_count, evidence_count,
                            independent_source_count, primary_source_count,
                            company_source_count, opinion_source_count,
                            latest_evidence_at, confidence, notes
                        )
                        VALUES (
                            '2026-05-29', 'AMZN', 'amzn-ready', 'product_launch',
                            'Amazon Bedrock launch confirmed', 'Two-source event',
                            'independent_confirmed', 2, 2, 1, 0, 1, 0,
                            '2026-05-29T12:00:00', 'high', ''
                        )
                        """
                    )
                    conn.execute(
                        """
                        INSERT INTO evidence_event_clusters (
                            event_date, symbol, event_key, event_type, headline,
                            summary, corroboration_label, source_count, evidence_count,
                            independent_source_count, primary_source_count,
                            company_source_count, opinion_source_count,
                            latest_evidence_at, confidence, notes
                        )
                        VALUES (
                            '2026-05-29', 'NVDA', 'nvda-company-only', 'ai_platform_update',
                            'NVIDIA Blackwell update', 'Company-only event',
                            'company_only', 1, 1, 0, 0, 1, 0,
                            '2026-05-29T12:00:00', 'medium', ''
                        )
                        """
                    )
                conn.close()

                clusters = subject.load_clusters()
                review_rows = subject.build_review_rows(clusters)
                readiness_rows, packets, packet_path = subject.build_packets(
                    clusters,
                    review_rows,
                    "2026-05-29",
                    output_dir,
                    5,
                )
                storage.record_evidence_review_queue(review_rows, rebuild=True)
                storage.record_synthesis_readiness(readiness_rows, rebuild=True)
                packet_exists = packet_path.exists()
                conn = storage.init_db()
                statuses = {
                    row[0]: row[1]
                    for row in conn.execute(
                        "SELECT event_key, review_status FROM evidence_review_queue"
                    ).fetchall()
                }
                readiness = {
                    row[0]: row[1]
                    for row in conn.execute(
                        "SELECT symbol, readiness_status FROM synthesis_readiness"
                    ).fetchall()
                }
                conn.close()

        self.assertEqual(statuses["amzn-ready"], "ready_for_synthesis")
        self.assertEqual(statuses["nvda-company-only"], "needs_corroboration")
        self.assertIn(readiness["AMZN"], {"partially_ready", "ready_for_ai_synthesis"})
        self.assertEqual(readiness["NVDA"], "needs_corroboration")
        self.assertTrue(packet_exists)
        self.assertIn("AMZN", packets["symbols"])
        self.assertIn("NVDA", packets["symbols"])
        self.assertIn("reason_codes", packets["symbols"]["NVDA"])

    def test_primary_high_impact_event_is_ready_even_single_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            db_file = data_dir / "stock_trading.sqlite"
            with patch.object(storage, "DATA_DIR", data_dir), patch.object(storage, "DB_FILE", db_file):
                conn = storage.init_db()
                with conn:
                    conn.execute(
                        """
                        INSERT INTO evidence_event_clusters (
                            event_date, symbol, event_key, event_type, headline,
                            summary, corroboration_label, source_count, evidence_count,
                            independent_source_count, primary_source_count,
                            company_source_count, opinion_source_count,
                            latest_evidence_at, confidence, notes
                        )
                        VALUES (
                            '2026-05-29', 'MSFT', 'msft-10q', 'filing_disclosure',
                            'Microsoft 10-Q filing', 'Primary filing event',
                            'single_source', 1, 1, 0, 1, 0, 0,
                            '2026-05-29T12:00:00', 'medium', ''
                        )
                        """
                    )
                conn.close()

                review = subject.build_review_rows(subject.load_clusters())[0]

        self.assertEqual(review["review_status"], "ready_for_synthesis")
        self.assertIn("primary-source", review["review_reason"])

    def test_provider_gap_blocks_packet_eligibility(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            db_file = data_dir / "stock_trading.sqlite"
            output_dir = data_dir / "reports"
            with patch.object(storage, "DATA_DIR", data_dir), patch.object(storage, "DB_FILE", db_file):
                conn = storage.init_db()
                with conn:
                    conn.execute(
                        """
                        INSERT INTO evidence_event_clusters (
                            event_date, symbol, event_key, event_type, headline,
                            summary, corroboration_label, source_count, evidence_count,
                            independent_source_count, primary_source_count,
                            company_source_count, opinion_source_count,
                            latest_evidence_at, confidence, notes
                        )
                        VALUES (
                            '2026-05-29', 'AVGO', 'avgo-ready-primary', 'product_launch',
                            'AVGO platform update', 'Primary plus independent event',
                            'primary_plus_confirmed', 2, 2, 1, 1, 0, 0,
                            '2026-05-29T12:00:00', 'high', ''
                        )
                        """
                    )
                    conn.execute(
                        """
                        INSERT INTO evidence_event_clusters (
                            event_date, symbol, event_key, event_type, headline,
                            summary, corroboration_label, source_count, evidence_count,
                            independent_source_count, primary_source_count,
                            company_source_count, opinion_source_count,
                            latest_evidence_at, confidence, notes
                        )
                        VALUES (
                            '2026-05-29', 'AVGO', 'avgo-ready-independent', 'analyst_target',
                            'AVGO target corroborated', 'Independent event',
                            'independent_confirmed', 2, 2, 1, 0, 0, 0,
                            '2026-05-29T12:00:00', 'high', ''
                        )
                        """
                    )
                conn.close()

                clusters = subject.load_clusters()
                review_rows = subject.build_review_rows(clusters)
                readiness_rows, packets, _ = subject.build_packets(
                    clusters,
                    review_rows,
                    "2026-05-29",
                    output_dir,
                    5,
                    provider_gaps=[
                        {
                            "symbol": "AVGO",
                            "provider": "SEC",
                            "field_name": "companyfacts",
                            "status": "blocked",
                        }
                    ],
                    recommendation_facts={"AVGO": {"target_confidence": "High"}},
                )

        self.assertEqual(readiness_rows[0]["readiness_status"], "blocked_by_provider_gap")
        self.assertFalse(packets["symbols"]["AVGO"]["eligible_for_ai_synthesis"])
        self.assertIn("provider_gap:blocked:SEC:companyfacts", packets["symbols"]["AVGO"]["reason_codes"])


if __name__ == "__main__":
    unittest.main()
