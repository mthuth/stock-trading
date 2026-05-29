#!/usr/bin/env python3
"""Create or update the local SQLite schema for the stock research engine."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from engine_common import DB_FILE, init_db  # noqa: E402


def main() -> int:
    conn = init_db()
    try:
        table_rows = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            ORDER BY name
            """
        ).fetchall()
        migration_rows = conn.execute(
            """
            SELECT version, name, applied_at
            FROM schema_migrations
            ORDER BY version
            """
        ).fetchall()
    finally:
        conn.close()

    tables = [row[0] for row in table_rows]
    print(f"Migrated {DB_FILE}")
    print("Tables:")
    for table in tables:
        print(f"- {table}")
    print("Migrations:")
    for version, name, applied_at in migration_rows:
        print(f"- {version}: {name} ({applied_at})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
