from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from range_library_memory.cli import main
from range_library_memory.config import ENV_DB_PATH, resolve_db_path
from range_library_memory.db import connect
from range_library_memory.schema import REQUIRED_TABLES, init_schema


def table_names(db_path: Path) -> set[str]:
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    return {row[0] for row in rows}


def test_init_creates_sqlite_file(tmp_path: Path) -> None:
    db_path = tmp_path / "memory" / "range_library_memory.sqlite3"

    init_schema(db_path)

    assert db_path.is_file()


def test_init_creates_all_required_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "range_library_memory.sqlite3"

    init_schema(db_path)

    assert set(REQUIRED_TABLES).issubset(table_names(db_path))


def test_connection_enables_foreign_keys(tmp_path: Path) -> None:
    db_path = tmp_path / "range_library_memory.sqlite3"

    with connect(db_path, initialize=True) as connection:
        foreign_keys_enabled = connection.execute("PRAGMA foreign_keys").fetchone()[0]

    assert foreign_keys_enabled == 1


def test_init_twice_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "range_library_memory.sqlite3"

    init_schema(db_path)
    first_tables = table_names(db_path)
    init_schema(db_path)

    assert table_names(db_path) == first_tables
    assert set(REQUIRED_TABLES).issubset(first_tables)


def test_env_var_db_path_is_respected(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "env" / "range_library_memory.sqlite3"
    monkeypatch.setenv(ENV_DB_PATH, str(db_path))

    assert resolve_db_path() == db_path

    result = main(["init"])

    assert result == 0
    assert db_path.is_file()


def test_cli_db_path_takes_precedence_over_env_var(tmp_path: Path, monkeypatch) -> None:
    env_db_path = tmp_path / "env" / "range_library_memory.sqlite3"
    cli_db_path = tmp_path / "cli" / "range_library_memory.sqlite3"
    monkeypatch.setenv(ENV_DB_PATH, str(env_db_path))

    result = main(["init", "--db-path", str(cli_db_path)])

    assert result == 0
    assert cli_db_path.is_file()
    assert not env_db_path.exists()


def test_no_generated_database_file_in_package_tree() -> None:
    package_root = Path(__file__).resolve().parents[1]

    generated_databases = [
        path
        for pattern in ("*.sqlite", "*.sqlite3", "*.db")
        for path in package_root.rglob(pattern)
    ]

    assert generated_databases == []
