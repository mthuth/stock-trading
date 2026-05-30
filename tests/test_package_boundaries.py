#!/usr/bin/env python3
"""Architecture guardrails for the three-track package boundary."""

from __future__ import annotations

import importlib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def module_source(module_path: str) -> str:
    return (ROOT / module_path).read_text()


class PackageBoundaryTests(unittest.TestCase):
    def test_package_modules_import_without_test_path_mutation(self) -> None:
        for module_name in (
            "stock_trading.ingestion",
            "stock_trading.analysis",
            "stock_trading.analysis_engine",
            "stock_trading.analysis_context",
            "stock_trading.analysis_insights",
            "stock_trading.analysis_models",
            "stock_trading.analysis_scoring",
            "stock_trading.analysis_snapshot",
            "stock_trading.analysis_targets",
            "stock_trading.presentation",
            "stock_trading.reporting.renderers",
            "stock_trading.storage",
            "stock_trading.config",
            "stock_trading.provider_repository",
            "stock_trading.recommendation_repository",
            "stock_trading.verification_queue",
            "stock_trading.cli.daily",
            "stock_trading.cli.run_analysis",
            "stock_trading.cli.render_report_context",
        ):
            importlib.import_module(module_name)

    def test_presentation_does_not_import_provider_or_scoring_internals(self) -> None:
        for module_path in ("stock_trading/presentation.py", "stock_trading/reporting/renderers.py"):
            source = module_source(module_path)
            for banned in (
                "provider_client",
                "fetch_json",
                "generate_daily_report",
                "score_stock",
                "stock_trading.storage",
                "record_recommendation",
                "init_db",
            ):
                self.assertNotIn(banned, source)

    def test_ingestion_does_not_render_reports(self) -> None:
        source = module_source("stock_trading/ingestion.py")
        for banned in ("render_report_context", "presentation", "generate_daily_report.py"):
            self.assertNotIn(banned, source)

    def test_analysis_does_not_import_provider_client(self) -> None:
        for module_path in (
            "stock_trading/analysis.py",
            "stock_trading/analysis_context.py",
            "stock_trading/analysis_engine.py",
            "stock_trading/analysis_insights.py",
            "stock_trading/analysis_models.py",
            "stock_trading/analysis_scoring.py",
            "stock_trading/analysis_snapshot.py",
            "stock_trading/analysis_targets.py",
        ):
            source = module_source(module_path)
            for banned in ("provider_client", "fetch_json", "scripts.generate_daily_report", "from scripts"):
                self.assertNotIn(banned, source)


if __name__ == "__main__":
    unittest.main()
