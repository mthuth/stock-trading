#!/usr/bin/env python3
"""Architecture guardrails for the three-track package boundary."""

from __future__ import annotations

import ast
import importlib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def module_source(module_path: str) -> str:
    return (ROOT / module_path).read_text()


def imported_modules(module_path: str) -> set[str]:
    tree = ast.parse(module_source(module_path), filename=module_path)
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def assert_no_imports(testcase: unittest.TestCase, module_path: str, banned_roots: tuple[str, ...]) -> None:
    imports = imported_modules(module_path)
    for imported in imports:
        for banned in banned_roots:
            testcase.assertFalse(
                imported == banned or imported.startswith(f"{banned}."),
                f"{module_path} must not import {banned}; found {imported}",
            )


class PackageBoundaryTests(unittest.TestCase):
    def test_package_modules_import_without_test_path_mutation(self) -> None:
        for module_name in (
            "stock_trading.ingestion",
            "stock_trading.ingestion_workflows",
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
            "stock_trading.storage.connection",
            "stock_trading.storage.schema",
            "stock_trading.storage.csv_files",
            "stock_trading.storage.workflow_repository",
            "stock_trading.storage.provider_repository",
            "stock_trading.storage.recommendation_repository",
            "stock_trading.storage.evidence_repository",
            "stock_trading.storage.source_quality_repository",
            "stock_trading.storage.ingestion_plan_repository",
            "stock_trading.storage.synthesis_repository",
            "stock_trading.config",
            "stock_trading.provider_repository",
            "stock_trading.recommendation_repository",
            "stock_trading.verification_queue",
            "stock_trading.workflows",
            "stock_trading.workflows.daily",
            "stock_trading.workflows.steps",
            "stock_trading.cli.daily",
            "stock_trading.cli.run_analysis",
            "stock_trading.cli.render_report_context",
        ):
            importlib.import_module(module_name)

    def test_presentation_does_not_import_provider_or_scoring_internals(self) -> None:
        for module_path in ("stock_trading/presentation.py", "stock_trading/reporting/renderers.py"):
            assert_no_imports(
                self,
                module_path,
                (
                    "stock_trading.provider_client",
                    "stock_trading.analysis_engine",
                    "stock_trading.storage",
                    "scripts.generate_daily_report",
                ),
            )

    def test_ingestion_does_not_render_reports(self) -> None:
        for module_path in ("stock_trading/ingestion.py", "stock_trading/ingestion_workflows.py"):
            assert_no_imports(
                self,
                module_path,
                (
                    "stock_trading.presentation",
                    "stock_trading.reporting",
                    "stock_trading.analysis_scoring",
                    "stock_trading.analysis_context",
                    "stock_trading.analysis_engine",
                ),
            )

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
            assert_no_imports(
                self,
                module_path,
                (
                    "stock_trading.provider_client",
                    "stock_trading.cli",
                    "stock_trading.presentation",
                    "scripts",
                ),
            )


if __name__ == "__main__":
    unittest.main()
