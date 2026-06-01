#!/usr/bin/env python3
"""Wave 15 decision-quality integration tests."""

from __future__ import annotations

import unittest

from stock_trading import presentation
from stock_trading.local_console import render_local_console
from stock_trading.local_console_panels import build_console_panels


def wave15_context() -> dict[str, object]:
    context = {section: {} for section in presentation.REQUIRED_CONTEXT_SECTIONS}
    context.update(
        {
            "metadata": {"report_date": "2026-06-01", "generated_at": "2026-06-01T08:00:00", "recommendation_only": True},
            "summary": {
                "top_symbol": "MSFT",
                "top_company": "Microsoft",
                "top_action": "Watch",
                "top_score": 78.4,
                "recommendation_label": "No decision-safe buy",
                "amount_label": "Buy capacity held",
                "suggested_amount": 0.0,
                "suggested_amount_text": "$0.00",
                "current_price_text": "$424.00",
                "target_text": "$480.00",
                "upside_text": "13.2%",
                "confidence": "Medium",
                "data_status": "Blended",
                "target_quality": "Blended",
                "top_notes": "Strong company, but the official model is still in review mode.",
                "decision_gate": {
                    "safe_to_buy": False,
                    "status": "Blocked",
                    "candidate_action": "Watch",
                    "reasons": ["Watch action is not a buy action", "Verification check is still open"],
                },
            },
            "decision_safety": {"safe_to_buy": False, "status": "Blocked"},
            "reliability": {"mode": "Fixture", "price_counts": {"fresh": 4, "missing": 1}},
            "source_health": {"summary": {"needs_attention": 1, "healthy": 4, "stale": 1, "not_implemented": 2}},
            "recommendations": [
                {"rank": 1, "symbol": "MSFT", "company": "Microsoft", "sleeve": "long_term", "trade_type": "long_term", "action": "Watch", "score": 78.4, "data_status": "Blended", "confidence": "Medium", "why": "Core quality is high, but the gate is cautious today."},
                {"rank": 2, "symbol": "NVDA", "company": "NVIDIA", "sleeve": "long_term", "trade_type": "long_term", "action": "Add", "score": 77.2, "data_status": "Wide range", "confidence": "Low", "why": "High upside with target-confidence caveats."},
                {"rank": 3, "symbol": "ALAB", "company": "Astera Labs", "sleeve": "speculative_ai", "trade_type": "speculative_ai", "action": "Watch", "score": 72.1, "data_status": "Needs price", "confidence": "Low", "why": "Higher-upside AI infrastructure review candidate."},
                {"rank": 4, "symbol": "META", "company": "Meta", "sleeve": "long_term", "trade_type": "long_term", "action": "Hold", "score": 70.0, "data_status": "Blended", "confidence": "Medium", "why": "Core mega-cap comparison row."},
                {"rank": 5, "symbol": "SNOW", "company": "Snowflake", "sleeve": "long_term", "trade_type": "long_term", "action": "Watch", "score": 68.5, "data_status": "Partial blend", "confidence": "Low", "why": "Needs better target evidence."},
            ],
            "queues": {"action_queue": {"headers": [], "rows": []}, "full_universe": {"headers": [], "rows": []}},
            "decision_quality": {
                "review_only": True,
                "recommendation_only": True,
                "note": "Decision-quality review is recommendation-only; official recommendations are unchanged.",
                "top_5_ranked_opportunities": [
                    {
                        "rank": 1,
                        "symbol": "MSFT",
                        "company": "Microsoft",
                        "lane": "Core mega-cap",
                        "action": "Watch",
                        "score": 78.4,
                        "decision_gate_status": "Blocked",
                        "plain_english_blocked_explanation": "The model is saying Watch, so buy/add capacity stays held until the official action clears the buy/add gate.",
                        "suggested_amount_text": "$0.00",
                        "top_reason": "Core quality is high, but the gate is cautious today.",
                        "top_blocker": "The model is saying Watch, so buy/add capacity stays held until the official action clears the buy/add gate.",
                        "data_reliability_note": "Missing data is a reliability blocker rather than bearish thesis.",
                    },
                    {
                        "rank": 2,
                        "symbol": "ALAB",
                        "company": "Astera Labs",
                        "lane": "Higher-upside / speculative",
                        "action": "Watch",
                        "score": 72.1,
                        "decision_gate_status": "Blocked",
                        "suggested_amount_text": "$0.00",
                        "top_reason": "Higher-upside AI infrastructure review candidate.",
                        "top_blocker": "Current price is missing, so upside and sizing are reliability-blocked rather than bearish.",
                        "data_reliability_note": "Needs price; Low confidence.",
                    },
                ],
                "decision_gate_explanations": [
                    "The model is saying Watch, so buy/add capacity stays held until the official action clears the buy/add gate.",
                    "A verification check is still open, so the candidate is not decision-safe yet.",
                ],
                "data_maintenance_work_requests": {
                    "rows": [["High", "Provider gap", "ALAB price", "Missing current price", "Fix config or add fallback."]]
                },
                "model_user_disagreement_learning": {
                    "rows": [["MSFT", "Watch / Blocked", "User may manually buy", "Track later as review-only learning.", "Does not change official recommendation"]]
                },
                "queue_refinement": {
                    "rows": [["Top 5", "First-screen daily opportunity scan", "Reduces repeated queue summaries."]]
                },
                "holdings_freshness": {
                    "rows": [["broker_readonly", "2026-06-01T07:50:00", "fresh", "Holdings freshness is visible when holdings exist."]]
                },
            },
        }
    )
    return context


