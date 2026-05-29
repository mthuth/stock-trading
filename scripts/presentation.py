#!/usr/bin/env python3
"""Compatibility wrapper for stock_trading.presentation."""

import sys

from stock_trading import presentation as _presentation

sys.modules[__name__] = _presentation
