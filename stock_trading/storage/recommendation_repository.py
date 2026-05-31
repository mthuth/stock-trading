#!/usr/bin/env python3
"""Recommendation, target, score, insight, and analysis repositories."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Mapping

from stock_trading.storage.connection import init_db

def record_recommendation_run(
    report_date: str,
    report_path: Path,
    dashboard_path: Path,
    csv_path: Path,
    email_path: Path,
    account_value: float,
    monthly_contribution: float,
    notes: str = "",
    workflow_run_id: int | None = None,
) -> int:
    conn = init_db()
    with conn:
        cursor = conn.execute(
            """
            INSERT INTO recommendation_runs (
                report_date, report_path, dashboard_path, csv_path, email_path,
                workflow_run_id, account_value, monthly_contribution, notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report_date,
                str(report_path),
                str(dashboard_path),
                str(csv_path),
                str(email_path),
                workflow_run_id,
                account_value,
                monthly_contribution,
                notes,
            ),
        )
        run_id = int(cursor.lastrowid)
    conn.close()
    return run_id

def record_target_sources(
    run_id: int,
    rows: List[Mapping[str, object]],
) -> int:
    if not rows:
        return 0
    conn = init_db()
    with conn:
        conn.executemany(
            """
            INSERT INTO target_sources (
                run_id, symbol, target_type, source_name, source_type, target_price,
                target_low, target_high, current_price, upside_pct, as_of_date,
                freshness_days, confidence, provider_endpoint, raw_payload_ref, notes
            )
            VALUES (
                :run_id, :symbol, :target_type, :source_name, :source_type, :target_price,
                :target_low, :target_high, :current_price, :upside_pct, :as_of_date,
                :freshness_days, :confidence, :provider_endpoint, :raw_payload_ref, :notes
            )
            """,
            rows,
        )
    conn.close()
    return len(rows)

def record_blended_targets(
    run_id: int,
    rows: List[Mapping[str, object]],
) -> int:
    if not rows:
        return 0
    conn = init_db()
    with conn:
        conn.executemany(
            """
            INSERT INTO blended_targets (
                run_id, symbol, blended_target, target_low, target_high, current_price,
                upside_pct, target_confidence, source_count, blend_status, weights_json, notes
            )
            VALUES (
                :run_id, :symbol, :blended_target, :target_low, :target_high, :current_price,
                :upside_pct, :target_confidence, :source_count, :blend_status, :weights_json, :notes
            )
            """,
            rows,
        )
    conn.close()
    return len(rows)

def record_recommendation_scores(
    run_id: int,
    rows: List[Mapping[str, object]],
) -> int:
    if not rows:
        return 0
    conn = init_db()
    with conn:
        conn.executemany(
            """
            INSERT INTO recommendation_scores (
                run_id, report_date, symbol, company, sleeve, trade_type, action,
                score, current_price, target_price, upside_pct, target_confidence,
                data_status, score_breakdown, rationale
            )
            VALUES (
                :run_id, :report_date, :symbol, :company, :sleeve, :trade_type, :action,
                :score, :current_price, :target_price, :upside_pct, :target_confidence,
                :data_status, :score_breakdown, :rationale
            )
            """,
            rows,
        )
    conn.close()
    return len(rows)

def recommendation_score_history(limit: int = 500, symbol: str = "") -> List[dict[str, object]]:
    conn = init_db()
    conn.row_factory = sqlite3.Row
    params: list[object] = []
    symbol_filter = ""
    if symbol:
        symbol_filter = "WHERE UPPER(symbol) = ?"
        params.append(symbol.upper())
    params.append(limit)
    rows = conn.execute(
        f"""
        SELECT id, created_at, run_id, report_date, symbol, company, sleeve, trade_type,
               action, score, current_price, target_price, upside_pct, target_confidence,
               data_status, score_breakdown, rationale
        FROM recommendation_scores
        {symbol_filter}
        ORDER BY report_date ASC, run_id ASC, id ASC
        LIMIT ?
        """,
        params,
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]

