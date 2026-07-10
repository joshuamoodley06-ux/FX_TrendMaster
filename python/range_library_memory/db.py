"""SQLite connection helpers for Range Library Memory."""

from __future__ import annotations

import sqlite3
from pathlib import Path


def ensure_db_parent(db_path: str | Path) -> Path:
    """Create the database parent directory and return a Path instance."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def connect(db_path: str | Path, *, initialize: bool = False) -> sqlite3.Connection:
    """Open a SQLite connection and enable foreign-key enforcement."""
    path = ensure_db_parent(db_path) if initialize else Path(db_path)
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA foreign_keys = ON")
    return connection
