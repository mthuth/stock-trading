#!/usr/bin/env python3
"""Tests for review-only prediction record helpers."""

from __future__ import annotations

import copy
import json
import unittest

from stock_trading import prediction_records as subject


CREATED_AT = "2026-05-31T12:00:00"


def prediction_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "created_at": CREATED_AT,
        "recommendation_run_id": 101,
        "report_date": "2026-05-31",
        "symbol": "NVDA",
        "company": "NVIDIA",
        "model_name": "daily_report_rules",
        "model_version": "daily-report-rules-v1",
        "model_role": "official",
        "decision_mode": "long_term_buy_add",
        "horizon": "12_months",
        "expected_direction": "up",
        "expected_return_low": 4.0,
        "expected_return_high": 18.0,
        "confidence": "medium",
        "thesis": "AI platform demand and target context support review.",
        "risks": ["Valuation risk", "Provider gaps could weaken confidence."],
        "invalidation_conditions": ["Target confidence falls to needs review."],
        "source_refs": [{"source_name": "SEC", "source_table": "source_depth"}],
        "decision_gate_status": "Ready",
        "target_confidence": "Medium",
    }
    row.update(overrides)
    return row


class PredictionRecordTests(unittest.TestCase):
    def assert_review_only_record(self, record: dict[str, object]) -> None:
        self.assertTrue(record["review_only"])
        self.assertIn("Review-only", record["recommendation_only_note"])
        self.assertIn("must not automatically change scores", record["recommendation_only_note"])
        self.assertTrue(record["prediction_id"].startswith("pred_"))
        json.dumps(record, sort_keys=True)

    def test_valid_long_term_prediction_from_recommendation(self) -> None:
        recommendation = {
            "report_date": "2026-05-31",
            "symbol": "NVDA",
            "company": "NVIDIA",
            "current_price": 100.0,
            "target_price": 125.0,
            "upside_pct": 25.0,
            "confidence": "Medium",
            "rationale": "Score and target context support long-term review.",
            "decision_gate_status": "Ready",
        }

        record = subject.prediction_from_recommendation(
            recommendation,
            model_name="daily_report_rules",
            model_version="daily-report-rules-v1",
            recommendation_run_id=42,
            created_at=CREATED_AT,
        )

        self.assertEqual(record["symbol"], "NVDA")
        self.assertEqual(record["model_role"], "official")
        self.assertEqual(record["decision_mode"], "long_term_buy_add")
        self.assertEqual(record["horizon"], "12_months")
        self.assertEqual(record["expected_direction"], "up")
        self.assertEqual(record["recommendation_run_id"], 42)
        self.assertTrue(subject.validate_prediction_record(record)["ok"])
        self.assert_review_only_record(record)

    def test_valid_tactical_prediction(self) -> None:
        record = subject.normalize_prediction_record(
            prediction_row(
                model_name="tactical_setup_rules",
                model_version="tactical-setup-v1",
                model_role="tactical",
                decision_mode="tactical_trade",
                horizon="5_trading_days",
                expected_return_low=-3.0,
                expected_return_high=7.0,
                thesis="Breakout review has short-term follow-through potential.",
                risks=["Breakout failure", "Provider gap"],
            )
        )

        self.assertTrue(subject.validate_prediction_record(record)["ok"])
        self.assertEqual(record["model_role"], "tactical")
        self.assertEqual(record["decision_mode"], "tactical_trade")
        self.assertEqual(record["horizon"], "5_trading_days")
        self.assert_review_only_record(record)

    def test_ai_thesis_prediction_from_packet(self) -> None:
        packet = {
            "report_date": "2026-05-31",
            "symbol": "MSFT",
            "company": "Microsoft",
            "target_context": {"upside_pct": 14.0, "confidence": "Medium"},
            "decision_safety": {"status": "Ready"},
            "what_would_change_the_view": "Fresh evidence contradicting AI demand would change the view.",
            "bear_risk_evidence": [{"summary": "Valuation risk remains."}],
            "source_attribution": [{"source_name": "SEC", "source_table": "source_depth"}],
        }

        record = subject.prediction_from_ai_packet(
            packet,
            model_name="llm_research_briefs",
            model_version="llm-research-briefs-v1",
            created_at=CREATED_AT,
        )

        self.assertEqual(record["model_role"], "ai_brief")
        self.assertEqual(record["symbol"], "MSFT")
        self.assertEqual(record["expected_direction"], "up")
        self.assertEqual(record["decision_gate_status"], "Ready")
        self.assertTrue(subject.validate_prediction_record(record)["ok"])
        self.assert_review_only_record(record)

    def test_missing_model_version_is_invalid(self) -> None:
        result = subject.validate_prediction_record(prediction_row(model_version=""))

        self.assertFalse(result["ok"])
        self.assertIn("model_version", {error["path"] for error in result["errors"]})

    def test_invalid_horizon_is_invalid(self) -> None:
        result = subject.validate_prediction_record(prediction_row(horizon="3_days"))

        self.assertFalse(result["ok"])
        self.assertIn("horizon", {error["path"] for error in result["errors"]})

    def test_invalid_decision_mode_is_invalid(self) -> None:
        result = subject.validate_prediction_record(prediction_row(decision_mode="day_trading_bot"))

        self.assertFalse(result["ok"])
        self.assertIn("decision_mode", {error["path"] for error in result["errors"]})

    def test_prediction_id_is_deterministic(self) -> None:
        first = subject.normalize_prediction_record(prediction_row())
        second = subject.normalize_prediction_record(prediction_row())

        self.assertEqual(first["prediction_id"], second["prediction_id"])

    def test_expected_return_range_must_be_ordered(self) -> None:
        result = subject.validate_prediction_record(
            prediction_row(expected_return_low=10.0, expected_return_high=2.0)
        )

        self.assertFalse(result["ok"])
        self.assertIn("expected_return_low", {error["path"] for error in result["errors"]})

    def test_record_set_is_deterministic_and_review_only(self) -> None:
        records = subject.build_prediction_record_set(
            [
                prediction_row(symbol="MSFT", horizon="5_trading_days", model_role="tactical", decision_mode="tactical_trade"),
                prediction_row(symbol="NVDA"),
            ]
        )

        self.assertTrue(records["review_only"])
        self.assertEqual(records["prediction_count"], 2)
        self.assertTrue(records["validation"]["ok"])
        self.assertEqual([row["symbol"] for row in records["predictions"]], ["MSFT", "NVDA"])

    def test_no_input_mutation(self) -> None:
        record = prediction_row(risks=["Valuation risk"], source_refs=[{"source": "fixture"}])
        before = copy.deepcopy(record)

        subject.normalize_prediction_record(record)
        subject.validate_prediction_record(record)

        self.assertEqual(record, before)


if __name__ == "__main__":
    unittest.main()
