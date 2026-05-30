#!/usr/bin/env python3
"""Workflow run and step-run repository functions."""

from __future__ import annotations

import json
import sqlite3

from stock_trading.storage.connection import init_db

def start_workflow_run(trigger: str, command: list[str] | str) -> int:
    command_text = " ".join(command) if isinstance(command, list) else str(command)
    conn = init_db()
    with conn:
        cursor = conn.execute(
            """
            INSERT INTO workflow_runs (trigger, command, status)
            VALUES (?, ?, 'running')
            """,
            (trigger, command_text),
        )
        workflow_run_id = int(cursor.lastrowid)
    conn.close()
    return workflow_run_id

def finish_workflow_run(
    workflow_run_id: int,
    status: str,
    message: str = "",
    summary: str = "",
    error_class: str = "",
    artifacts: list[str] | None = None,
) -> None:
    conn = init_db()
    with conn:
        conn.execute(
            """
            UPDATE workflow_runs
            SET finished_at = CURRENT_TIMESTAMP,
                status = ?,
                message = ?,
                summary = ?,
                error_class = ?,
                artifacts_json = ?
            WHERE id = ?
            """,
            (
                status,
                message,
                summary,
                error_class,
                json.dumps(artifacts or []),
                workflow_run_id,
            ),
        )
    conn.close()

def start_workflow_step(
    workflow_run_id: int | None,
    step_name: str,
    command: list[str] | str,
    required: bool = True,
) -> int:
    command_text = " ".join(command) if isinstance(command, list) else str(command)
    conn = init_db()
    with conn:
        cursor = conn.execute(
            """
            INSERT INTO workflow_step_runs (
                workflow_run_id, step_name, command, status, required
            )
            VALUES (?, ?, ?, 'running', ?)
            """,
            (workflow_run_id, step_name, command_text, 1 if required else 0),
        )
        step_run_id = int(cursor.lastrowid)
    conn.close()
    return step_run_id

def finish_workflow_step(
    step_run_id: int,
    status: str,
    exit_code: int | None = None,
    message: str = "",
    error_class: str = "",
    retry_count: int = 0,
    artifacts: list[str] | None = None,
) -> None:
    conn = init_db()
    with conn:
        conn.execute(
            """
            UPDATE workflow_step_runs
            SET finished_at = CURRENT_TIMESTAMP,
                status = ?,
                exit_code = ?,
                message = ?,
                error_class = ?,
                retry_count = ?,
                artifacts_json = ?
            WHERE id = ?
            """,
            (
                status,
                exit_code,
                message,
                error_class,
                retry_count,
                json.dumps(artifacts or []),
                step_run_id,
            ),
        )
    conn.close()

def latest_workflow_run() -> sqlite3.Row | None:
    conn = init_db()
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        """
        SELECT id, started_at, finished_at, trigger, status, summary, message, artifacts_json
        FROM workflow_runs
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()
    conn.close()
    return row
