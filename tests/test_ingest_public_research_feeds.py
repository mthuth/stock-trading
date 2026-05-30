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
        self.assertEqual(status["status_label"], "rss_ok")
        record_raw_ingestion_payload.assert_called_once()
        self.assertEqual(record_raw_ingestion_payload.call_args.kwargs["endpoint"], "public_feed_body")
        self.assertIn("NVIDIA AI platform update", record_raw_ingestion_payload.call_args.kwargs["payload_text"])
        record_provider_payload.assert_called_once()
        self.assertEqual(record_provider_payload.call_args.args[1], "public_feed")
        self.assertEqual(recorded_evidence[0]["provider_endpoint"], "public_rss_or_archive")

    def test_page_link_items_dedupes_public_source_links(self) -> None:
        html = """
        <html><body>
          <a href="/news-releases/amd-ai-chip-launch">AMD launches AI chip</a>
          <a href="/news-releases/amd-ai-chip-launch">AMD launches AI chip</a>
          <a href="/privacy">Privacy policy</a>
          <a href="https://external.example/news">External semiconductor article</a>
        </body></html>
        """
        source = {"source_name": "AMD Newsroom", "source_category": "company_newsroom"}

        items = subject.page_link_items(source, "https://ir.amd.com/news-events/press-releases", html, 5)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "AMD launches AI chip")
        self.assertEqual(items[0]["link"], "https://ir.amd.com/news-releases/amd-ai-chip-launch")

    def test_page_link_evidence_uses_public_page_link_type(self) -> None:
        rows = subject.evidence_rows(
            {"source_name": "AMD Newsroom", "source_category": "company_newsroom"},
            "https://ir.amd.com/news-events/press-releases",
            [
                {
                    "title": "AMD reports financial results",
                    "link": "https://ir.amd.com/news-releases/results",
                    "published": "",
                    "summary": "Public source page link.",
                    "guid": "https://ir.amd.com/news-releases/results",
                }
            ],
            "public_page_link",
            "public_page_link",
        )

        self.assertEqual(rows[0]["evidence_type"], "company_newsroom_public_page_link")
        self.assertEqual(rows[0]["provider_endpoint"], "public_page_link")
        self.assertEqual(rows[0]["confidence"], "medium_high")

    def test_ingest_source_auto_falls_back_to_page_links(self) -> None:
        source = {
            "source_name": "AMD Newsroom",
            "source_category": "company_newsroom",
            "official_url": "https://ir.amd.com/news-events/press-releases",
            "feed_url": "",
            "access_model": "free_public",
        }
        html = """
        <html><body>
          <a href="/news-releases/amd-ai-chip-launch">AMD launches AI chip</a>
        </body></html>
        """
        recorded_evidence: list[dict[str, object]] = []

        def fake_record_research_evidence(rows: list[dict[str, object]]) -> int:
            recorded_evidence.extend(rows)
            return len(rows)

        with (
            patch.object(subject, "discover_feed_url", return_value=("missing", "", "", "No RSS/Atom feed discovered")),
            patch.object(subject, "fetch_text", return_value=("ok", html, "text/html")),
            patch.object(subject, "record_raw_ingestion_payload"),
            patch.object(subject, "record_provider_payload", return_value=1) as record_provider_payload,
            patch.object(subject, "record_research_evidence", side_effect=fake_record_research_evidence),
        ):
            inserted, status = subject.ingest_source(source, item_limit=5, mode="auto")

        self.assertEqual(inserted, 1)
        self.assertEqual(status["status"], "ok")
        self.assertEqual(status["field_name"], "public_page_link")
        self.assertEqual(status["status_label"], "page_links_ok")
        self.assertEqual(record_provider_payload.call_args.args[1], "public_page_link")
        self.assertTrue(record_provider_payload.call_args.kwargs["payload_json"]["fallback_used"])
        self.assertEqual(record_provider_payload.call_args.kwargs["payload_json"]["status_label"], "page_links_ok")
        self.assertEqual(recorded_evidence[0]["provider_endpoint"], "public_page_link")

    def test_normalize_categories_rejects_unknown_category(self) -> None:
        with self.assertRaises(ValueError):
            subject.normalize_categories("company_newsroom,unknown")


if __name__ == "__main__":
    unittest.main()
