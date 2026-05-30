"""Recommendation, analysis, and signal repository boundary."""

from stock_trading.storage import (  # noqa: F401
    latest_analysis_run,
    latest_decision_insights_by_symbol,
    latest_open_verification_queue,
    latest_verification_queue,
    record_analysis_run,
    record_blended_targets,
    record_decision_insights,
    record_recommendation_run,
    record_recommendation_scores,
    record_score_signals,
    record_target_sources,
    record_verification_queue_items,
    update_verification_queue_item_status,
)
