#!/usr/bin/env python3
"""Wave 7 integration tests for long-term capital deployment review surfaces."""

from __future__ import annotations

import unittest

from stock_trading import analysis_engine
from stock_trading import presentation as subject


def base_context() -> dict[str, object]:
    context = {section: {} for section in subject.REQUIRED_CONTEXT_SECTIONS}
    context["metadata"] = {"report_date": "2026-05-31", "generated_at": "2026-05-31T08:00:00"}
    context["summary"] = {
        "top_symbol": "NVDA",
        "top_company": "NVIDIA",
        "top_action": "Add",
        "top_score": 82.0,
        "decision_gate": {"safe_to_buy": True, "status": "Ready", "reasons": []},
    }
    context["reliability"] = {"mode": "Fixture", "price_counts": {"fresh": 1, "missing": 0}}
    context["source_health"] = {"summary": {"needs_attention": 0, "healthy": 1, "stale": 0, "not_implemented": 0}}
    return context


def deployment_context(*, fallback: bool = False, hold: bool = False) -> dict[str, object]:
    primary_safe = not fallback and not hold
    return {
        "review_only": True,
        "recommendation_only": True,
        "decision_mode": "long_term_buy_add",
        "question": "What should I buy/add today for long-term holdings?",
        "status": "hold_capacity" if hold else "fallback_add" if fallback else "deployable",
        "primary_candidate": {
            "candidate_role": "blocked_candidate" if fallback or hold else "top_candidate",
            "rank": 1,
            "symbol": "NVDA",
            "company": "NVIDIA",
            "action": "Add",
            "decision_safe": primary_safe,
            "decision_gate_status": "Ready" if primary_safe else "Blocked",
            "target_confidence": "Medium",
            "suggested_amount": 2500.0 if primary_safe else 0.0,
            "suggested_amount_text": "$2,500.00" if primary_safe else "$0.00",
            "key_rationale": ["Top-ranked long-term add candidate."],
            "key_blockers": [] if primary_safe else ["Decision safety is blocked."],
        },
        "fallback_candidate": {
            "candidate_role": "fallback_candidate",
            "rank": 2,
            "symbol": "MSFT",
            "company": "Microsoft",
            "action": "Add",
            "decision_safe": True,
            "decision_gate_status": "Ready",
            "target_confidence": "High",
            "suggested_amount": 1500.0,
            "suggested_amount_text": "$1,500.00",
            "key_rationale": ["Fallback is decision-safe."],
            "key_blockers": [],
        } if fallback else None,
        "hold_capacity_message": "No decision-safe fallback add is available; hold buy capacity for review." if hold else "",
        "capital_availability": {
            "source": "configured",
            "status": "current",
            "as_of_date": "2026-05-31",
            "available_capital": 2500.0,
            "available_capital_text": "$2,500.00",
            "deployable_amount": 0.0 if hold else 1500.0 if fallback else 2500.0,
            "deployable_amount_text": "$0.00" if hold else "$1,500.00" if fallback else "$2,500.00",
            "held_amount": 2500.0 if hold else 1000.0 if fallback else 0.0,
            "held_amount_text": "$2,500.00" if hold else "$1,000.00" if fallback else "$0.00",
            "reason": "Capital is available for manual long-term add review.",
        },
        "key_rationale": ["Top-ranked long-term add candidate."],
        "key_blockers": ["Decision safety is blocked."] if fallback or hold else [],
        "long_term_holding_health_summary": {
            "available": True,
            "holding_count": 1,
            "summary": {"healthy": 1},
            "message": "Long-term holding health is constructive; continue routine review.",
            "top_review_rows": [],
        },
        "ai_synthesis_note": "AI synthesis is explanatory only and does not change the official recommendation.",
        "note": "Review-only and recommendation-only; official recommendations, scores, targets, gates, and allocation rules are unchanged.",
    }


class Wave7CapitalDeploymentIntegrationTests(unittest.TestCase):
    def test_run_analysis_adds_top_level_capital_deployment_context(self) -> None:
        context = analysis_engine.run_analysis(persist=False, write_context=False, report_date="2026-05-31")
        review = context["long_term_capital_deployment"]

        self.assertEqual(review["decision_mode"], "long_term_buy_add")
        self.assertTrue(review["review_only"])
        self.assertTrue(review["recommendation_only"])
        self.assertIn("primary_candidate", review)
        self.assertIn("capital_availability", review)
        self.assertIn("long_term_holding_health_summary", review)
        self.assertIn("fallback_candidate", review)
        self.assertIn("hold_capacity_message", review)
        self.assertIn("long_term_add_queue", context)
        self.assertIn("official recommendations", review["note"])

    def test_dashboard_and_markdown_place_capital_deployment_before_secondary_reviews(self) -> None:
        context = base_context()
        context["long_term_capital_deployment"] = deployment_context()

        dashboard = subject.render_dashboard_html(context)
        markdown = subject.render_markdown(context)

        self.assertIn("Long-Term Capital Deployment Review", dashboard)
        self.assertIn("What should I buy/add today for long-term holdings?", dashboard)
        self.assertIn("Primary Add Review", dashboard)
        self.assertLess(dashboard.index("Daily Decision Review"), dashboard.index("Long-Term Capital Deployment Review"))
        self.assertLess(dashboard.index("Long-Term Capital Deployment Review"), dashboard.index("Product Review Path"))
        self.assertLess(dashboard.index("Long-Term Capital Deployment Review"), dashboard.index("Learning Review"))
        self.assertIn("Long-Term Capital Deployment Review", markdown)
        self.assertLess(markdown.index("Daily Decision Review"), markdown.index("Long-Term Capital Deployment Review"))
        self.assertLess(markdown.index("Long-Term Capital Deployment Review"), markdown.index("Learning Review"))

    def test_blocked_top_candidate_shows_fallback(self) -> None:
        context = base_context()
        context["long_term_capital_deployment"] = deployment_context(fallback=True)

        dashboard = subject.render_dashboard_html(context)
        markdown = subject.render_markdown(context)

        self.assertIn("NVDA", dashboard)
        self.assertIn("MSFT", dashboard)
        self.assertIn("Fallback Candidate", dashboard)
        self.assertIn("Decision safety is blocked.", markdown)
        self.assertIn("Fallback candidate: **MSFT Add**", markdown)

    def test_no_safe_add_holds_capacity_and_missing_context_is_graceful(self) -> None:
        hold_context = base_context()
        hold_context["long_term_capital_deployment"] = deployment_context(hold=True)

        hold_dashboard = subject.render_dashboard_html(hold_context)
        self.assertIn("Hold capacity", hold_dashboard)
        self.assertIn("No decision-safe fallback add is available", hold_dashboard)

        missing_context = base_context()
        missing_context.pop("long_term_capital_deployment", None)
        missing_dashboard = subject.render_dashboard_html(missing_context)
        missing_markdown = subject.render_markdown(missing_context)
        self.assertIn("No long-term capital deployment context is available yet.", missing_dashboard)
        self.assertIn("No long-term capital deployment context is available yet.", missing_markdown)


if __name__ == "__main__":
    unittest.main()
