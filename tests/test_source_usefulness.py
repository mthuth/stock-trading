#!/usr/bin/env python3
"""Tests for review-only source usefulness history."""

from __future__ import annotations

import copy
import unittest

from stock_trading import source_usefulness as subject


def quality_row(
    source_name: str,
    metric_date: str,
    *,
    total_evidence: int,
    tag_rate: float,
    avg_tag_confidence: float,
    quality_label: str = "useful_source",
    records_seen: int | None = None,
    duplicate_records: int = 0,
    low_confidence_matches: int = 0,
    blocked_count: int = 0,
    parser_gap_count: int = 0,
) -> dict[str, object]:
    return {
        "source_name": source_name,
        "source_category": "tech_news",
        "metric_date": metric_date,
        "total_evidence": total_evidence,
        "records_seen": records_seen if records_seen is not None else total_evidence,
        "duplicate_records": duplicate_records,
        "tag_rate": tag_rate,
        "avg_tag_confidence": avg_tag_confidence,
        "low_confidence_matches": low_confidence_matches,
        "blocked_count": blocked_count,
        "parser_gap_count": parser_gap_count,
        "quality_label": quality_label,
    }


def row_by_source(rows: list[dict[str, object]], name: str) -> dict[str, object]:
    return next(row for row in rows if row["source_name"] == name)


