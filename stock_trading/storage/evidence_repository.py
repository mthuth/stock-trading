#!/usr/bin/env python3
"""Research evidence, tagging, identifiers, and review repositories."""

from __future__ import annotations

from datetime import datetime
from typing import List, Mapping

from stock_trading.storage.connection import init_db

def record_evidence_event_clusters(
    clusters: List[Mapping[str, object]],
    members_by_event_key: Mapping[str, List[Mapping[str, object]]],
    rebuild: bool = False,
) -> int:
    if not clusters and not rebuild:
        return 0
    conn = init_db()
    inserted = 0
    with conn:
        if rebuild:
            conn.execute("DELETE FROM evidence_event_members")
            conn.execute("DELETE FROM evidence_event_clusters")
        for cluster in clusters:
            cursor = conn.execute(
                """
                INSERT OR REPLACE INTO evidence_event_clusters (
                    event_date, symbol, event_key, event_type, headline, summary,
                    corroboration_label, source_count, evidence_count,
                    independent_source_count, primary_source_count,
                    company_source_count, opinion_source_count, latest_evidence_at,
                    confidence, notes
                )
                VALUES (
                    :event_date, :symbol, :event_key, :event_type, :headline, :summary,
                    :corroboration_label, :source_count, :evidence_count,
                    :independent_source_count, :primary_source_count,
                    :company_source_count, :opinion_source_count, :latest_evidence_at,
                    :confidence, :notes
                )
                """,
                cluster,
            )
            inserted += cursor.rowcount
            cluster_id = conn.execute(
                """
                SELECT id
                FROM evidence_event_clusters
                WHERE symbol = ? AND event_key = ?
                """,
                (cluster["symbol"], cluster["event_key"]),
            ).fetchone()[0]
            conn.execute(
                "DELETE FROM evidence_event_members WHERE cluster_id = ?",
                (cluster_id,),
            )
            for member in members_by_event_key.get(str(cluster["event_key"]), []):
                values = {"cluster_id": cluster_id, **dict(member)}
                conn.execute(
                    """
                    INSERT OR IGNORE INTO evidence_event_members (
                        cluster_id, evidence_id, source_name, source_family,
                        match_reason, confidence_bucket
                    )
                    VALUES (
                        :cluster_id, :evidence_id, :source_name, :source_family,
                        :match_reason, :confidence_bucket
                    )
                    """,
                    values,
                )
    conn.close()
    return inserted

def record_evidence_review_queue(rows: List[Mapping[str, object]], rebuild: bool = False) -> int:
    if not rows and not rebuild:
        return 0
    conn = init_db()
    inserted = 0
    with conn:
        if rebuild:
            conn.execute("DELETE FROM evidence_review_queue")
        for row in rows:
            cursor = conn.execute(
                """
                INSERT OR REPLACE INTO evidence_review_queue (
                    cluster_id, symbol, event_key, event_type, review_status,
                    priority_rank, review_reason, recommended_action,
                    corroboration_label, confidence, source_count, evidence_count,
                    latest_evidence_at
                )
                VALUES (
                    :cluster_id, :symbol, :event_key, :event_type, :review_status,
                    :priority_rank, :review_reason, :recommended_action,
                    :corroboration_label, :confidence, :source_count, :evidence_count,
                    :latest_evidence_at
                )
                """,
                row,
            )
            inserted += cursor.rowcount
    conn.close()
    return inserted

def record_research_evidence(rows: List[Mapping[str, object]]) -> int:
    if not rows:
        return 0
    conn = init_db()
    inserted = 0
    with conn:
        for row in rows:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO research_evidence (
                    run_id, symbol, evidence_type, source_name, source_type, source_url,
                    provider_endpoint, provider_id, source_timestamp, title, summary,
                    raw_text_ref, confidence, corroboration_status, user_feedback
                )
                VALUES (
                    :run_id, :symbol, :evidence_type, :source_name, :source_type, :source_url,
                    :provider_endpoint, :provider_id, :source_timestamp, :title, :summary,
                    :raw_text_ref, :confidence, :corroboration_status, :user_feedback
                )
                """,
                row,
            )
            inserted += cursor.rowcount
    conn.close()
    return inserted

def record_evidence_symbol_tags(rows: List[Mapping[str, object]]) -> int:
    if not rows:
        return 0
    conn = init_db()
    inserted = 0
    with conn:
        for row in rows:
            values = dict(row)
            values.setdefault("confidence_bucket", "low")
            values.setdefault("match_reason", values.get("match_type", ""))
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO evidence_symbol_tags (
                    evidence_id, symbol, match_type, matched_text, confidence,
                    confidence_bucket, match_reason
                )
                VALUES (
                    :evidence_id, :symbol, :match_type, :matched_text, :confidence,
                    COALESCE(:confidence_bucket, 'low'), COALESCE(:match_reason, :match_type)
                )
                """,
                values,
            )
            inserted += cursor.rowcount
    conn.close()
    return inserted

def upsert_company_identifier(
    symbol: str,
    cik: str,
    company_name: str,
    exchange: str = "",
    source_name: str = "SEC company_tickers",
) -> None:
    conn = init_db()
    with conn:
        conn.execute(
            """
            INSERT INTO company_identifiers (
                symbol, cik, company_name, exchange, source_name, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                cik = excluded.cik,
                company_name = excluded.company_name,
                exchange = excluded.exchange,
                source_name = excluded.source_name,
                updated_at = excluded.updated_at
            """,
            (
                symbol.upper(),
                cik,
                company_name,
                exchange,
                source_name,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
    conn.close()
