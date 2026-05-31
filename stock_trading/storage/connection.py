#!/usr/bin/env python3
"""Database connection and shared storage paths."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
REPORTS_DIR = ROOT / "reports"
RAW_PAYLOAD_DIR = DATA_DIR / "raw_payloads"
ENV_FILE = ROOT / ".env"
DB_FILE = DATA_DIR / "stock_trading.sqlite"
RESEARCH_FILE = CONFIG_DIR / "research_inputs.csv"
TARGETS_FILE = CONFIG_DIR / "portfolio_targets.json"
SOURCES_FILE = CONFIG_DIR / "research_sources.csv"
SYMBOL_ALIASES_FILE = CONFIG_DIR / "symbol_aliases.csv"
SCHEMA_VERSION = 12
RAW_INLINE_LIMIT_BYTES = 128_000

def utc_now_text() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")

def table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row[1]) for row in rows}

def ensure_column(conn: sqlite3.Connection, table_name: str, column_name: str, definition: str) -> None:
    if column_name not in table_columns(conn, table_name):
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def init_db() -> sqlite3.Connection:
    DATA_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    from stock_trading.storage.schema import apply_schema_migrations

    apply_schema_migrations(conn)
    conn.commit()
    return conn
