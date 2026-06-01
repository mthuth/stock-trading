#!/usr/bin/env python3
"""Wave 13 multi-model shadow competition integration tests."""

from __future__ import annotations

import unittest

from stock_trading.local_console import render_local_console
from stock_trading.local_console_panels import build_console_panels
from stock_trading.reporting.renderers import (
    render_dashboard_html,
    render_markdown,
    render_multi_model_competition,
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
        "data_ingestion": {},
        "research_sources": {},
        "feedback": {},
        "learning_review": {"note": "Review-only learning outputs.", "manual_trade_journal": {}, "recommendation_outcomes": {}},
        "long_term_capital_deployment": {
            "review_only": True,
            "question": "What should I buy/add today for long-term holdings?",
            "status": "deployable",
            "primary_candidate": {"symbol": "NVDA", "action": "Add", "decision_gate_status": "Ready", "target_confidence": "Medium"},
            "capital_availability": {"deployable_amount_text": "$2,500.00", "status": "current", "source": "configured"},
            "key_blockers": [],
            "long_term_holding_health_summary": {"available": False, "message": "No long-term holding health rows are available yet."},
            "note": "Review-only and recommendation-only; official recommendations are unchanged.",
        },
        "earnings_review": {
            "review_only": True,
            "note": "Recommendation-only earnings review; official recommendation outputs are unchanged.",
            "upcoming_earnings_queue": {"rows": []},
            "recent_earnings_queue": {"rows": []},
            "pre_earnings_setup_review": {"rows": []},
            "post_earnings_reaction_review": {"rows": []},
            "earnings_signal_summary": {"overall_direction": "missing", "signal_count": 0, "categories": {}},
            "provider_data_gaps": {"rows": []},
        },
        "tactical_review": {
            "review_only": True,
            "recommendation_only": True,
            "does_not_override_long_term": True,
            "tactical_watchlist_queue": {"rows": []},
            "risk_zones": {"rows": []},
            "provider_data_gaps": {"rows": []},
            "earnings_event_context": {"rows": []},
            "tactical_outcome_history": {"summary": {"outcome_count": 0}, "rows": []},
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
        "alerts_review": {
            "review_only": True,
            "recommendation_only": True,
            "no_live_notifications": True,
            "active_alerts_summary": {"total_alerts": 0, "active_alerts": 0},
            "top_priority_alerts": [],
            "alerts_by_review_area": {},
            "alerts_by_severity": {},
            "alerts_by_status": {},
            "alert_lifecycle_metadata": {},
        },
        "artifacts": {},
    }


def multi_model_context() -> dict[str, object]:
    return {
        "review_only": True,
        "recommendation_only": True,
        "shadow_only": True,
        "no_auto_promotion": True,
        "note": "Recommendation-only shadow competition; shadow outputs are non-authoritative and do not change official recommendations.",
        "active_shadow_models": {
            "model_count": 1,
            "rows": [{"model_name": "conservative_long_term", "model_version": "shadow-v1", "model_role": "shadow", "promotion_status": "not_eligible"}],
            "empty_state": "No shadow models are registered yet.",
        },
        "official_baseline_comparison": {
            "model_name": "official_recommendation_model",
            "model_version": "fixture-v1",
            "official_status": "official",
            "shadow_model_count": 1,
            "official_recommendations_unchanged": True,
        },
        "shadow_recommendations": {
            "run_count": 1,
            "rows": [{"model_name": "conservative_long_term", "symbol": "NVDA", "shadow_action": "shadow_hold", "shadow_score": 62.5, "confidence": "medium", "horizon": "12_months", "official_action": "Add"}],
            "empty_state": "No shadow recommendation rows are available yet.",
        },
        "model_competition_scoreboard": {
            "rows": [{"rank": 1, "model_name": "official_recommendation_model", "status": "official", "decision_mode": "long_term_buy_add", "horizon": "12_months", "sample_size": 0, "score": 0.0, "warnings": "insufficient_sample_size"}],
            "empty_state": "No model competition scoreboard rows are available yet.",
        },
        "debate_packet_summary": {
            "packet_count": 1,
            "rows": [{"symbol": "NVDA", "models_compared": 1, "consensus_status": "models_agree", "dominant_stance": "neutral", "disagreement_status": "agreement"}],
            "empty_state": "No model debate packets are available yet.",
        },
        "promotion_readiness_summary": {
            "rows": [{"model_name": "conservative_long_term", "model_version": "shadow-v1", "label": "not_enough_data", "readiness_score": 0.0, "sample_size": 0, "recommended_action": "collect_more_shadow_outcomes", "no_auto_promotion": True}],
            "empty_state": "No promotion-readiness rows are available yet.",
        },
        "warnings": ["Insufficient sample size for model competition."],
    }


class Wave13MultiModelIntegrationTests(unittest.TestCase):
    def test_multi_model_section_renders_shadow_only_without_execution_language(self) -> None:
        context = base_context()
        context["multi_model_competition"] = multi_model_context()

        html = render_multi_model_competition(context)

        self.assertIn("Multi-Model Shadow Competition", html)
        self.assertIn("Active Shadow Models", html)
        self.assertIn("Model Competition Scoreboard", html)
        self.assertIn("Promotion Readiness Summary", html)
        self.assertIn("non-authoritative", html)
        lower = html.lower()
        for phrase in ("broker", "order", "trading"):
            self.assertNotIn(phrase, lower)

    def test_dashboard_and_markdown_place_multi_model_before_learning_review(self) -> None:
        context = base_context()
        context["multi_model_competition"] = multi_model_context()

        dashboard = render_dashboard_html(context)
        markdown = render_markdown(context)

        self.assertLess(dashboard.index("Long-Term Capital Deployment Review"), dashboard.index("Earnings Review"))
        self.assertLess(dashboard.index("Earnings Review"), dashboard.index("Tactical Review"))
        self.assertLess(dashboard.index("Tactical Review"), dashboard.index("Model Evaluation"))
        self.assertLess(dashboard.index("Model Evaluation"), dashboard.index("Alerts And Review Triggers"))
        self.assertLess(dashboard.index("Alerts And Review Triggers"), dashboard.index("Multi-Model Shadow Competition"))
        self.assertLess(dashboard.index("Multi-Model Shadow Competition"), dashboard.index('id="learningReviewTab"'))
        self.assertIn("## Multi-Model Shadow Competition", markdown)
        self.assertLess(markdown.index("## Alerts And Review Triggers"), markdown.index("## Multi-Model Shadow Competition"))
        self.assertLess(markdown.index("## Multi-Model Shadow Competition"), markdown.index("## Learning Review"))

    def test_missing_multi_model_data_is_graceful(self) -> None:
        context = base_context()
        context["multi_model_competition"] = {
            "review_only": True,
            "recommendation_only": True,
            "shadow_only": True,
            "no_auto_promotion": True,
            "active_shadow_models": {"rows": [], "empty_state": "No shadow models are registered yet."},
            "shadow_recommendations": {"rows": [], "empty_state": "No shadow recommendation rows are available yet."},
            "model_competition_scoreboard": {"rows": [], "empty_state": "No model competition scoreboard rows are available yet."},
            "debate_packet_summary": {"rows": [], "empty_state": "No model debate packets are available yet."},
            "promotion_readiness_summary": {"rows": [], "empty_state": "No promotion-readiness rows are available yet."},
            "warnings": [],
        }

        html = render_multi_model_competition(context)

        self.assertIn("No shadow models are registered yet.", html)
        self.assertIn("No model competition scoreboard rows are available yet.", html)
        self.assertIn("No model debate packets are available yet.", html)

    def test_local_console_includes_multi_model_after_alerts(self) -> None:
        context = base_context()
        context["multi_model_competition"] = multi_model_context()
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

        self.assertIn("multi_model_competition", panels)
        self.assertLess(html.index("Alerts And Review Triggers"), html.index("Multi-Model Shadow Competition"))
        self.assertLess(html.index("Multi-Model Shadow Competition"), html.index("Learning Review"))


if __name__ == "__main__":
    unittest.main()
