#!/usr/bin/env python3
"""Ingestion plan and backfill queue repository functions."""

from __future__ import annotations

from typing import List, Mapping

from stock_trading.storage.connection import init_db

def record_ingestion_run_plan(rows: List[Mapping[str, object]], rebuild: bool = False) -> int:
    if not rows and not rebuild:
        return 0
    conn = init_db()
    inserted = 0
    with conn:
        if rebuild:
            conn.execute("DELETE FROM ingestion_run_plan")
        for row in rows:
            cursor = conn.execute(
                """
                INSERT OR REPLACE INTO ingestion_run_plan (
                    source_name, updated_at, source_category, source_tier,
                    cadence_days, latest_attempt, latest_success, next_run_at,
                    cooldown_until, due_status, priority_rank, records, raw_payloads,
                    duplicate_records, latest_issue, run_command, reason
                )
                VALUES (
                    :source_name, CURRENT_TIMESTAMP, :source_category, :source_tier,
                    :cadence_days, :latest_attempt, :latest_success, :next_run_at,
                    :cooldown_until, :due_status, :priority_rank, :records, :raw_payloads,
                    :duplicate_records, :latest_issue, :run_command, :reason
                )
                """,
                row,
            )
            inserted += cursor.rowcount
    conn.close()
    return inserted

def record_ingestion_backfill_queue(rows: List[Mapping[str, object]], rebuild: bool = False) -> int:
    if not rows and not rebuild:
        return 0
    conn = init_db()
    inserted = 0
    with conn:
        if rebuild:
            conn.execute("DELETE FROM ingestion_backfill_queue")
        for row in rows:
            cursor = conn.execute(
                """
                INSERT OR REPLACE INTO ingestion_backfill_queue (
                    source_name, symbol, backfill_type, status, priority_rank,
                    desired_window_days, covered_since, covered_until, record_count,
                    next_action, command, reason
                )
                VALUES (
                    :source_name, :symbol, :backfill_type, :status, :priority_rank,
                    :desired_window_days, :covered_since, :covered_until, :record_count,
                    :next_action, :command, :reason
                )
                """,
                row,
            )
            inserted += cursor.rowcount
    conn.close()
    return inserted
