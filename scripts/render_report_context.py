#!/usr/bin/env python3
"""Compatibility wrapper for report-context rendering."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from stock_trading.cli.render_report_context import main


if __name__ == "__main__":
    sys.exit(main())
