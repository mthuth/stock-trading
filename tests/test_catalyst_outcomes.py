#!/usr/bin/env python3
"""Regression tests for review-only catalyst follow-through analysis."""

from __future__ import annotations

import copy
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from stock_trading import catalyst_outcomes as subject
from stock_trading.storage import connection
from stock_trading.storage import evidence_repository, provider_repository, recommendation_repository


def event(
    *,
    symbol: str = "MSFT",
    event_date: str = "2026-05-01",
    event_type: str = "product",
    headline: str = "Microsoft announces AI infrastructure milestone",
    summary: str = "A catalyst fixture for review-only follow-through.",
    corroboration_label: str = "independent_confirmed",
    source_count: int = 3,
    evidence_count: int = 4,
    independent_source_count: int = 2,
    primary_source_count: int = 1,
    company_source_count: int = 0,
    opinion_source_count: int = 0,
    confidence: float = 0.82,
) -> dict[str, object]:
    return {
        "event_date": event_date,
        "symbol": symbol,
        "event_key": f"{symbol}:{event_date}:{event_type}",
        "event_type": event_type,
        "headline": headline,
        "summary": summary,
        "corroboration_label": corroboration_label,
        "source_count": source_count,
        "evidence_count": evidence_count,
        "independent_source_count": independent_source_count,
        "primary_source_count": primary_source_count,
        "company_source_count": company_source_count,
        "opinion_source_count": opinion_source_count,
        "latest_evidence_at": f"{event_date}T12:00:00",
        "confidence": confidence,
        "notes": "fixture",
    }


def recommendation(
    *,
    symbol: str = "MSFT",
    report_date: str = "2026-04-30",
    action: str = "Watch",
    score: float = 68.0,
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "report_date": report_date,
        "action": action,
        "score": score,
    }


def price_rows(symbol: str, closes: list[float], start_day: int = 1) -> list[dict[str, object]]:
    return [
        {
            "symbol": symbol,
            "price_date": (date(2026, 5, start_day) + timedelta(days=index)).isoformat(),
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "adjusted_close": close,
            "volume": 1000 + index,
            "provider": "Unit",
        }
        for index, close in enumerate(closes)
    ]


class CatalystOutcomeTests(unittest.TestCase):
    def row_for(
        self,
        catalyst: dict[str, object],
        closes: list[float],
        recommendations: list[dict[str, object]] | None = None,
    ) -> dict[str, object]:
        recommendations = recommendations or []
        rows = subject.catalyst_follow_through_rows(
            [catalyst],
            {str(catalyst["symbol"]): price_rows(str(catalyst["symbol"]), closes)},
            recommendations,
        )
        return rows[0]

    def test_event_with_positive_follow_through_is_likely_useful(self) -> None:
        catalyst = event()
        row = self.row_for(
            catalyst,
            [100, 102, 104, 106, 108, 110],
            [
                recommendation(action="Watch", report_date="2026-04-30"),
                recommendation(action="Add", report_date="2026-05-08"),
            ],
        )

        self.assertEqual(row["outcome_label"], "likely_useful")
        self.assertEqual(row["price_moves"]["5d"]["percent_change"], 10.0)
        self.assertEqual(row["recommendation_change"]["direction"], "stronger")
        self.assertTrue(row["review_only"])

    def test_event_with_negative_follow_through_is_likely_noisy(self) -> None:
        row = self.row_for(event(), [100, 99, 98, 96, 94, 92])

        self.assertEqual(row["outcome_label"], "likely_noisy")
        self.assertIn("negative_follow_through", row["outcome_reasons"])
        self.assertEqual(row["price_moves"]["5d"]["percent_change"], -8.0)

    def test_event_with_no_price_history_is_neutral_and_missing_history(self) -> None:
        rows = subject.catalyst_follow_through_rows([event()], {}, [])

        row = rows[0]
        self.assertEqual(row["outcome_label"], "neutral")
        self.assertIn("missing_price_history", row["outcome_reasons"])
        self.assertEqual(row["price_moves"]["1d"]["status"], "missing_price_history")

    def test_company_only_event_stays_neutral_without_independent_support(self) -> None:
        catalyst = event(
            event_type="company_update",
            corroboration_label="company_only",
            source_count=1,
            evidence_count=1,
            independent_source_count=0,
            primary_source_count=0,
            company_source_count=1,
            opinion_source_count=0,
        )

        row = self.row_for(catalyst, [100, 103, 105, 106, 107, 108])

        self.assertEqual(row["source_mix"]["label"], "company_only")
        self.assertEqual(row["outcome_label"], "neutral")
        self.assertIn("company_only_needs_independent_review", row["outcome_reasons"])

    def test_independent_confirmed_event_records_source_mix(self) -> None:
        row = self.row_for(event(independent_source_count=2, primary_source_count=0), [100, 101, 102])

        self.assertEqual(row["source_mix"]["label"], "independent_confirmed")
        self.assertEqual(row["source_mix"]["independent_source_count"], 2)

    def test_opinion_context_only_event_is_marked_noisy(self) -> None:
        catalyst = event(
            event_type="context",
            corroboration_label="context_only",
            source_count=2,
            evidence_count=2,
            independent_source_count=0,
            primary_source_count=0,
            company_source_count=0,
            opinion_source_count=2,
        )

        row = self.row_for(catalyst, [100, 100.5, 100.2, 100.1, 100.0, 99.8])

        self.assertEqual(row["source_mix"]["label"], "opinion_context_only")
        self.assertEqual(row["outcome_label"], "likely_noisy")
        self.assertIn("opinion_context_only", row["outcome_reasons"])

    def test_no_recommendation_mutation(self) -> None:
        catalyst = event()
        recs = [
            recommendation(action="Hold", report_date="2026-04-30"),
            recommendation(action="Add", report_date="2026-05-10"),
        ]
        before = copy.deepcopy(recs)

        row = self.row_for(catalyst, [100, 101], recs)

        self.assertEqual(recs, before)
        self.assertTrue(row["review_only"])
        self.assertIn("must not automatically change scores", row["notes"])

    def test_local_review_output_loads_existing_storage_without_schema_change(self) -> None:
        original_db_file = connection.DB_FILE
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                connection.DB_FILE = Path(tmpdir) / "catalyst_outcomes.sqlite"
                catalyst = event()
                evidence_repository.record_evidence_event_clusters(
                    [catalyst],
                    {str(catalyst["event_key"]): []},
                    rebuild=True,
                )
                provider_repository.record_price_history(
                    price_rows("MSFT", [100, 102, 104], start_day=1)
                )
                recommendation_repository.record_recommendation_scores(
                    1,
                    [
                        {
                            "run_id": 1,
                            "report_date": "2026-05-02",
                            "symbol": "MSFT",
                            "company": "Microsoft",
                            "sleeve": "long_term",
                            "trade_type": "long_term",
                            "action": "Add",
                            "score": 82.0,
                            "current_price": 102.0,
                            "target_price": 140.0,
                            "upside_pct": 37.3,
                            "target_confidence": "medium",
                            "data_status": "Blended",
                            "score_breakdown": "fixture",
                            "rationale": "fixture",
                        }
                    ],
                )

                review = subject.build_catalyst_follow_through_review(windows=(1,))
        finally:
            connection.DB_FILE = original_db_file

        self.assertTrue(review["metadata"]["review_only"])
        self.assertEqual(review["metadata"]["windows"], [1])
        self.assertEqual(review["outcomes"][0]["symbol"], "MSFT")
        self.assertEqual(review["outcomes"][0]["price_moves"]["1d"]["percent_change"], 2.0)


if __name__ == "__main__":
    unittest.main()
