#!/usr/bin/env python3
"""Wave 10 tactical review report and console integration tests."""

from __future__ import annotations

import unittest

from stock_trading.local_console import render_local_console
from stock_trading.local_console_panels import build_console_panels
from stock_trading.reporting.renderers import (
    render_dashboard_html,
    render_markdown,
    render_tactical_review,
)


def base_context() -> dict[str, object]:
    return {
        "metadata": {"report_date": "2026-05-31", "generated_at": "2026-05-31T08:00:00", "recommendation_only": True},
        "summary": {
            "top_symbol": "NVDA",
            "top_company": "NVIDIA",
            "top_action": "Add",
            "top_score": 84.2,
            "recommendation_label": "Recommended next buy",
            "suggested_amount_text": "$2,500.00",
            "confidence": "Medium",
            "decision_gate": {"status": "Ready", "safe_to_buy": True, "reasons": []},
        },
        "decision_safety": {"status": "Ready", "safe_to_buy": True},
        "reliability": {"mode": "Fixture", "price_counts": {"fresh": 1, "missing": 0}},
        "source_health": {"summary": {"needs_attention": 0, "healthy": 1, "stale": 0, "not_implemented": 0}},
        "recommendations": [{"symbol": "NVDA", "action": "Add", "score": 84.2}],
        "holdings": {},
        "queues": {"action_queue": {"headers": [], "rows": []}, "data_gaps": {"headers": [], "rows": []}, "next_day": {"headers": [], "rows": []}},
        "decision_briefs": {"rows": []},
        "insight_themes": {},
        "score_movement": {},
        "trend_insights": {},
        "data_gaps": {},
        "source_health": {"summary": {"needs_attention": 0, "healthy": 1, "stale": 0, "not_implemented": 0}},
        "data_ingestion": {},
        "research_sources": {},
        "feedback": {},
        "learning_review": {"note": "Review-only learning outputs.", "manual_trade_journal": {}, "recommendation_outcomes": {}},
        "long_term_capital_deployment": {
            "review_only": True,
            "question": "What should I buy/add today for long-term holdings?",
            "status": "deployable",
            "primary_candidate": {
                "symbol": "NVDA",
                "action": "Add",
                "decision_gate_status": "Ready",
                "target_confidence": "Medium",
                "suggested_amount_text": "$2,500.00",
                "key_rationale": ["Decision safe long-term add."],
            },
            "capital_availability": {"deployable_amount_text": "$2,500.00", "status": "current", "source": "configured"},
            "key_blockers": [],
            "long_term_holding_health_summary": {"available": False, "message": "No long-term holding health rows are available yet."},
            "note": "Review-only and recommendation-only; official recommendations are unchanged.",
        },
        "earnings_review": {
            "review_only": True,
            "note": "Recommendation-only earnings review; official recommendation outputs are unchanged.",
            "upcoming_earnings_queue": {"rows": [], "empty_state": "No upcoming earnings dates are available."},
            "recent_earnings_queue": {"rows": [], "empty_state": "No recent earnings events are available."},
            "pre_earnings_setup_review": {"rows": [], "empty_state": "No pre-earnings setup review rows are available."},
            "post_earnings_reaction_review": {"rows": [], "empty_state": "No post-earnings reaction review rows are available."},
            "earnings_signal_summary": {"overall_direction": "missing", "signal_count": 0, "categories": {}},
            "provider_data_gaps": {"rows": [], "empty_state": "No earnings-specific provider/data gaps are visible."},
        },
        "artifacts": {},
    }


