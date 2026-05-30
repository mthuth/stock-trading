#!/usr/bin/env python3
"""Source-quality metric repository functions."""

from __future__ import annotations

from typing import List, Mapping

from stock_trading.storage.connection import init_db

def record_source_quality_metrics(rows: List[Mapping[str, object]], rebuild: bool = False) -> int:
    if not rows and not rebuild:
        return 0
    conn = init_db()
    inserted = 0
    with conn:
        if rebuild:
            conn.execute("DELETE FROM source_quality_metrics")
        for row in rows:
            normalized = {
                "confidence_bucket_summary": "",
                "low_confidence_matches": 0,
                **dict(row),
            }
            cursor = conn.execute(
                """
                INSERT OR REPLACE INTO source_quality_metrics (
                    metric_date, source_name, source_category, records_seen,
                    records_inserted, duplicate_records, raw_payloads, ok_runs,
                    error_runs, blocked_runs, total_evidence, tagged_evidence,
                    tag_count, matched_symbol_count, avg_tag_confidence, tag_rate,
                    latest_success, latest_issue, latest_evidence_at,
                    days_since_success, top_matched_terms, match_reason_summary,
                    confidence_bucket_summary, low_confidence_matches,
                    feedback_delta, quality_label, notes
                )
                VALUES (
                    :metric_date, :source_name, :source_category, :records_seen,
                    :records_inserted, :duplicate_records, :raw_payloads, :ok_runs,
                    :error_runs, :blocked_runs, :total_evidence, :tagged_evidence,
                    :tag_count, :matched_symbol_count, :avg_tag_confidence, :tag_rate,
                    :latest_success, :latest_issue, :latest_evidence_at,
                    :days_since_success, :top_matched_terms, :match_reason_summary,
                    :confidence_bucket_summary, :low_confidence_matches,
                    :feedback_delta, :quality_label, :notes
                )
                """,
                normalized,
            )
            inserted += cursor.rowcount
    conn.close()
    return inserted
