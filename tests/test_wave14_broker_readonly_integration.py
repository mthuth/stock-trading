#!/usr/bin/env python3
"""Wave 14 broker read-only report/local-console integration tests."""

from __future__ import annotations

import json
import unittest
from datetime import date
from pathlib import Path

from stock_trading.broker_capital_availability import broker_capital_availability_context
from stock_trading.local_console import render_local_console
from stock_trading.local_console_panels import build_console_panels
from stock_trading.reporting.broker_readonly import build_broker_readonly_view
from stock_trading.reporting.renderers import render_broker_readonly, render_dashboard_html, render_markdown


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "broker_readonly"


def load_report_context() -> dict[str, object]:
    return json.loads((ROOT / "tests" / "fixtures" / "report_context.json").read_text())


def broker_section() -> dict[str, object]:
    return {
        "read_only": True,
        "no_order_capability": True,
        "recommendation_only": True,
        "note": "Read-only broker context supports manual capital and exposure review; official recommendations stay unchanged.",
        "snapshot_status": "available",
        "as_of": "2026-06-01T08:00:00",
        "last_pulled_at": "2026-06-01T08:05:00",
        "source": "broker_readonly",
        "snapshot_source": "fixture_broker_snapshot",
        "freshness_summary": {
            "source": "broker_readonly",
            "source_detail": "fixture_broker_snapshot",
            "as_of": "2026-06-01T08:00:00",
            "last_pulled_at": "2026-06-01T08:05:00",
            "freshness_label": "fresh",
            "warning": "",
            "read_only": True,
            "no_order_capability": True,
        },
        "account_count": 1,
        "masked_account_labels": ["retirement review account (acct-****-001)"],
        "cash_available": 2500.0,
        "cash_available_text": "$2,500.00",
        "positions_summary": {
            "position_count": 1,
            "total_market_value": 9000.0,
            "total_market_value_text": "$9,000.00",
            "top_holdings": [
                {
                    "symbol": "MSFT",
                    "company": "Microsoft",
                    "market_value": 9000.0,
                    "market_value_text": "$9,000.00",
                    "sleeve": "long_term_core",
                    "account_label": "retirement review account (acct-****-001)",
                }
            ],
        },
        "sleeve_exposure": {
            "rows": [
                {
                    "sleeve": "long_term_core",
                    "market_value": 9000.0,
                    "market_value_text": "$9,000.00",
                    "pct_of_holdings": 100.0,
                    "cap_pct": "",
                }
            ]
        },
        "concentration_cap_warnings": ["MSFT is above the review threshold."],
        "stale_missing_warnings": [],
        "warnings": [],
        "manual_config_fallback": {
            "fallback_used": False,
            "source": "configured",
            "status": "available",
            "available_amount": 2500.0,
            "available_amount_text": "$2,500.00",
        },
    }


class Wave14BrokerReadonlyIntegrationTests(unittest.TestCase):
    def test_broker_readonly_section_renders_masked_context(self) -> None:
        context = load_report_context()
        context["broker_readonly"] = broker_section()

        html = render_broker_readonly(context)

        self.assertIn("Broker Read-Only Context", html)
        self.assertIn("Holdings source", html)
        self.assertIn("Last pulled", html)
        self.assertIn("Freshness", html)
        self.assertIn("Read-only snapshot", html)
        self.assertIn("acct-****-001", html)
        self.assertIn("$2,500.00", html)
        self.assertIn("Top Broker-Reported Positions", html)
        self.assertNotIn("123456789", html)
        lower = html.lower()
        for phrase in ("place order", "preview order", "execute trade", "buy now", "sell now"):
            self.assertNotIn(phrase, lower)

    def test_dashboard_and_markdown_place_broker_context_near_capital_deployment(self) -> None:
        context = load_report_context()
        context["broker_readonly"] = broker_section()

        dashboard = render_dashboard_html(context)
        markdown = render_markdown(context)

        self.assertLess(dashboard.index("Long-Term Capital Deployment Review"), dashboard.index("Broker Read-Only Context"))
        self.assertLess(dashboard.index("Broker Read-Only Context"), dashboard.index("Earnings Review"))
        self.assertIn("## Broker Read-Only Context", markdown)
        self.assertLess(markdown.index("## Long-Term Capital Deployment Review"), markdown.index("## Broker Read-Only Context"))
        self.assertLess(markdown.index("## Broker Read-Only Context"), markdown.index("## Earnings Review"))

    def test_capital_availability_uses_fresh_cash_and_ignores_buying_power_for_cash(self) -> None:
        snapshot = {
            "source": "broker_readonly",
            "status": "available",
            "as_of": "2026-06-01T08:00:00",
            "cash_available": 1200.0,
            "buying_power": 9000.0,
            "read_only": True,
            "no_order_capability": True,
        }

        context = broker_capital_availability_context(
            snapshot,
            {"capital_availability": {"monthly_buy_capacity": 2500, "source": "configured"}},
            today=date(2026, 6, 1),
        )

        self.assertEqual(context["source"], "broker_readonly")
        self.assertEqual(context["available_amount"], 1200.0)
        self.assertEqual(context["broker_cash_context"]["buying_power"]["buying_power"], 9000.0)
        self.assertIn("Buying power", " ".join(context["warnings"]))

    def test_stale_or_missing_snapshot_falls_back_to_manual_config(self) -> None:
        stale = {
            "source": "broker_readonly",
            "status": "available",
            "as_of": "2026-05-01T08:00:00",
            "cash_available": 1200.0,
            "read_only": True,
            "no_order_capability": True,
        }
        config = {"capital_availability": {"monthly_buy_capacity": 2500, "source": "configured"}}

        stale_context = broker_capital_availability_context(stale, config, today=date(2026, 6, 1))
        missing_context = broker_capital_availability_context(None, config, today=date(2026, 6, 1))

        self.assertEqual(stale_context["source"], "configured")
        self.assertEqual(stale_context["available_amount"], 2500.0)
        self.assertIn("old", " ".join(stale_context["warnings"]))
        self.assertEqual(missing_context["source"], "configured")
        self.assertEqual(missing_context["available_amount"], 2500.0)

    def test_missing_broker_view_is_graceful(self) -> None:
        view = build_broker_readonly_view({"broker_readonly": {}})

        self.assertEqual(view["cards"][0]["value"], "missing")
        self.assertIn("No masked broker account labels", view["accounts"]["empty_state"])

    def test_local_console_places_broker_panel_after_capital_deployment(self) -> None:
        context = load_report_context()
        context["broker_readonly"] = broker_section()
        panels = build_console_panels(context, artifacts={}, runs={})
        manifest = {
            "generated_at": "2026-06-01T08:00:00",
            "guardrails": ["Recommendation-only decision support."],
            "report_context": {"report_date": "2026-06-01"},
            "panels": panels,
            "artifacts": {},
            "run_history": {},
            "workflow": {},
        }

        html = render_local_console(manifest)

        self.assertIn("broker_readonly", panels)
        self.assertLess(html.index("Long-Term Capital Deployment"), html.index("Broker Read-Only Context"))
        self.assertLess(html.index("Broker Read-Only Context"), html.index("Earnings Review"))

    def test_fixture_snapshot_contains_no_live_call_marker(self) -> None:
        snapshot = json.loads((FIXTURES / "sample_snapshot.json").read_text())

        self.assertNotIn("broker_api_called", snapshot)
        self.assertTrue(snapshot["accounts"])


if __name__ == "__main__":
    unittest.main()
