"""Recommendation, analysis, and signal repository boundary."""

from stock_trading.storage import (  # noqa: F401
    latest_analysis_run,
    record_analysis_run,
    record_blended_targets,
    record_recommendation_run,
    record_recommendation_scores,
    record_score_signals,
    record_target_sources,
)

