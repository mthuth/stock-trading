#!/usr/bin/env python3
"""Scheduler-friendly entry point for recurring stock-engine refreshes."""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "reports" / "logs"


def default_slot() -> str:
    hour = datetime.now().hour
    return "pre_market" if hour < 12 else "after_close"


def command_for_slot(slot: str) -> list[str]:
    base = [sys.executable, "scripts/run_daily.py", "--show-gaps"]
    if slot == "pre_market":
        return [*base, "--ingest-price-history", "--ingest-evidence"]
    if slot == "after_close":
        return [*base, "--ingest-evidence"]
    raise ValueError(f"Unsupported slot: {slot}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a scheduled stock research refresh.")
    parser.add_argument(
        "--slot",
        choices=["pre_market", "after_close"],
        default=default_slot(),
        help="Refresh slot. Defaults to pre_market before noon, otherwise after_close.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the command without running it.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    command = command_for_slot(args.slot)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"scheduled-refresh-{datetime.now():%Y-%m-%d}-{args.slot}.log"
    print(" ".join(command))
    if args.dry_run:
        print(f"Would write log to {log_path}")
        return 0

    with log_path.open("a") as handle:
        handle.write(f"\n[{datetime.now().isoformat(timespec='seconds')}] {' '.join(command)}\n")
        process = subprocess.run(
            command,
            cwd=ROOT,
            stdout=handle,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        handle.write(f"[{datetime.now().isoformat(timespec='seconds')}] exit={process.returncode}\n")
    print(f"Wrote {log_path}")
    return process.returncode


if __name__ == "__main__":
    sys.exit(main())
