#!/usr/bin/env python3
"""Provider status, payload, and price-history repository functions."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import List, Mapping

from stock_trading.provider_gap_status import normalize_provider_status
from stock_trading.storage import connection
from stock_trading.storage.connection import init_db

def latest_successful_provider_refresh() -> sqlite3.Row | None:
    conn = init_db()
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        """
        SELECT id, refreshed_at, provider, status, message
        FROM provider_refresh_runs
        WHERE status = 'ok'
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()
    conn.close()
    return row

def record_price_history(rows: List[Mapping[str, object]]) -> int:
    if not rows:
        return 0
    conn = init_db()
    with conn:
        conn.executemany(
            """
            INSERT INTO price_history (
                symbol, price_date, open, high, low, close, adjusted_close, volume, provider
            )
            VALUES (
                :symbol, :price_date, :open, :high, :low, :close, :adjusted_close, :volume, :provider
            )
            ON CONFLICT(symbol, price_date, provider) DO UPDATE SET
                open = excluded.open,
                high = excluded.high,
                low = excluded.low,
                close = excluded.close,
                adjusted_close = excluded.adjusted_close,
                volume = excluded.volume,
                fetched_at = CURRENT_TIMESTAMP
            """
            ,
            rows,
        )
    conn.close()
    return len(rows)

def record_provider_payload(
    provider: str,
    endpoint: str,
    symbol: str,
    status: str,
    message: str = "",
    payload_ref: str = "",
    payload_json: object | None = None,
) -> int:
    status = normalize_provider_status(status, message)
    conn = init_db()
    payload_text = json.dumps(payload_json) if payload_json is not None else None
    raw_payload_ref = record_raw_ingestion_payload(
        provider=provider,
        endpoint=endpoint,
        symbol=symbol,
        status=status,
        message=message,
        payload_text=payload_text,
        content_type="application/json" if payload_text is not None else "",
    )
    if not payload_ref and raw_payload_ref:
        payload_ref = raw_payload_ref
    with conn:
        cursor = conn.execute(
            """
            INSERT INTO provider_payloads (
                provider, endpoint, symbol, payload_ref, payload_json, status, message
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (provider, endpoint, symbol, payload_ref, payload_text, status, message),
        )
        payload_id = int(cursor.lastrowid)
    conn.close()
    return payload_id

def safe_path_part(value: object) -> str:
    text = str(value or "unknown").strip().lower()
    text = re.sub(r"[^a-z0-9._-]+", "-", text)
    return text.strip("-") or "unknown"

def raw_payload_file(provider: str, endpoint: str, symbol: str, content_hash: str, content_type: str) -> Path:
    suffix = ".json" if "json" in content_type.lower() else ".txt"
    return (
        connection.RAW_PAYLOAD_DIR
        / safe_path_part(provider)
        / safe_path_part(endpoint)
        / safe_path_part(symbol or "market")
        / f"{content_hash}{suffix}"
    )

def record_raw_ingestion_payload(
    provider: str,
    endpoint: str,
    symbol: str = "",
    status: str = "ok",
    message: str = "",
    payload_text: str | None = None,
    request_hash: str = "",
    content_type: str = "",
) -> str:
    status = normalize_provider_status(status, message)
    payload_bytes = (payload_text or "").encode("utf-8")
    payload_size = len(payload_bytes)
    content_hash = hashlib.sha256(payload_bytes).hexdigest() if payload_bytes else ""
    payload_ref = ""
    payload_inline = payload_text if payload_size and payload_size <= connection.RAW_INLINE_LIMIT_BYTES else None
    if payload_size > connection.RAW_INLINE_LIMIT_BYTES and content_hash:
        path = raw_payload_file(provider, endpoint, symbol, content_hash, content_type)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(payload_text or "")
        payload_ref = str(path.relative_to(connection.ROOT))
    conn = init_db()
    with conn:
        conn.execute(
            """
            INSERT INTO raw_ingestion_payloads (
                provider, endpoint, symbol, request_hash, status, content_hash,
                payload_size, payload_ref, payload_inline, content_type, message
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                provider,
                endpoint,
                symbol,
                request_hash,
                status,
                content_hash,
                payload_size,
                payload_ref,
                payload_inline,
                content_type,
                message,
            ),
        )
    conn.close()
    return payload_ref or (f"raw_ingestion_payloads:{content_hash}" if content_hash else "")

def record_provider_run(
    provider: str,
    status: str,
    message: str,
    field_rows: List[Mapping[str, object]],
) -> int:
    run_status = normalize_provider_status(status, message)
    conn = init_db()
    with conn:
        cursor = conn.execute(
            """
            INSERT INTO provider_refresh_runs (provider, status, message)
            VALUES (?, ?, ?)
            """,
            (provider, run_status, message),
        )
        run_id = int(cursor.lastrowid)
        for row in field_rows:
            conn.execute(
                """
                INSERT INTO provider_field_status (
                    run_id, symbol, provider, field_name, status, message
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    row.get("symbol"),
                    row.get("provider", provider),
                    row.get("field_name"),
                    normalize_provider_status(row.get("status"), row.get("message", "")),
                    row.get("message", ""),
                ),
            )
    conn.close()
    return run_id

def latest_provider_gaps(limit: int = 200) -> List[Mapping[str, object]]:
    conn = init_db()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT p.refreshed_at, f.symbol, f.provider, f.field_name, f.status, f.message
        FROM provider_field_status f
        JOIN provider_refresh_runs p ON p.id = f.run_id
        WHERE f.status != 'ok'
          AND NOT EXISTS (
              SELECT 1
              FROM provider_field_status newer_f
              WHERE newer_f.symbol = f.symbol
                AND newer_f.provider = f.provider
                AND newer_f.field_name = f.field_name
                AND newer_f.run_id > f.run_id
          )
          AND NOT EXISTS (
              SELECT 1
              FROM provider_field_status ok_f
              WHERE ok_f.symbol = f.symbol
                AND ok_f.field_name = f.field_name
                AND ok_f.status = 'ok'
                AND ok_f.run_id > f.run_id
          )
        ORDER BY p.id DESC, f.symbol, f.field_name
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    normalized_rows = []
    for row in rows:
        item = dict(row)
        item["status"] = normalize_provider_status(item.get("status"), item.get("message"))
        if item["status"] == "ok":
            continue
        normalized_rows.append(item)
    conn.close()
    return normalized_rows