def record_score_signals(rows: List[Mapping[str, object]], rebuild: bool = False) -> int:
    conn = init_db()
    inserted = 0
    with conn:
        if rebuild:
            conn.execute("DELETE FROM score_signals WHERE signal_mode = 'shadow'")
        for row in rows:
            cursor = conn.execute(
                """
                INSERT OR REPLACE INTO score_signals (
                    symbol, signal_date, signal_type, metric_name, raw_value,
                    normalized_delta, confidence, source_name, source_type,
                    source_ref, freshness_days, signal_mode, notes
                )
                VALUES (
                    :symbol, :signal_date, :signal_type, :metric_name, :raw_value,
                    :normalized_delta, :confidence, :source_name, :source_type,
                    :source_ref, :freshness_days, :signal_mode, :notes
                )
                """,
                row,
            )
            inserted += cursor.rowcount
    conn.close()
    return inserted

def record_decision_insights(rows: List[Mapping[str, object]]) -> int:
    if not rows:
        return 0
    conn = init_db()
    inserted = 0
    with conn:
        for row in rows:
            cursor = conn.execute(
                """
                INSERT OR REPLACE INTO decision_insights (
                    run_id, report_date, rank, symbol, action, score, insight_type,
                    headline, why_it_matters, supporting_data, risk_or_uncertainty,
                    next_check, what_would_change_the_view, source_ref
                )
                VALUES (
                    :run_id, :report_date, :rank, :symbol, :action, :score, :insight_type,
                    :headline, :why_it_matters, :supporting_data, :risk_or_uncertainty,
                    :next_check, :what_would_change_the_view, :source_ref
                )
                """,
                row,
            )
            inserted += cursor.rowcount
    conn.close()
    return inserted

def record_verification_queue_items(rows: List[Mapping[str, object]]) -> int:
    if not rows:
        return 0
    conn = init_db()
    inserted = 0
    with conn:
        for row in rows:
            cursor = conn.execute(
                """
                INSERT OR REPLACE INTO verification_queue_items (
                    run_id, report_date, symbol, priority_rank, insight_type, reason,
                    expected_score_impact, next_check, command_mapping, automation_mode,
                    status, result_summary, workflow_step_id, started_at, completed_at
                )
                VALUES (
                    :run_id, :report_date, :symbol, :priority_rank, :insight_type, :reason,
                    :expected_score_impact, :next_check, :command_mapping, :automation_mode,
                    :status, :result_summary, :workflow_step_id, :started_at, :completed_at
                )
                """,
                row,
            )
            inserted += cursor.rowcount
    conn.close()
    return inserted