class SourceUsefulnessTests(unittest.TestCase):
    def test_consistently_useful_source_from_history(self) -> None:
        rows = [
            quality_row("Deep Research Wire", "2026-05-01", total_evidence=8, tag_rate=0.75, avg_tag_confidence=0.80),
            quality_row("Deep Research Wire", "2026-05-08", total_evidence=12, tag_rate=0.78, avg_tag_confidence=0.82),
            quality_row("Deep Research Wire", "2026-05-15", total_evidence=16, tag_rate=0.82, avg_tag_confidence=0.84),
        ]

        result = row_by_source(subject.build_source_usefulness(rows), "Deep Research Wire")

        self.assertEqual(result["label"], "consistently_useful")
        self.assertEqual(result["evidence_count"], 16)
        self.assertEqual(result["metric_observations"], 3)
        self.assertGreaterEqual(result["symbol_match_quality"], 0.7)
        self.assertTrue(result["review_only"])
        self.assertEqual(result["score_impact"], "none")
        self.assertEqual(result["source_weight_impact"], "none")

    def test_sparse_but_useful_source(self) -> None:
        rows = [
            quality_row("Specialist Blog", "2026-05-20", total_evidence=2, tag_rate=1.0, avg_tag_confidence=0.88),
        ]

        result = row_by_source(subject.build_source_usefulness(rows), "Specialist Blog")

        self.assertEqual(result["label"], "useful_but_sparse")
        self.assertEqual(result["evidence_count"], 2)

    def test_noisy_source_from_low_match_and_duplicates(self) -> None:
        rows = [
            quality_row(
                "Broad Aggregator",
                "2026-05-10",
                total_evidence=12,
                records_seen=20,
                duplicate_records=8,
                tag_rate=0.20,
                avg_tag_confidence=0.48,
                low_confidence_matches=8,
                quality_label="noisy_source",
            ),
        ]

        result = row_by_source(subject.build_source_usefulness(rows), "Broad Aggregator")

        self.assertEqual(result["label"], "noisy")
        self.assertGreaterEqual(result["duplicate_rate"], 0.35)
        self.assertGreaterEqual(result["low_confidence_match_rate"], 0.5)

    def test_stale_or_blocked_source_from_latest_status(self) -> None:
        rows = [
            quality_row("Blocked Feed", "2026-05-01", total_evidence=8, tag_rate=0.80, avg_tag_confidence=0.80),
            quality_row(
                "Blocked Feed",
                "2026-05-20",
                total_evidence=8,
                tag_rate=0.80,
                avg_tag_confidence=0.80,
                quality_label="blocked_source",
                blocked_count=1,
            ),
        ]

        result = row_by_source(subject.build_source_usefulness(rows), "Blocked Feed")

        self.assertEqual(result["label"], "stale_or_blocked")
        self.assertEqual(result["blocked_count"], 1)
        self.assertEqual(result["latest_status"], "blocked_source")

    def test_source_with_insufficient_history(self) -> None:
        rows = [
            quality_row(
                "New Feed",
                "2026-05-30",
                total_evidence=1,
                tag_rate=0.0,
                avg_tag_confidence=0.0,
                quality_label="not_enough_data",
            ),
        ]

        result = row_by_source(subject.build_source_usefulness(rows), "New Feed")

        self.assertEqual(result["label"], "needs_more_history")
        self.assertEqual(result["evidence_count"], 1)

    def test_positive_user_feedback_promotes_sparse_source_without_weight_changes(self) -> None:
        rows = [
            quality_row(
                "Helpful Niche Source",
                "2026-05-28",
                total_evidence=1,
                tag_rate=0.50,
                avg_tag_confidence=0.60,
                quality_label="not_enough_data",
            ),
        ]
        feedback = [{"source_name": "Helpful Niche Source", "feedback_type": "useful_source"}]

        result = row_by_source(subject.build_source_usefulness(rows, feedback_rows=feedback), "Helpful Niche Source")

        self.assertEqual(result["label"], "useful_but_sparse")
        self.assertEqual(result["positive_user_feedback"], 1)
        self.assertEqual(result["score_impact"], "none")
        self.assertEqual(result["source_weight_impact"], "none")

    def test_negative_user_feedback_flags_source_as_noisy(self) -> None:
        rows = [
            quality_row(
                "Questionable Feed",
                "2026-05-21",
                total_evidence=5,
                tag_rate=0.70,
                avg_tag_confidence=0.75,
            ),
        ]
        feedback = [{"source_name": "Questionable Feed", "feedback_type": "noisy_source"}]

        result = row_by_source(subject.build_source_usefulness(rows, feedback_rows=feedback), "Questionable Feed")

        self.assertEqual(result["label"], "noisy")
        self.assertEqual(result["negative_user_feedback"], 1)

    def test_follow_through_association_is_review_only(self) -> None:
        rows = [
            quality_row("Catalyst Source", "2026-05-10", total_evidence=4, tag_rate=0.70, avg_tag_confidence=0.76),
        ]
        follow_through = [
            {"source_name": "Catalyst Source", "outcome_status": "positive_follow_through"},
            {"sources": ["Catalyst Source"], "outcome_status": "negative_follow_through"},
        ]

        result = row_by_source(subject.build_source_usefulness(rows, follow_through_rows=follow_through), "Catalyst Source")

        self.assertEqual(result["follow_through_count"], 2)
        self.assertEqual(result["positive_follow_through"], 1)
        self.assertEqual(result["negative_follow_through"], 1)
        self.assertIn(result["label"], subject.USEFULNESS_LABELS)
        self.assertTrue(result["review_only"])

    def test_raw_evidence_rows_calculate_duplicate_history(self) -> None:
        rows = [
            {
                "source_name": "Raw Feed",
                "source_timestamp": "2026-05-01T10:00:00",
                "symbol": "NVDA",
                "confidence": "high",
                "provider_id": "item-1",
            },
            {
                "source_name": "Raw Feed",
                "source_timestamp": "2026-05-01T10:00:00",
                "symbol": "NVDA",
                "confidence": "high",
                "provider_id": "item-1",
            },
            {
                "source_name": "Raw Feed",
                "source_timestamp": "2026-05-02T10:00:00",
                "symbol": "MSFT",
                "confidence": "medium",
                "provider_id": "item-2",
            },
        ]

        result = row_by_source(subject.build_source_usefulness(rows), "Raw Feed")

        self.assertEqual(result["evidence_count"], 3)
        self.assertEqual(result["duplicate_records"], 1)
        self.assertGreater(result["duplicate_rate"], 0)

    def test_input_rows_are_not_mutated(self) -> None:
        rows = [quality_row("Stable Source", "2026-05-01", total_evidence=4, tag_rate=0.8, avg_tag_confidence=0.8)]
        feedback = [{"source_name": "Stable Source", "feedback_type": "useful_source"}]
        before_rows = copy.deepcopy(rows)
        before_feedback = copy.deepcopy(feedback)

        subject.build_source_usefulness(rows, feedback_rows=feedback)

        self.assertEqual(rows, before_rows)
        self.assertEqual(feedback, before_feedback)

    def test_summary_counts_labels(self) -> None:
        rows = subject.build_source_usefulness(
            [
                quality_row("Useful", "2026-05-01", total_evidence=12, tag_rate=0.8, avg_tag_confidence=0.8),
                quality_row("Useful", "2026-05-02", total_evidence=13, tag_rate=0.8, avg_tag_confidence=0.8),
                quality_row("Useful", "2026-05-03", total_evidence=14, tag_rate=0.8, avg_tag_confidence=0.8),
                quality_row("Thin", "2026-05-01", total_evidence=1, tag_rate=0.0, avg_tag_confidence=0.0),
            ]
        )

        summary = subject.summarize_source_usefulness(rows)

        self.assertTrue(summary["review_only"])
        self.assertEqual(summary["source_count"], 2)
        self.assertEqual(summary["labels"]["consistently_useful"], 1)
        self.assertEqual(summary["labels"]["needs_more_history"], 1)


if __name__ == "__main__":
    unittest.main()
