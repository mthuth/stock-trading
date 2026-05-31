#!/usr/bin/env python3
"""Regression tests for deterministic AI prompt packets."""

from __future__ import annotations

import json
import unittest

from stock_trading.ai_prompt_packets import (
    PACKET_VERSION,
    RECOMMENDATION_ONLY_INSTRUCTION,
    build_prompt_packet_context,
)


def prompt_context() -> dict[str, object]:
    return {
        "metadata": {
            "report_date": "2026-05-31",
            "generated_at": "2026-05-31T08:00:00",
            "recommendation_only": True,
        },
        "summary": {
            "top_symbol": "MSFT",
            "decision_gate": {
                "safe_to_buy": True,
                "status": "Ready",
                "candidate_action": "Add",
                "reasons": [],
                "summary": "Decision-safe buy candidate.",
            },
        },
        "recommendations": [
            {
                "rank": 1,
                "symbol": "MSFT",
                "company": "Microsoft",
                "action": "Add",
                "score": 84.2,
                "target_price": 520.0,
                "target_price_text": "$520.00",
                "upside_pct": 20.0,
                "upside_text": "20.0%",
                "confidence": "Medium",
                "data_status": "Blended",
                "score_breakdown": "Long-term model: quality and target upside lead.",
                "score_explanation": {
                    "model": "Long-term",
                    "top_drivers": [{"label": "Quality", "points": 22.5}],
                    "top_risks": [{"label": "Valuation risk", "points": -4.0}],
                },
                "rationale": "Score is high enough to add.",
                "what_would_change_the_view": "A negative primary filing or weaker AI demand would change the view.",
            },
            {
                "rank": 2,
                "symbol": "NVDA",
                "company": "NVIDIA",
                "action": "Watch",
                "score": 78.4,
                "target_price": 160.0,
                "target_price_text": "$160.00",
                "upside_pct": 12.0,
                "upside_text": "12.0%",
                "confidence": "Low",
                "data_status": "Partial blend",
                "score_breakdown": "Target breadth and provider gaps limit confidence.",
                "score_explanation": {
                    "model": "Long-term",
                    "top_drivers": [{"label": "Momentum", "points": 12.0}],
                    "top_risks": [{"label": "Provider gap", "points": -3.0}],
                },
                "rationale": "Needs target breadth review.",
            },
            {
                "rank": 3,
                "symbol": "BBAI",
                "company": "BigBear.ai",
                "action": "Watch",
                "score": 62.0,
                "target_price": 0,
                "target_price_text": "Needs target",
                "upside_pct": 0,
                "upside_text": "Refresh",
                "confidence": "Low",
                "data_status": "Needs price",
                "score_breakdown": "Missing current price and thin evidence.",
                "score_explanation": {"model": "Speculative", "top_drivers": [], "top_risks": []},
                "rationale": "Watchlist-only until data coverage improves.",
            },
        ],
        "target_drilldowns": {
            "by_symbol": {
                "MSFT": {
                    "blend_label": "full blend",
                    "blend_status": "Analyst + fundamental + technical",
                    "labels": ["full blend"],
                    "source_count": 3,
                    "sources": [
                        {
                            "target_type": "analyst",
                            "source_name": "Financial Modeling Prep",
                            "source_type": "data_provider",
                            "target_price_text": "$520.00",
                            "freshness": "Fresh (0 days)",
                            "confidence": "medium",
                            "notes": "Consensus target input.",
                        }
                    ],
                },
                "NVDA": {
                    "blend_label": "partial blend",
                    "blend_status": "Fundamental + technical",
                    "labels": ["partial blend", "missing input: analyst"],
                    "source_count": 2,
                    "sources": [],
                },
                "BBAI": {
                    "blend_label": "missing input",
                    "blend_status": "Missing usable target inputs",
                    "labels": ["missing input: analyst", "missing input: fundamental", "missing input: technical"],
                    "source_count": 0,
                    "sources": [],
                },
            }
        },
        "source_health": {
            "provider_blockers": {
                "headers": [
                    "Severity",
                    "Symbol",
                    "Provider",
                    "Field",
                    "Blocks",
                    "Likely Cause",
                    "Decision Context",
                    "Latest Detail",
                    "Next Action",
                ],
                "rows": [
                    [
                        "High",
                        "NVDA",
                        "Financial Modeling Prep",
                        "analyst_targets",
                        "Analyst target breadth",
                        "Provider plan/access blocker",
                        "Rank 2 / Watch / 78.4",
                        "HTTP 402 plan block",
                        "Review provider access",
                    ],
                    [
                        "High",
                        "BBAI",
                        "FMP/Alpha Vantage",
                        "current_price",
                        "Current price",
                        "Missing data",
                        "Rank 3 / Watch / 62.0",
                        "No current price",
                        "Refresh price data",
                    ],
                ],
            }
        },
        "evidence_events": {
            "headers": [
                "Event Date",
                "Symbol",
                "Event Type",
                "Headline",
                "Corroboration",
                "Sources",
                "Evidence",
                "Source Mix",
                "Confidence",
                "Latest Evidence",
                "Summary",
            ],
            "rows": [
                [
                    "2026-05-30",
                    "MSFT",
                    "ai_platform_update",
                    "Azure AI demand update",
                    "primary_plus_confirmed",
                    2,
                    3,
                    "primary 1 / company 1 / independent 1 / opinion 0",
                    "medium_high",
                    "2026-05-30",
                    "Primary and independent sources support demand.",
                ],
                [
                    "2026-05-30",
                    "NVDA",
                    "valuation_risk",
                    "Valuation risk remains elevated",
                    "independent_confirmed",
                    2,
                    2,
                    "primary 0 / company 0 / independent 2 / opinion 0",
                    "medium",
                    "2026-05-30",
                    "Independent reports flag valuation risk.",
                ],
                [
                    "2026-05-29",
                    "BBAI",
                    "ai_context",
                    "Generic AI mention",
                    "single_source",
                    1,
                    1,
                    "primary 0 / company 0 / independent 0 / opinion 1",
                    "low",
                    "2026-05-29",
                    "Opinion-only context.",
                ],
            ],
        },
        "source_depth": {
            "headers": ["Symbol", "Depth Type", "Signal", "Detail", "Confidence", "Corroboration", "As Of", "Source URL"],
            "rows": [
                [
                    "MSFT",
                    "sec_filing",
                    "10-Q filing",
                    "Recent filing confirms AI infrastructure spend.",
                    "high",
                    "primary_source",
                    "2026-05-01",
                    "https://www.sec.gov/",
                ],
                [
                    "NVDA",
                    "official_ir_link",
                    "Company presentation",
                    "Company-only product update needs independent confirmation.",
                    "medium",
                    "official_company_source",
                    "2026-05-28",
                    "https://investor.nvidia.com/",
                ],
            ],
        },
        "source_quality": {
            "low_confidence_matches": {
                "headers": ["Source", "Symbol", "Reason", "Matched Text", "Bucket", "Confidence", "Title", "Timestamp"],
                "rows": [["Noisy public feed", "BBAI", "weak_alias", "AI", "low", "0.20", "Generic AI roundup", "2026-05-29"]],
            }
        },
        "verification": {
            "headers": ["Symbol", "Type", "Risk Or Uncertainty", "Next Check", "What Would Change The View"],
            "rows": [
                ["NVDA", "target_breadth", "No analyst target breadth", "Update analyst targets", "Second analyst source confirms target."],
                ["BBAI", "price", "Missing current price", "Refresh price data", "Current price refresh succeeds."],
            ],
        },
        "synthesis_readiness": {
            "headers": [
                "Symbol",
                "Readiness",
                "Score",
                "Ready Events",
                "Needs Review",
                "Needs Corroboration",
                "Ignored",
                "Primary Events",
                "Independent Confirmed",
                "Latest Event",
                "Packet",
                "Notes",
            ],
            "rows": [
                ["MSFT", "ready_for_ai_synthesis", "1.0", 3, 0, 0, 0, 2, 2, "2026-05-30", "synthesis-packets.json", "Ready."],
                ["NVDA", "partially_ready", "0.4", 1, 2, 1, 0, 1, 1, "2026-05-30", "synthesis-packets.json", "Needs review."],
                ["BBAI", "not_enough_data", "0.0", 0, 1, 0, 2, 0, 0, "2026-05-29", "synthesis-packets.json", "Not enough data."],
            ],
        },
    }


