#!/usr/bin/env python3
"""Synthesis readiness repository functions."""

from __future__ import annotations

from typing import List, Mapping

from stock_trading.storage.connection import init_db

def record_synthesis_readiness(rows: List[Mapping[str, object]], rebuild: bool = False) -> int:
    if not rows and not rebuild:
        return 0
    conn = init_db()
    inserted = 0
    with conn:
        if rebuild:
            conn.execute("DELETE FROM synthesis_readiness")
        for row in rows:
            cursor = conn.execute(
                """
                INSERT OR REPLACE INTO synthesis_readiness (
                    symbol, readiness_status, readiness_score, ready_events,
                    needs_review_events, needs_corroboration_events, ignored_events,
                    primary_events, independent_confirmed_events, latest_event_at,
                    packet_ref, notes
                )
                VALUES (
                    :symbol, :readiness_status, :readiness_score, :ready_events,
                    :needs_review_events, :needs_corroboration_events, :ignored_events,
                    :primary_events, :independent_confirmed_events, :latest_event_at,
                    :packet_ref, :notes
                )
                """,
                row,
            )
            inserted += cursor.rowcount
    conn.close()
    return inserted
