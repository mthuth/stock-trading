#!/usr/bin/env python3
"""Compatibility wrapper for daily analysis and presentation rendering."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from stock_trading.analysis_engine import *  # noqa: F401,F403,E402
from stock_trading import analysis_engine as _analysis_engine  # noqa: E402
from stock_trading.presentation import render_report_context  # noqa: E402


def target_source_rows(research, run_id, as_of_date, targets):  # type: ignore[no-untyped-def]
    patched_names = (
        "load_manual_analyst_targets",
        "latest_sec_facts_by_symbol",
        "latest_price_history_by_symbol",
        "fundamental_target_row",
        "technical_target_row",
    )
    previous = {name: getattr(_analysis_engine, name) for name in patched_names}
    try:
        for name in patched_names:
            setattr(_analysis_engine, name, globals()[name])
        return _analysis_engine.target_source_rows(research, run_id, as_of_date, targets)
    finally:
        for name, value in previous.items():
            setattr(_analysis_engine, name, value)


def maybe_refresh_market_data(argv: List[str]) -> None:
    if "--refresh" not in argv:
        return
    result = subprocess.run(
        [sys.executable, str(_analysis_engine.REFRESH_SCRIPT)],
        cwd=ROOT,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        raise SystemExit("Market-data refresh failed; report was not generated.")


def generate_report() -> List[Path]:
    context = _analysis_engine.run_analysis(persist=True, write_context=True)
    rendered_paths = render_report_context(context, _analysis_engine.REPORTS_DIR)
    ai_context = context.get("artifacts", {}).get("ai_context", "")
    ai_context_path = _analysis_engine.REPORTS_DIR / str(ai_context) if ai_context else None
    return [*rendered_paths, *([ai_context_path] if ai_context_path else [])]


def main() -> int:
    maybe_refresh_market_data(sys.argv[1:])
    for report_path in generate_report():
        print(f"Wrote {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
