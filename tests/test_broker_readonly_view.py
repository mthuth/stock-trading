#!/usr/bin/env python3
"""Tests for broker read-only context view model."""

from __future__ import annotations

import json
import unittest
from datetime import date
from pathlib import Path

from stock_trading.broker_readonly_view import (
    RECOMMENDATION_ONLY_NOTE,
    build_broker_readonly_view,
    mask_account_id,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "broker_readonly"
BANNED_ACTION_LANGUAGE = (
    "<button",
    "order ticket",
    "submit order",
    "submit a trade",
    "execute trade",
    "execute order",
    "buy now",
    "sell now",
    "broker write",
    "margin permission",
)


def load_fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text())


class BrokerReadonlyViewTests(unittest.TestCase):
    def test_broker_context_present(self) -> None:
        view = build_broker_readonly_view(
            load_fixture("broker_snapshot_present.json"),
            capital_availability={"available_amount": 2500, "source": "configured"},
            today=date(2026, 6, 1),
        )

        self.assertTrue(view["available"])
        self.assertEqual(view["status"], "available")
        self.assertEqual(view["account_count"], 2)
        self.assertEqual(view["position_count"], 5)
        self.assertEqual(view["cash_summary"]["total_cash"], 5000.0)
        self.assertEqual(view["cash_summary"]["buying_capacity"], 5000.0)
        self.assertEqual(view["data_source"], "fixture_broker_snapshot")
        self.assertEqual(view["as_of"], "2026-06-01T08:30:00")
        self.assertEqual(view["freshness_label"], "fresh")
        self.assertEqual(view["freshness_summary"]["source"], "fixture")
        self.assertEqual(view["freshness_summary"]["as_of"], "2026-06-01T08:30:00")
        self.assertEqual(view["freshness_summary"]["last_pulled_at"], "2026-06-01T08:30:00")
        labels = [row["label"] for row in view["freshness_summary"]["display_rows"]]
        self.assertIn("Holdings source", labels)
        self.assertIn("As of", labels)
        self.assertIn("Last pulled", labels)
        self.assertIn("Freshness", labels)
        self.assertIn("Read-only snapshot", labels)
        self.assertTrue(view["read_only"])
        self.assertTrue(view["no_order_capability"])
        self.assertEqual(view["recommendation_only_note"], RECOMMENDATION_ONLY_NOTE)

    def test_missing_snapshot_empty_state_uses_manual_config_fallback(self) -> None:
        view = build_broker_readonly_view(
            None,
            capital_availability={"available_amount": 2500, "source": "configured", "status": "available"},
            today=date(2026, 6, 1),
        )

        self.assertFalse(view["available"])
        self.assertEqual(view["status"], "missing_snapshot")
        self.assertEqual(view["account_count"], 0)
        self.assertEqual(view["position_count"], 0)
        self.assertEqual(view["freshness_label"], "missing")
        self.assertEqual(view["freshness_summary"]["freshness_label"], "missing")
        self.assertTrue(any("missing" in warning.lower() for warning in view["freshness_summary"]["warnings"]))
        self.assertIn("manual/config capital availability", view["empty_state"])
        self.assertEqual(view["cash_summary"]["manual_config_fallback"]["available_amount"], 2500.0)
        self.assertTrue(view["read_only"])
        self.assertTrue(view["no_order_capability"])

    def test_stale_snapshot_warning(self) -> None:
        view = build_broker_readonly_view(
            load_fixture("broker_snapshot_stale.json"),
            today=date(2026, 6, 1),
            stale_after_days=3,
        )

        self.assertEqual(view["status"], "stale")
        self.assertEqual(view["snapshot_age_days"], 12)
        self.assertEqual(view["freshness_label"], "stale")
        self.assertEqual(view["freshness_summary"]["age_days"], 12)
        self.assertTrue(any("stale" in warning.lower() for warning in view["warnings"]))

    def test_top_holdings_displayed_by_market_value(self) -> None:
        view = build_broker_readonly_view(load_fixture("broker_snapshot_present.json"), today=date(2026, 6, 1))
        holdings = view["top_holdings"]

        self.assertEqual([row["symbol"] for row in holdings[:3]], ["NVDA", "MSFT", "QQQM"])
        self.assertEqual(holdings[0]["market_value"], 12600.0)
        self.assertEqual(holdings[0]["market_value_text"], "$12,600.00")

    def test_concentration_warning(self) -> None:
        view = build_broker_readonly_view(
            load_fixture("broker_snapshot_present.json"),
            today=date(2026, 6, 1),
            concentration_threshold_pct=30.0,
        )

        self.assertTrue(any("NVDA" in warning for warning in view["concentration_warnings"]))
        self.assertTrue(any("review threshold" in warning for warning in view["concentration_warnings"]))

    def test_long_term_core_exposure_when_available(self) -> None:
        view = build_broker_readonly_view(load_fixture("broker_snapshot_present.json"), today=date(2026, 6, 1))
        exposure = view["long_term_core_exposure"]

        self.assertEqual(exposure["market_value"], 26500.0)
        self.assertEqual(exposure["market_value_text"], "$26,500.00")
        self.assertAlmostEqual(exposure["pct_of_total"], 77.26, places=2)

    def test_account_ids_masked(self) -> None:
        view = build_broker_readonly_view(load_fixture("broker_snapshot_present.json"), today=date(2026, 6, 1))
        labels = " ".join(view["masked_account_labels"])

        self.assertEqual(mask_account_id("FAKEIRA123456789"), "acct-****6789")
        self.assertIn("acct-****6789", labels)
        self.assertIn("acct-****4321", labels)
        self.assertNotIn("FAKEIRA123456789", labels)
        self.assertNotIn("FAKETAXABLE987654321", labels)

    def test_margin_like_fields_are_warning_only(self) -> None:
        view = build_broker_readonly_view(load_fixture("broker_snapshot_present.json"), today=date(2026, 6, 1))

        self.assertTrue(any("read-only context" in warning for warning in view["warnings"]))
        self.assertTrue(any("not trade permission" in warning for warning in view["warnings"]))

    def test_no_order_or_trade_action_language(self) -> None:
        view = build_broker_readonly_view(load_fixture("broker_snapshot_present.json"), today=date(2026, 6, 1))
        rendered = json.dumps(view, sort_keys=True).lower()

        for phrase in BANNED_ACTION_LANGUAGE:
            self.assertNotIn(phrase, rendered)
        self.assertIn("read-only", rendered)
        self.assertIn("recommendation-only", rendered)
        self.assertIn("does not place trades", rendered)


if __name__ == "__main__":
    unittest.main()
