"""Read-only workflow run-history view models for the local decision console."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable, Mapping

from stock_trading.storage.connection import DB_FILE


REVIEW_ONLY_NOTE = (
    "Read-only local console run history. This view inspects existing workflow "
    "manifests only and must not execute runs, refresh providers, alter "
    "recommendations, or trade."
)


def text(value: object, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def parse_artifacts(value: object) -> list[str]:
    raw = text(value)
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return [raw]
    if isinstance(parsed, list):
        return [text(item) for item in parsed if text(item)]
    if isinstance(parsed, str) and parsed:
        return [parsed]
    return []


def read_only_connection(db_path: Path | str) -> sqlite3.Connection | None:
    path = Path(db_path)
    if not path.exists():
        return None
    uri = f"file:{path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def has_table(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def workflow_step_rows(conn: sqlite3.Connection, run_ids: Iterable[int]) -> dict[int, list[dict[str, object]]]:
    ids = [int(run_id) for run_id in run_ids]
    if not ids or not has_table(conn, "workflow_step_runs"):
        return {}
    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(
        f"""
        SELECT workflow_run_id, step_name, status, started_at, finished_at,
               exit_code, error_class, message, artifacts_json
        FROM workflow_step_runs
        WHERE workflow_run_id IN ({placeholders})
        ORDER BY workflow_run_id DESC, id ASC
        """,
        ids,
    ).fetchall()
    grouped: dict[int, list[dict[str, object]]] = {}
    for row in rows:
        run_id = int(row["workflow_run_id"])
        grouped.setdefault(run_id, []).append(
            {
                "step_name": text(row["step_name"]),
                "status": text(row["status"]),
                "started_at": text(row["started_at"]),
                "finished_at": text(row["finished_at"]),
                "exit_code": row["exit_code"],
                "error_class": text(row["error_class"]),
                "message": text(row["message"]),
                "artifact_references": parse_artifacts(row["artifacts_json"]),
            }
        )
    return grouped


def run_warnings_errors(row: Mapping[str, object], steps: Iterable[Mapping[str, object]]) -> dict[str, list[str]]:
    warnings: list[str] = []
    errors: list[str] = []
    status = text(row.get("status"))
    summary = text(row.get("summary"))
    message = text(row.get("message"))
    error_class = text(row.get("error_class"))
    if status == "ok_with_warnings" and summary:
        warnings.extend(part.strip() for part in summary.split(";") if part.strip())
    if status == "failed":
        if error_class or message:
            errors.append(": ".join(part for part in (error_class, message) if part))
        elif summary:
            errors.append(summary)
    for step in steps:
        step_status = text(step.get("status"))
        step_message = text(step.get("message"))
        step_name = text(step.get("step_name"))
        if step_status in {"failed", "error"}:
            errors.append(f"{step_name}: {step_message or step_status}")
        elif step_status and step_status not in {"ok", "running"} and step_message:
            warnings.append(f"{step_name}: {step_message}")
    return {"warnings": warnings, "errors": errors}


def workflow_run_rows(db_path: Path | str = DB_FILE, *, limit: int = 20) -> list[dict[str, object]]:
    """Return existing workflow run manifests without creating or mutating storage."""

    conn = read_only_connection(db_path)
    if conn is None:
        return []
    try:
        if not has_table(conn, "workflow_runs"):
            return []
        run_rows = conn.execute(
            """
            SELECT id, started_at, finished_at, trigger, command, status,
                   summary, error_class, message, artifacts_json
            FROM workflow_runs
            ORDER BY id DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
        steps_by_run = workflow_step_rows(conn, [int(row["id"]) for row in run_rows])
    finally:
        conn.close()

    results: list[dict[str, object]] = []
    for row in run_rows:
        run_id = int(row["id"])
        steps = steps_by_run.get(run_id, [])
        artifact_references = parse_artifacts(row["artifacts_json"])
        for step in steps:
            artifact_references.extend(str(item) for item in step.get("artifact_references", []))
        warnings_errors = run_warnings_errors(dict(row), steps)
        results.append(
            {
                "run_id": run_id,
                "workflow_name": text(row["trigger"]) or "workflow",
                "status": text(row["status"]),
                "started_at": text(row["started_at"]),
                "finished_at": text(row["finished_at"]),
                "summary": text(row["summary"] or row["message"]),
                "warnings": warnings_errors["warnings"],
                "errors": warnings_errors["errors"],
                "artifact_references": sorted(set(artifact_references)),
                "steps": steps,
                "review_only": True,
                "notes": REVIEW_ONLY_NOTE,
            }
        )
    return results


def run_history_view_model(db_path: Path | str = DB_FILE, *, limit: int = 20) -> dict[str, object]:
    rows = workflow_run_rows(db_path, limit=limit)
    return {
        "metadata": {
            "review_only": True,
            "available": bool(rows),
            "run_count": len(rows),
            "notes": REVIEW_ONLY_NOTE if rows else f"{REVIEW_ONLY_NOTE} No workflow run history is available.",
        },
        "runs": rows,
        "latest_run": rows[0] if rows else {},
        "review_only": True,
    }
