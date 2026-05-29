#!/usr/bin/env python3
"""Regression tests for public research feed/archive parsing."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import ingest_public_research_feeds as subject  # noqa: E402


class IngestPublicResearchFeedsTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
