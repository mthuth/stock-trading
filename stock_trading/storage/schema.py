#!/usr/bin/env python3
"""SQLite schema ownership and idempotent migrations."""

from __future__ import annotations

import sqlite3

from stock_trading.storage.connection import SCHEMA_VERSION, ensure_column

def apply_schema_migrations(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS workflow_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            finished_at TEXT,
            trigger TEXT NOT NULL DEFAULT 'manual',
            command TEXT,
            status TEXT NOT NULL DEFAULT 'running',
            summary TEXT,
            error_class TEXT,
            message TEXT,
            artifacts_json TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS workflow_step_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workflow_run_id INTEGER,
            step_name TEXT NOT NULL,
            command TEXT,
            started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            finished_at TEXT,
            status TEXT NOT NULL DEFAULT 'running',
            required INTEGER NOT NULL DEFAULT 1,
            retry_count INTEGER NOT NULL DEFAULT 0,
            exit_code INTEGER,
            error_class TEXT,
            message TEXT,
            artifacts_json TEXT,
            FOREIGN KEY (workflow_run_id) REFERENCES workflow_runs(id)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_workflow_step_runs_workflow
        ON workflow_step_runs(workflow_run_id, id)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS etrade_sync_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            synced_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            environment TEXT NOT NULL,
            account_id_key TEXT NOT NULL,
            account_type TEXT,
            institution_type TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS etrade_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            security_type TEXT,
            quantity REAL,
            last_price REAL,
            market_value REAL,
            price_paid REAL,
            total_gain REAL,
            total_gain_pct REAL,
            pct_of_portfolio REAL,
            position_type TEXT,
            raw_json TEXT NOT NULL,
            FOREIGN KEY (run_id) REFERENCES etrade_sync_runs(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS provider_refresh_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            refreshed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            provider TEXT NOT NULL,
            status TEXT NOT NULL,
            message TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS provider_field_status (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            provider TEXT NOT NULL,
            field_name TEXT NOT NULL,
            status TEXT NOT NULL,
            message TEXT,
            FOREIGN KEY (run_id) REFERENCES provider_refresh_runs(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS source_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            source_name TEXT NOT NULL,
            symbol TEXT,
            feedback_type TEXT NOT NULL,
            rating_delta REAL DEFAULT 0,
            notes TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS recommendation_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            report_date TEXT,
            symbol TEXT NOT NULL,
            feedback_type TEXT NOT NULL,
            notes TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS manual_trade_journal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            decision_date TEXT NOT NULL,
            symbol TEXT NOT NULL,
            action_taken TEXT NOT NULL,
            amount REAL,
            shares REAL,
            price REAL,
            rationale TEXT,
            recommendation_run_id INTEGER,
            report_date TEXT,
            notes TEXT,
            FOREIGN KEY (recommendation_run_id) REFERENCES recommendation_runs(id)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_manual_trade_journal_symbol_date
        ON manual_trade_journal(symbol, report_date, decision_date)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS recommendation_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            generated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            report_date TEXT NOT NULL,
            report_path TEXT,
            dashboard_path TEXT,
            csv_path TEXT,
            email_path TEXT,
            workflow_run_id INTEGER,
            account_value REAL,
            monthly_contribution REAL,
            notes TEXT,
            FOREIGN KEY (workflow_run_id) REFERENCES workflow_runs(id)
        )
        """
    )
    ensure_column(conn, "recommendation_runs", "workflow_run_id", "INTEGER")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS target_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            run_id INTEGER,
            symbol TEXT NOT NULL,
            target_type TEXT NOT NULL,
            source_name TEXT NOT NULL,
            source_type TEXT NOT NULL,
            target_price REAL NOT NULL,
            target_low REAL,
            target_high REAL,
            current_price REAL,
            upside_pct REAL,
            as_of_date TEXT,
            freshness_days INTEGER,
            confidence TEXT,
            provider_endpoint TEXT,
            raw_payload_ref TEXT,
            notes TEXT,
            FOREIGN KEY (run_id) REFERENCES recommendation_runs(id)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_target_sources_symbol_run
        ON target_sources(symbol, run_id)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_target_sources_source_type
        ON target_sources(source_name, target_type)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS blended_targets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            run_id INTEGER,
            symbol TEXT NOT NULL,
            blended_target REAL NOT NULL,
            target_low REAL,
            target_high REAL,
            current_price REAL,
            upside_pct REAL,
            target_confidence TEXT NOT NULL,
            source_count INTEGER NOT NULL DEFAULT 0,
            blend_status TEXT NOT NULL,
            weights_json TEXT,
            notes TEXT,
            FOREIGN KEY (run_id) REFERENCES recommendation_runs(id)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_blended_targets_symbol_run
        ON blended_targets(symbol, run_id)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS recommendation_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            run_id INTEGER,
            report_date TEXT NOT NULL,
            symbol TEXT NOT NULL,
            company TEXT,
            sleeve TEXT,
            trade_type TEXT,
            action TEXT NOT NULL,
            score REAL NOT NULL,
            current_price REAL,
            target_price REAL,
            upside_pct REAL,
            target_confidence TEXT,
            data_status TEXT,
            score_breakdown TEXT,
            rationale TEXT,
            FOREIGN KEY (run_id) REFERENCES recommendation_runs(id)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_recommendation_scores_symbol_run
        ON recommendation_scores(symbol, run_id)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS research_evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            run_id INTEGER,
            symbol TEXT NOT NULL,
            evidence_type TEXT NOT NULL,
            source_name TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_url TEXT,
            provider_endpoint TEXT,
            provider_id TEXT,
            source_timestamp TEXT,
            fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            title TEXT,
            summary TEXT,
            raw_text_ref TEXT,
            confidence TEXT,
            corroboration_status TEXT,
            user_feedback TEXT,
            UNIQUE(symbol, source_name, evidence_type, provider_id, source_url, source_timestamp),
            FOREIGN KEY (run_id) REFERENCES recommendation_runs(id)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_research_evidence_symbol_created
        ON research_evidence(symbol, created_at)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_research_evidence_source_type
        ON research_evidence(source_name, evidence_type)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS evidence_symbol_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            evidence_id INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            match_type TEXT NOT NULL,
            matched_text TEXT NOT NULL,
            confidence REAL NOT NULL DEFAULT 0.0,
            confidence_bucket TEXT NOT NULL DEFAULT 'low',
            match_reason TEXT,
            UNIQUE(evidence_id, symbol, matched_text),
            FOREIGN KEY (evidence_id) REFERENCES research_evidence(id)
        )
        """
    )
    ensure_column(conn, "evidence_symbol_tags", "confidence_bucket", "TEXT NOT NULL DEFAULT 'low'")
    ensure_column(conn, "evidence_symbol_tags", "match_reason", "TEXT")
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_evidence_symbol_tags_symbol_created
        ON evidence_symbol_tags(symbol, created_at)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_evidence_symbol_tags_evidence
        ON evidence_symbol_tags(evidence_id)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS provider_payloads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            provider TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            symbol TEXT,
            payload_ref TEXT,
            payload_json TEXT,
            status TEXT NOT NULL,
            message TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS raw_ingestion_payloads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            provider TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            symbol TEXT,
            request_hash TEXT,
            status TEXT NOT NULL,
            content_hash TEXT,
            payload_size INTEGER NOT NULL DEFAULT 0,
            payload_ref TEXT,
            payload_inline TEXT,
            content_type TEXT,
            message TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_raw_ingestion_provider_endpoint
        ON raw_ingestion_payloads(provider, endpoint, symbol, created_at)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_raw_ingestion_content_hash
        ON raw_ingestion_payloads(content_hash)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS score_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            symbol TEXT NOT NULL,
            signal_date TEXT NOT NULL,
            signal_type TEXT NOT NULL,
            metric_name TEXT NOT NULL,
            raw_value REAL,
            normalized_delta REAL NOT NULL DEFAULT 0,
            confidence TEXT NOT NULL DEFAULT 'low',
            source_name TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_ref TEXT,
            freshness_days INTEGER,
            signal_mode TEXT NOT NULL DEFAULT 'shadow',
            notes TEXT,
            UNIQUE(symbol, signal_date, signal_type, metric_name, source_name, source_ref, signal_mode)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_score_signals_symbol_date
        ON score_signals(symbol, signal_date, signal_mode)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_score_signals_type
        ON score_signals(signal_type, metric_name)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS source_quality_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            metric_date TEXT NOT NULL,
            source_name TEXT NOT NULL,
            source_category TEXT,
            records_seen INTEGER NOT NULL DEFAULT 0,
            records_inserted INTEGER NOT NULL DEFAULT 0,
            duplicate_records INTEGER NOT NULL DEFAULT 0,
            raw_payloads INTEGER NOT NULL DEFAULT 0,
            ok_runs INTEGER NOT NULL DEFAULT 0,
            error_runs INTEGER NOT NULL DEFAULT 0,
            blocked_runs INTEGER NOT NULL DEFAULT 0,
            total_evidence INTEGER NOT NULL DEFAULT 0,
            tagged_evidence INTEGER NOT NULL DEFAULT 0,
            tag_count INTEGER NOT NULL DEFAULT 0,
            matched_symbol_count INTEGER NOT NULL DEFAULT 0,
            avg_tag_confidence REAL,
            tag_rate REAL NOT NULL DEFAULT 0,
            latest_success TEXT,
            latest_issue TEXT,
            latest_evidence_at TEXT,
            days_since_success REAL,
            top_matched_terms TEXT,
            match_reason_summary TEXT,
            confidence_bucket_summary TEXT,
            low_confidence_matches INTEGER NOT NULL DEFAULT 0,
            feedback_delta REAL NOT NULL DEFAULT 0,
            quality_label TEXT NOT NULL,
            notes TEXT,
            UNIQUE(metric_date, source_name)
        )
        """
    )
    ensure_column(conn, "source_quality_metrics", "confidence_bucket_summary", "TEXT")
    ensure_column(conn, "source_quality_metrics", "low_confidence_matches", "INTEGER NOT NULL DEFAULT 0")
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_source_quality_metrics_source_date
        ON source_quality_metrics(source_name, metric_date)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_source_quality_metrics_label
        ON source_quality_metrics(quality_label, metric_date)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ingestion_run_plan (
            source_name TEXT PRIMARY KEY,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            source_category TEXT,
            source_tier TEXT,
            cadence_days INTEGER NOT NULL DEFAULT 1,
            latest_attempt TEXT,
            latest_success TEXT,
            next_run_at TEXT,
            cooldown_until TEXT,
            due_status TEXT NOT NULL DEFAULT 'due',
            priority_rank INTEGER NOT NULL DEFAULT 999,
            records INTEGER NOT NULL DEFAULT 0,
            raw_payloads INTEGER NOT NULL DEFAULT 0,
            duplicate_records INTEGER NOT NULL DEFAULT 0,
            latest_issue TEXT,
            run_command TEXT,
            reason TEXT,
            UNIQUE(source_name)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ingestion_run_plan_due
        ON ingestion_run_plan(due_status, priority_rank, next_run_at)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ingestion_backfill_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            source_name TEXT NOT NULL,
            symbol TEXT NOT NULL DEFAULT 'ALL',
            backfill_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            priority_rank INTEGER NOT NULL DEFAULT 999,
            desired_window_days INTEGER NOT NULL DEFAULT 30,
            covered_since TEXT,
            covered_until TEXT,
            record_count INTEGER NOT NULL DEFAULT 0,
            next_action TEXT,
            command TEXT,
            reason TEXT,
            UNIQUE(source_name, symbol, backfill_type)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ingestion_backfill_queue_status
        ON ingestion_backfill_queue(status, priority_rank, source_name)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS evidence_event_clusters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            event_date TEXT NOT NULL,
            symbol TEXT NOT NULL,
            event_key TEXT NOT NULL,
            event_type TEXT NOT NULL,
            headline TEXT NOT NULL,
            summary TEXT,
            corroboration_label TEXT NOT NULL,
            source_count INTEGER NOT NULL DEFAULT 0,
            evidence_count INTEGER NOT NULL DEFAULT 0,
            independent_source_count INTEGER NOT NULL DEFAULT 0,
            primary_source_count INTEGER NOT NULL DEFAULT 0,
            company_source_count INTEGER NOT NULL DEFAULT 0,
            opinion_source_count INTEGER NOT NULL DEFAULT 0,
            latest_evidence_at TEXT,
            confidence TEXT NOT NULL DEFAULT 'low',
            notes TEXT,
            UNIQUE(symbol, event_key)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_evidence_event_clusters_symbol_date
        ON evidence_event_clusters(symbol, event_date)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS evidence_event_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cluster_id INTEGER NOT NULL,
            evidence_id INTEGER NOT NULL,
            source_name TEXT NOT NULL,
            source_family TEXT NOT NULL,
            match_reason TEXT,
            confidence_bucket TEXT,
            UNIQUE(cluster_id, evidence_id),
            FOREIGN KEY (cluster_id) REFERENCES evidence_event_clusters(id),
            FOREIGN KEY (evidence_id) REFERENCES research_evidence(id)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_evidence_event_members_evidence
        ON evidence_event_members(evidence_id)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS evidence_review_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            cluster_id INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            event_key TEXT NOT NULL,
            event_type TEXT NOT NULL,
            review_status TEXT NOT NULL,
            priority_rank INTEGER NOT NULL DEFAULT 999,
            review_reason TEXT,
            recommended_action TEXT,
            corroboration_label TEXT,
            confidence TEXT,
            source_count INTEGER NOT NULL DEFAULT 0,
            evidence_count INTEGER NOT NULL DEFAULT 0,
            latest_evidence_at TEXT,
            UNIQUE(cluster_id),
            FOREIGN KEY (cluster_id) REFERENCES evidence_event_clusters(id)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_evidence_review_queue_status
        ON evidence_review_queue(review_status, priority_rank, symbol)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS synthesis_readiness (
            symbol TEXT PRIMARY KEY,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            readiness_status TEXT NOT NULL,
            readiness_score REAL NOT NULL DEFAULT 0,
            ready_events INTEGER NOT NULL DEFAULT 0,
            needs_review_events INTEGER NOT NULL DEFAULT 0,
            needs_corroboration_events INTEGER NOT NULL DEFAULT 0,
            ignored_events INTEGER NOT NULL DEFAULT 0,
            primary_events INTEGER NOT NULL DEFAULT 0,
            independent_confirmed_events INTEGER NOT NULL DEFAULT 0,
            latest_event_at TEXT,
            packet_ref TEXT,
            notes TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS analysis_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            recommendation_run_id INTEGER,
            model_version TEXT NOT NULL,
            config_version TEXT,
            input_snapshot TEXT,
            output_counts_json TEXT,
            status TEXT NOT NULL DEFAULT 'ok',
            message TEXT,
            context_path TEXT,
            FOREIGN KEY (recommendation_run_id) REFERENCES recommendation_runs(id)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_analysis_runs_recommendation
        ON analysis_runs(recommendation_run_id)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS decision_insights (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            run_id INTEGER,
            report_date TEXT NOT NULL,
            rank INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            action TEXT NOT NULL,
            score REAL NOT NULL,
            insight_type TEXT NOT NULL,
            headline TEXT NOT NULL,
            why_it_matters TEXT,
            supporting_data TEXT,
            risk_or_uncertainty TEXT,
            next_check TEXT,
            what_would_change_the_view TEXT,
            source_ref TEXT,
            UNIQUE(run_id, symbol),
            FOREIGN KEY (run_id) REFERENCES recommendation_runs(id)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_decision_insights_symbol_run
        ON decision_insights(symbol, run_id)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_decision_insights_type
        ON decision_insights(insight_type, report_date)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS verification_queue_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            run_id INTEGER,
            report_date TEXT NOT NULL,
            symbol TEXT NOT NULL,
            priority_rank INTEGER NOT NULL,
            insight_type TEXT NOT NULL,
            reason TEXT NOT NULL,
            expected_score_impact REAL NOT NULL DEFAULT 0,
            next_check TEXT NOT NULL,
            command_mapping TEXT,
            automation_mode TEXT NOT NULL DEFAULT 'manual',
            status TEXT NOT NULL DEFAULT 'queued',
            result_summary TEXT,
            workflow_step_id INTEGER,
            started_at TEXT,
            completed_at TEXT,
            UNIQUE(run_id, symbol, next_check, reason),
            FOREIGN KEY (run_id) REFERENCES recommendation_runs(id),
            FOREIGN KEY (workflow_step_id) REFERENCES workflow_step_runs(id)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_verification_queue_status
        ON verification_queue_items(status, priority_rank, created_at)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_verification_queue_symbol
        ON verification_queue_items(symbol, run_id)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_provider_payloads_provider_symbol
        ON provider_payloads(provider, symbol, created_at)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS price_history (
            symbol TEXT NOT NULL,
            price_date TEXT NOT NULL,
            open REAL,
            high REAL,
            low REAL,
            close REAL NOT NULL,
            adjusted_close REAL,
            volume REAL,
            provider TEXT NOT NULL,
            fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (symbol, price_date, provider)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_price_history_symbol_date
        ON price_history(symbol, price_date)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS company_identifiers (
            symbol TEXT PRIMARY KEY,
            cik TEXT,
            company_name TEXT,
            exchange TEXT,
            source_name TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO schema_migrations (version, name)
        VALUES (?, ?)
        """,
        (1, "base stock research engine schema"),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO schema_migrations (version, name)
        VALUES (?, ?)
        """,
        (2, "local batch workflow run manifest"),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO schema_migrations (version, name)
        VALUES (?, ?)
        """,
        (3, "raw ingestion ledger and shadow score signals"),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO schema_migrations (version, name)
        VALUES (?, ?)
        """,
        (4, "analysis run boundary"),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO schema_migrations (version, name)
        VALUES (?, ?)
        """,
        (5, "persisted decision insights and verification queue"),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO schema_migrations (version, name)
        VALUES (?, ?)
        """,
        (6, "source quality metrics"),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO schema_migrations (version, name)
        VALUES (?, ?)
        """,
        (7, "source relevance confidence buckets"),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO schema_migrations (version, name)
        VALUES (?, ?)
        """,
        (8, "ingestion freshness and backfill planning"),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO schema_migrations (version, name)
        VALUES (?, ?)
        """,
        (9, "evidence event clustering"),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO schema_migrations (version, name)
        VALUES (?, ?)
        """,
        (10, "synthesis readiness and evidence review queue"),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO schema_migrations (version, name)
        VALUES (?, ?)
        """,
        (11, "etrade holdings snapshot tables"),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO schema_migrations (version, name)
        VALUES (?, ?)
        """,
        (12, "manual trade journal"),
    )
    conn.execute(
        """
        UPDATE schema_migrations
        SET name = 'raw ingestion ledger and shadow score signals'
        WHERE version = 3
          AND name != 'raw ingestion ledger and shadow score signals'
        """
    )
