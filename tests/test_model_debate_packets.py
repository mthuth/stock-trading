#!/usr/bin/env python3
"""Tests for deterministic shadow-model debate packets."""

from __future__ import annotations

import copy
import inspect
import json
import unittest
from pathlib import Path

import stock_trading.model_debate_packets as subject


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "shadow_models" / "model_debate_cases.json"


class ModelDebatePacketTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cases = json.loads(FIXTURE.read_text())

    def packet(self, case_name: str) -> dict[str, object]:
        case = self.cases[case_name]
        return subject.build_model_debate_packet(
            official_recommendation=case["official_recommendation"],
            shadow_recommendations=case["shadow_recommendations"],
            model_competition_rows=case.get("model_competition_rows", []),
            evidence_context=case.get("evidence_context", []),
            provider_gaps=case.get("provider_gaps", []),
            target_context=case.get("target_context", {}),
            decision_safety_context=case.get("decision_safety_context", {}),
            ai_brief_context=case.get("ai_brief_context", {}),
        )

    def assert_guardrails(self, packet: dict[str, object]) -> None:
        self.assertTrue(packet["review_only"])
        self.assertTrue(packet["shadow_only"])
        self.assertTrue(packet["no_official_change"])
        instructions = packet["llm_instructions"]
        self.assertTrue(instructions["do_not_change_official_recommendation"])
        self.assertTrue(instructions["do_not_place_trades"])
        self.assertTrue(instructions["do_not_preview_orders"])
        self.assertTrue(instructions["explain_only"])

    def test_models_agree_packet(self) -> None:
        packet = self.packet("agree")

        self.assertEqual(packet["symbol"], "NVDA")
        self.assertEqual(packet["consensus_view"]["status"], "models_agree")
        self.assertEqual(packet["disagreement_summary"]["status"], "agreement")
        self.assertEqual(len(packet["bullish_models"]), 2)
        self.assertEqual(packet["strongest_bull_case"]["model_name"], "growth_shadow")
        self.assertEqual(packet["model_competition"]["leader_model"], "growth_shadow")
        self.assert_guardrails(packet)

    def test_models_disagree_packet(self) -> None:
        packet = self.packet("disagree")

        self.assertEqual(packet["consensus_view"]["status"], "models_disagree")
        self.assertEqual(packet["disagreement_summary"]["status"], "disagreement")
        self.assertTrue(any(row["type"] == "action" for row in packet["key_disagreements"]))
        self.assertEqual(len(packet["bullish_models"]), 1)
        self.assertEqual(len(packet["bearish_or_skeptical_models"]), 0)
        self.assertIn("provider/data gaps", " ".join(packet["what_would_resolve_disagreement"]).lower())
        self.assert_guardrails(packet)

    def test_aggressive_vs_conservative_disagreement(self) -> None:
        packet = self.packet("aggressive_vs_conservative")

        self.assertEqual(packet["strongest_bull_case"]["model_name"], "aggressive_growth")
        self.assertEqual(packet["strongest_bear_case"]["model_name"], "risk_control")
        self.assertTrue(any(row["type"] == "action" for row in packet["key_disagreements"]))
        self.assertEqual(packet["target_context"]["target_confidence"], "low")
        self.assert_guardrails(packet)

    def test_tactical_vs_long_term_disagreement(self) -> None:
        packet = self.packet("tactical_vs_long_term")

        self.assertEqual(len(packet["tactical_models"]), 1)
        self.assertEqual(packet["tactical_models"][0]["model_name"], "tactical_momentum")
        self.assertTrue(any(row["type"] == "decision_mode" for row in packet["key_disagreements"]))
        self.assertTrue(any("long-term, tactical" in item for item in packet["what_would_resolve_disagreement"]))
        self.assert_guardrails(packet)

    def test_earnings_model_disagreement(self) -> None:
        packet = self.packet("earnings_disagreement")

        self.assertEqual(len(packet["earnings_models"]), 1)
        self.assertEqual(packet["earnings_models"][0]["model_name"], "earnings_reaction")
        self.assertTrue(any(row["type"] == "decision_mode" for row in packet["key_disagreements"]))
        self.assert_guardrails(packet)

    def test_missing_evidence_is_explicit(self) -> None:
        packet = self.packet("missing_evidence")

        self.assertEqual(packet["provider_gap_notes"], ["No provider-gap notes supplied."])
        self.assertEqual(packet["source_quality_notes"], ["No source-quality notes supplied."])
        self.assertEqual(packet["evidence_each_model_used"], {"speculative_ai_shadow": []})
        self.assert_guardrails(packet)

    def test_provider_gap_present(self) -> None:
        packet = self.packet("disagree")

        self.assertEqual(
            packet["provider_gap_notes"],
            ["Analyst targets target breadth missing Only one fresh target source."],
        )
        self.assertTrue(any("Resolve provider/data gaps" in item for item in packet["what_would_resolve_disagreement"]))
        self.assert_guardrails(packet)

    def test_packet_is_json_serializable(self) -> None:
        packet = self.packet("agree")

        encoded = json.dumps(packet, sort_keys=True)

        self.assertIn("growth_shadow", encoded)
        self.assertIn("no_official_change", encoded)

    def test_no_llm_call_or_client_import(self) -> None:
        source = inspect.getsource(subject)

        self.assertNotIn("openai", source.lower())
        self.assertNotIn("chatcompletion", source.lower())
        self.assertNotIn("responses.create", source.lower())
        self.assertNotIn("requests.", source.lower())

    def test_no_official_recommendation_mutation(self) -> None:
        case = copy.deepcopy(self.cases["disagree"])
        original = copy.deepcopy(case)

        packet = subject.build_model_debate_packet(
            official_recommendation=case["official_recommendation"],
            shadow_recommendations=case["shadow_recommendations"],
            evidence_context=case.get("evidence_context", []),
            provider_gaps=case.get("provider_gaps", []),
        )

        self.assertEqual(case, original)
        self.assertEqual(packet["official_recommendation"]["action"], "Add")
        self.assertTrue(packet["official_recommendation"]["review_only"])
        self.assertFalse(packet["official_recommendation"]["shadow_only"])
        self.assert_guardrails(packet)


if __name__ == "__main__":
    unittest.main()
