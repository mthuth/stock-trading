#!/usr/bin/env python3
"""Manual decision/trade journal helpers.

Journal entries record what the user chose to do outside the app. They are
review-only and never alter recommendations, scores, targets, allocation, or
broker behavior.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from stock_trading.storage import (
    manual_trade_journal_entries,
    record_manual_trade_journal_entry,
)


ACTION_TAKEN_VALUES = {
    "bought",
    "added",
    "held",
    "watched",
    "skipped",
    "trimmed",
    "avoided",
    "reviewed_only",
}


def clean(value: object) -> str:
    return str(value or "").strip()


def optional_float(value: object, field_name: str) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be numeric when provided.") from exc


def optional_int(value: object, field_name: str) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer when provided.") from exc


def normalize_entry(payload: dict[str, Any]) -> dict[str, object]:
    symbol = clean(payload.get("symbol")).upper()
    if not symbol:
        raise ValueError("Manual journal entry requires a symbol.")

    action_taken = clean(payload.get("action_taken") or payload.get("action")).lower()
    if action_taken not in ACTION_TAKEN_VALUES:
        allowed = ", ".join(sorted(ACTION_TAKEN_VALUES))
        raise ValueError(f"action_taken must be one of: {allowed}.")

    decision_date = clean(payload.get("decision_date")) or date.today().isoformat()
    return {
        "decision_date": decision_date,
        "symbol": symbol,
        "action_taken": action_taken,
        "amount": optional_float(payload.get("amount"), "amount"),
        "shares": optional_float(payload.get("shares"), "shares"),
        "price": optional_float(payload.get("price"), "price"),
        "rationale": clean(payload.get("rationale")),
        "recommendation_run_id": optional_int(
            payload.get("recommendation_run_id") or payload.get("run_id"),
            "recommendation_run_id",
        ),
        "report_date": clean(payload.get("report_date")),
        "notes": clean(payload.get("notes")),
    }


def record_manual_journal_entry(payload: dict[str, Any]) -> dict[str, object]:
    row = normalize_entry(payload)
    entry_id = record_manual_trade_journal_entry(row)
    return {
        "id": entry_id,
        "kind": "manual_trade_journal",
        "symbol": row["symbol"],
        "action_taken": row["action_taken"],
        "message": f"Recorded manual journal entry {entry_id} for {row['symbol']}",
    }


def list_manual_journal_entries(
    *,
    symbol: str = "",
    report_date: str = "",
    limit: int = 50,
) -> list[dict[str, object]]:
    rows = manual_trade_journal_entries(symbol=symbol, report_date=report_date, limit=limit)
    return [dict(row) for row in rows]
