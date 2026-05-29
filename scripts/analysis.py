#!/usr/bin/env python3
"""Compatibility wrapper for stock_trading.analysis."""

import sys

from stock_trading import analysis as _analysis

sys.modules[__name__] = _analysis
