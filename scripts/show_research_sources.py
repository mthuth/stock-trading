#!/usr/bin/env python3
"""Show configured deep-research sources and ratings."""

from __future__ import annotations

import csv
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCES_FILE = ROOT / "config" / "research_sources.csv"


def main() -> int:
    if not SOURCES_FILE.exists():
        print(f"No source file found at {SOURCES_FILE}")
        return 1

    with SOURCES_FILE.open(newline="") as handle:
        rows = list(csv.DictReader(handle))

    headers = [
        "Source",
        "Type",
        "Reliability",
        "Timeliness",
        "Signal",
        "Weight",
        "Effective",
        "Corroborate",
        "Risk Note",
    ]
    table = [
        [
            row["source_name"],
            row["source_type"],
            row["reliability_rating"],
            row["timeliness_rating"],
            row["signal_rating"],
            row["default_weight"],
            f"{effective_weight(row):.2f}",
            row.get("corroboration_required", ""),
            row["bias_risk_note"],
        ]
        for row in rows
    ]
    widths = [
        max(len(str(row[index])) for row in [headers] + table)
        for index in range(len(headers))
    ]

    print("Configured Research Sources")
    print()
    print("  ".join(header.ljust(widths[index]) for index, header in enumerate(headers)))
    print("  ".join("-" * width for width in widths))
    for row in table:
        print("  ".join(value.ljust(widths[index]) for index, value in enumerate(row)))
    return 0


def as_float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def effective_weight(row: dict[str, str]) -> float:
    reliability = as_float(row.get("reliability_rating")) / 5
    timeliness = as_float(row.get("timeliness_rating")) / 5
    signal = as_float(row.get("signal_rating")) / 5
    quality = (reliability * 0.45) + (timeliness * 0.20) + (signal * 0.35)
    base_weight = as_float(row.get("default_weight"))
    corroboration_multiplier = (
        0.85 if str(row.get("corroboration_required", "")).lower() == "true" else 1.0
    )
    return max(0.0, min(1.0, quality * base_weight * corroboration_multiplier))


if __name__ == "__main__":
    sys.exit(main())
