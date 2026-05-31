#!/usr/bin/env python3
"""Regression tests for optional LLM research brief drafting."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from stock_trading.llm_research_briefs import (
    MockLLMResearchBriefClient,
    build_llm_research_briefs,
    render_llm_research_briefs_markdown,
    write_llm_research_brief_artifacts,
)


class FakeLLMClient:
    provider = "unit-test"
    model = "fake-brief-model"

    def __init__(self, response: object | None = None, error: Exception | None = None) -> None:
        self.response = response or {
            "summary": "MSFT has source-backed AI infrastructure evidence, but this remains decision support.",
            "bull_case": "Bull case: primary and independent evidence support durable AI platform demand.",
            "bear_case": "Bear case: risk or uncertainty remains around valuation and provider freshness.",
            "key_evidence": ["Azure AI demand update", "10-Q filing confirms infrastructure spend"],
            "open_data_gaps": ["No major data gaps found."],
            "what_would_change_the_view": "A negative primary filing or weaker AI demand would change the view.",
        }
        self.error = error

    def draft_research_brief(self, prompt: str, packet: dict[str, object]) -> dict[str, object]:
        if self.error:
            raise self.error
        return self.response  # type: ignore[return-value]


def packet_context() -> dict[str, object]:
    return {
        "metadata": {
            "packet_version": "ai-prompt-packets-v1",
            "report_date": "2026-05-31",
            "generated_at": "2026-05-31T08:00:00",
            "llm_generated": False,
            "recommendation_only": True,
        },
        "packets": [
            {
                "symbol": "MSFT",
                "company": "Microsoft",
                "current_action": "Add",
                "score": 84.2,
                "synthesis_readiness": {
                    "status": "ready_for_ai_synthesis",
                    "score": "1.0",
                    "ready_events": 3,
                    "needs_review": 0,
                },
                "score_explanation_summary": {"summary": "Quality and target context support review."},
                "target_context": {"confidence": "Medium", "blend_label": "full blend"},
                "decision_safety": {"status": "Ready", "safe_to_buy": True},
                "top_usable_evidence_events": [
                    {
                        "headline": "Azure AI demand update",
                        "summary": "Primary and independent sources support AI demand.",
                        "source_name": "Company IR",
                        "source_table": "evidence_events",
                        "source_url": "https://example.test/msft-ir",
                        "corroboration_label": "primary_plus_confirmed",
                        "confidence": "medium_high",
                    }
                ],
                "source_attribution": [
                    {
                        "source_name": "Company IR",
                        "source_table": "evidence_events",
                        "source_url": "https://example.test/msft-ir",
                        "corroboration_label": "primary_plus_confirmed",
                        "confidence": "medium_high",
                    }
                ],
                "bull_case_evidence": [{"summary": "AI demand evidence is corroborated."}],
                "bear_risk_evidence": [{"summary": "Valuation risk remains."}],
                "what_changed_recently": [{"headline": "Azure AI demand update"}],
                "provider_source_gaps": [],
                "what_would_change_the_view": "A negative primary filing or weaker AI demand would change the view.",
            },
            {
                "symbol": "BBAI",
                "company": "BigBear.ai",
                "current_action": "Watch",
                "score": 62.0,
                "synthesis_readiness": {
                    "status": "not_enough_data",
                    "score": "0.0",
                    "ready_events": 0,
                    "needs_review": 1,
                },
                "top_usable_evidence_events": [],
                "source_attribution": [],
                "provider_source_gaps": [
                    {
                        "provider": "FMP",
                        "field": "current_price",
                        "latest_detail": "No current price",
                        "next_action": "Refresh price data",
                    }
                ],
                "what_would_change_the_view": "Fresh price and corroborated evidence would change the view.",
            },
        ],
    }


class LLMResearchBriefTests(unittest.TestCase):
    def test_brief_generated_from_ready_packet(self) -> None:
        result = build_llm_research_briefs(
            packet_context(),
            client=FakeLLMClient(),
            generated_at="2026-05-31T09:00:00",
        )
        brief = result["briefs"][0]

        self.assertTrue(result["metadata"]["llm_generated"])
        self.assertEqual(brief["symbol"], "MSFT")
        self.assertEqual(brief["status"], "generated")
        self.assertTrue(brief["llm_generated"])
        self.assertEqual(brief["provider"], "unit-test")
        self.assertEqual(brief["model"], "fake-brief-model")
        self.assertEqual(brief["readiness_status"], "ready_for_ai_synthesis")
        self.assertIn("source-backed", brief["summary"])
        self.assertIn("Bull case", brief["bull_case"])
        self.assertIn("Bear case", brief["bear_case"])

    def test_refusal_when_packet_is_not_ready(self) -> None:
        result = build_llm_research_briefs(packet_context(), client=FakeLLMClient())
        brief = result["briefs"][1]

        self.assertEqual(brief["symbol"], "BBAI")
        self.assertEqual(brief["status"], "refused")
        self.assertEqual(brief["readiness_status"], "not_enough_data")
        self.assertIn("Not enough evidence", brief["summary"])
        self.assertIn("current_price", brief["open_data_gaps"][0])

    def test_source_references_and_disclaimer_are_included(self) -> None:
        result = build_llm_research_briefs(packet_context(), client=FakeLLMClient())
        brief = result["briefs"][0]

        self.assertEqual(brief["source_references"][0]["source_name"], "Company IR")
        self.assertIn("Recommendation-only", brief["recommendation_only_disclaimer"])
        self.assertIn("prompt_packet_evidence:MSFT", brief["audit_refs"])
        self.assertTrue(brief["guardrails"]["passed"])

    def test_mock_llm_failure_refuses_without_raising(self) -> None:
        result = build_llm_research_briefs(
            packet_context(),
            client=FakeLLMClient(error=RuntimeError("model unavailable")),
        )
        brief = result["briefs"][0]

        self.assertEqual(brief["status"], "refused")
        self.assertIn("model unavailable", brief["summary"])

    def test_malformed_llm_response_refuses_without_raising(self) -> None:
        result = build_llm_research_briefs(
            packet_context(),
            client=FakeLLMClient(response={"summary": "Incomplete"}),
        )
        brief = result["briefs"][0]

        self.assertEqual(brief["status"], "refused")
        self.assertIn("missing required field", brief["summary"].lower())

    def test_default_without_client_is_dry_run_refusal(self) -> None:
        result = build_llm_research_briefs(packet_context())
        brief = result["briefs"][0]

        self.assertEqual(brief["status"], "refused")
        self.assertEqual(brief["provider"], "disabled")
        self.assertFalse(result["metadata"]["live_model_calls_enabled"])

    def test_json_and_markdown_artifacts_render(self) -> None:
        result = build_llm_research_briefs(
            packet_context(),
            client=MockLLMResearchBriefClient(),
            generated_at="2026-05-31T09:00:00",
        )
        markdown = render_llm_research_briefs_markdown(result)

        self.assertIn("LLM Research Briefs", markdown)
        self.assertIn("Recommendation-only", markdown)
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = write_llm_research_brief_artifacts(result, Path(temp_dir), "2026-05-31")
            json_path = Path(temp_dir) / "llm-research-briefs-2026-05-31.json"
            markdown_path = Path(temp_dir) / "llm-research-briefs-2026-05-31.md"

            self.assertIn(json_path, paths)
            self.assertIn(markdown_path, paths)
            self.assertEqual(json.loads(json_path.read_text())["briefs"][0]["symbol"], "MSFT")
            self.assertIn("MSFT", markdown_path.read_text())


if __name__ == "__main__":
    unittest.main()
