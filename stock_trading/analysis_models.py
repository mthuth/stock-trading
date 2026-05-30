#!/usr/bin/env python3
"""Shared analysis model aliases.

The rules engine still owns the concrete dataclasses during this extraction
step. These aliases give the analysis track stable import points so future
model edits do not require consumers to import the engine monolith.
"""

from __future__ import annotations

from stock_trading.analysis_engine import (
    BlendedTarget,
    DecisionInsight,
    InsightSignal,
    ResearchInput,
    ScoreBreakdown,
)

__all__ = [
    "BlendedTarget",
    "DecisionInsight",
    "InsightSignal",
    "ResearchInput",
    "ScoreBreakdown",
]