def latest_decision_insights_by_symbol(limit_per_symbol: int = 2) -> Dict[str, List[sqlite3.Row]]:
    conn = init_db()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT id, created_at, run_id, report_date, rank, symbol, action, score,
               insight_type, headline, why_it_matters, supporting_data,
               risk_or_uncertainty, next_check, what_would_change_the_view,
               source_ref
        FROM decision_insights
        ORDER BY run_id DESC, id DESC
        LIMIT 2000
        """
    ).fetchall()
    conn.close()
    grouped: Dict[str, List[sqlite3.Row]] = {}
    for row in rows:
        symbol = str(row["symbol"] or "").upper()
        grouped.setdefault(symbol, [])
        if len(grouped[symbol]) < limit_per_symbol:
            grouped[symbol].append(row)
    return grouped

def latest_open_verification_queue(limit: int = 50, symbol: str = "") -> List[sqlite3.Row]:
    conn = init_db()
    conn.row_factory = sqlite3.Row
    params: list[object] = []
    symbol_filter = ""
    if symbol:
        symbol_filter = "AND q.symbol = ?"
        params.append(symbol.upper())
    params.append(limit)
    rows = conn.execute(
        f"""
        SELECT id, created_at, updated_at, run_id, report_date, symbol,
               priority_rank, insight_type, reason, expected_score_impact,
               next_check, command_mapping, automation_mode, status,
               result_summary, workflow_step_id, started_at, completed_at
        FROM verification_queue_items q
        WHERE q.status != 'completed'
          {symbol_filter}
          AND NOT EXISTS (
              SELECT 1
              FROM verification_queue_items newer_q
              WHERE newer_q.symbol = q.symbol
                AND newer_q.next_check = q.next_check
                AND newer_q.reason = q.reason
                AND newer_q.id > q.id
          )
        ORDER BY
          CASE status
            WHEN 'queued' THEN 0
            WHEN 'failed' THEN 1
            WHEN 'running' THEN 2
            WHEN 'manual_required' THEN 3
            WHEN 'blocked_provider_fix_needed' THEN 4
            ELSE 5
          END,
          priority_rank ASC,
          run_id DESC,
          id DESC
        LIMIT ?
        """,
        params,
    ).fetchall()
    conn.close()
    return rows

def latest_verification_queue(limit: int = 50, symbol: str = "") -> List[sqlite3.Row]:
    conn = init_db()
    conn.row_factory = sqlite3.Row
    params: list[object] = []
    symbol_filter = ""
    if symbol:
        symbol_filter = "WHERE symbol = ?"
        params.append(symbol.upper())
    params.append(limit)
    rows = conn.execute(
        f"""
        SELECT id, created_at, updated_at, run_id, report_date, symbol,
               priority_rank, insight_type, reason, expected_score_impact,
               next_check, command_mapping, automation_mode, status,
               result_summary, workflow_step_id, started_at, completed_at
        FROM verification_queue_items
        {symbol_filter}
        ORDER BY run_id DESC, priority_rank ASC, id DESC
        LIMIT ?
        """,
        params,
    ).fetchall()
    conn.close()
    return rows

def update_verification_queue_item_status(
    item_id: int,
    status: str,
    result_summary: str = "",
    workflow_step_id: int | None = None,
    started: bool = False,
    completed: bool = False,
) -> None:
    conn = init_db()
    assignments = [
        "status = ?",
        "result_summary = ?",
        "updated_at = CURRENT_TIMESTAMP",
    ]
    params: list[object] = [status, result_summary]
    if workflow_step_id is not None:
        assignments.append("workflow_step_id = ?")
        params.append(workflow_step_id)
    if started:
        assignments.append("started_at = COALESCE(started_at, CURRENT_TIMESTAMP)")
    if completed:
        assignments.append("completed_at = CURRENT_TIMESTAMP")
    params.append(item_id)
    with conn:
        conn.execute(
            f"UPDATE verification_queue_items SET {', '.join(assignments)} WHERE id = ?",
            params,
        )
    conn.close()

def record_analysis_run(
    recommendation_run_id: int | None,
    model_version: str,
    config_version: str = "",
    input_snapshot: Mapping[str, object] | None = None,
    output_counts: Mapping[str, object] | None = None,
    status: str = "ok",
    message: str = "",
    context_path: str = "",
) -> int:
    conn = init_db()
    with conn:
        cursor = conn.execute(
            """
            INSERT INTO analysis_runs (
                recommendation_run_id, model_version, config_version, input_snapshot,
                output_counts_json, status, message, context_path
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                recommendation_run_id,
                model_version,
                config_version,
                json.dumps(input_snapshot or {}, sort_keys=True),
                json.dumps(output_counts or {}, sort_keys=True),
                status,
                message,
                context_path,
            ),
        )
        analysis_run_id = int(cursor.lastrowid)
    conn.close()
    return analysis_run_id

def latest_analysis_run() -> sqlite3.Row | None:
    conn = init_db()
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        """
        SELECT id, created_at, recommendation_run_id, model_version, status,
               output_counts_json, message, context_path
        FROM analysis_runs
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()
    conn.close()
    return row
