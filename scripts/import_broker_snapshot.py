#!/usr/bin/env python3
"""Import local broker-like fixture/manual snapshots into read-only JSON."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stock_trading.broker_snapshot_importer import import_broker_snapshot, write_snapshot


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Normalize a local JSON or CSV broker snapshot without live broker calls.",
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to a JSON snapshot file or directory containing accounts.csv/positions.csv.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path for normalized read-only broker snapshot JSON.",
    )
    parser.add_argument(
        "--stale-after-days",
        type=int,
        default=7,
        help="Warn when the snapshot as-of date is older than this many days.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        snapshot = import_broker_snapshot(args.input, stale_after_days=args.stale_after_days)
        output_path = write_snapshot(snapshot, args.output)
    except Exception as exc:  # noqa: BLE001 - CLI should surface validation errors cleanly.
        print(f"Broker snapshot import failed: {exc}", file=sys.stderr)
        return 2
    print(f"Wrote read-only broker snapshot to {output_path}")
    warnings = snapshot.get("validation", {}).get("warnings", []) if isinstance(snapshot.get("validation"), dict) else []
    for warning in warnings:
        print(f"Warning: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
