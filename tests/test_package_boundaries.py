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
            "stock_trading.presentation",
            "stock_trading.storage",
            "stock_trading.config",
            "stock_trading.provider_repository",
            "stock_trading.recommendation_repository",
            "stock_trading.cli.daily",
            "stock_trading.cli.run_analysis",
            "stock_trading.cli.render_report_context",
        ):
            importlib.import_module(module_name)

    def test_presentation_does_not_import_provider_or_scoring_internals(self) -> None:
        source = module_source("stock_trading/presentation.py")
        for banned in ("provider_client", "fetch_json", "generate_daily_report", "score_stock"):
            self.assertNotIn(banned, source)

    def test_ingestion_does_not_render_reports(self) -> None:
        source = module_source("stock_trading/ingestion.py")
        for banned in ("render_report_context", "presentation", "generate_daily_report.py"):
            self.assertNotIn(banned, source)

    def test_analysis_does_not_import_provider_client(self) -> None:
        source = module_source("stock_trading/analysis.py")
        self.assertNotIn("provider_client", source)


if __name__ == "__main__":
    unittest.main()
