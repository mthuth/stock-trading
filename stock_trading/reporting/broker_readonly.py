"""Presentation helpers for read-only broker context."""

from __future__ import annotations

from typing import Any


NOTE = (
    "Read-only broker context supports manual capital and exposure review; "
    "official recommendations stay unchanged."
)


def as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: object) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def text(value: object, default: str = "") -> str:
    if value is None or value == "":
        return default
    return str(value)


def money(value: object) -> str:
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return "n/a"


def broker_table(headers: list[str], rows: list[list[object]], empty_state: str) -> dict[str, object]:
    return {"headers": headers, "rows": rows, "empty_state": empty_state}


def build_broker_readonly_view(context: dict[str, object]) -> dict[str, object]:
    broker = as_dict(context.get("broker_readonly"))
    if not broker:
        broker = {
            "read_only": True,
            "no_order_capability": True,
            "snapshot_status": "missing",
            "source": "manual_config_fallback",
            "note": NOTE,
            "manual_config_fallback": {"fallback_used": True, "status": "needs_manual_update"},
        }
    positions = as_dict(broker.get("positions_summary"))
    fallback = as_dict(broker.get("manual_config_fallback"))
    account_labels = [text(item) for item in as_list(broker.get("masked_account_labels")) if text(item)]
    sleeve_rows = [
        [
            item.get("sleeve", ""),
            item.get("market_value_text") or money(item.get("market_value")),
            item.get("pct_of_holdings", ""),
            item.get("cap_pct", ""),
        ]
        for item in (as_dict(row) for row in as_list(as_dict(broker.get("sleeve_exposure")).get("rows")))
    ]
    top_holding_rows = [
        [
            item.get("symbol", ""),
            item.get("company", ""),
            item.get("market_value_text") or money(item.get("market_value")),
            item.get("sleeve", ""),
            item.get("account_label", ""),
        ]
        for item in (as_dict(row) for row in as_list(positions.get("top_holdings")))
    ]
    return {
        "read_only": broker.get("read_only", True),
        "no_order_capability": broker.get("no_order_capability", True),
        "note": text(broker.get("note"), NOTE),
        "cards": [
            {
                "label": "Snapshot status",
                "value": text(broker.get("snapshot_status"), "missing"),
                "detail": f"Source: {text(broker.get('source'), 'manual_config_fallback')}; as of {text(broker.get('as_of'), 'n/a')}.",
            },
            {
                "label": "Accounts",
                "value": text(broker.get("account_count"), "0"),
                "detail": ", ".join(account_labels[:3]) or "No masked account labels available.",
            },
            {
                "label": "Cash available",
                "value": text(broker.get("cash_available_text")) or money(broker.get("cash_available")),
                "detail": "Cash is read from a fresh snapshot only; otherwise manual/config fallback remains in use.",
            },
            {
                "label": "Positions",
                "value": text(positions.get("position_count"), "0"),
                "detail": f"Market value: {text(positions.get('total_market_value_text')) or money(positions.get('total_market_value'))}.",
            },
            {
                "label": "Manual/config fallback",
                "value": "Used" if fallback.get("fallback_used") else "Not used",
                "detail": f"Fallback source: {text(fallback.get('source'), 'manual_or_config')}; status: {text(fallback.get('status'), 'unknown')}.",
            },
            {
                "label": "Write capability",
                "value": "Disabled",
                "detail": "This section is read-only and recommendation-only.",
            },
        ],
        "accounts": broker_table(
            ["Masked Account Label"],
            [[label] for label in account_labels],
            "No masked broker account labels are available.",
        ),
        "positions": broker_table(
            ["Symbol", "Company", "Market Value", "Sleeve", "Account"],
            top_holding_rows,
            "No broker position rows are available.",
        ),
        "sleeves": broker_table(
            ["Sleeve", "Market Value", "Pct Of Holdings", "Cap Pct"],
            sleeve_rows,
            "No broker sleeve exposure is available.",
        ),
        "warnings": broker_table(
            ["Warning"],
            [[text(item)] for item in as_list(broker.get("warnings")) if text(item)],
            "No broker read-only warnings are available.",
        ),
        "cap_warnings": broker_table(
            ["Warning"],
            [[text(item)] for item in as_list(broker.get("concentration_cap_warnings")) if text(item)],
            "No broker concentration or cap warnings are available.",
        ),
        "stale_missing_warnings": broker_table(
            ["Warning"],
            [[text(item)] for item in as_list(broker.get("stale_missing_warnings")) if text(item)],
            "No stale or missing broker warnings are available.",
        ),
    }


__all__ = ["build_broker_readonly_view"]
