#!/usr/bin/env python3
"""Golden report-context regression tests for recommendation summary behavior."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from stock_trading import presentation


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "golden_report_contexts"


EXPECTED = {
    "normal_decision_safe_buy.json": {
        "top_symbol": "MSFT",
        "top_action": "Add",
        "gate_status": "Ready",
        "safe_to_buy": True,
        "suggested_amount": 2500.0,
        "suggested_amount_text": "$2,500.00",
        "confidence": "Medium",
        "data_status": "Blended",
        "reasons": [],
    },
    "blocked_buy_candidate.json": {
        "top_symbol": "NVDA",
        "top_action": "Add blocked",
        "gate_status": "Blocked",
        "safe_to_buy": False,
        "suggested_amount": 0.0,
        "suggested_amount_text": "$0.00",
        "confidence": "Low",
        "data_status": "Wide range",
        "reasons": [
            "Low target confidence",
            "Wide target range",
            "Verification check is still open",
        ],
    },
    "missing_price_data.json": {
        "top_symbol": "ALAB",
        "top_action": "Add blocked",
        "gate_status": "Blocked",
        "safe_to_buy": False,
        "suggested_amount": 0.0,
        "suggested_amount_text": "$0.00",
        "confidence": "Medium",
        "data_status": "Needs price",
        "reasons": ["Needs price"],
    },
    "partial_target_blend.json": {
        "top_symbol": "SNOW",
        "top_action": "Add blocked",
        "gate_status": "Blocked",
        "safe_to_buy": False,
        "suggested_amount": 0.0,
        "suggested_amount_text": "$0.00",
        "confidence": "Low",
        "data_status": "Partial blend",
        "reasons": ["Low target confidence", "Partial target blend"],
    },
    "wide_target_range.json": {
        "top_symbol": "NVDA",
        "top_action": "Add blocked",
        "gate_status": "Blocked",
        "safe_to_buy": False,
        "suggested_amount": 0.0,
        "suggested_amount_text": "$0.00",
        "confidence": "Low",
        "data_status": "Wide range",
        "reasons": ["Low target confidence", "Wide target range"],
    },
}


class GoldenReportContextTests(unittest.TestCase):
    maxDiff = None

    def rendered_summary(self, fixture_name: str) -> dict[str, object]:
        context = presentation.load_report_context(FIXTURE_DIR / fixture_name)
        report_date = context["metadata"]["report_date"]
        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch("stock_trading.provider_client.fetch_json_url") as fetch_json_url,
                patch("scripts.generate_daily_report.score_stock") as score_stock,
            ):
                presentation.render_report_context(context, Path(tmpdir))

            fetch_json_url.assert_not_called()
            score_stock.assert_not_called()
            rendered_context = json.loads((Path(tmpdir) / f"report-context-{report_date}.json").read_text())
        return rendered_context["summary"]

    def assert_summary_matches(self, fixture_name: str) -> None:
        summary = self.rendered_summary(fixture_name)
        expected = EXPECTED[fixture_name]
        gate = summary["decision_gate"]

        self.assertEqual(summary["top_symbol"], expected["top_symbol"])
        self.assertEqual(summary["top_action"], expected["top_action"])
        self.assertEqual(gate["status"], expected["gate_status"])
        self.assertEqual(gate["safe_to_buy"], expected["safe_to_buy"])
        self.assertEqual(summary["suggested_amount"], expected["suggested_amount"])
        self.assertEqual(summary["suggested_amount_text"], expected["suggested_amount_text"])
        self.assertEqual(summary["confidence"], expected["confidence"])
        self.assertEqual(summary["data_status"], expected["data_status"])
        self.assertEqual(gate.get("reasons", []), expected["reasons"])

    def test_normal_decision_safe_buy_candidate(self) -> None:
        self.assert_summary_matches("normal_decision_safe_buy.json")

    def test_blocked_buy_candidate(self) -> None:
        self.assert_summary_matches("blocked_buy_candidate.json")

    def test_missing_price_data(self) -> None:
        self.assert_summary_matches("missing_price_data.json")

    def test_partial_target_blend(self) -> None:
        self.assert_summary_matches("partial_target_blend.json")

    def test_wide_target_range(self) -> None:
        self.assert_summary_matches("wide_target_range.json")


if __name__ == "__main__":
    unittest.main()