class AiPromptPacketsTests(unittest.TestCase):
    def packets_by_symbol(self) -> dict[str, dict[str, object]]:
        result = build_prompt_packet_context(prompt_context())
        return {packet["symbol"]: packet for packet in result["packets"]}

    def test_ready_symbol_packet_includes_core_schema(self) -> None:
        result = build_prompt_packet_context(prompt_context())
        packet = {row["symbol"]: row for row in result["packets"]}["MSFT"]

        self.assertEqual(result["metadata"]["packet_version"], PACKET_VERSION)
        self.assertFalse(result["metadata"]["llm_generated"])
        self.assertEqual(packet["company"], "Microsoft")
        self.assertEqual(packet["current_action"], "Add")
        self.assertEqual(packet["score"], 84.2)
        self.assertEqual(packet["synthesis_readiness"]["status"], "ready_for_ai_synthesis")
        self.assertEqual(packet["target_context"]["blend_label"], "full blend")
        self.assertEqual(packet["decision_safety"]["status"], "Ready")
        self.assertTrue(packet["bull_case_evidence"])
        self.assertTrue(packet["what_changed_recently"])

    def test_partially_ready_symbol_packet_preserves_gaps_and_verification(self) -> None:
        packet = self.packets_by_symbol()["NVDA"]

        self.assertEqual(packet["synthesis_readiness"]["status"], "partially_ready")
        self.assertEqual(packet["target_context"]["blend_label"], "partial blend")
        self.assertEqual(packet["provider_source_gaps"][0]["provider"], "Financial Modeling Prep")
        self.assertEqual(packet["what_needs_verification"][0]["type"], "target_breadth")
        self.assertTrue(packet["bear_risk_evidence"])

    def test_blocked_not_enough_data_symbol_packet_marks_excluded_evidence(self) -> None:
        packet = self.packets_by_symbol()["BBAI"]

        self.assertEqual(packet["synthesis_readiness"]["status"], "not_enough_data")
        self.assertEqual(packet["target_context"]["blend_label"], "missing input")
        self.assertEqual(packet["provider_source_gaps"][0]["field"], "current_price")
        reasons = [row["exclusion_reason"] for row in packet["excluded_or_flagged_evidence"]]
        self.assertTrue(any("low-confidence" in reason or "weak corroboration" in reason for reason in reasons))

    def test_source_attribution_and_recommendation_only_instruction_are_included(self) -> None:
        packet = self.packets_by_symbol()["MSFT"]

        self.assertEqual(packet["source_attribution"][0]["corroboration_label"], "primary_plus_confirmed")
        self.assertIn("Recommendation-only", packet["instructions"]["recommendation_only"])
        self.assertEqual(packet["instructions"]["recommendation_only"], RECOMMENDATION_ONLY_INSTRUCTION)

    def test_packet_context_is_json_serializable_and_does_not_change_actions(self) -> None:
        context = prompt_context()
        result = build_prompt_packet_context(context)
        json.dumps(result, sort_keys=True)

        original_actions = [row["action"] for row in context["recommendations"]]
        packet_actions = [row["current_action"] for row in result["packets"]]
        self.assertEqual(packet_actions, original_actions)


if __name__ == "__main__":
    unittest.main()
