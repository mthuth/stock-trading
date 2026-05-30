#!/usr/bin/env python3
"""Regression tests for source-depth curation."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import curate_source_depth as subject
from stock_trading import storage


class SourceDepthCurationTests(unittest.TestCase):
    def test_sec_companyfacts_become_normalized_depth_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            db_file = data_dir / "stock_trading.sqlite"
            with (
                patch.object(storage, "DATA_DIR", data_dir),
                patch.object(storage, "DB_FILE", db_file),
            ):
                conn = storage.init_db()
                with conn:
                    conn.execute(
                        """
                        INSERT INTO research_evidence (
                            symbol, evidence_type, source_name, source_type, source_url,
                            provider_id, source_timestamp, title, summary, confidence,
                            corroboration_status
                        )
                        VALUES (
                            'NVDA', 'sec_company_fact', 'SEC EDGAR companyfacts API', 'sec',
                            'https://data.sec.gov/api/xbrl/companyfacts/CIK0001045810.json',
                            'nvda-revenue-2026', '2026-01-31', 'NVDA Revenue',
                            'Revenue: 130497000000 for period ending 2026-01-31 from 10-K.',
                            'high', 'primary_source'
                        )
                        """
                    )
                conn.close()

                seen, inserted = subject.curate(["NVDA"], rebuild=True)

                conn = storage.init_db()
                row = conn.execute(
                    """
                    SELECT evidence_type, title, summary, confidence, corroboration_status
                    FROM research_evidence
                    WHERE source_name = ?
                    """,
                    (subject.CURATOR_SOURCE,),
                ).fetchone()
                conn.close()

        self.assertEqual(seen, 1)
        self.assertEqual(inserted, 1)
        self.assertEqual(row[0], "sec_fundamental_depth_signal")
        self.assertIn("revenue growth input", row[1])
        self.assertIn("130497000000", row[2])
        self.assertEqual(row[3], "high")
        self.assertEqual(row[4], "curated_from_sec_companyfacts")

    def test_official_ir_links_are_classified(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            db_file = data_dir / "stock_trading.sqlite"
            with (
                patch.object(storage, "DATA_DIR", data_dir),
                patch.object(storage, "DB_FILE", db_file),
            ):
                conn = storage.init_db()
                with conn:
                    conn.execute(
                        """
                        INSERT INTO research_evidence (
                            symbol, evidence_type, source_name, source_type, source_url,
                            provider_id, source_timestamp, title, summary, confidence,
                            corroboration_status
                        )
                        VALUES (
                            'MSFT', 'official_ir_link', 'Microsoft Investor Relations',
                            'official_ir', 'https://www.microsoft.com/investor/reports',
                            'msft-ir-annual-report', '2026-05-01',
                            'Annual report and Form 10-K', 'Official annual report link.',
                            'medium_high', 'official_company_source'
                        )
                        """
                    )
                conn.close()

                seen, inserted = subject.curate(["MSFT"], rebuild=True)

                conn = storage.init_db()
                row = conn.execute(
                    """
                    SELECT evidence_type, title, summary, confidence, corroboration_status
                    FROM research_evidence
                    WHERE source_name = ?
                    """,
                    (subject.CURATOR_SOURCE,),
                ).fetchone()
                conn.close()

        self.assertEqual(seen, 1)
        self.assertEqual(inserted, 1)
        self.assertEqual(row[0], "official_ir_depth_signal")
        self.assertIn("annual report", row[1])
        self.assertIn("Official IR item classified", row[2])
        self.assertEqual(row[3], "medium_high")
        self.assertEqual(row[4], "curated_from_official_ir")

    def test_official_company_source_uses_direct_source_mapping_and_product_alias(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            db_file = data_dir / "stock_trading.sqlite"
            with (
                patch.object(storage, "DATA_DIR", data_dir),
                patch.object(storage, "DB_FILE", db_file),
                patch.object(subject, "load_direct_symbol_sources", return_value={"AWS News Blog": "AMZN"}),
                patch.object(subject, "load_product_aliases", return_value={"AMZN": ["bedrock", "trainium"]}),
            ):
                conn = storage.init_db()
                with conn:
                    conn.execute(
                        """
                        INSERT INTO research_evidence (
                            symbol, evidence_type, source_name, source_type, source_url,
                            provider_id, source_timestamp, title, summary, confidence,
                            corroboration_status
                        )
                        VALUES (
                            'MARKET', 'company_blog_public_feed', 'AWS News Blog',
                            'company_blog', 'https://aws.amazon.com/blogs/aws/bedrock-update',
                            'aws-bedrock-update', '2026-05-01',
                            'New Amazon Bedrock agent tools launch',
                            'AWS introduces Bedrock tooling for enterprise AI agents.',
                            'medium_high', 'company_framed_needs_corroboration'
                        )
                        """
                    )
                conn.close()

                seen, inserted = subject.curate([], rebuild=True)

                conn = storage.init_db()
                row = conn.execute(
                    """
                    SELECT symbol, evidence_type, title, summary, corroboration_status
                    FROM research_evidence
                    WHERE source_name = ?
                    """,
                    (subject.CURATOR_SOURCE,),
                ).fetchone()
                conn.close()

        self.assertEqual(seen, 1)
        self.assertEqual(inserted, 1)
        self.assertEqual(row[0], "AMZN")
        self.assertEqual(row[1], "official_source_depth_signal")
        self.assertIn("product launch", row[2])
        self.assertIn("bedrock", row[3])
        self.assertEqual(row[4], "curated_from_official_company_source")

    def test_rerun_dedupes_stable_depth_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            db_file = data_dir / "stock_trading.sqlite"
            with (
                patch.object(storage, "DATA_DIR", data_dir),
                patch.object(storage, "DB_FILE", db_file),
            ):
                conn = storage.init_db()
                with conn:
                    conn.execute(
                        """
                        INSERT INTO research_evidence (
                            symbol, evidence_type, source_name, source_type, source_url,
                            provider_id, source_timestamp, title, summary, confidence,
                            corroboration_status
                        )
                        VALUES (
                            'NVDA', 'sec_filing', 'SEC EDGAR submissions API', 'sec',
                            'https://www.sec.gov/Archives/nvda-10q',
                            'nvda-10q-2026', '2026-04-30', 'NVDA 10-Q',
                            '10-Q filing for report date 2026-04-30.',
                            'high', 'primary_source'
                        )
                        """
                    )
                conn.close()

                first_seen, first_inserted = subject.curate(["NVDA"], rebuild=True)
                second_seen, second_inserted = subject.curate(["NVDA"], rebuild=False)

        self.assertEqual(first_seen, 1)
        self.assertEqual(first_inserted, 1)
        self.assertEqual(second_seen, 1)
        self.assertEqual(second_inserted, 0)


if __name__ == "__main__":
    unittest.main()