def tactical_context() -> dict[str, object]:
    return {
        "review_only": True,
        "recommendation_only": True,
        "does_not_override_long_term": True,
        "decision_mode": "tactical_trade",
        "note": "Recommendation-only tactical review; it is separate from and does not override long-term capital deployment or official recommendations.",
        "tactical_watchlist_queue": {
            "rows": [
                {
                    "symbol": "NVDA",
                    "setup_label": "breakout_review",
                    "tactical_horizon": "same_week",
                    "review_action": "tactical_buy_review",
                    "risk_zone_label": "moderate",
                    "priority_rank": 1,
                    "invalidation_condition": "Invalidated below support.",
                }
            ],
            "empty_state": "No tactical review setups are available yet.",
        },
        "risk_zones": {
            "rows": [
                {
                    "symbol": "NVDA",
                    "setup_label": "breakout_review",
                    "tactical_horizon": "same_week",
                    "risk_zone_label": "moderate",
                    "support_reference": 190.0,
                    "resistance_reference": 220.0,
                    "invalidation_condition": "Invalidated below support.",
                }
            ],
            "empty_state": "No tactical risk-zone rows are available yet.",
        },
        "provider_data_gaps": {"rows": [], "empty_state": "No tactical provider/data gaps are visible."},
        "earnings_event_context": {
            "rows": [
                {
                    "symbol": "NVDA",
                    "event_type": "upcoming_earnings",
                    "earnings_date": "2026-06-05",
                    "recommended_review_action": "review_pre_earnings",
                }
            ],
            "empty_state": "No earnings/event context is attached to tactical review rows.",
        },
        "tactical_outcome_history": {
            "summary": {"outcome_count": 0, "review_only": True},
            "rows": [],
            "empty_state": "No tactical outcome history is available yet.",
        },
    }


class Wave10TacticalIntegrationTests(unittest.TestCase):
    def test_tactical_review_renders_without_execution_language(self) -> None:
        context = base_context()
        context["tactical_review"] = tactical_context()

        html = render_tactical_review(context)

        self.assertIn("Tactical Review", html)
        self.assertIn("Tactical Watchlist Queue", html)
        self.assertIn("Tactical Risk Zones", html)
        self.assertIn("Review-only", html)
        self.assertIn("official recommendations", html)
        lower = html.lower()
        self.assertNotIn("broker", lower)
        self.assertNotIn("order", lower)

    def test_dashboard_and_markdown_hierarchy_keep_long_term_first(self) -> None:
        context = base_context()
        context["tactical_review"] = tactical_context()

        dashboard = render_dashboard_html(context)
        markdown = render_markdown(context)

        self.assertLess(dashboard.index("Long-Term Capital Deployment Review"), dashboard.index("Earnings Review"))
        self.assertLess(dashboard.index("Earnings Review"), dashboard.index("Tactical Review"))
        self.assertLess(dashboard.index("Tactical Review"), dashboard.index("Data Reliability Review"))
        self.assertIn("## Tactical Review", markdown)
        self.assertLess(markdown.index("## Long-Term Capital Deployment Review"), markdown.index("## Earnings Review"))
        self.assertLess(markdown.index("## Earnings Review"), markdown.index("## Tactical Review"))

    def test_missing_tactical_data_is_graceful(self) -> None:
        context = base_context()
        context["tactical_review"] = {
            "review_only": True,
            "recommendation_only": True,
            "does_not_override_long_term": True,
            "tactical_watchlist_queue": {"rows": [], "empty_state": "No tactical review setups are available yet."},
            "risk_zones": {"rows": [], "empty_state": "No tactical risk-zone rows are available yet."},
            "provider_data_gaps": {"rows": [], "empty_state": "No tactical provider/data gaps are visible."},
            "earnings_event_context": {"rows": [], "empty_state": "No earnings/event context is attached to tactical review rows."},
            "tactical_outcome_history": {"summary": {"outcome_count": 0}, "rows": [], "empty_state": "No tactical outcome history is available yet."},
        }

        html = render_tactical_review(context)

        self.assertIn("No tactical review setups are available yet.", html)
        self.assertIn("No tactical risk-zone rows are available yet.", html)
        self.assertIn("No tactical outcome history is available yet.", html)

    def test_local_console_includes_tactical_panel_after_earnings(self) -> None:
        context = base_context()
        context["tactical_review"] = tactical_context()
        panels = build_console_panels(context, artifacts={}, runs={})
        manifest = {
            "generated_at": "2026-05-31T08:00:00",
            "guardrails": ["No automatic trading"],
            "report_context": {"report_date": "2026-05-31"},
            "panels": panels,
            "artifacts": {},
            "run_history": {},
            "workflow": {},
        }

        html = render_local_console(manifest)

        self.assertIn("tactical_review", panels)
        self.assertLess(html.index("Earnings Review"), html.index("Tactical Review"))
        self.assertLess(html.index("Tactical Review"), html.index("Provider/Data Reliability"))


if __name__ == "__main__":
    unittest.main()
