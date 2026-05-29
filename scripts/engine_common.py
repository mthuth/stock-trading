#!/usr/bin/env python3
"""Compatibility wrapper for stock_trading.storage."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from stock_trading import storage as _storage

sys.modules[__name__] = _storage
