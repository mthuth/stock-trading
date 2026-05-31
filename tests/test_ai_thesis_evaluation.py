#!/usr/bin/env python3
"""Regression tests for review-only AI thesis evaluation."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from stock_trading.ai_thesis_evaluation import evaluate_ai_thesis, evaluate_ai_theses


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


def load_json(path: str) -> object:
    return json.loads((FIXTURE_DIR / path).read_text())


def base_brief(**overrides: object) -> dict[str, object]:
    brief: dict[str, object] = {
        "brief_id": "brief-nvda-2026-05-01-1",
        "symbol": "NVDA",
        "report_date": "2026-05-01",
        "artifact_ref": "llm-research-briefs-2026-05-01.json",
        "summary": "NVDA has source-backed AI infrastructure evidence. Recommendation-only decision support.",
        "bull_case": "Bull case: AI infrastructure demand supports the thesis.",
        "bear_case": "Bear case: supply risk and valuation could pressure returns.",
        "risk_or_uncertainty": "Risk or uncertainty: valuation and supply risk need review.",
        "key_evidence": ["Primary and independent evidence support AI infrastructure demand."],
        "open_data_gaps": ["No major data gaps found."],
        "what_would_change_the_view": "A demand slowdown or margin guide-down would change the view.",
        "source_references": [{"source_name": "Company IR", "source_table": "evidence_events"}],
        "audit_refs": ["ai_prompt_packet:NVDA", "prompt_packet_evidence:NVDA"],
        "guardrails": {"passed": True, "warnings": [], "failures": [], "recommended_action": "accept"},
    }
    brief.update(overrides)
    return brief


class AiThesisEvaluationTests(unittest.TestCase):
    def test_thesis_supported_from_fixture_evidence_and_positive_outcome(self) -> None:
        brief = load_json("ai/msft_ai_thesis_brief.json")
        later_evidence = load_json("model_evaluation/msft_later_evidence_supported.json")

        result = evaluate_ai_thesis(
            brief,  # type: ignore[arg-type]
            later_evidence=later_evidence,  # type: ignore[arg-type]
            recommendation_outcomes=[{"outcome_status": "positive_follow_through"}],
        )

        self.assertEqual(result["symbol"], "MSFT")
        self.assertEqual(result["thesis_evaluation_label"], "thesis_supported")
        self.assertEqual(result["outcome_alignment"], "aligned")
        self.assertTrue(result["review_only"])
        self.assertTrue(result["no_model_change"])
        self.assertGreaterEqual(len(result["supported_claims"]), 2)

    def test_thesis_contradicted_by_later_evidence_and_outcome(self) -> None:
        result = evaluate_ai_thesis(
            base_brief(),
            later_evidence=[
                {
                    "claim_type": "bull_case",
                    "relation": "contradicted",
                    "summary": "Later evidence showed AI infrastructure demand softened.",
                }
            ],
            recommendation_outcomes=[{"outcome_status": "drawdown_warning"}],
        )

        self.assertEqual(result["thesis_evaluation_label"], "thesis_contradicted")
        self.assertEqual(result["outcome_alignment"], "contradicted")
        self.assertTrue(result["evaluations"]["outcome_contradicted_thesis"])
        self.assertEqual(result["contradicted_claims"][0]["claim_type"], "bull_case")

    def test_thesis_partially_supported_when_risk_materializes(self) -> None:
        result = evaluate_ai_thesis(
            base_brief(),
            later_evidence=[
                {
                    "claim_type": "bull_case",
                    "relation": "supported",
                    "summary": "Demand evidence remained intact.",
                },
                {
                    "claim_type": "risk",
                    "relation": "risk_materialized",
                    "summary": "Valuation compression became the dominant return driver.",
                },
            ],
            recommendation_outcomes=[{"outcome_status": "mixed"}],
        )

        self.assertEqual(result["thesis_evaluation_label"], "thesis_partially_supported")
        self.assertTrue(result["evaluations"]["bull_case_supported"])
        self.assertTrue(result["evaluations"]["key_risk_materialized"])

    def test_too_early_to_judge_when_outcome_history_is_pending(self) -> None:
        result = evaluate_ai_thesis(
            base_brief(),
            recommendation_outcomes=[{"outcome_status": "not_enough_history"}],
        )

        self.assertEqual(result["thesis_evaluation_label"], "too_early_to_judge")
        self.assertEqual(result["outcome_alignment"], "pending")
        self.assertEqual(result["confidence"], "low")

    def test_insufficient_evidence_for_low_readiness_or_source_warning(self) -> None:
        result = evaluate_ai_thesis(
            base_brief(open_data_gaps=["Provider gap: missing source corroboration."]),
            prompt_packet={"synthesis_readiness": {"status": "not_enough_data"}},
        )

        self.assertEqual(result["thesis_evaluation_label"], "insufficient_evidence")
        self.assertTrue(result["evaluations"]["stale_or_missing_source_warning"])
        self.assertEqual(result["evaluations"]["synthesis_readiness_status"], "not_enough_data")

    def test_guardrail_failed_takes_precedence(self) -> None:
        result = evaluate_ai_thesis(
            base_brief(
                guardrails={
                    "passed": False,
                    "warnings": [],
                    "failures": [{"category": "order_or_execution_language", "message": "Order language."}],
                    "recommended_action": "reject",
                }
            ),
            later_evidence=[{"claim_type": "bull_case", "relation": "supported", "summary": "Supported."}],
            recommendation_outcomes=[{"outcome_status": "positive_follow_through"}],
        )

        self.assertEqual(result["thesis_evaluation_label"], "guardrail_failed")
        self.assertEqual(result["guardrail_status"], "failed")
        self.assertEqual(result["guardrail_failures"][0]["category"], "order_or_execution_language")

    def test_no_ai_generation_inputs_are_mutated(self) -> None:
        brief = base_brief()
        packet = {
            "symbol": "NVDA",
            "report_date": "2026-05-01",
            "synthesis_readiness": {"status": "ready_for_ai_synthesis"},
            "provider_source_gaps": [],
        }
        before_brief = copy.deepcopy(brief)
        before_packet = copy.deepcopy(packet)

        evaluate_ai_thesis(
            brief,
            prompt_packet=packet,
            later_evidence=[{"claim_type": "bull_case", "relation": "supported", "summary": "Supported."}],
        )

        self.assertEqual(brief, before_brief)
        self.assertEqual(packet, before_packet)

    def test_no_recommendation_outcome_inputs_are_mutated(self) -> None:
        outcome_rows = [{"symbol": "NVDA", "outcome_status": "positive_follow_through"}]
        before = copy.deepcopy(outcome_rows)

        evaluate_ai_thesis(base_brief(), recommendation_outcomes=outcome_rows)

        self.assertEqual(outcome_rows, before)

    def test_batch_summary_is_review_only_and_counts_labels(self) -> None:
        result = evaluate_ai_theses(
            [base_brief(symbol="NVDA"), base_brief(symbol="MSFT")],
            later_evidence_by_symbol={
                "NVDA": [{"claim_type": "bull_case", "relation": "supported", "summary": "Supported."}],
                "MSFT": [{"claim_type": "bull_case", "relation": "contradicted", "summary": "Contradicted."}],
            },
            recommendation_outcomes_by_symbol={
                "NVDA": [{"outcome_status": "positive_follow_through"}],
                "MSFT": [{"outcome_status": "negative_follow_through"}],
            },
        )

        self.assertTrue(result["metadata"]["review_only"])
        self.assertTrue(result["metadata"]["no_model_change"])
        self.assertEqual(result["metadata"]["evaluation_count"], 2)
        self.assertEqual(result["metadata"]["label_counts"]["thesis_supported"], 1)
        self.assertEqual(result["metadata"]["label_counts"]["thesis_contradicted"], 1)


if __name__ == "__main__":
    unittest.main()
