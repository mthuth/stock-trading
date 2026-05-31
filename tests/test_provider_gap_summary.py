#!/usr/bin/env python3
"""Regression tests for normalized provider-gap review summaries."""

from __future__ import annotations

import unittest

from stock_trading.provider_gap_summary import build_provider_gap_review
from stock_trading.reporting.provider_gaps import (
    render_provider_gap_review_html,
    render_provider_gap_review_markdown,
)


def gap(
    provider: str,
    field_name: str,
    symbol: str,
    status: str,
    message: str,
    refreshed_at: str = "2026-05-31 08:00:00",
    last_success_at: str = "",
) -> dict[str, str]:
    return {
        "provider": provider,
        "field_name": field_name,
        "symbol": symbol,
        "status": status,
        "message": message,
        "refreshed_at": refreshed_at,
        "last_success_at": last_success_at,
    }


class ProviderGapSummaryTests(unittest.TestCase):
    def test_review_groups_blocked_stale_missing_rate_limited_and_top_candidate_gaps(self) -> None:
        review = build_provider_gap_review(
            [
                gap("Financial Modeling Prep", "analyst_targets", "NVDA", "blocked", "HTTP 403 blocked by plan"),
                gap("Yahoo", "price_history", "MSFT", "stale", "Stale price history", last_success_at="2026-05-29 18:00:00"),
                gap("Alpha Vantage", "target_price", "NVDA", "missing", "No target returned"),
                gap("Finnhub", "quote", "MARKET", "rate_limited", "HTTP 429 quota exceeded"),
                gap("Public feeds", "public_feed", "META", "error", "parser_gap: no parseable items"),
                gap("Options Flow", "options_flow", "GLOBAL", "not_implemented", "Source not implemented yet"),
            ],
            top_symbol="NVDA",
        )

        summary = review["summary"]
        self.assertEqual(summary["total"], 6)
        self.assertEqual(summary["blocker"], 2)
        self.assertEqual(summary["review_needed"], 1)
        self.assertEqual(summary["stale_missing"], 2)
        self.assertEqual(summary["informational"], 1)
        self.assertTrue(summary["top_candidate_affected"])
        self.assertEqual(summary["top_candidate_gap_count"], 2)
        self.assertEqual(summary["top_candidate_highest_severity"], "blocker")
        self.assertIn("ok_with_warnings", summary["status_note"])

        severity_groups = review["severity_groups"]
        self.assertEqual(len(severity_groups["blocker"]), 2)
        self.assertEqual(severity_groups["blocker"][0]["provider"], "Financial Modeling Prep")
        self.assertEqual(severity_groups["blocker"][1]["issue_type"], "Rate limited")
        stale_record = next(record for record in severity_groups["stale/missing"] if record["symbol"] == "MSFT")
        self.assertEqual(stale_record["last_success"], "2026-05-29 18:00:00")
        self.assertEqual(severity_groups["review needed"][0]["issue_type"], "Parser gap")
        self.assertEqual(severity_groups["informational"][0]["issue_type"], "Not implemented")

        provider_groups = {group["provider"]: group for group in review["provider_groups"]}
        self.assertEqual(provider_groups["Financial Modeling Prep"]["highest_severity"], "blocker")
        self.assertEqual(provider_groups["Alpha Vantage"]["affected_symbols"], ["NVDA"])

        symbol_groups = {group["symbol"]: group for group in review["symbol_groups"]}
        self.assertEqual(symbol_groups["NVDA"]["count"], 2)
        self.assertEqual(symbol_groups["NVDA"]["highest_severity"], "blocker")
        self.assertEqual(symbol_groups["MSFT"]["highest_severity"], "stale/missing")

        rows = review["rows"]
        self.assertEqual(rows[0][0], "blocker")
        self.assertEqual(rows[0][1], "Yes")
        self.assertEqual(rows[0][3], "NVDA")
        self.assertIn("provider", str(rows[0][8]).lower())

    def test_no_gaps_case_returns_empty_review(self) -> None:
        review = build_provider_gap_review(
            [
                gap("Financial Modeling Prep", "quote", "NVDA", "ok", ""),
            ],
            top_symbol="NVDA",
        )

        self.assertEqual(review["summary"]["total"], 0)
        self.assertFalse(review["summary"]["top_candidate_affected"])
        self.assertEqual(review["rows"], [])
        self.assertEqual(review["provider_groups"], [])
        self.assertEqual(review["symbol_groups"], [])

    def test_rendered_review_distinguishes_blockers_from_stale_missing_data(self) -> None:
        review = build_provider_gap_review(
            [
                gap("Finnhub", "quote", "NVDA", "rate_limited", "HTTP 429 quota exceeded"),
                gap("Yahoo", "price_history", "MSFT", "stale", "Stale price history"),
            ],
            top_symbol="NVDA",
        )

        html = render_provider_gap_review_html(review)
        markdown = render_provider_gap_review_markdown(review)

        self.assertIn("Provider Gap Review", html)
        self.assertIn("provider-gap-count-blocker", html)
        self.assertIn("provider-gap-count-stale-missing", html)
        self.assertIn("provider-gap-severity-blocker", html)
        self.assertIn("provider-gap-severity-stale-missing", html)
        self.assertIn("NVDA affected by 1 active gap", html)
        self.assertIn("**1 blocker**", markdown)
        self.assertIn("**1 stale/missing**", markdown)
        self.assertIn("Top candidate affected: **Yes**", markdown)

    def test_rendered_no_gaps_case_is_compact_and_positive(self) -> None:
        review = build_provider_gap_review([], top_symbol="NVDA")

        html = render_provider_gap_review_html(review)
        markdown = render_provider_gap_review_markdown(review)

        self.assertIn("No active provider gaps", html)
        self.assertEqual(markdown, "No active provider gaps are blocking daily review.")


if __name__ == "__main__":
    unittest.main()
