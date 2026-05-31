#!/usr/bin/env python3
"""Regression tests for deterministic AI synthesis readiness."""

from __future__ import annotations

import unittest

from stock_trading.ai_synthesis_readiness import (
    READINESS_STATUSES,
    classify_event_review,
    evaluate_synthesis_readiness,
)


def event(
    symbol: str = "MSFT",
    *,
    event_type: str = "product_launch",
    corroboration_label: str = "independent_confirmed",
    source_count: int = 2,
    evidence_count: int = 2,
    independent_source_count: int = 1,
    primary_source_count: int = 0,
    company_source_count: int = 1,
    opinion_source_count: int = 0,
    confidence: str = "high",
    latest_evidence_at: str = "2026-05-29T12:00:00",
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "event_type": event_type,
        "corroboration_label": corroboration_label,
        "source_count": source_count,
        "evidence_count": evidence_count,
        "independent_source_count": independent_source_count,
        "primary_source_count": primary_source_count,
        "company_source_count": company_source_count,
        "opinion_source_count": opinion_source_count,
        "confidence": confidence,
        "latest_evidence_at": latest_evidence_at,
    }


def review_counts(events: list[dict[str, object]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in events:
        status = classify_event_review(row).status
        counts[status] = counts.get(status, 0) + 1
    return counts


class AiSynthesisReadinessTests(unittest.TestCase):
    def test_status_vocabulary_is_controlled(self) -> None:
        self.assertEqual(
            READINESS_STATUSES,
            {
                "ready_for_ai_synthesis",
                "partially_ready",
                "needs_review",
                "needs_corroboration",
                "not_enough_data",
                "blocked_by_provider_gap",
                "ignore_for_now",
            },
        )

    def test_ready_symbol_has_primary_plus_independent_corroboration(self) -> None:
        events = [
            event(
                "MSFT",
                corroboration_label="primary_plus_confirmed",
                primary_source_count=1,
                company_source_count=0,
            ),
            event("MSFT", corroboration_label="independent_confirmed"),
        ]

        readiness = evaluate_synthesis_readiness(
            "MSFT",
            events,
            review_counts(events),
            {"target_confidence": "High"},
            report_date="2026-05-31",
        )

        self.assertEqual(readiness.status, "ready_for_ai_synthesis")
        self.assertTrue(readiness.eligible_for_ai_synthesis)
        self.assertEqual(readiness.reason_codes, [])

    def test_partially_ready_allows_primary_source_with_careful_framing(self) -> None:
        events = [
            event(
                "NVDA",
                event_type="filing_disclosure",
                corroboration_label="single_source",
                source_count=2,
                evidence_count=2,
                independent_source_count=0,
                primary_source_count=1,
                company_source_count=0,
                confidence="medium",
            )
        ]

        review = classify_event_review(events[0])
        readiness = evaluate_synthesis_readiness("NVDA", events, review_counts(events), report_date="2026-05-31")

        self.assertEqual(review.status, "ready_for_synthesis")
        self.assertIn("primary-source framing", review.action)
        self.assertEqual(readiness.status, "partially_ready")

    def test_company_only_evidence_needs_corroboration(self) -> None:
        events = [
            event(
                "AMZN",
                corroboration_label="company_only",
                source_count=2,
                evidence_count=2,
                independent_source_count=0,
                primary_source_count=0,
                company_source_count=2,
                confidence="medium",
            )
        ]

        readiness = evaluate_synthesis_readiness("AMZN", events, review_counts(events), report_date="2026-05-31")

        self.assertEqual(classify_event_review(events[0]).status, "needs_corroboration")
        self.assertEqual(readiness.status, "needs_corroboration")

    def test_needs_review_when_target_confidence_or_verification_blocks_context(self) -> None:
        events = [event("META", primary_source_count=1, corroboration_label="primary_plus_confirmed")]

        readiness = evaluate_synthesis_readiness(
            "META",
            events,
            review_counts(events),
            {
                "target_confidence": "Needs Review",
                "verification_queue": [{"status": "open", "insight_type": "Verification Needed"}],
            },
            report_date="2026-05-31",
        )

        self.assertEqual(readiness.status, "needs_review")
        self.assertIn("weak_target_confidence:needs_review", readiness.reason_codes)
        self.assertIn("verification_open:Verification Needed", readiness.reason_codes)

    def test_not_enough_data_without_event_clusters(self) -> None:
        readiness = evaluate_synthesis_readiness("AMD", [], {}, report_date="2026-05-31")

        self.assertEqual(readiness.status, "not_enough_data")
        self.assertFalse(readiness.eligible_for_ai_synthesis)

    def test_blocked_provider_gap_wins_over_otherwise_ready_evidence(self) -> None:
        events = [
            event(
                "AVGO",
                corroboration_label="primary_plus_confirmed",
                primary_source_count=1,
                company_source_count=0,
            ),
            event("AVGO", corroboration_label="independent_confirmed"),
        ]

        readiness = evaluate_synthesis_readiness(
            "AVGO",
            events,
            review_counts(events),
            {
                "provider_gaps": [
                    {
                        "symbol": "AVGO",
                        "provider": "SEC",
                        "field_name": "companyfacts",
                        "status": "blocked",
                    }
                ]
            },
            report_date="2026-05-31",
        )

        self.assertEqual(readiness.status, "blocked_by_provider_gap")
        self.assertLessEqual(readiness.score, 0.15)

    def test_opinion_only_evidence_is_ignored_for_now(self) -> None:
        events = [
            event(
                "NET",
                corroboration_label="single_source",
                source_count=1,
                evidence_count=1,
                independent_source_count=0,
                primary_source_count=0,
                company_source_count=0,
                opinion_source_count=1,
                confidence="medium",
            )
        ]

        readiness = evaluate_synthesis_readiness("NET", events, review_counts(events), report_date="2026-05-31")

        self.assertEqual(classify_event_review(events[0]).status, "ignore_for_now")
        self.assertEqual(readiness.status, "ignore_for_now")

    def test_stale_evidence_needs_review(self) -> None:
        events = [
            event(
                "SNOW",
                primary_source_count=1,
                corroboration_label="primary_plus_confirmed",
                latest_evidence_at="2026-03-01T12:00:00",
            )
        ]

        readiness = evaluate_synthesis_readiness("SNOW", events, review_counts(events), report_date="2026-05-31")

        self.assertEqual(readiness.status, "needs_review")
        self.assertTrue(any(code.startswith("stale_evidence:") for code in readiness.reason_codes))

    def test_decision_safety_block_keeps_readiness_explanatory_only(self) -> None:
        events = [
            event(
                "CRWD",
                corroboration_label="primary_plus_confirmed",
                primary_source_count=1,
                company_source_count=0,
            ),
            event("CRWD", corroboration_label="independent_confirmed"),
        ]

        readiness = evaluate_synthesis_readiness(
            "CRWD",
            events,
            review_counts(events),
            {"decision_safety": {"safe_to_buy": False, "status": "Blocked"}},
            report_date="2026-05-31",
        )

        self.assertEqual(readiness.status, "needs_review")
        self.assertIn("decision_safety:blocked", readiness.reason_codes)

    def test_source_health_issue_lowers_readiness(self) -> None:
        events = [
            event(
                "PANW",
                corroboration_label="primary_plus_confirmed",
                primary_source_count=1,
                company_source_count=0,
            ),
            event("PANW", corroboration_label="independent_confirmed"),
        ]

        readiness = evaluate_synthesis_readiness(
            "PANW",
            events,
            review_counts(events),
            {"source_health": [{"source_name": "Unit Source", "quality_label": "stale"}]},
            report_date="2026-05-31",
        )

        self.assertEqual(readiness.status, "needs_review")
        self.assertIn("source_health:stale:Unit Source", readiness.reason_codes)


if __name__ == "__main__":
    unittest.main()
