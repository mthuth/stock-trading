#!/usr/bin/env python3
"""Regression tests for shadow score-signal curation."""

from __future__ import annotations

import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]

from scripts import curate_score_signals as subject
from stock_trading import storage as engine_common


class CurateScoreSignalsTests(unittest.TestCase):
    def test_technical_signals_are_capped_and_shadow_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            db_file = data_dir / "stock_trading.sqlite"
            with (
                patch.object(engine_common, "DATA_DIR", data_dir),
                patch.object(engine_common, "DB_FILE", db_file),
                patch.object(subject, "DB_FILE", db_file),
            ):
                conn = engine_common.init_db()
                base = date(2025, 9, 1)
                rows = []
                for index in range(80):
                    rows.append(
                        {
                            "symbol": "NVDA",
                            "price_date": (base + timedelta(days=index)).isoformat(),
                            "open": 100 + index,
                            "high": 101 + index,
                            "low": 99 + index,
                            "close": 100 + index,
                            "adjusted_close": 100 + index,
                            "volume": 1_000_000,
                            "provider": "Unit",
                        }
                    )
                engine_common.record_price_history(rows)
                conn.close()

                conn = engine_common.init_db()
                conn.row_factory = subject.sqlite3.Row
                signals = subject.technical_signals(conn, "NVDA")
                conn.close()

        self.assertGreaterEqual(len(signals), 3)
        self.assertTrue(all(signal["signal_mode"] == "shadow" for signal in signals))
        self.assertTrue(all(-5 <= float(signal["normalized_delta"]) <= 5 for signal in signals))
        self.assertIn("moving_average_trend", {signal["metric_name"] for signal in signals})


if __name__ == "__main__":
    unittest.main()
