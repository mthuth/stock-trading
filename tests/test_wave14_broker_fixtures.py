#!/usr/bin/env python3
"""Wave 14 broker read-only fixture contracts."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "broker_readonly"


EXPECTED_SCENARIOS = {
    "account_with_cash_and_positions": "Account with cash and positions",
    "no_cash_available": "No cash available",
    "stale_broker_snapshot": "Stale broker snapshot",
    "missing_broker_snapshot": "Missing broker snapshot",
    "holding_exceeds_single_stock_cap": "Holding exceeds single-stock cap",
    "holding_below_target_sleeve": "Holding below target sleeve",
    "unknown_cost_basis": "Unknown cost basis",
    "masked_account_identifiers": "Masked account identifiers",
    "multiple_accounts": "Multiple accounts",
    "broker_unavailable_error": "Broker unavailable/error",
    "margin_buying_power_context_only": "Margin/buying-power field present but treated as context-only",
    "manual_config_fallback_used": "No broker data, manual/config capital availability fallback used",
}

SNAPSHOT_STATUSES = {"available", "stale", "missing", "error", "unavailable"}
CAPITAL_SOURCES = {"broker_read_only_snapshot", "manual_config_fallback", "configured"}
COST_BASIS_STATUSES = {"available", "unknown", "not_applicable"}

REQUIRED_GUARDRAILS = {
    "no_automatic_trading",
    "no_order_preview",
    "no_order_placement",
    "no_order_modification",
    "no_order_cancellation",
    "no_broker_write_actions",
    "no_margin_day_trading_compliance_engine",
    "no_options_short_execution",
    "no_live_broker_calls_in_tests",
    "no_real_credentials_in_repo",
    "no_automatic_score_changes_from_broker_data",
    "no_automatic_target_changes_from_broker_data",
    "no_automatic_recommendation_changes_from_broker_data",
    "no_automatic_decision_safety_changes_from_broker_data",
    "no_automatic_source_weight_changes_from_broker_data",
    "no_automatic_model_tuning_from_broker_data",
}

ACCOUNT_FIELDS = {
    "account_id_masked",
    "account_label",
    "account_type",
    "broker_name",
    "snapshot_at",
    "source",
    "source_status",
    "currency",
    "total_market_value",
    "cash_available",
    "buying_capacity",
    "read_only",
    "warnings",
}

POSITION_FIELDS = {
    "account_id_masked",
    "symbol",
    "company",
    "quantity",
    "market_value",
    "last_price",
    "sleeve",
    "position_pct",
    "cost_basis",
    "cost_basis_status",
    "source",
    "snapshot_at",
    "warnings",
}

FORBIDDEN_SUBSTRINGS = (
    "oauth",
    "refresh_token",
    "session_token",
    "access_token",
    "consumer_secret",
    "private_key",
    "password",
    "ssn",
)


def load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURE_DIR / f"{name}.json").read_text())


def iter_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        strings: list[str] = []
        for nested in value.values():
            strings.extend(iter_strings(nested))
        return strings
    if isinstance(value, list):
        strings = []
        for nested in value:
            strings.extend(iter_strings(nested))
        return strings
    return []


class Wave14BrokerReadonlyFixtureTests(unittest.TestCase):
    maxDiff = None

    def test_expected_fixture_set_exists(self) -> None:
        fixture_ids = {
            path.stem
            for path in FIXTURE_DIR.glob("*.json")
            if path.stem in EXPECTED_SCENARIOS
        }

        self.assertEqual(fixture_ids, set(EXPECTED_SCENARIOS))

    def test_common_fixture_contract(self) -> None:
        for scenario_id, scenario_label in EXPECTED_SCENARIOS.items():
            with self.subTest(scenario_id=scenario_id):
                fixture = load_fixture(scenario_id)

                self.assertEqual(fixture["scenario_id"], scenario_id)
                self.assertEqual(fixture["scenario_label"], scenario_label)
                self.assertEqual(fixture["broker_layer"], "broker_readonly")
                self.assertIs(fixture["review_only"], True)
                self.assertIs(fixture["recommendation_only"], True)
                self.assertIs(fixture["read_only"], True)
                self.assertIs(fixture["official_recommendation_unchanged"], True)

                sync = fixture["sync_status"]
                self.assertIn(sync["status"], SNAPSHOT_STATUSES)
                self.assertIn("snapshot_at", sync)
                self.assertIn("last_success_at", sync)
                self.assertIn("stale_after_hours", sync)
                self.assertIsInstance(sync["warnings"], list)
                self.assertIsInstance(sync["fallback_used"], bool)

                for account in fixture["accounts"]:
                    self.assertEqual(set(account), ACCOUNT_FIELDS)
                    self.assertRegex(account["account_id_masked"], r"^acct-\*{4}-[0-9]{3}$")
                    self.assertIn(account["source_status"], SNAPSHOT_STATUSES)
                    self.assertIs(account["read_only"], True)
                    self.assertIsInstance(account["warnings"], list)

                for position in fixture["positions"]:
                    self.assertEqual(set(position), POSITION_FIELDS)
                    self.assertRegex(position["account_id_masked"], r"^acct-\*{4}-[0-9]{3}$")
                    self.assertIn(position["cost_basis_status"], COST_BASIS_STATUSES)
                    self.assertIsInstance(position["warnings"], list)

                cash = fixture["cash_context"]
                self.assertIn(cash["source"], CAPITAL_SOURCES)
                self.assertIsInstance(cash["manual_config_fallback_used"], bool)
                self.assertIsInstance(cash["warnings"], list)
                self.assertIsInstance(cash["context_only_fields"], list)

                allocation = fixture["allocation_context"]
                self.assertIn("account_value", allocation)
                self.assertIsInstance(allocation["sleeves"], list)
                self.assertIsInstance(allocation["cap_warnings"], list)

                expected = fixture["expected_behavior"]
                self.assertIn("capital_review_result", expected)
                self.assertIsInstance(expected["scenario_assertions"], list)
                self.assertIn("official_recommendation_unchanged", expected["scenario_assertions"])

                guardrails = fixture["guardrails"]
                self.assertEqual(set(guardrails), REQUIRED_GUARDRAILS)
                for value in guardrails.values():
                    self.assertIs(value, True)

    def test_fixture_statuses_cover_required_states(self) -> None:
        statuses = {load_fixture(scenario_id)["sync_status"]["status"] for scenario_id in EXPECTED_SCENARIOS}

        self.assertTrue(SNAPSHOT_STATUSES.issubset(statuses))

    def test_fixture_ids_are_masked_and_no_sensitive_values_appear(self) -> None:
        unmasked_long_digits = re.compile(r"\b\d{6,}\b")
        for scenario_id in EXPECTED_SCENARIOS:
            with self.subTest(scenario_id=scenario_id):
                fixture = load_fixture(scenario_id)
                strings = [value.lower() for value in iter_strings(fixture)]

                for value in strings:
                    self.assertIsNone(unmasked_long_digits.search(value), value)
                    for forbidden in FORBIDDEN_SUBSTRINGS:
                        self.assertNotIn(forbidden, value)

    def test_missing_and_error_cases_use_manual_config_fallback(self) -> None:
        missing = load_fixture("missing_broker_snapshot")
        error = load_fixture("broker_unavailable_error")
        fallback = load_fixture("manual_config_fallback_used")

        for fixture in (missing, error, fallback):
            self.assertTrue(fixture["sync_status"]["fallback_used"])
            self.assertTrue(fixture["cash_context"]["manual_config_fallback_used"])
            self.assertIn("manual_config_fallback", fixture["expected_behavior"]["scenario_assertions"])

    def test_stale_snapshot_warns_without_inventing_current_data(self) -> None:
        fixture = load_fixture("stale_broker_snapshot")

        self.assertEqual(fixture["sync_status"]["status"], "stale")
        self.assertIn("broker_snapshot_stale", fixture["sync_status"]["warnings"])
        self.assertIn("stale_snapshot_warning", fixture["expected_behavior"]["scenario_assertions"])

    def test_cap_and_sleeve_context_remain_review_only(self) -> None:
        single_stock = load_fixture("holding_exceeds_single_stock_cap")
        sleeve = load_fixture("holding_below_target_sleeve")

        self.assertIn("single_stock_cap_exceeded", single_stock["allocation_context"]["cap_warnings"])
        self.assertIn("sleeve_below_target", sleeve["allocation_context"]["cap_warnings"])
        self.assertIn("allocation_context_only", single_stock["expected_behavior"]["scenario_assertions"])
        self.assertIn("allocation_context_only", sleeve["expected_behavior"]["scenario_assertions"])

    def test_unknown_cost_basis_is_explicit(self) -> None:
        fixture = load_fixture("unknown_cost_basis")
        unknown = next(position for position in fixture["positions"] if position["cost_basis_status"] == "unknown")

        self.assertIsNone(unknown["cost_basis"])
        self.assertIn("cost_basis_unknown", unknown["warnings"])
        self.assertIn("cost_basis_not_inferred", fixture["expected_behavior"]["scenario_assertions"])

    def test_margin_buying_power_is_context_only(self) -> None:
        fixture = load_fixture("margin_buying_power_context_only")

        self.assertIn("margin_buying_power", fixture["cash_context"]["context_only_fields"])
        self.assertIn("margin_context_only", fixture["cash_context"]["warnings"])
        self.assertTrue(fixture["guardrails"]["no_margin_day_trading_compliance_engine"])
        self.assertIn("margin_not_trade_permission", fixture["expected_behavior"]["scenario_assertions"])

    def test_no_fixture_enables_broker_writes_or_order_language(self) -> None:
        forbidden_phrases = ("place order", "preview order", "modify order", "cancel order", "execute trade")
        for scenario_id in EXPECTED_SCENARIOS:
            with self.subTest(scenario_id=scenario_id):
                fixture = load_fixture(scenario_id)
                serialized = json.dumps(fixture).lower()

                for phrase in forbidden_phrases:
                    self.assertNotIn(phrase, serialized)
                self.assertTrue(fixture["guardrails"]["no_broker_write_actions"])
                self.assertTrue(fixture["guardrails"]["no_order_preview"])
                self.assertTrue(fixture["guardrails"]["no_live_broker_calls_in_tests"])


if __name__ == "__main__":
    unittest.main()
