#!/usr/bin/env python3
"""Tests for review-only tactical risk zones."""

from __future__ import annotations

import copy
import unittest

from stock_trading import tactical_risk as subject


def risk_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "symbol": "MSFT",
        "tactical_horizon": "same_week",
        "setup_label": "pullback",
        "current_price": 101.0,
        "support_estimate": 100.0,
        "resistance_estimate": 110.0,
        "moving_average_context": {"ma20": 102.0, "ma50": 99.0},
        "recent_volatility_pct": 2.5,
        "price_history_quality": {"status": "available", "history_days": 60},
    }
    row.update(overrides)
    return row


class TacticalRiskTests(unittest.TestCase):
    def test_favorable_review_zone_near_support(self) -> None:
        result = subject.tactical_risk_zone(**risk_row())

        self.assertEqual(result["symbol"], "MSFT")
        self.assertEqual(result["tactical_horizon"], "same_week")
        self.assertEqual(result["risk_zone_label"], "favorable_review_zone")
        self.assertEqual(result["support_reference"], 100.0)
        self.assertEqual(result["resistance_reference"], 110.0)
        self.assertIn("Closes below support reference", result["invalidation_condition"])
        self.assertTrue(result["review_only"])
        self.assertIn("No order preview", result["no_order_preview_note"])

    def test_extended_chase_risk_above_resistance(self) -> None:
        result = subject.tactical_risk_zone(
            **risk_row(
                setup_label="breakout",
                current_price=115.0,
                support_estimate=100.0,
                resistance_estimate=110.0,
            )
        )

        self.assertEqual(result["risk_zone_label"], "extended_chase_risk")
        self.assertIn("breakout confirmation", result["invalidation_condition"])

    def test_support_break_risk_below_support(self) -> None:
        result = subject.tactical_risk_zone(
            **risk_row(
                current_price=98.0,
                support_estimate=100.0,
                resistance_estimate=110.0,
            )
        )

        self.assertEqual(result["risk_zone_label"], "support_break_risk")
        self.assertEqual(result["invalidation_condition"], "Closes below support reference or support fails to recover.")

    def test_high_volatility_event_risk(self) -> None:
        result = subject.tactical_risk_zone(
            **risk_row(
                setup_label="news_catalyst",
                current_price=104.0,
                recent_volatility_pct=7.5,
            )
        )

        self.assertEqual(result["risk_zone_label"], "high_volatility_event_risk")
        self.assertEqual(result["volatility_context"]["label"], "high")
        self.assertTrue(any("volatility" in note.lower() for note in result["notes"]))

    def test_insufficient_price_history(self) -> None:
        result = subject.tactical_risk_zone(
            **risk_row(
                price_history_quality={"status": "thin", "history_days": 8},
            )
        )

        self.assertEqual(result["risk_zone_label"], "data_insufficient")
        self.assertEqual(result["data_quality"], "insufficient")
        self.assertIn("Provider data insufficient", result["invalidation_condition"])
        self.assertTrue(any("8 day" in note for note in result["notes"]))

    def test_earnings_event_risk(self) -> None:
        result = subject.tactical_risk_zone(
            **risk_row(
                current_price=101.0,
                recent_volatility_pct=2.5,
                earnings_event={"event_type": "earnings", "days_to_event": 2},
            )
        )

        self.assertEqual(result["risk_zone_label"], "high_volatility_event_risk")
        self.assertIn("Earnings/guidance", result["invalidation_condition"])
        self.assertTrue(any("earnings within 2 day" in note for note in result["notes"]))

    def test_neutral_when_not_near_support_or_extended(self) -> None:
        result = subject.tactical_risk_zone(
            **risk_row(
                current_price=105.0,
                support_estimate=100.0,
                resistance_estimate=112.0,
                recent_volatility_pct=3.0,
            )
        )

        self.assertEqual(result["risk_zone_label"], "neutral")
        self.assertIn("review-only", result["invalidation_condition"])

    def test_no_order_preview_language_or_trading_instruction(self) -> None:
        result = subject.tactical_risk_zone(**risk_row())
        payload = " ".join(
            [
                result["invalidation_condition"],
                result["no_order_preview_note"],
                result["recommendation_only_note"],
                *result["notes"],
            ]
        ).lower()

        self.assertNotIn("stop-loss", payload)
        self.assertNotIn("limit order", payload)
        self.assertNotIn("place trade", payload)
        self.assertNotIn("order-entry", payload)
        self.assertNotIn("buy at", payload)

    def test_no_input_mutation(self) -> None:
        row = risk_row(
            moving_average_context={"ma20": 102.0, "ma50": 99.0},
            notes=["fixture note"],
        )
        before = copy.deepcopy(row)

        subject.tactical_risk_zones([row])

        self.assertEqual(row, before)

    def test_batch_is_deterministic_and_scoped_to_tactical_context(self) -> None:
        rows = subject.tactical_risk_zones(
            [
                risk_row(symbol="NVDA", tactical_horizon="same_day", setup_label="momentum"),
                risk_row(symbol="MSFT", tactical_horizon="same_month", setup_label="pullback"),
            ]
        )

        self.assertEqual([row["symbol"] for row in rows], ["MSFT", "NVDA"])
        self.assertTrue(all(row["review_only"] for row in rows))
        self.assertTrue(all(row["tactical_horizon"] in subject.TACTICAL_HORIZONS for row in rows))


if __name__ == "__main__":
    unittest.main()
