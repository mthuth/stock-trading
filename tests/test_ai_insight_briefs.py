#!/usr/bin/env python3
"""Regression tests for deterministic V1.9 AI insight briefs."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from stock_trading.ai_briefs import (
    BRIEF_VERSION,
    build_ai_insight_briefs,
    render_ai_briefs_markdown,
)
from stock_trading.presentation import render_report_context


def brief_context() -> dict[str, object]:
    return {
        "metadata": {"report_date": "2026-05-29", "generated_at": "2026-05-29T12:00:00"},
        "artifacts": {"context": "report-context-2026-05-29.json"},
        "ai_analysis": {
            "decision_insights": [
                {
                    "rank": 1,
                    "symbol": "MSFT",
                    "action": "Add",
                    "score": 81.2,
                    "insight_type": "Verification Needed",
                    "headline": "MSFT is near action, but one provider check remains.",
                    "why_it_matters": "Final score is 81.2 after a positive overlay.",
                    "supporting_data": "Evidence improved after IR pull.",
                    "risk_or_uncertainty": "Provider gap remains.",
                    "next_check": "scripts/show_provider_gaps.py",
                    "what_would_change_the_view": "Provider gap closes.",
                }
            ],
            "verification_queue": [
                {
                    "symbol": "MSFT",
                    "status": "blocked_provider_fix_needed",
                    "reason": "Provider failure/blocked endpoint in latest notes",
                    "command_mapping": "scripts/show_provider_gaps.py",
                }
            ],
        },
        "score_movement": {
            "headers": ["Symbol", "Base", "Evidence", "Trend", "Targets", "Gaps", "Final", "Action", "Top Driver"],
            "rows": [["MSFT", "78.9", "+1.8", "+0.0", "+1.5", "-1.0", "81.2", "Add", "Evidence +1.8"]],
        },
        "trend_insights": {
            "headers": ["Symbol", "Overlay", "Trend Insight", "Score Movement"],
            "rows": [["MSFT", "+2.2", "Mixed price trend.", "78.9 base +2.2 overlay = 81.2"]],
        },
        "source_health": {
            "provider_blockers": {
                "headers": ["Severity", "Symbol", "Provider", "Field", "Blocks", "Likely Cause", "Decision Context", "Latest Detail", "Next Action"],
                "rows": [["Medium", "MSFT", "Finnhub", "quote", "Current price reliability", "Network / DNS", "Rank 1 / Add / 81.2", "DNS failure", "Retry"]],
            }
        },
        "evidence_events": {
            "headers": ["Event Date", "Symbol", "Event Type", "Headline", "Corroboration", "Sources", "Evidence", "Source Mix", "Confidence", "Latest Evidence", "Summary"],
            "rows": [["2026-05-29", "MSFT", "Ai Platform Update", "Azure AI infrastructure update", "primary_plus_confirmed", 2, 3, "primary 1 / company 1 / independent 0 / opinion 0", "medium_high", "2026-05-29", "Representative event."]],
        },
        "synthesis_readiness": {
            "headers": ["Symbol", "Readiness", "Score", "Ready Events", "Needs Review", "Needs Corroboration", "Ignored", "Primary Events", "Independent Confirmed", "Latest Event", "Packet", "Notes"],
            "rows": [["MSFT", "partially_ready", "0.75", 1, 1, 0, 0, 1, 0, "2026-05-29", "synthesis-packets-2026-05-29.json", "At least one ready event."]],
        },
        "summary": {},
        "reliability": {"price_counts": {}},
        "recommendations": [],
        "holdings": {},
        "queues": {},
        "decision_briefs": {},
        "insight_themes": {},
        "data_gaps": {},
        "data_ingestion": {},
        "research_sources": {},
        "feedback": {},
    }


class AiInsightBriefTests(unittest.TestCase):
    def test_brief_is_deterministic_and_audit_cited(self) -> None:
        result = build_ai_insight_briefs(brief_context())
        brief = result["briefs"][0]

        self.assertEqual(result["metadata"]["brief_version"], BRIEF_VERSION)
        self.assertFalse(result["metadata"]["llm_generated"])
        self.assertEqual(brief["symbol"], "MSFT")
        self.assertIn("MSFT is Add at 81.2/100", brief["brief"])
        self.assertIn("Top evidence event is Ai Platform Update", brief["brief"])
        self.assertIn("Synthesis readiness is partially_ready", brief["brief"])
        self.assertIn("score_movement:MSFT", brief["audit_refs"])
        self.assertIn("evidence_events:MSFT", brief["audit_refs"])
        self.assertIn("synthesis_readiness:MSFT", brief["audit_refs"])
        self.assertIn("provider_blockers:MSFT", brief["audit_refs"])
        self.assertTrue(brief["guardrails"]["passed"])
        self.assertEqual(brief["guardrails"]["recommended_action"], "accept")
        self.assertIn("Recommendation-only", brief["recommendation_only_disclaimer"])
        self.assertIn("Finnhub", brief["data_gaps"])

    def test_markdown_mentions_no_llm_and_next_check(self) -> None:
        markdown = render_ai_briefs_markdown(build_ai_insight_briefs(brief_context()))

        self.assertIn("No LLM generated these briefs", markdown)
        self.assertIn("scripts/show_provider_gaps.py", markdown)
        self.assertIn("Recommendation-only", markdown)
        self.assertIn("Guardrails: accept", markdown)

    def test_report_render_writes_ai_brief_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = render_report_context(brief_context(), Path(temp_dir))
            markdown = Path(temp_dir) / "ai-insight-briefs-2026-05-29.md"
            payload = Path(temp_dir) / "ai-insight-briefs-2026-05-29.json"
            html = Path(temp_dir) / "ai-insight-briefs-2026-05-29.html"

            self.assertIn(markdown, paths)
            self.assertIn(payload, paths)
            self.assertIn(html, paths)
            self.assertIn("AI Insight Briefs", markdown.read_text())
            self.assertEqual(json.loads(payload.read_text())["briefs"][0]["symbol"], "MSFT")


if __name__ == "__main__":
    unittest.main()
