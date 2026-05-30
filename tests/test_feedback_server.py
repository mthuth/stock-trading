#!/usr/bin/env python3
"""Tests for local dashboard feedback persistence."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.serve_dashboard import handle_feedback_payload
from stock_trading.feedback import recent_feedback, record_feedback


class FeedbackServerTests(unittest.TestCase):
    def test_record_feedback_persists_recommendation_and_source_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "feedback.sqlite"
            with patch("stock_trading.storage.DB_FILE", db_path):
                recommendation = record_feedback(
                    {
                        "kind": "recommendation",
                        "symbol": "nvda",
                        "report_date": "2026-05-29",
                        "type": "agree",
                        "notes": "Makes sense.",
                    }
                )
                source = record_feedback(
                    {
                        "kind": "source",
                        "source_name": "Alpha Vantage",
                        "type": "noisy_source",
                        "notes": "Too much transient noise.",
                    }
                )
                records = recent_feedback()

        self.assertEqual(recommendation["message"], "Recorded recommendation feedback for NVDA")
        self.assertEqual(source["message"], "Recorded source feedback for Alpha Vantage")
        self.assertEqual({record["kind"] for record in records}, {"recommendation", "source"})
        self.assertIn("NVDA", {record["subject"] for record in records})
        self.assertIn("Alpha Vantage", {record["subject"] for record in records})

    def test_feedback_endpoint_payload_records_json_feedback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "feedback.sqlite"
            with patch("stock_trading.storage.DB_FILE", db_path):
                payload = handle_feedback_payload(
                    {
                        "kind": "recommendation",
                        "symbol": "MSFT",
                        "report_date": "2026-05-29",
                        "type": "too_risky",
                    }
                )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["feedback"]["message"], "Recorded recommendation feedback for MSFT")
        self.assertEqual(payload["recent"][0]["subject"], "MSFT")


if __name__ == "__main__":
    unittest.main()
