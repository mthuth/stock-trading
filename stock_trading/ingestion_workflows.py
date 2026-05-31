#!/usr/bin/env python3
"""In-process wrappers for local ingestion workflow scripts.

These functions preserve the existing script entrypoint behavior while letting
workflow orchestration call package-level functions instead of spawning Python
subprocesses for deterministic/local ingestion steps.
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any


@contextmanager
def _script_argv(argv: list[str]) -> Iterator[None]:
    previous = sys.argv[:]
    sys.argv = argv[:]
    try:
        yield
    finally:
        sys.argv = previous


def _exit_code(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    return int(value)


def _call_script_main(module_name: str, argv: list[str]) -> int:
    module = importlib.import_module(module_name)
    with _script_argv(argv):
        try:
            return _exit_code(module.main())
        except SystemExit as exc:
            return exc.code if isinstance(exc.code, int) else 1


def ingest_price_history() -> int:
    return _call_script_main(
        "scripts.ingest_price_history",
        ["scripts/ingest_price_history.py"],
    )


def ingest_public_research_feeds() -> int:
    return _call_script_main(
        "scripts.ingest_public_research_feeds",
        ["scripts/ingest_public_research_feeds.py"],
    )


def tag_research_evidence() -> int:
    return _call_script_main(
        "scripts.tag_research_evidence",
        ["scripts/tag_research_evidence.py"],
    )


def curate_source_depth() -> int:
    return _call_script_main(
        "scripts.curate_source_depth",
        ["scripts/curate_source_depth.py"],
    )


def cluster_evidence_events() -> int:
    return _call_script_main(
        "scripts.cluster_evidence_events",
        ["scripts/cluster_evidence_events.py", "--rebuild"],
    )


def prepare_synthesis_packets() -> int:
    return _call_script_main(
        "scripts.prepare_synthesis_packets",
        ["scripts/prepare_synthesis_packets.py", "--rebuild"],
    )


def score_source_quality() -> int:
    return _call_script_main(
        "scripts.score_source_quality",
        ["scripts/score_source_quality.py", "--rebuild"],
    )


def plan_ingestion_runs() -> int:
    return _call_script_main(
        "scripts.plan_ingestion_runs",
        ["scripts/plan_ingestion_runs.py", "--rebuild"],
    )
