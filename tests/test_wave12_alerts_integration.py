#!/usr/bin/env python3
"""Wave 12 alert/review-trigger report and console integration tests."""

from __future__ import annotations

import unittest

from stock_trading.local_console import render_local_console
from stock_trading.local_console_panels import build_console_panels
from stock_trading.reporting.renderers import render_alerts_review, render_dashboard_html, render_markdown


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
                "key_rationale": ["Decision-safe long-term add."],
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
        "tactical_review": {
            "review_only": True,
            "recommendation_only": True,
            "does_not_override_long_term": True,
            "tactical_watchlist_queue": {"rows": [], "empty_state": "No tactical review setups are available yet."},
            "risk_zones": {"rows": [], "empty_state": "No tactical risk-zone rows are available yet."},
            "provider_data_gaps": {"rows": [], "empty_state": "No tactical provider/data gaps are visible."},
            "earnings_event_context": {"rows": [], "empty_state": "No earnings/event context is attached to tactical review rows."},
            "tactical_outcome_history": {"summary": {"outcome_count": 0}, "rows": [], "empty_state": "No tactical outcome history is available yet."},
        },
        "model_evaluation": {
            "review_only": True,
            "recommendation_only": True,
            "no_model_promotion": True,
            "prediction_records": {"prediction_count": 0, "rows": []},
            "model_registry": {"model_count": 1, "rows": []},
            "recommendation_backtest": {"summary": {"row_count": 0}, "rows": []},
            "benchmark_comparison": {"summary": {"status": "missing"}, "rows": []},
            "model_trust_score_v1": {"trust_level": "observe", "trust_score": 0.0, "review_only": True},
            "ai_thesis_evaluation": {"evaluation_count": 0, "rows": []},
            "warnings": [],
        },
        "artifacts": {},
    }


def alerts_context() -> dict[str, object]:
    note = "Review-only alert prompts for manual attention; official recommendations stay unchanged and no live notifications are sent."
    return {
        "review_only": True,
        "recommendation_only": True,
        "no_live_notifications": True,
        "does_not_override_recommendations": True,
        "note": note,
        "active_alerts_summary": {
            "total_alerts": 2,
            "active_alerts": 1,
            "top_priority_count": 1,
            "by_review_area": {"capital_deployment": 1, "provider_data": 1},
            "by_severity": {"high": 1, "informational": 1},
            "by_status": {"new": 1, "resolved": 1},
        },
        "top_priority_alerts": [
            {
                "priority": 201,
                "display_severity": "high",
                "review_area": "capital_deployment",
                "symbol": "NVDA",
                "status": "new",
                "why_review": "Long-term capital deployment needs review",
                "review_action": "review_long_term_capital_deployment",
            }
        ],
        "alerts_by_review_area": {"capital_deployment": 1, "provider_data": 1},
        "alerts_by_severity": {"high": 1, "informational": 1},
        "alerts_by_status": {"new": 1, "resolved": 1},
        "alert_lifecycle_metadata": {
            "dismissed_count": 0,
            "resolved_count": 1,
            "stale_deferred_alerts": 0,
            "local_review_metadata_only": True,
        },
        "rows": [],
        "empty_state": "No active review alerts. Existing recommendations remain unchanged.",
    }


class Wave12AlertsIntegrationTests(unittest.TestCase):
    def test_alerts_review_renders_without_notification_or_execution_language(self) -> None:
        context = base_context()
        context["alerts_review"] = alerts_context()

        html = render_alerts_review(context)

        self.assertIn("Alerts And Review Triggers", html)
        self.assertIn("Top Priority Alerts", html)
        self.assertIn("Alerts By Review Area", html)
        self.assertIn("Live notifications", html)
        lower = html.lower()
        for phrase in ("broker", "order", "trading", "sms", "email", "push", "websocket"):
            self.assertNotIn(phrase, lower)

    def test_dashboard_and_markdown_place_alerts_after_model_review(self) -> None:
        context = base_context()
        context["alerts_review"] = alerts_context()

        dashboard = render_dashboard_html(context)
        markdown = render_markdown(context)

        self.assertLess(dashboard.index("Long-Term Capital Deployment Review"), dashboard.index("Earnings Review"))
        self.assertLess(dashboard.index("Earnings Review"), dashboard.index("Tactical Review"))
        self.assertLess(dashboard.index("Tactical Review"), dashboard.index("Model Evaluation"))
        self.assertLess(dashboard.index("Model Evaluation"), dashboard.index("Alerts And Review Triggers"))
        self.assertLess(dashboard.index("Alerts And Review Triggers"), dashboard.index('id="learningReviewTab"'))
        self.assertIn("## Alerts And Review Triggers", markdown)
        self.assertLess(markdown.index("## Model Evaluation"), markdown.index("## Alerts And Review Triggers"))
        self.assertLess(markdown.index("## Alerts And Review Triggers"), markdown.index("## Learning Review"))

    def test_missing_alert_data_is_graceful(self) -> None:
        context = base_context()
        context["alerts_review"] = {
            "review_only": True,
            "recommendation_only": True,
            "no_live_notifications": True,
            "active_alerts_summary": {"total_alerts": 0, "active_alerts": 0},
            "top_priority_alerts": [],
            "alerts_by_review_area": {},
            "alerts_by_severity": {},
            "alerts_by_status": {},
            "alert_lifecycle_metadata": {},
            "empty_state": "No active review alerts. Existing recommendations remain unchanged.",
        }

        html = render_alerts_review(context)

        self.assertIn("No active review alerts.", html)
        self.assertIn("official recommendations stay unchanged", html)

    def test_local_console_includes_alerts_between_model_and_learning(self) -> None:
        context = base_context()
        context["alerts_review"] = alerts_context()
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

        self.assertIn("alerts_review", panels)
        self.assertLess(html.index("Model Evaluation"), html.index("Alerts And Review Triggers"))
        self.assertLess(html.index("Alerts And Review Triggers"), html.index("Learning Review"))


if __name__ == "__main__":
    unittest.main()
