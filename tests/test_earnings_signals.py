#!/usr/bin/env python3
"""Regression tests for deterministic review-only earnings signals."""

from __future__ import annotations

import ast
import copy
import unittest
from pathlib import Path

from stock_trading.earnings_signals import (
    SIGNAL_TYPES,
    extract_earnings_signals,
    extract_earnings_signals_for_row,
    summarize_earnings_signals,
)


ROOT = Path(__file__).resolve().parents[1]


def evidence(text: str, **overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "symbol": "MSFT",
        "evidence_type": "earnings_release",
        "source_name": "Fixture Earnings",
        "source_type": "official_ir",
        "title": "Quarterly earnings update",
        "summary": text,
        "confidence": "medium",
        "corroboration_label": "primary_plus_confirmed",
    }
    row.update(overrides)
    return row


def only_signal_type(row: dict[str, object]) -> str:
    signals = [signal for signal in extract_earnings_signals_for_row(row) if signal["signal_type"] != "data_insufficient"]
    if len(signals) != 1:
        raise AssertionError(f"expected one signal, got {signals}")
    return str(signals[0]["signal_type"])


class EarningsSignalsTests(unittest.TestCase):
    def test_signal_vocabulary_includes_required_types(self) -> None:
        self.assertEqual(
            SIGNAL_TYPES,
            {
                "eps_beat",
                "eps_miss",
                "revenue_beat",
                "revenue_miss",
                "guidance_raise",
                "guidance_cut",
                "margin_expansion",
                "margin_pressure",
                "ai_demand_strength",
                "capex_risk",
                "customer_growth",
                "churn_or_demand_risk",
                "cybersecurity_or_operational_risk",
                "valuation_risk",
                "data_insufficient",
            },
        )

    def test_eps_beat_signal(self) -> None:
        row = evidence("Adjusted EPS beat consensus expectations and management said demand remained healthy.")

        signal = extract_earnings_signals_for_row(row)[0]

        self.assertEqual(signal["signal_type"], "eps_beat")
        self.assertEqual(signal["signal_direction"], "positive")
        self.assertTrue(signal["review_only"])
        self.assertEqual(signal["recommendation_impact"], "none")

    def test_eps_miss_signal(self) -> None:
        row = evidence("Quarterly EPS missed consensus and fell short of the prior forecast.")

        signal = extract_earnings_signals_for_row(row)[0]

        self.assertEqual(signal["signal_type"], "eps_miss")
        self.assertEqual(signal["signal_direction"], "negative")

    def test_revenue_beat_signal(self) -> None:
        row = evidence("Revenue exceeded analyst estimates as cloud adoption improved.")

        self.assertEqual(only_signal_type(row), "revenue_beat")

    def test_guidance_raise_signal(self) -> None:
        row = evidence("Management raised full-year guidance after a stronger-than-expected quarter.")

        self.assertEqual(only_signal_type(row), "guidance_raise")

    def test_guidance_cut_signal(self) -> None:
        row = evidence("The company lowered its full-year outlook and guidance is now below prior expectations.")

        signal = extract_earnings_signals_for_row(row)[0]

        self.assertEqual(signal["signal_type"], "guidance_cut")
        self.assertEqual(signal["signal_direction"], "negative")

    def test_margin_pressure_signal(self) -> None:
        row = evidence("Operating margins declined as discounting and infrastructure costs created pressure.")

        self.assertEqual(only_signal_type(row), "margin_pressure")

    def test_ai_demand_strength_signal(self) -> None:
        row = evidence("Management cited strong AI demand and record GPU orders during the earnings call.")

        signal = extract_earnings_signals_for_row(row)[0]

        self.assertEqual(signal["signal_type"], "ai_demand_strength")
        self.assertEqual(signal["signal_direction"], "positive")

    def test_capex_risk_signal(self) -> None:
        row = evidence("Capital expenditures are expected to remain elevated, creating capex risk for free cash flow.")

        signal = extract_earnings_signals_for_row(row)[0]

        self.assertEqual(signal["signal_type"], "capex_risk")
        self.assertEqual(signal["signal_direction"], "negative")

    def test_mixed_signals_are_summarized_without_new_recommendation_label(self) -> None:
        row = evidence("EPS beat expectations, but management cut guidance due to softer enterprise demand.")

        signals = extract_earnings_signals_for_row(row)
        summary = summarize_earnings_signals(signals)

        self.assertIn("eps_beat", {signal["signal_type"] for signal in signals})
        self.assertIn("guidance_cut", {signal["signal_type"] for signal in signals})
        self.assertEqual(summary["overall_direction"], "mixed")
        self.assertEqual(summary["recommendation_impact"], "none")

    def test_no_signal_returns_data_insufficient_for_earnings_text(self) -> None:
        row = evidence("The earnings call transcript repeated previously announced product details.")

        signals = extract_earnings_signals_for_row(row)

        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["signal_type"], "data_insufficient")
        self.assertEqual(signals[0]["signal_direction"], "unknown")

    def test_no_earnings_rows_returns_data_insufficient_collection_signal(self) -> None:
        signals = extract_earnings_signals(
            [
                {
                    "symbol": "MSFT",
                    "evidence_type": "product_launch",
                    "summary": "A normal product launch update about developer tooling.",
                }
            ]
        )

        self.assertEqual(signals[0]["signal_type"], "data_insufficient")
        self.assertEqual(signals[0]["confidence"], 0.0)

    def test_recommendation_context_is_not_mutated(self) -> None:
        recommendation = {
            "symbol": "NVDA",
            "action": "Add",
            "score": 84.2,
            "target_price": 160.0,
            "decision_safety": {"safe_to_buy": True},
        }
        row = evidence(
            "Revenue beat expectations and AI demand remained strong.",
            symbol="NVDA",
            recommendation_context=recommendation,
        )
        before = copy.deepcopy(row)

        signals = extract_earnings_signals_for_row(row)

        self.assertEqual(row, before)
        self.assertEqual(recommendation["action"], "Add")
        self.assertTrue(all(signal["score_impact"] == "none" for signal in signals))
        self.assertTrue(all(signal["target_impact"] == "none" for signal in signals))

    def test_extraction_is_deterministic(self) -> None:
        rows = [
            evidence("Revenue beat expectations and management raised guidance.", symbol="AMZN"),
            evidence("Operating margins declined and capex risk remains elevated.", symbol="META"),
        ]

        self.assertEqual(extract_earnings_signals(rows), extract_earnings_signals(rows))

    def test_no_provider_or_model_imports(self) -> None:
        tree = ast.parse((ROOT / "stock_trading" / "earnings_signals.py").read_text())
        forbidden = {
            "openai",
            "urllib",
            "requests",
            "stock_trading.provider_client",
            "stock_trading.analysis_engine",
            "stock_trading.analysis_scoring",
        }
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)

        self.assertFalse(imports & forbidden)


if __name__ == "__main__":
    unittest.main()