class Wave15DecisionQualityIntegrationTests(unittest.TestCase):
    def test_dashboard_and_markdown_surface_top5_decision_quality(self) -> None:
        context = wave15_context()

        dashboard = presentation.render_dashboard_html(context)
        markdown = presentation.render_markdown(context)

        self.assertIn("Decision Quality Review", dashboard)
        self.assertIn("Top 5 Ranked Opportunities Today", dashboard)
        self.assertIn("Core mega-cap", dashboard)
        self.assertIn("Higher-upside / speculative", dashboard)
        self.assertIn("Plain-English Decision Gate", dashboard)
        self.assertIn("Data Maintenance Work Requests", dashboard)
        self.assertIn("Model / User Disagreement Learning", dashboard)
        self.assertIn("Score Driver Glossary", dashboard)
        self.assertIn("Queue Drilldowns", dashboard)
        self.assertIn("Holdings / Capital Freshness", dashboard)
        self.assertIn("reliability blocker rather than bearish", dashboard)
        self.assertIn("official recommendations are unchanged", dashboard)
        self.assertLess(dashboard.index("Decision Quality Review"), dashboard.index("Daily Decision Review"))
        self.assertNotIn("preview order", dashboard.lower())
        self.assertNotIn("place trade", dashboard.lower())

        self.assertIn("## Decision Quality Review", markdown)
        self.assertIn("Top 5 Ranked Opportunities Today", markdown)
        self.assertIn("MSFT", markdown)
        self.assertIn("User may manually buy", markdown)
        self.assertIn("Does not change official recommendation", markdown)

    def test_local_console_includes_decision_quality_before_capital_deployment(self) -> None:
        context = wave15_context()
        panels = build_console_panels(context, {"items": [], "latest": {}}, {"workflow_runs": [], "recommendation_runs": []})
        manifest = {
            "generated_at": "2026-06-01T08:00:00",
            "guardrails": ["Recommendation-only decision support.", "No order preview or order placement."],
            "report_context": {"report_date": "2026-06-01"},
            "panels": panels,
            "artifacts": {"items": []},
            "run_history": {"workflow_runs": [], "recommendation_runs": []},
            "workflow": {
                "build_manifest": "python3 scripts/build_local_console_manifest.py --output reports/local-console-manifest.json",
                "render_console": "python3 scripts/render_local_console.py --manifest reports/local-console-manifest.json --output reports/local-console.html",
                "open_console": "Open reports/local-console.html manually in a browser.",
                "note": "Manual only.",
            },
        }

        html = render_local_console(manifest)

        self.assertIn("decision_quality", panels)
        self.assertIn("Decision Quality Review", html)
        self.assertIn("Top 5 daily review", html)
        self.assertLess(html.index("Decision Quality Review"), html.index("Long-Term Capital Deployment"))
        self.assertNotIn("<button", html.lower())
        self.assertNotIn("preview order", html.lower())


if __name__ == "__main__":
    unittest.main()
