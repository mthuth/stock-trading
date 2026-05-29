#!/usr/bin/env python3
"""Compatibility wrapper for stock_trading.cli.daily."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from stock_trading.cli import daily as _daily  # noqa: E402

finish_workflow_run = _daily.finish_workflow_run
has_any_core_price_data = _daily.has_any_core_price_data
run = _daily.run
start_workflow_run = _daily.start_workflow_run


def main() -> int:
    _daily.finish_workflow_run = finish_workflow_run
    _daily.has_any_core_price_data = has_any_core_price_data
    _daily.run = run
    _daily.start_workflow_run = start_workflow_run
    return _daily.main()


if __name__ == "__main__":
    sys.exit(main())
