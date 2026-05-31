"""Read-only run-history helpers for the local decision console."""

from __future__ import annotations

from pathlib import Path
import json
import sqlite3
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT / "data" / "stock_trading.sqlite"


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def safe_json_list(value: object) -> list[object]:
    if not value:
        return []
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def row_dict(row: sqlite3.Row, *, json_list_fields: Iterable[str] = ()) -> dict[str, object]:
    item = {key: row[key] for key in row.keys()}
    for field in json_list_fields:
        item[field] = safe_json_list(item.get(field))
    return item


def read_recent_runs(db_path: str | Path = DEFAULT_DB_PATH, *, limit: int = 8) -> dict[str, object]:
    path = Path(db_path)
    if not path.exists():
        return {
            "database": str(path),
            "available": False,
            "workflow_runs": [],
            "recommendation_runs": [],
            "empty_state": "No local SQLite run history is available yet.",
        }

    uri = f"file:{path.resolve()}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
    except sqlite3.Error as exc:
        return {
            "database": str(path),
            "available": False,
            "workflow_runs": [],
            "recommendation_runs": [],
            "empty_state": f"Run history could not be opened read-only: {exc}",
        }

    conn.row_factory = sqlite3.Row
    try:
        workflow_runs = []
        recommendation_runs = []
        if table_exists(conn, "workflow_runs"):
            workflow_runs = [
                row_dict(row, json_list_fields=("artifacts_json",))
                for row in conn.execute(
                    """
                    SELECT id, started_at, finished_at, trigger, command, status, summary, message, artifacts_json
                    FROM workflow_runs
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            ]
        if table_exists(conn, "recommendation_runs"):
            recommendation_runs = [
                row_dict(row)
                for row in conn.execute(
                    """
                    SELECT id, generated_at, report_date, report_path, dashboard_path, csv_path, email_path, workflow_run_id
                    FROM recommendation_runs
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            ]
    finally:
        conn.close()

    return {
        "database": str(path),
        "available": True,
        "workflow_runs": workflow_runs,
        "recommendation_runs": recommendation_runs,
        "empty_state": "" if workflow_runs or recommendation_runs else "No workflow or recommendation runs are recorded yet.",
    }


__all__ = ["DEFAULT_DB_PATH", "read_recent_runs"]
