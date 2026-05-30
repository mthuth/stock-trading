#!/usr/bin/env python3
"""Feedback persistence helpers for local dashboard review."""

from __future__ import annotations

from typing import Any

from stock_trading.storage import init_db


SOURCE_FEEDBACK_DELTAS = {
    "useful_source": 0.1,
    "noisy_source": -0.1,
}


def record_feedback(payload: dict[str, Any]) -> dict[str, Any]:
    kind = str(payload.get("kind") or "").strip().lower()
    feedback_type = str(payload.get("type") or payload.get("feedback_type") or "").strip()
    notes = str(payload.get("notes") or "").strip()
    if kind not in {"recommendation", "source"}:
        raise ValueError("Feedback kind must be recommendation or source.")
    if not feedback_type:
        raise ValueError("Feedback type is required.")

    conn = init_db()
    try:
        with conn:
            if kind == "source":
                source_name = str(payload.get("source_name") or payload.get("source") or "").strip()
                symbol = str(payload.get("symbol") or "").strip().upper()
                if not source_name:
                    raise ValueError("Source feedback requires a source name.")
                rating_delta = payload.get("rating_delta", payload.get("delta"))
                if rating_delta is None:
                    rating_delta = SOURCE_FEEDBACK_DELTAS.get(feedback_type, 0.0)
                cursor = conn.execute(
                    """
                    INSERT INTO source_feedback (
                        source_name, symbol, feedback_type, rating_delta, notes
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (source_name, symbol, feedback_type, float(rating_delta or 0), notes),
                )
                record_id = int(cursor.lastrowid)
            else:
                symbol = str(payload.get("symbol") or "").strip().upper()
                report_date = str(payload.get("report_date") or "").strip()
                if not symbol:
                    raise ValueError("Recommendation feedback requires a symbol.")
                cursor = conn.execute(
                    """
                    INSERT INTO recommendation_feedback (
                        report_date, symbol, feedback_type, notes
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (report_date, symbol, feedback_type, notes),
                )
                record_id = int(cursor.lastrowid)
        return {"id": record_id, "kind": kind, "type": feedback_type, "message": feedback_message(kind, payload)}
    finally:
        conn.close()


def feedback_message(kind: str, payload: dict[str, Any]) -> str:
    if kind == "source":
        source_name = str(payload.get("source_name") or payload.get("source") or "").strip()
        return f"Recorded source feedback for {source_name}"
    symbol = str(payload.get("symbol") or "").strip().upper()
    return f"Recorded recommendation feedback for {symbol}"


def recent_feedback(limit: int = 8) -> list[dict[str, Any]]:
    conn = init_db()
    conn.row_factory = None
    try:
        recommendation_rows = conn.execute(
            """
            SELECT created_at, 'recommendation' AS kind, symbol AS subject,
                   feedback_type, notes
            FROM recommendation_feedback
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        source_rows = conn.execute(
            """
            SELECT created_at, 'source' AS kind, source_name AS subject,
                   feedback_type, notes
            FROM source_feedback
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    finally:
        conn.close()
    records = [
        {
            "created_at": row[0],
            "kind": row[1],
            "subject": row[2],
            "type": row[3],
            "notes": row[4] or "",
        }
        for row in [*recommendation_rows, *source_rows]
    ]
    records.sort(key=lambda record: str(record["created_at"]), reverse=True)
    return records[:limit]
