#!/usr/bin/env python3
"""Regression tests for research-depth ingestion control flow."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import ingest_research_depth as subject  # noqa: E402


class IngestResearchDepthTests(unittest.TestCase):
    def test_alpha_news_sentiment_records_payload_status_and_evidence(self) -> None:
        payload = {
            "feed": [
                {
                    "title": "NVIDIA expands AI platform",
                    "summary": "Relevant company news.",
                    "url": "https://example.com/nvda-ai",
                    "time_published": "20260528T120000",
                    "ticker_sentiment": [
                        {
                            "ticker": "NVDA",
                            "relevance_score": "0.91",
                            "ticker_sentiment_label": "Bullish",
                            "ticker_sentiment_score": "0.42",
                        }
                    ],
                }
            ]
        }
        recorded_payloads: list[tuple[object, ...]] = []
        recorded_evidence: list[dict[str, object]] = []

        def fake_record_provider_payload(*args: object, **kwargs: object) -> int:
            recorded_payloads.append(args + (kwargs,))
            return 1

        def fake_record_research_evidence(rows: list[dict[str, object]]) -> int:
            recorded_evidence.extend(rows)
            return len(rows)

        with (
            patch.object(subject, "fetch_json", return_value=("ok", payload, "")) as fetch_json,
            patch.object(subject, "record_provider_payload", side_effect=fake_record_provider_payload),
            patch.object(subject, "record_research_evidence", side_effect=fake_record_research_evidence),
        ):
            inserted, statuses = subject.ingest_symbol(
                "NVDA",
                alpha_key="alpha-key",
                fmp_key="",
                limits={"max_news_per_symbol": 5, "max_transcripts_per_symbol": 2},
                allow_alpha=True,
            )

        self.assertEqual(inserted, 1)
        self.assertEqual(len(statuses), 1)
        self.assertEqual(statuses[0]["provider"], "Alpha Vantage")
        self.assertEqual(statuses[0]["field_name"], "news_sentiment")
        self.assertEqual(statuses[0]["status"], "ok")
        self.assertEqual(len(recorded_payloads), 1)
        self.assertEqual(recorded_payloads[0][0], "Alpha Vantage")
        self.assertEqual(recorded_payloads[0][1], "NEWS_SENTIMENT")
        self.assertEqual(recorded_evidence[0]["source_name"], "Alpha Vantage news sentiment")
        fetch_json.assert_called_once()

    def test_alpha_budget_skip_does_not_call_provider(self) -> None:
        with (
            patch.object(subject, "fetch_json") as fetch_json,
            patch.object(subject, "record_provider_payload") as record_provider_payload,
            patch.object(subject, "record_research_evidence", return_value=0),
        ):
            inserted, statuses = subject.ingest_symbol(
                "NVDA",
                alpha_key="alpha-key",
                fmp_key="",
                limits={"max_news_per_symbol": 5, "max_transcripts_per_symbol": 2},
                allow_alpha=False,
            )

        self.assertEqual(inserted, 0)
        self.assertEqual(statuses, [])
        fetch_json.assert_not_called()
        record_provider_payload.assert_not_called()


if __name__ == "__main__":
    unittest.main()
