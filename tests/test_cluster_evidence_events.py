#!/usr/bin/env python3
"""Regression tests for evidence event clustering and corroboration."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import cluster_evidence_events as subject
from stock_trading import storage


class EvidenceEventClusterTests(unittest.TestCase):
    def test_clusters_related_direct_and_tagged_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            db_file = data_dir / "stock_trading.sqlite"
            with patch.object(storage, "DATA_DIR", data_dir), patch.object(storage, "DB_FILE", db_file):
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
                            'company_blog', datetime('now'), datetime('now'),
                            'Amazon Bedrock agent tools launch',
                            'AWS launches Bedrock agent tools for enterprise AI.'
                        )
                        """
                    )
                    cursor = conn.execute(
                        """
                        INSERT INTO research_evidence (
                            symbol, evidence_type, source_name, source_type,
                            source_timestamp, fetched_at, title, summary
                        )
                        VALUES (
                            'MARKET', 'tech_news_public_feed', 'TechCrunch AI',
                            'tech_news', datetime('now'), datetime('now'),
                            'Amazon Bedrock agent tools launch for AI apps',
                            'TechCrunch covers the Amazon Bedrock AI launch.'
                        )
                        """
                    )
                    conn.execute(
                        """
                        INSERT INTO evidence_symbol_tags (
                            evidence_id, symbol, match_type, matched_text,
                            confidence, confidence_bucket, match_reason
                        )
                        VALUES (?, 'AMZN', 'product_alias', 'Bedrock', 0.85, 'medium', 'product_alias')
                        """,
                        (cursor.lastrowid,),
                    )
                conn.close()

                clusters, members = subject.build_clusters({"AMZN"}, days=45, min_evidence=1)
                inserted = storage.record_evidence_event_clusters(clusters, members, rebuild=True)
                conn = storage.init_db()
                stored = conn.execute(
                    """
                    SELECT symbol, event_type, corroboration_label, source_count,
                           evidence_count, independent_source_count, company_source_count
                    FROM evidence_event_clusters
                    WHERE symbol = 'AMZN'
                    """
                ).fetchone()
                member_count = conn.execute("SELECT COUNT(*) FROM evidence_event_members").fetchone()[0]
                conn.close()

        self.assertGreaterEqual(len(clusters), 1)
        self.assertEqual(inserted, len(clusters))
        self.assertEqual(stored[0], "AMZN")
        self.assertEqual(stored[1], "product_launch")
        self.assertIn(stored[2], {"independent_confirmed", "multi_source_confirmed"})
        self.assertEqual(stored[3], 2)
        self.assertEqual(stored[4], 2)
        self.assertEqual(stored[5], 1)
        self.assertEqual(stored[6], 1)
        self.assertEqual(member_count, 2)

    def test_company_only_cluster_gets_company_only_label(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            db_file = data_dir / "stock_trading.sqlite"
            with patch.object(storage, "DATA_DIR", data_dir), patch.object(storage, "DB_FILE", db_file):
                conn = storage.init_db()
                with conn:
                    conn.execute(
                        """
                        INSERT INTO research_evidence (
                            symbol, evidence_type, source_name, source_type,
                            source_timestamp, fetched_at, title, summary
                        )
                        VALUES (
                            'NVDA', 'company_blog_public_feed', 'NVIDIA official RSS',
                            'company_blog', datetime('now'), datetime('now'),
                            'NVIDIA Blackwell platform available',
                            'NVIDIA says Blackwell is available for AI systems.'
                        )
                        """
                    )
                conn.close()

                clusters, _members = subject.build_clusters({"NVDA"}, days=45, min_evidence=1)

        self.assertEqual(clusters[0]["corroboration_label"], "company_only")
        self.assertEqual(clusters[0]["confidence"], "medium")


if __name__ == "__main__":
    unittest.main()
