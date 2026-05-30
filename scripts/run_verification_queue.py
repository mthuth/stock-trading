#!/usr/bin/env python3
"""Compatibility wrapper for stock_trading.verification_queue."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from stock_trading import verification_queue as _verification_queue  # noqa: E402


def main() -> int:
    return _verification_queue.main()


if __name__ == "__main__":
    sys.exit(main())
