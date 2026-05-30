#!/usr/bin/env python3
"""Backward-compatible storage facade.

Existing imports from ``stock_trading.storage`` continue to work while the
implementation lives in focused connection, schema, CSV, and repository modules.
"""

from __future__ import annotations

import sys
import types

from stock_trading.storage import connection as _connection
from stock_trading.storage.connection import *  # noqa: F401,F403
from stock_trading.storage.csv_files import *  # noqa: F401,F403
from stock_trading.storage.evidence_repository import *  # noqa: F401,F403
from stock_trading.storage.ingestion_plan_repository import *  # noqa: F401,F403
from stock_trading.storage.provider_repository import *  # noqa: F401,F403
from stock_trading.storage.recommendation_repository import *  # noqa: F401,F403
from stock_trading.storage.schema import apply_schema_migrations  # noqa: F401
from stock_trading.storage.source_quality_repository import *  # noqa: F401,F403
from stock_trading.storage.synthesis_repository import *  # noqa: F401,F403
from stock_trading.storage.workflow_repository import *  # noqa: F401,F403

_FORWARDED_CONSTANTS = {
    "ROOT",
    "CONFIG_DIR",
    "DATA_DIR",
    "REPORTS_DIR",
    "RAW_PAYLOAD_DIR",
    "ENV_FILE",
    "DB_FILE",
    "RESEARCH_FILE",
    "TARGETS_FILE",
    "SOURCES_FILE",
    "SYMBOL_ALIASES_FILE",
    "SCHEMA_VERSION",
    "RAW_INLINE_LIMIT_BYTES",
}


class _StorageFacadeModule(types.ModuleType):
    def __setattr__(self, name: str, value: object) -> None:
        super().__setattr__(name, value)
        if name in _FORWARDED_CONSTANTS:
            setattr(_connection, name, value)


sys.modules[__name__].__class__ = _StorageFacadeModule
