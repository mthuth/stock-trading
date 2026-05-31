#!/usr/bin/env python3
"""Regression tests for review-only post-earnings reaction analysis."""

from __future__ import annotations

import copy
import unittest
from datetime import date, timedelta

from stock_trading import post_earnings_review as subject


def event(
    *,
    symbol: str = "MSFT",
    company: str = "Microsoft",
    earnings_date: str = "2026-05-20",
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "company": company,
        "earnings_date": earnings_date,
    }


def evidence(
    *,
    symbol: str = "MSFT",
    event_date: str = "2026-05-21",
    headline: str = "Microsoft beats expectations and raises guidance",
    summary: str = "AI demand strengthened and margins improved after earnings.",
    thesis_signal: str = "positive",
    source_name: str = "Official IR",
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "event_date": event_date,
        "headline": headline,
        "summary": summary,
        "thesis_signal": thesis_signal,
        "source_name": source_name,
    }


def price_rows(
    symbol: str = "MSFT",
    *,
    earnings_close: float = 100.0,
    reaction_close: float = 108.0,
    earnings_date: str = "2026-05-20",
) -> list[dict[str, object]]:
    parsed = date.fromisoformat(earnings_date)
    return [
        {
            "symbol": symbol,
            "price_date": parsed.isoformat(),
            "close": earnings_close,
            "adjusted_close": earnings_close,
            "provider": "Unit",
        },
        {
            "symbol": symbol,
            "price_date": (parsed + timedelta(days=1)).isoformat(),
            "close": reaction_close,
            "adjusted_close": reaction_close,
            "provider": "Unit",
        },
    ]


def recommendation(
    *,
    symbol: str = "MSFT",
    report_date: str = "2026-05-19",
    action: str = "Add",
    score: float = 81.0,
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "report_date": report_date,
        "action": action,
        "score": score,
    }


