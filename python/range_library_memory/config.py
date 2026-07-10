"""Configuration helpers for Range Library Memory storage."""

from __future__ import annotations

import os
from pathlib import Path

ENV_DB_PATH = "FXTM_RANGE_LIBRARY_MEMORY_DB"
DEFAULT_DB_PATH = Path("data/python_database/range_library_memory.sqlite3")


def resolve_db_path(cli_db_path: str | Path | None = None) -> Path:
    """Resolve the SQLite path with CLI, environment, then default precedence."""
    if cli_db_path:
        return Path(cli_db_path).expanduser()

    env_db_path = os.environ.get(ENV_DB_PATH)
    if env_db_path:
        return Path(env_db_path).expanduser()

    return DEFAULT_DB_PATH
