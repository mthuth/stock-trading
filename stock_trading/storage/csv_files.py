#!/usr/bin/env python3
"""CSV/config file helpers for curated local inputs."""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Dict, List, Mapping

from stock_trading.storage import connection


def load_env(path: Path | None = None) -> None:
    path = path or connection.ENV_FILE
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
    return json.loads(connection.TARGETS_FILE.read_text())
