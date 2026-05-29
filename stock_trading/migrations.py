"""Database migration boundary."""

from stock_trading.storage import (  # noqa: F401
    DB_FILE,
    SCHEMA_VERSION,
    apply_schema_migrations,
    init_db,
)

