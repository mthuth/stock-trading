#!/usr/bin/env python3
"""Manual decision/trade journal repository functions."""

from __future__ import annotations

import sqlite3
from typing import List, Mapping

from stock_trading.storage.connection import init_db


def record_manual_trade_journal_entry(row: Mapping[str, object]) -> int:
    conn = init_db()
    with conn:
        cursor = conn.execute(
            """
            INSERT INTO manual_trade_journal (
                decision_date, symbol, action_taken, amount, shares, price,
                rationale, recommendation_run_id, report_date, notes
            )
            VALUES (
                :decision_date, :symbol, :action_taken, :amount, :shares, :price,
                :rationale, :recommendation_run_id, :report_date, :notes
            )
            """,
            row,
        )
        entry_id = int(cursor.lastrowid)
    conn.close()
    return entry_id


def manual_trade_journal_entries(
    *,
    symbol: str = "",
    report_date: str = "",
    limit: int = 50,
) -> List[sqlite3.Row]:
    conn = init_db()
    conn.row_factory = sqlite3.Row
    filters: list[str] = []
    params: list[object] = []
    if symbol:
        filters.append("symbol = ?")
        params.append(symbol.upper())
    if report_date:
        filters.append("report_date = ?")
        params.append(report_date)
    params.append(limit)
    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
    rows = conn.execute(
        f"""
        SELECT id, created_at, decision_date, symbol, action_taken, amount,
               shares, price, rationale, recommendation_run_id, report_date, notes
        FROM manual_trade_journal
        {where_clause}
        ORDER BY decision_date DESC, created_at DESC, id DESC
        LIMIT ?
        """,
        params,
    ).fetchall()
    conn.close()
    return rows
