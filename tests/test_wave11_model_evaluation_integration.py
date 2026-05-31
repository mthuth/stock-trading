#!/usr/bin/env python3
"""Wave 11 model evaluation report and console integration tests."""

from __future__ import annotations

import unittest

from stock_trading.local_console import render_local_console
from stock_trading.local_console_panels import build_console_panels
from stock_trading.reporting.renderers import (
    render_dashboard_html,
    render_markdown,
    render_model_evaluation,
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
        "artifacts": {},
    }


def model_evaluation_context() -> dict[str, object]:
    return {
        "review_only": True,
        "recommendation_only": True,
        "no_model_promotion": True,
        "note": "Recommendation-only model evaluation; review-only learning context does not change official recommendations or promote models.",
        "prediction_records": {
            "prediction_count": 1,
            "rows": [
                {
                    "symbol": "NVDA",
                    "model_name": "official_recommendation_model",
                    "model_version": "fixture-v1",
                    "decision_mode": "long_term_buy_add",
                    "horizon": "12_months",
                    "expected_direction": "up",
                    "confidence": "Medium",
                }
            ],
            "empty_state": "No prediction records are available yet.",
        },
        "model_registry": {
            "model_count": 1,
            "rows": [
                {
                    "model_name": "official_recommendation_model",
                    "model_version": "fixture-v1",
                    "model_role": "official",
                    "official_or_shadow": "official",
                    "recommendation_impact": "none",
                    "score_impact": "none",
                }
            ],
            "empty_state": "No model registry rows are available yet.",
        },
        "recommendation_backtest": {
            "summary": {
                "row_count": 1,
                "enough_history_count": 0,
                "warnings": ["Insufficient sample size: 0 evaluable row(s), minimum review threshold is 5."],
            },
            "rows": [
                {
                    "symbol": "NVDA",
                    "window": "60_trading_days",
                    "action": "Add",
                    "outcome_status": "not_enough_history",
                    "return_pct": None,
                    "excess_return_pct": None,
                    "model_version": "fixture-v1",
                }
            ],
            "empty_state": "No recommendation backtest rows are available yet.",
        },
        "benchmark_comparison": {
            "summary": {"status": "missing", "average_excess_return_pct": None},
            "rows": [],
            "empty_state": "No benchmark comparison rows are available yet.",
        },
        "model_trust_score_v1": {
            "trust_score": 12.0,
            "trust_level": "observe",
            "confidence": "low",
            "review_only": True,
            "no_model_promotion": True,
            "warnings": ["Benchmark data is missing or insufficient for model evaluation."],
        },
        "ai_thesis_evaluation": {
            "evaluation_count": 0,
            "rows": [],
            "empty_state": "No AI thesis evaluation rows are available yet.",
        },
        "warnings": [
            "Insufficient sample size: 0 evaluable row(s), minimum review threshold is 5.",
            "Benchmark data is missing or insufficient for model evaluation.",
            "No AI thesis evaluation rows are available yet.",
        ],
    }


class Wave11ModelEvaluationIntegrationTests(unittest.TestCase):
    def test_model_evaluation_renders_without_execution_language(self) -> None:
        context = base_context()
        context["model_evaluation"] = model_evaluation_context()

        html = render_model_evaluation(context)

        self.assertIn("Model Evaluation", html)
        self.assertIn("Model Trust Score V1", html)
        self.assertIn("Prediction Records", html)
        self.assertIn("Recommendation Backtest", html)
        self.assertIn("No model promotion", html)
        lower = html.lower()
        self.assertNotIn("broker", lower)
        self.assertNotIn("order", lower)
        self.assertNotIn("trading", lower)

    def test_dashboard_and_markdown_hierarchy_keep_model_evaluation_secondary(self) -> None:
        context = base_context()
        context["model_evaluation"] = model_evaluation_context()

        dashboard = render_dashboard_html(context)
        markdown = render_markdown(context)

        self.assertLess(dashboard.index("Long-Term Capital Deployment Review"), dashboard.index("Earnings Review"))
        self.assertLess(dashboard.index("Earnings Review"), dashboard.index("Tactical Review"))
        self.assertLess(dashboard.index("Tactical Review"), dashboard.index("Model Evaluation"))
        self.assertLess(dashboard.index("Model Evaluation"), dashboard.index("Learning Review"))
        self.assertIn("## Model Evaluation", markdown)
        self.assertLess(markdown.index("## Tactical Review"), markdown.index("## Model Evaluation"))
        self.assertLess(markdown.index("## Model Evaluation"), markdown.index("## Learning Review"))

    def test_missing_model_evaluation_data_is_graceful(self) -> None:
        context = base_context()
        context["model_evaluation"] = {
            "review_only": True,
            "recommendation_only": True,
            "no_model_promotion": True,
            "prediction_records": {"rows": [], "empty_state": "No prediction records are available yet."},
            "model_registry": {"rows": [], "empty_state": "No model registry rows are available yet."},
            "recommendation_backtest": {"rows": [], "empty_state": "No recommendation backtest rows are available yet."},
            "benchmark_comparison": {"rows": [], "empty_state": "No benchmark comparison rows are available yet."},
            "ai_thesis_evaluation": {"rows": [], "empty_state": "No AI thesis evaluation rows are available yet."},
            "warnings": [],
        }

        html = render_model_evaluation(context)

        self.assertIn("No prediction records are available yet.", html)
        self.assertIn("No recommendation backtest rows are available yet.", html)
        self.assertIn("No AI thesis evaluation rows are available yet.", html)

    def test_local_console_includes_model_evaluation_panel_after_ai_status(self) -> None:
        context = base_context()
        context["model_evaluation"] = model_evaluation_context()
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

        self.assertIn("model_evaluation", panels)
        self.assertLess(html.index("AI Brief Status"), html.index("Model Evaluation"))
        self.assertLess(html.index("Model Evaluation"), html.index("Learning Review"))


if __name__ == "__main__":
    unittest.main()
