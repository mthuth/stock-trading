#!/usr/bin/env python3
"""Regression tests for public research feed/archive parsing."""

from __future__ import annotations

import unittest
from unittest.mock import patch


from scripts import ingest_public_research_feeds as subject


class IngestPublicResearchFeedsTests(unittest.TestCase):
    def test_integration_rows_accepts_expanded_public_categories(self) -> None:
        rows = [
            {
                "source_name": "AWS News Blog",
                "source_category": "company_blog",
                "access_model": "free_public",
            },
            {
                "source_name": "Business Wire",
                "source_category": "press_wire",
                "access_model": "free_public",
            },
            {
                "source_name": "Paid options",
                "source_category": "paid_options_flow",
                "access_model": "paid_api_candidate",
            },
        ]

        with patch.object(subject, "read_csv", return_value=(rows, [])):
            selected = subject.integration_rows(None)

        self.assertEqual([row["source_name"] for row in selected], ["AWS News Blog", "Business Wire"])

    def test_evidence_rows_use_category_specific_defaults(self) -> None:
        rows = subject.evidence_rows(
            {
                "source_name": "AWS News Blog",
                "source_category": "company_blog",
                "corroboration_required": "true",
            },
            "https://aws.amazon.com/blogs/aws/feed/",
            [
                {
                    "title": "AWS launches AI infrastructure",
                    "link": "https://example.com/post",
                    "published": "2026-05-28",
                    "summary": "AWS AI update",
                    "guid": "post-1",
                }
            ],
        )

        self.assertEqual(rows[0]["evidence_type"], "company_blog_public_feed")
        self.assertEqual(rows[0]["confidence"], "medium_high")
        self.assertEqual(rows[0]["corroboration_status"], "company_framed_needs_corroboration")

    def test_batch_archive_parser_extracts_public_links(self) -> None:
        html = """
        <html><body>
          <a href="/the-batch/google-launches-ai-feature/">Google launches AI feature</a>
          <a href="https://www.deeplearning.ai/the-batch/chip-shortage-update/">Chip shortage update</a>
        </body></html>
        """
        with patch.object(subject, "fetch_text", return_value=("ok", html, "text/html")):
            status, items, message = subject.batch_archive_items(
                "https://www.deeplearning.ai/the-batch/",
                5,
            )

        self.assertEqual(status, "ok")
        self.assertEqual(message, "the_batch_archive")
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["title"], "Google launches AI feature")
        self.assertTrue(items[0]["link"].startswith("https://www.deeplearning.ai/the-batch/"))

    def test_ingest_source_records_public_feed_body_payload(self) -> None:
        feed_body = """<?xml version="1.0"?>
        <rss><channel><item>
          <title>NVIDIA AI platform update</title>
          <link>https://example.com/nvda</link>
          <description>Public feed item.</description>
          <guid>item-1</guid>
        </item></channel></rss>
        """
        source = {
            "source_name": "Unit Public Feed",
            "source_category": "tech_news",
            "official_url": "https://example.com",
            "feed_url": "https://example.com/feed.xml",
            "access_model": "free_public",
        }
        recorded_evidence: list[dict[str, object]] = []

        def fake_record_research_evidence(rows: list[dict[str, object]]) -> int:
            recorded_evidence.extend(rows)
            return len(rows)

        with (
            patch.object(subject, "discover_feed_url", return_value=("ok", source["feed_url"], feed_body, "configured_feed")),
            patch.object(subject, "record_raw_ingestion_payload") as record_raw_ingestion_payload,
            patch.object(subject, "record_provider_payload", return_value=1) as record_provider_payload,
            patch.object(subject, "record_research_evidence", side_effect=fake_record_research_evidence),
        ):
            inserted, status = subject.ingest_source(source, item_limit=5)

        self.assertEqual(inserted, 1)
        self.assertEqual(status["status"], "ok")
        record_raw_ingestion_payload.assert_called_once()
        self.assertEqual(record_raw_ingestion_payload.call_args.kwargs["endpoint"], "public_feed_body")
        self.assertIn("NVIDIA AI platform update", record_raw_ingestion_payload.call_args.kwargs["payload_text"])
        record_provider_payload.assert_called_once()
        self.assertEqual(record_provider_payload.call_args.args[1], "public_feed")
        self.assertEqual(recorded_evidence[0]["provider_endpoint"], "public_rss_or_archive")


if __name__ == "__main__":
    unittest.main()
