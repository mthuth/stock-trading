#!/usr/bin/env python3
"""Regression tests for SQLite migration and workflow manifest primitives."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


from stock_trading import storage as subject


class EngineCommonResilienceTests(unittest.TestCase):
    def test_migrations_are_idempotent_and_create_workflow_tables(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            db_file = data_dir / "stock_trading.sqlite"
            with patch.object(subject, "DATA_DIR", data_dir), patch.object(subject, "DB_FILE", db_file):
                conn = subject.init_db()
                conn.close()
                conn = subject.init_db()
                rows = conn.execute(
                    "SELECT version, name FROM schema_migrations ORDER BY version"
                ).fetchall()
                tables = {
                    row[0]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    ).fetchall()
                }
                conn.close()

        self.assertIn((1, "base stock research engine schema"), rows)
        self.assertIn((2, "local batch workflow run manifest"), rows)
        self.assertIn((3, "raw ingestion ledger and shadow score signals"), rows)
        self.assertIn((4, "analysis run boundary"), rows)
        self.assertIn((5, "persisted decision insights and verification queue"), rows)
        self.assertIn((6, "source quality metrics"), rows)
        self.assertIn((7, "source relevance confidence buckets"), rows)
        self.assertIn((8, "ingestion freshness and backfill planning"), rows)
        self.assertIn((9, "evidence event clustering"), rows)
        self.assertIn((10, "synthesis readiness and evidence review queue"), rows)
        self.assertIn((11, "etrade holdings snapshot tables"), rows)
        self.assertIn("workflow_runs", tables)
        self.assertIn("workflow_step_runs", tables)
        self.assertIn("etrade_sync_runs", tables)
        self.assertIn("etrade_positions", tables)
        self.assertIn("raw_ingestion_payloads", tables)
        self.assertIn("score_signals", tables)
        self.assertIn("analysis_runs", tables)
        self.assertIn("decision_insights", tables)
        self.assertIn("verification_queue_items", tables)
        self.assertIn("source_quality_metrics", tables)
        self.assertIn("ingestion_run_plan", tables)
        self.assertIn("ingestion_backfill_queue", tables)
        self.assertIn("evidence_event_clusters", tables)
        self.assertIn("evidence_event_members", tables)
        self.assertIn("evidence_review_queue", tables)
        self.assertIn("synthesis_readiness", tables)

    def test_recommendation_run_links_to_workflow_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            db_file = data_dir / "stock_trading.sqlite"
            with patch.object(subject, "DATA_DIR", data_dir), patch.object(subject, "DB_FILE", db_file):
                workflow_run_id = subject.start_workflow_run("test", ["python3", "scripts/run_daily.py"])
                recommendation_run_id = subject.record_recommendation_run(
                    "2026-05-28",
                    data_dir / "report.md",
                    data_dir / "dashboard.html",
                    data_dir / "report.csv",
                    data_dir / "email.txt",
                    50000,
                    2500,
                    workflow_run_id=workflow_run_id,
                )
                conn = subject.init_db()
                row = conn.execute(
                    "SELECT workflow_run_id FROM recommendation_runs WHERE id = ?",
                    (recommendation_run_id,),
                ).fetchone()
                conn.close()

        self.assertEqual(row[0], workflow_run_id)

    def test_provider_payload_records_raw_ingestion_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            db_file = data_dir / "stock_trading.sqlite"
            with (
                patch.object(subject, "DATA_DIR", data_dir),
                patch.object(subject, "RAW_PAYLOAD_DIR", data_dir / "raw_payloads"),
                patch.object(subject, "DB_FILE", db_file),
            ):
                payload_id = subject.record_provider_payload(
                    "Unit Provider",
                    "unit_endpoint",
                    "NVDA",
                    "ok",
                    payload_json={"hello": "world"},
                )
                conn = subject.init_db()
                payload_row = conn.execute(
                    "SELECT payload_ref FROM provider_payloads WHERE id = ?",
                    (payload_id,),
                ).fetchone()
                raw_row = conn.execute(
                    """
                    SELECT provider, endpoint, symbol, status, payload_size, payload_inline
                    FROM raw_ingestion_payloads
                    """
                ).fetchone()
                conn.close()

        self.assertTrue(str(payload_row[0]).startswith("raw_ingestion_payloads:"))
        self.assertEqual(raw_row[0], "Unit Provider")
        self.assertEqual(raw_row[1], "unit_endpoint")
        self.assertEqual(raw_row[2], "NVDA")
        self.assertEqual(raw_row[3], "ok")
        self.assertGreater(raw_row[4], 0)
        self.assertIn("hello", raw_row[5])

    def test_score_signal_rebuild_replaces_shadow_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            db_file = data_dir / "stock_trading.sqlite"
            row = {
                "symbol": "NVDA",
                "signal_date": "2026-05-28",
                "signal_type": "momentum",
                "metric_name": "unit_signal",
                "raw_value": 1.0,
                "normalized_delta": 2.0,
                "confidence": "medium",
                "source_name": "Unit",
                "source_type": "test",
                "source_ref": "unit:1",
                "freshness_days": 0,
                "signal_mode": "shadow",
                "notes": "test",
            }
            with patch.object(subject, "DATA_DIR", data_dir), patch.object(subject, "DB_FILE", db_file):
                subject.record_score_signals([row], rebuild=True)
                updated = dict(row)
                updated["normalized_delta"] = 3.0
                subject.record_score_signals([updated], rebuild=True)
                conn = subject.init_db()
                rows = conn.execute(
                    "SELECT normalized_delta FROM score_signals WHERE symbol = 'NVDA'"
                ).fetchall()
                conn.close()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], 3.0)

    def test_analysis_run_records_output_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            db_file = data_dir / "stock_trading.sqlite"
            with patch.object(subject, "DATA_DIR", data_dir), patch.object(subject, "DB_FILE", db_file):
                analysis_run_id = subject.record_analysis_run(
                    recommendation_run_id=None,
                    model_version="unit-model",
                    config_version="unit-config",
                    input_snapshot={"symbols": ["NVDA"]},
                    output_counts={"recommendations": 1},
                    context_path="reports/analysis-context-unit.json",
                )
                conn = subject.init_db()
                row = conn.execute(
                    "SELECT model_version, output_counts_json, context_path FROM analysis_runs WHERE id = ?",
                    (analysis_run_id,),
                ).fetchone()
                conn.close()

        self.assertEqual(row[0], "unit-model")
        self.assertIn("recommendations", row[1])
        self.assertEqual(row[2], "reports/analysis-context-unit.json")

    def test_decision_insights_and_verification_queue_are_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            db_file = data_dir / "stock_trading.sqlite"
            insight_row = {
                "run_id": 7,
                "report_date": "2026-05-29",
                "rank": 1,
                "symbol": "NVDA",
                "action": "Add",
                "score": 82.5,
                "insight_type": "Verification Needed",
                "headline": "NVDA needs one verification pull.",
                "why_it_matters": "High score near action.",
                "supporting_data": "Score and target support.",
                "risk_or_uncertainty": "Primary-source gap.",
                "next_check": "scripts/ingest_sec.py + scripts/ingest_official_ir.py",
                "what_would_change_the_view": "Primary-source evidence resolves the gap.",
                "source_ref": "recommendation_run:7",
            }
            queue_row = {
                "run_id": 7,
                "report_date": "2026-05-29",
                "symbol": "NVDA",
                "priority_rank": 1,
                "insight_type": "Verification Needed",
                "reason": "Top candidate lacks primary-source evidence",
                "expected_score_impact": 1.75,
                "next_check": "scripts/ingest_sec.py + scripts/ingest_official_ir.py",
                "command_mapping": "scripts/ingest_sec.py NVDA; scripts/ingest_official_ir.py --symbols NVDA",
                "automation_mode": "auto",
                "status": "queued",
                "result_summary": "",
                "workflow_step_id": None,
                "started_at": None,
                "completed_at": None,
            }
            with patch.object(subject, "DATA_DIR", data_dir), patch.object(subject, "DB_FILE", db_file):
                self.assertEqual(subject.record_decision_insights([insight_row]), 1)
                self.assertEqual(subject.record_verification_queue_items([queue_row]), 1)
                insights = subject.latest_decision_insights_by_symbol()
                queue = subject.latest_open_verification_queue()
                subject.update_verification_queue_item_status(
                    int(queue[0]["id"]),
                    "completed",
                    "unit complete",
                    started=True,
                    completed=True,
                )
                latest_queue = subject.latest_verification_queue()

        self.assertEqual(insights["NVDA"][0]["insight_type"], "Verification Needed")
        self.assertEqual(queue[0]["symbol"], "NVDA")
        self.assertEqual(latest_queue[0]["status"], "completed")
        self.assertEqual(latest_queue[0]["result_summary"], "unit complete")


if __name__ == "__main__":
    unittest.main()
