#!/usr/bin/env python3
"""Regression tests for the review-only earnings event queue."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from stock_trading.earnings_events import build_earnings_event_queue


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "earnings"


def universe_row(symbol: str, *, company: str | None = None, category: str = "Mega-cap AI/platform", sleeve: str = "long_term", trade_type: str = "long_term") -> dict[str, object]:
    return {
        "symbol": symbol,
        "company": company or symbol,
        "category": category,
        "sleeve": sleeve,
        "trade_type": trade_type,
    }


def fixture_events() -> list[dict[str, object]]:
    return json.loads((FIXTURE_DIR / "events.json").read_text())


def by_symbol(queue: dict[str, object], symbol: str) -> dict[str, object]:
    for row in queue["rows"]:
        if row["symbol"] == symbol:
            return row
    raise AssertionError(f"missing row for {symbol}")


class EarningsEventQueueTests(unittest.TestCase):
    def test_upcoming_earnings_inside_pre_earnings_window(self) -> None:
        queue = build_earnings_event_queue(
            [universe_row("MSFT", company="Microsoft")],
            report_date="2026-05-31",
            fixture_events=fixture_events(),
        )
        row = by_symbol(queue, "MSFT")

        self.assertEqual(row["event_type"], "upcoming_earnings")
        self.assertEqual(row["earnings_date"], "2026-06-05")
        self.assertEqual(row["days_until_earnings"], 5)
        self.assertEqual(row["review_window"], "pre_earnings")
        self.assertEqual(row["recommended_review_action"], "review_pre_earnings")
        self.assertTrue(row["review_only"])

    def test_upcoming_earnings_outside_window(self) -> None:
        queue = build_earnings_event_queue(
            [universe_row("NVDA", company="NVIDIA")],
            report_date="2026-05-31",
            fixture_events=fixture_events(),
        )
        row = by_symbol(queue, "NVDA")

        self.assertEqual(row["event_type"], "upcoming_earnings")
        self.assertEqual(row["days_until_earnings"], 45)
        self.assertEqual(row["review_window"], "not_in_window")
        self.assertEqual(row["recommended_review_action"], "ignore_for_now")

    def test_recent_earnings_inside_post_earnings_window(self) -> None:
        queue = build_earnings_event_queue(
            [universe_row("AMZN", company="Amazon")],
            report_date="2026-05-31",
            fixture_events=fixture_events(),
        )
        row = by_symbol(queue, "AMZN")

        self.assertEqual(row["event_type"], "recent_earnings")
        self.assertEqual(row["days_since_earnings"], 2)
        self.assertEqual(row["review_window"], "post_earnings")
        self.assertEqual(row["recommended_review_action"], "review_post_earnings")

    def test_recent_earnings_outside_post_window_is_monitored(self) -> None:
        queue = build_earnings_event_queue(
            [universe_row("MDB", company="MongoDB")],
            report_date="2026-05-31",
            fixture_events=[
                {
                    "symbol": "MDB",
                    "earnings_date": "2026-05-10",
                    "source": "fixture earnings calendar",
                    "source_confidence": "medium",
                    "source_status": "ok",
                }
            ],
        )
        row = by_symbol(queue, "MDB")

        self.assertEqual(row["event_type"], "recent_earnings")
        self.assertEqual(row["review_window"], "not_in_window")
        self.assertEqual(row["recommended_review_action"], "monitor_after_report")

    def test_missing_earnings_date_waits_for_confirmation(self) -> None:
        queue = build_earnings_event_queue(
            [universe_row("CRWD", company="CrowdStrike")],
            report_date="2026-05-31",
            fixture_events=[],
        )
        row = by_symbol(queue, "CRWD")

        self.assertEqual(row["event_type"], "unknown_earnings_date")
        self.assertEqual(row["review_window"], "unknown")
        self.assertEqual(row["recommended_review_action"], "wait_for_date_confirmation")

    def test_provider_gap_blocked_earnings_source(self) -> None:
        queue = build_earnings_event_queue(
            [universe_row("PANW", company="Palo Alto Networks")],
            report_date="2026-05-31",
            provider_gap_rows=[
                {
                    "symbol": "PANW",
                    "provider": "Finnhub",
                    "field_name": "earnings_calendar",
                    "status": "blocked",
                    "message": "403 blocked earnings endpoint",
                }
            ],
        )
        row = by_symbol(queue, "PANW")

        self.assertEqual(row["event_type"], "earnings_data_gap")
        self.assertEqual(row["provider_gap_status"], "blocked")
        self.assertEqual(row["source_status"], "blocked")
        self.assertEqual(row["recommended_review_action"], "data_gap_review")

    def test_etf_is_marked_not_applicable(self) -> None:
        queue = build_earnings_event_queue(
            [
                universe_row(
                    "QQQM",
                    company="Invesco NASDAQ 100 ETF",
                    category="ETF/ballast",
                    sleeve="etf",
                    trade_type="etf",
                )
            ],
            report_date="2026-05-31",
        )
        row = by_symbol(queue, "QQQM")

        self.assertEqual(row["event_type"], "unknown_earnings_date")
        self.assertEqual(row["source"], "not_applicable")
        self.assertEqual(row["source_status"], "non_operating_company")
        self.assertEqual(row["provider_gap_status"], "expected")
        self.assertEqual(row["recommended_review_action"], "ignore_for_now")

    def test_foreign_issuer_is_review_unknown(self) -> None:
        queue = build_earnings_event_queue(
            [universe_row("TSM", company="Taiwan Semiconductor", category="Semiconductors")],
            report_date="2026-05-31",
        )
        row = by_symbol(queue, "TSM")

        self.assertEqual(row["event_type"], "unknown_earnings_date")
        self.assertEqual(row["source"], "foreign issuer filing pattern review")
        self.assertEqual(row["source_confidence"], "low")
        self.assertEqual(row["recommended_review_action"], "wait_for_date_confirmation")

    def test_stored_evidence_rows_can_supply_earnings_dates(self) -> None:
        queue = build_earnings_event_queue(
            [universe_row("META", company="Meta Platforms")],
            report_date="2026-05-31",
            stored_evidence_rows=[
                {
                    "symbol": "META",
                    "evidence_type": "earnings_calendar",
                    "source_name": "Finnhub earnings calendar",
                    "provider_endpoint": "calendar/earnings",
                    "source_timestamp": "2026-06-07",
                    "confidence": "medium",
                }
            ],
        )
        row = by_symbol(queue, "META")

        self.assertEqual(row["event_type"], "upcoming_earnings")
        self.assertEqual(row["earnings_date"], "2026-06-07")
        self.assertEqual(row["source"], "Finnhub earnings calendar")
        self.assertEqual(row["recommended_review_action"], "review_pre_earnings")

    def test_no_recommendation_mutation(self) -> None:
        universe = [universe_row("MSFT", company="Microsoft")]
        events = fixture_events()
        before_universe = copy.deepcopy(universe)
        before_events = copy.deepcopy(events)

        queue = build_earnings_event_queue(universe, report_date="2026-05-31", fixture_events=events)

        self.assertEqual(universe, before_universe)
        self.assertEqual(events, before_events)
        self.assertTrue(queue["review_only"])
        self.assertTrue(queue["recommendation_only"])
        self.assertIn("does not change scores", queue["note"])


if __name__ == "__main__":
    unittest.main()
