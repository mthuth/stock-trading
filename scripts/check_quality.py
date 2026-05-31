#!/usr/bin/env python3
"""Run lightweight local quality gates for the stock-trading app."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def py_files(*roots: str) -> list[str]:
    files: list[str] = []
    for root in roots:
        files.extend(str(path.relative_to(ROOT)) for path in sorted((ROOT / root).glob("*.py")))
    files.extend(str(path.relative_to(ROOT)) for path in sorted((ROOT / "stock_trading" / "cli").glob("*.py")))
    files.extend(str(path.relative_to(ROOT)) for path in sorted((ROOT / "stock_trading" / "reporting").glob("*.py")))
    files.extend(str(path.relative_to(ROOT)) for path in sorted((ROOT / "stock_trading" / "workflows").glob("*.py")))
    return files


def run(command: list[str], env: dict[str, str] | None = None) -> int:
    print(f"$ {' '.join(command)}", flush=True)
    return subprocess.call(command, cwd=ROOT, env={**os.environ, **(env or {})})


def main() -> int:
    checks = [
        [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
        [
            sys.executable,
            "-m",
            "py_compile",
            *py_files("scripts", "stock_trading"),
        ],
    ]
    compile_env = {"PYTHONPYCACHEPREFIX": "/private/tmp/stock-pycache"}
    for index, command in enumerate(checks):
        status = run(command, compile_env if index == 1 else None)
        if status != 0:
            return status
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
