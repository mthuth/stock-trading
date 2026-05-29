#!/usr/bin/env python3
"""Shared helpers for the stock research engine."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Mapping


ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
REPORTS_DIR = ROOT / "reports"
RAW_PAYLOAD_DIR = DATA_DIR / "raw_payloads"
ENV_FILE = ROOT / ".env"
DB_FILE = DATA_DIR / "stock_trading.sqlite"
RESEARCH_FILE = CONFIG_DIR / "research_inputs.csv"
TARGETS_FILE = CONFIG_DIR / "portfolio_targets.json"
SOURCES_FILE = CONFIG_DIR / "research_sources.csv"
SCHEMA_VERSION = 4
RAW_INLINE_LIMIT_BYTES = 128_000


def utc_now_text() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


def table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row[1]) for row in rows}


def ensure_column(conn: sqlite3.Connection, table_name: str, column_name: str, definition: str) -> None:
    if column_name not in table_columns(conn, table_name):
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def load_env(path: Path = ENV_FILE) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def read_csv(path: Path) -> tuple[List[Dict[str, str]], List[str]]:
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fieldnames = list(reader.fieldnames or [])
    for row in rows:
        row.pop(None, None)
    return rows, fieldnames


def write_csv_atomic(path: Path, rows: List[Mapping[str, object]], fieldnames: List[str]) -> None:
    path.parent.mkdir(exist_ok=True)
    temp_file = path.with_suffix(path.suffix + ".tmp")
    with temp_file.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    temp_file.replace(path)


def load_targets() -> Dict[str, object]:
    return json.loads(TARGETS_FILE.read_text())


def apply_schema_migrations(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS workflow_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            finished_at TEXT,
            trigger TEXT NOT NULL DEFAULT 'manual',
            command TEXT,
            status TEXT NOT NULL DEFAULT 'running',
            summary TEXT,
            error_class TEXT,
            message TEXT,
            artifacts_json TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS workflow_step_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workflow_run_id INTEGER,
            step_name TEXT NOT NULL,
            command TEXT,
            started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            finished_at TEXT,
            status TEXT NOT NULL DEFAULT 'running',
            required INTEGER NOT NULL DEFAULT 1,
            retry_count INTEGER NOT NULL DEFAULT 0,
            exit_code INTEGER,
            error_class TEXT,
            message TEXT,
            artifacts_json TEXT,
            FOREIGN KEY (workflow_run_id) REFERENCES workflow_runs(id)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_workflow_step_runs_workflow
        ON workflow_step_runs(workflow_run_id, id)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS provider_refresh_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            refreshed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            provider TEXT NOT NULL,
            status TEXT NOT NULL,
            message TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS provider_field_status (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            provider TEXT NOT NULL,
            field_name TEXT NOT NULL,
            status TEXT NOT NULL,
            message TEXT,
            FOREIGN KEY (run_id) REFERENCES provider_refresh_runs(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS source_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            source_name TEXT NOT NULL,
            symbol TEXT,
            feedback_type TEXT NOT NULL,
            rating_delta REAL DEFAULT 0,
            notes TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS recommendation_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            report_date TEXT,
            symbol TEXT NOT NULL,
            feedback_type TEXT NOT NULL,
            notes TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS recommendation_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            generated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            report_date TEXT NOT NULL,
            report_path TEXT,
            dashboard_path TEXT,
            csv_path TEXT,
            email_path TEXT,
            workflow_run_id INTEGER,
            account_value REAL,
            monthly_contribution REAL,
            notes TEXT,
            FOREIGN KEY (workflow_run_id) REFERENCES workflow_runs(id)
        )
        """
    )
    ensure_column(conn, "recommendation_runs", "workflow_run_id", "INTEGER")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS target_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            run_id INTEGER,
            symbol TEXT NOT NULL,
            target_type TEXT NOT NULL,
            source_name TEXT NOT NULL,
            source_type TEXT NOT NULL,
            target_price REAL NOT NULL,
            target_low REAL,
            target_high REAL,
            current_price REAL,
            upside_pct REAL,
            as_of_date TEXT,
            freshness_days INTEGER,
            confidence TEXT,
            provider_endpoint TEXT,
            raw_payload_ref TEXT,
            notes TEXT,
            FOREIGN KEY (run_id) REFERENCES recommendation_runs(id)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_target_sources_symbol_run
        ON target_sources(symbol, run_id)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_target_sources_source_type
        ON target_sources(source_name, target_type)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS blended_targets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            run_id INTEGER,
            symbol TEXT NOT NULL,
            blended_target REAL NOT NULL,
            target_low REAL,
            target_high REAL,
            current_price REAL,
            upside_pct REAL,
            target_confidence TEXT NOT NULL,
            source_count INTEGER NOT NULL DEFAULT 0,
            blend_status TEXT NOT NULL,
            weights_json TEXT,
            notes TEXT,
            FOREIGN KEY (run_id) REFERENCES recommendation_runs(id)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_blended_targets_symbol_run
        ON blended_targets(symbol, run_id)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS recommendation_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            run_id INTEGER,
            report_date TEXT NOT NULL,
            symbol TEXT NOT NULL,
            company TEXT,
            sleeve TEXT,
            trade_type TEXT,
            action TEXT NOT NULL,
            score REAL NOT NULL,
            current_price REAL,
            target_price REAL,
            upside_pct REAL,
            target_confidence TEXT,
            data_status TEXT,
            score_breakdown TEXT,
            rationale TEXT,
            FOREIGN KEY (run_id) REFERENCES recommendation_runs(id)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_recommendation_scores_symbol_run
        ON recommendation_scores(symbol, run_id)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS research_evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            run_id INTEGER,
            symbol TEXT NOT NULL,
            evidence_type TEXT NOT NULL,
            source_name TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_url TEXT,
            provider_endpoint TEXT,
            provider_id TEXT,
            source_timestamp TEXT,
            fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            title TEXT,
            summary TEXT,
            raw_text_ref TEXT,
            confidence TEXT,
            corroboration_status TEXT,
            user_feedback TEXT,
            UNIQUE(symbol, source_name, evidence_type, provider_id, source_url, source_timestamp),
            FOREIGN KEY (run_id) REFERENCES recommendation_runs(id)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_research_evidence_symbol_created
        ON research_evidence(symbol, created_at)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_research_evidence_source_type
        ON research_evidence(source_name, evidence_type)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS evidence_symbol_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            evidence_id INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            match_type TEXT NOT NULL,
            matched_text TEXT NOT NULL,
            confidence REAL NOT NULL DEFAULT 0.0,
            UNIQUE(evidence_id, symbol, matched_text),
            FOREIGN KEY (evidence_id) REFERENCES research_evidence(id)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_evidence_symbol_tags_symbol_created
        ON evidence_symbol_tags(symbol, created_at)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_evidence_symbol_tags_evidence
        ON evidence_symbol_tags(evidence_id)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS provider_payloads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            provider TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            symbol TEXT,
            payload_ref TEXT,
            payload_json TEXT,
            status TEXT NOT NULL,
            message TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS raw_ingestion_payloads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            provider TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            symbol TEXT,
            request_hash TEXT,
            status TEXT NOT NULL,
            content_hash TEXT,
            payload_size INTEGER NOT NULL DEFAULT 0,
            payload_ref TEXT,
            payload_inline TEXT,
            content_type TEXT,
            message TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_raw_ingestion_provider_endpoint
        ON raw_ingestion_payloads(provider, endpoint, symbol, created_at)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_raw_ingestion_content_hash
        ON raw_ingestion_payloads(content_hash)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS score_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            symbol TEXT NOT NULL,
            signal_date TEXT NOT NULL,
            signal_type TEXT NOT NULL,
            metric_name TEXT NOT NULL,
            raw_value REAL,
            normalized_delta REAL NOT NULL DEFAULT 0,
            confidence TEXT NOT NULL DEFAULT 'low',
            source_name TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_ref TEXT,
            freshness_days INTEGER,
            signal_mode TEXT NOT NULL DEFAULT 'shadow',
            notes TEXT,
            UNIQUE(symbol, signal_date, signal_type, metric_name, source_name, source_ref, signal_mode)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_score_signals_symbol_date
        ON score_signals(symbol, signal_date, signal_mode)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_score_signals_type
        ON score_signals(signal_type, metric_name)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS analysis_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            recommendation_run_id INTEGER,
            model_version TEXT NOT NULL,
            config_version TEXT,
            input_snapshot TEXT,
            output_counts_json TEXT,
            status TEXT NOT NULL DEFAULT 'ok',
            message TEXT,
            context_path TEXT,
            FOREIGN KEY (recommendation_run_id) REFERENCES recommendation_runs(id)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_analysis_runs_recommendation
        ON analysis_runs(recommendation_run_id)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_provider_payloads_provider_symbol
        ON provider_payloads(provider, symbol, created_at)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS price_history (
            symbol TEXT NOT NULL,
            price_date TEXT NOT NULL,
            open REAL,
            high REAL,
            low REAL,
            close REAL NOT NULL,
            adjusted_close REAL,
            volume REAL,
            provider TEXT NOT NULL,
            fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (symbol, price_date, provider)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_price_history_symbol_date
        ON price_history(symbol, price_date)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS company_identifiers (
            symbol TEXT PRIMARY KEY,
            cik TEXT,
            company_name TEXT,
            exchange TEXT,
            source_name TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO schema_migrations (version, name)
        VALUES (?, ?)
        """,
        (1, "base stock research engine schema"),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO schema_migrations (version, name)
        VALUES (?, ?)
        """,
        (2, "local batch workflow run manifest"),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO schema_migrations (version, name)
        VALUES (?, ?)
        """,
        (3, "raw ingestion ledger and shadow score signals"),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO schema_migrations (version, name)
        VALUES (?, ?)
        """,
        (4, "analysis run boundary"),
    )
    conn.execute(
        """
        UPDATE schema_migrations
        SET name = 'raw ingestion ledger and shadow score signals'
        WHERE version = 3
          AND name != 'raw ingestion ledger and shadow score signals'
        """
    )


def init_db() -> sqlite3.Connection:
    DATA_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    apply_schema_migrations(conn)
    conn.commit()
    return conn


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
        RAW_PAYLOAD_DIR
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
    payload_bytes = (payload_text or "").encode("utf-8")
    payload_size = len(payload_bytes)
    content_hash = hashlib.sha256(payload_bytes).hexdigest() if payload_bytes else ""
    payload_ref = ""
    payload_inline = payload_text if payload_size and payload_size <= RAW_INLINE_LIMIT_BYTES else None
    if payload_size > RAW_INLINE_LIMIT_BYTES and content_hash:
        path = raw_payload_file(provider, endpoint, symbol, content_hash, content_type)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(payload_text or "")
        payload_ref = str(path.relative_to(ROOT))
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


def record_research_evidence(rows: List[Mapping[str, object]]) -> int:
    if not rows:
        return 0
    conn = init_db()
    inserted = 0
    with conn:
        for row in rows:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO research_evidence (
                    run_id, symbol, evidence_type, source_name, source_type, source_url,
                    provider_endpoint, provider_id, source_timestamp, title, summary,
                    raw_text_ref, confidence, corroboration_status, user_feedback
                )
                VALUES (
                    :run_id, :symbol, :evidence_type, :source_name, :source_type, :source_url,
                    :provider_endpoint, :provider_id, :source_timestamp, :title, :summary,
                    :raw_text_ref, :confidence, :corroboration_status, :user_feedback
                )
                """,
                row,
            )
            inserted += cursor.rowcount
    conn.close()
    return inserted


def record_evidence_symbol_tags(rows: List[Mapping[str, object]]) -> int:
    if not rows:
        return 0
    conn = init_db()
    inserted = 0
    with conn:
        for row in rows:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO evidence_symbol_tags (
                    evidence_id, symbol, match_type, matched_text, confidence
                )
                VALUES (
                    :evidence_id, :symbol, :match_type, :matched_text, :confidence
                )
                """,
                row,
            )
            inserted += cursor.rowcount
    conn.close()
    return inserted


def upsert_company_identifier(
    symbol: str,
    cik: str,
    company_name: str,
    exchange: str = "",
    source_name: str = "SEC company_tickers",
) -> None:
    conn = init_db()
    with conn:
        conn.execute(
            """
            INSERT INTO company_identifiers (
                symbol, cik, company_name, exchange, source_name, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                cik = excluded.cik,
                company_name = excluded.company_name,
                exchange = excluded.exchange,
                source_name = excluded.source_name,
                updated_at = excluded.updated_at
            """,
            (
                symbol.upper(),
                cik,
                company_name,
                exchange,
                source_name,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
    conn.close()


def record_provider_run(
    provider: str,
    status: str,
    message: str,
    field_rows: List[Mapping[str, object]],
) -> int:
    conn = init_db()
    with conn:
        cursor = conn.execute(
            """
            INSERT INTO provider_refresh_runs (provider, status, message)
            VALUES (?, ?, ?)
            """,
            (provider, status, message),
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
                    row.get("status"),
                    row.get("message", ""),
                ),
            )
    conn.close()
    return run_id


def latest_provider_gaps(limit: int = 200) -> List[sqlite3.Row]:
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
    conn.close()
    return rows
