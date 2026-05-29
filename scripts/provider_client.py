#!/usr/bin/env python3
"""Compatibility wrapper for stock_trading.provider_client."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from stock_trading import provider_client as _provider_client

sys.modules[__name__] = _provider_client
