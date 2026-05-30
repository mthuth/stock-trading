#!/usr/bin/env python3
"""Regression tests for deterministic source-to-symbol relevance tagging."""

from __future__ import annotations

import sqlite3
import unittest

from scripts import tag_research_evidence as subject


def evidence_row(
    title: str,
    summary: str = "",
    source_name: str = "Unit Source",
    source_url: str = "",
) -> sqlite3.Row:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE evidence (
            id INTEGER, symbol TEXT, source_name TEXT, evidence_type TEXT,
            title TEXT, summary TEXT, source_url TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO evidence VALUES (1, 'MARKET', ?, 'public_feed', ?, ?, ?)
        """,
        (source_name, title, summary, source_url),
    )
    row = conn.execute("SELECT * FROM evidence").fetchone()
    conn.close()
    return row


class TagResearchEvidenceTests(unittest.TestCase):
    def test_config_aliases_preserve_product_mappings(self) -> None:
        rules = subject.alias_rules()
        rows = [evidence_row("AWS launches new Bedrock agent tools")]

        tags = subject.tag_rows(rows, rules)

        self.assertTrue(
            any(
                tag["symbol"] == "AMZN"
                and tag["match_reason"] == "product_alias"
                and tag["confidence_bucket"] == "medium"
                for tag in tags
            )
        )

    def test_official_company_source_defaults_to_symbol(self) -> None:
        rules = subject.alias_rules()
        rows = [evidence_row("Meet our newest cloud builders", source_name="AWS News Blog")]

        tags = subject.tag_rows(rows, rules)

        self.assertIn(
            {
                "evidence_id": 1,
                "symbol": "AMZN",
                "match_type": "direct_symbol",
                "matched_text": "AWS News Blog",
                "confidence": 1.0,
                "confidence_bucket": "high",
                "match_reason": "direct_symbol",
            },
            tags,
        )

    def test_broad_terms_do_not_create_stock_specific_tags(self) -> None:
        rules = subject.alias_rules()
        rows = [evidence_row("AI cloud platform infrastructure spending grows")]

        tags = subject.tag_rows(rows, rules)

        self.assertEqual(tags, [])

    def test_press_wire_requires_headline_match_not_summary_only(self) -> None:
        rules = subject.alias_rules()
        rows = [
            evidence_row(
                "Technology company announces conference appearance",
                summary="The release mentions NVIDIA and Blackwell only in the body.",
                source_name="Business Wire technology feed",
            )
        ]

        tags = subject.tag_rows(rows, rules)

        self.assertEqual(tags, [])

    def test_confidence_bucket_logic_is_deterministic(self) -> None:
        self.assertEqual(subject.confidence_bucket(0.95, "company_alias"), "high")
        self.assertEqual(subject.confidence_bucket(0.75, "product_alias"), "medium")
        self.assertEqual(subject.confidence_bucket(0.55, "fund_alias"), "low")
        self.assertEqual(subject.confidence_bucket(0.95, "sector_context"), "needs_review")


if __name__ == "__main__":
    unittest.main()