class PostEarningsReviewTests(unittest.TestCase):
    def review(
        self,
        *,
        earnings_event: dict[str, object] | None = None,
        evidence_rows: list[dict[str, object]] | None = None,
        prices: list[dict[str, object]] | None = None,
        recommendations: list[dict[str, object]] | None = None,
        provider_gaps: list[dict[str, object]] | None = None,
        source_usefulness: list[dict[str, object]] | None = None,
        as_of: str = "2026-05-23",
    ) -> dict[str, object]:
        return subject.build_post_earnings_review(
            earnings_event or event(),
            evidence_rows=evidence_rows if evidence_rows is not None else [evidence()],
            price_history=prices if prices is not None else price_rows(),
            recommendation_rows=recommendations or [],
            provider_gaps=provider_gaps or [],
            source_usefulness=source_usefulness or [],
            as_of=as_of,
        )

    def test_strong_positive_reaction_with_supporting_evidence_improves_thesis(self) -> None:
        row = self.review()

        self.assertEqual(row["reaction_label"], "thesis_improved")
        self.assertEqual(row["thesis_impact"], "improved")
        self.assertEqual(row["recommended_review_action"], "review_for_add_after_earnings")
        self.assertEqual(row["price_reaction_pct"], 8.0)
        self.assertTrue(row["review_only"])
        self.assertIn("Recommendation-only", row["recommendation_only_note"])

    def test_price_drop_with_positive_evidence_flags_possible_overreaction(self) -> None:
        row = self.review(prices=price_rows(earnings_close=100.0, reaction_close=94.0))

        self.assertEqual(row["reaction_label"], "market_overreaction_possible")
        self.assertEqual(row["thesis_impact"], "intact_but_market_sold_off")
        self.assertEqual(row["recommended_review_action"], "review_for_add_after_earnings")
        self.assertEqual(row["price_reaction_pct"], -6.0)

    def test_guidance_or_risk_weakening_reviews_thesis_risk(self) -> None:
        row = self.review(
            evidence_rows=[
                evidence(
                    headline="Management lowers guidance and warns of margin pressure",
                    summary="Revenue miss and demand softening weaken the post-earnings thesis.",
                    thesis_signal="negative",
                )
            ],
            prices=price_rows(earnings_close=100.0, reaction_close=92.0),
        )

        self.assertEqual(row["reaction_label"], "thesis_weakened")
        self.assertEqual(row["thesis_impact"], "weakened")
        self.assertEqual(row["recommended_review_action"], "review_thesis_risk")
        self.assertTrue(any("guidance" in item.lower() for item in row["risk_summary"]))

    def test_missing_evidence_is_data_insufficient(self) -> None:
        row = self.review(evidence_rows=[])

        self.assertEqual(row["reaction_label"], "data_insufficient")
        self.assertEqual(row["recommended_review_action"], "wait_for_call_or_filing")
        self.assertIn("Missing post-earnings evidence or call/filing review.", row["data_gaps"])

    def test_missing_price_reaction_is_data_insufficient(self) -> None:
        row = self.review(prices=[])

        self.assertEqual(row["reaction_label"], "data_insufficient")
        self.assertIsNone(row["price_reaction_pct"])
        self.assertIn("Missing stored price history.", row["data_gaps"])

    def test_mixed_reaction_monitors_evidence_conflict(self) -> None:
        row = self.review(
            evidence_rows=[
                evidence(headline="Company beats EPS and raises AI demand outlook", thesis_signal="positive"),
                evidence(
                    headline="Management warns margin pressure could persist",
                    summary="Margin pressure and risk language offset the revenue beat.",
                    thesis_signal="negative",
                ),
            ],
            prices=price_rows(earnings_close=100.0, reaction_close=102.0),
        )

        self.assertEqual(row["reaction_label"], "mixed_reaction")
        self.assertEqual(row["thesis_impact"], "mixed")
        self.assertEqual(row["recommended_review_action"], "monitor_reaction")

    def test_outside_post_earnings_window_is_ignored_for_now(self) -> None:
        row = self.review(as_of="2026-06-15")

        self.assertEqual(row["reaction_label"], "not_in_post_earnings_window")
        self.assertEqual(row["recommended_review_action"], "ignore_for_now")
        self.assertEqual(row["days_since_earnings"], 26)

    def test_provider_and_source_context_remain_review_only(self) -> None:
        row = self.review(
            prices=price_rows(earnings_close=100.0, reaction_close=103.5),
            provider_gaps=[
                {
                    "symbol": "MSFT",
                    "provider": "FMP",
                    "field_name": "earnings_transcripts",
                    "status": "blocked",
                    "latest_issue": "plan does not include transcripts",
                }
            ],
            source_usefulness=[
                {
                    "symbol": "MSFT",
                    "source_name": "Example Blog",
                    "label": "noisy",
                }
            ],
        )

        self.assertEqual(row["reaction_label"], "market_confirmation")
        self.assertTrue(any("earnings_transcripts" in gap for gap in row["data_gaps"]))
        self.assertTrue(any("noisy" in risk for risk in row["risk_summary"]))
        self.assertTrue(row["review_only"])

    def test_no_recommendation_mutation(self) -> None:
        recommendations = [
            recommendation(action="Hold", report_date="2026-05-19"),
            recommendation(action="Add", report_date="2026-05-22"),
        ]
        before = copy.deepcopy(recommendations)

        row = self.review(recommendations=recommendations)

        self.assertEqual(recommendations, before)
        self.assertTrue(row["recommendation_context"]["changed"])
        self.assertEqual(row["recommendation_context"]["before_action"], "Hold")
        self.assertEqual(row["recommendation_context"]["after_action"], "Add")
        self.assertIn("must not automatically change scores", row["recommendation_only_note"])

    def test_batch_reviews_are_sorted_and_symbol_scoped(self) -> None:
        rows = subject.build_post_earnings_reviews(
            [
                event(symbol="NVDA", company="Nvidia", earnings_date="2026-05-21"),
                event(symbol="MSFT", company="Microsoft", earnings_date="2026-05-20"),
            ],
            evidence_rows=[
                evidence(symbol="MSFT", event_date="2026-05-21", headline="Microsoft beats and raises guidance"),
                evidence(symbol="NVDA", event_date="2026-05-22", headline="Nvidia beats and raises guidance"),
            ],
            price_history_by_symbol={
                "MSFT": price_rows("MSFT", earnings_date="2026-05-20"),
                "NVDA": price_rows("NVDA", earnings_date="2026-05-21"),
            },
            as_of="2026-05-23",
        )

        self.assertEqual([row["symbol"] for row in rows], ["MSFT", "NVDA"])
        self.assertEqual(rows[0]["reaction_label"], "thesis_improved")
        self.assertEqual(rows[1]["reaction_label"], "thesis_improved")


if __name__ == "__main__":
    unittest.main()
