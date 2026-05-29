#!/usr/bin/env python3
"""Compatibility wrapper for stock_trading.ingestion."""

import sys

from stock_trading import ingestion as _ingestion

sys.modules[__name__] = _ingestion
