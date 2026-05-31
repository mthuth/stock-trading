#!/usr/bin/env python3
"""Wave 8 integration tests for review-only earnings report surfaces."""

from __future__ import annotations

import unittest

from stock_trading import analysis_engine
from stock_trading import presentation as subject
from stock_trading.reporting import renderers


def base_context() -> dict[str, object]:
    context = {section: {} for section in subject.REQUIRED_CONTEXT_SECTIONS}
    context["metadata"] = {"report_date": "2026-05-31", "generated_at": "2026-05-31T08:00:00"}
    context["summary"] = {
        "top_symbol": "NVDA",
        "top_company": "NVIDIA",
        "top_action": "Add",
        "top_score": 82.0,
        "recommendation_label": "Recommended next buy",
        "decision_gate": {"safe_to_buy": True, "status": "Ready", "reasons": []},
    }
    context["reliability"] = {"mode": "Fixture", "price_counts": {"fresh": 1, "missing": 0}}
    context["source_health"] = {"summary": {"needs_attention": 0, "healthy": 1, "stale": 0, "not_implemented": 0}}
    context["long_term_capital_deployment"] = {
        "review_only": True,
        "recommendation_only": True,
        "question": "What should I buy/add today for long-term holdings?",
        "primary_candidate": {
            "candidate_role": "top_candidate",
            "symbol": "NVDA",
            "action": "Add",
            "decision_gate_status": "Ready",
            "target_confidence": "Medium",
            "suggested_amount_text": "$2,500.00",
            "key_rationale": ["Fixture long-term add."],
            "key_blockers": [],
        },
        "capital_availability": {"deployable_amount_text": "$2,500.00", "status": "current"},
        "long_term_holding_health_summary": {"available": False, "message": "No long-term holding health rows are available yet."},
        "note": "Review-only and recommendation-only; official recommendations are unchanged.",
    }
    return context


def earnings_context() -> dict[str, object]:
    return {
        "review_only": True,
        "recommendation_only": True,
        "decision_mode": "earnings_event",
        "note": "Recommendation-only earnings review; official recommendation outputs are unchanged.",
        "upcoming_earnings_queue": {
            "rows": [
                {
                    "symbol": "MSFT",
                    "company": "Microsoft",
                    "earnings_date": "2026-06-05",
                    "days_until_earnings": 5,
                    "source_status": "ok",
                    "provider_gap_status": "ok",
                    "recommended_review_action": "review_pre_earnings",
                },
                {
                    "symbol": "QQQM",
                    "company": "Invesco NASDAQ 100 ETF",
                    "earnings_date": "",
                    "source_status": "non_operating_company",
                    "provider_gap_status": "expected",
                    "recommended_review_action": "ignore_for_now",
                },
            ],
            "empty_state": "No upcoming earnings dates are available.",
        },
        "recent_earnings_queue": {
            "rows": [
                {
                    "symbol": "AMZN",
                    "company": "Amazon.com",
                    "earnings_date": "2026-05-29",
                    "days_since_earnings": 2,
                    "source_status": "ok",
                    "provider_gap_status": "ok",
                    "recommended_review_action": "review_post_earnings",
                }
            ],
            "empty_state": "No recent earnings events are available.",
        },
        "pre_earnings_setup_review": {
            "rows": [
                {
                    "symbol": "MSFT",
                    "earnings_date": "2026-06-05",
                    "days_until_earnings": 5,
                    "recommended_review_action": "wait_until_after_report",
                    "setup_label": "wait_for_earnings",
                    "blockers": [],
                }
            ],
            "empty_state": "No pre-earnings setup review rows are available.",
        },
        "post_earnings_reaction_review": {
            "rows": [
                {
                    "symbol": "AMZN",
                    "earnings_date": "2026-05-29",
                    "days_since_earnings": 2,
                    "recommended_review_action": "review_for_add_after_earnings",
                    "reaction_label": "market_confirmation",
                    "price_reaction_pct": 4.2,
                    "thesis_impact": "improved",
                }
            ],
            "empty_state": "No post-earnings reaction review rows are available.",
        },
        "earnings_signal_summary": {
            "overall_direction": "positive",
            "signal_count": 2,
            "categories": {
                "guidance": "improved",
                "estimates": "missing",
                "margins": "neutral",
                "revenue": "improved",
                "eps": "neutral",
                "ai_capex_commentary": "improved",
                "risk_language": "neutral",
                "market_reaction": "improved",
                "thesis_impact": "improved",
            },
        },
        "provider_data_gaps": {
            "rows": [
                {
                    "symbol": "PANW",
                    "provider": "Finnhub",
                    "field": "earnings_calendar",
                    "status": "blocked",
                    "latest_issue": "Fixture blocked earnings calendar.",
                }
            ],
            "event_rows": [],
            "empty_state": "No earnings-specific provider/data gaps are visible.",
        },
    }


class Wave8EarningsIntegrationTests(unittest.TestCase):
    def test_run_analysis_adds_review_only_earnings_context(self) -> None:
        context = analysis_engine.run_analysis(persist=False, write_context=False, report_date="2026-05-31")
        review = context["earnings_review"]

        self.assertTrue(review["review_only"])
        self.assertTrue(review["recommendation_only"])
        self.assertEqual(review["decision_mode"], "earnings_event")
        self.assertIn("upcoming_earnings_queue", review)
        self.assertIn("recent_earnings_queue", review)
        self.assertIn("pre_earnings_setup_review", review)
        self.assertIn("post_earnings_reaction_review", review)
        self.assertIn("earnings_signal_summary", review)
        self.assertIn("provider_data_gaps", review)
        self.assertEqual(context["summary"]["top_symbol"], "NVDA")

    def test_dashboard_and_markdown_place_earnings_after_capital_deployment(self) -> None:
        context = base_context()
        context["earnings_review"] = earnings_context()

        dashboard = subject.render_dashboard_html(context)
        markdown = subject.render_markdown(context)

        self.assertIn("Earnings Review", dashboard)
        self.assertIn("Upcoming Earnings Queue", dashboard)
        self.assertIn("Recent Earnings Queue", dashboard)
        self.assertIn("Wait for earnings", dashboard)
        self.assertIn("Review after earnings", dashboard)
        self.assertIn("Not applicable now", dashboard)
        self.assertLess(dashboard.index("Long-Term Capital Deployment Review"), dashboard.index("Earnings Review"))
        self.assertLess(dashboard.index("Earnings Review"), dashboard.index("Product Review Path"))
        self.assertLess(markdown.index("Long-Term Capital Deployment Review"), markdown.index("Earnings Review"))
        self.assertLess(markdown.index("Earnings Review"), markdown.index("Learning Review"))
        self.assertIn("Recommendation-only earnings review", markdown)

    def test_missing_earnings_context_is_graceful(self) -> None:
        context = base_context()
        context.pop("earnings_review", None)

        dashboard = subject.render_dashboard_html(context)
        markdown = subject.render_markdown(context)

        self.assertIn("No earnings review context is available yet.", dashboard)
        self.assertIn("No earnings review context is available yet.", markdown)

    def test_new_earnings_surface_does_not_add_execution_language(self) -> None:
        context = base_context()
        context["earnings_review"] = earnings_context()

        section_html = renderers.render_earnings_review(context)

        self.assertNotIn("order", section_html.lower())
        self.assertNotIn("broker", section_html.lower())
        self.assertNotIn("trading", section_html.lower())
        self.assertIn("official recommendations stay unchanged", section_html)


if __name__ == "__main__":
    unittest.main()
