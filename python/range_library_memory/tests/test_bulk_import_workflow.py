from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from range_library_memory.bulk_import import bulk_import_source_dir, json_files
from range_library_memory.cli import main
from range_library_memory.export_cases import export_cases

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
BASIC_FIXTURE = FIXTURE_DIR / "basic_import.json"
CURRENT_FIXTURE = FIXTURE_DIR / "current_fxtm_export_smoke.json"


def fetch_one(db_path: Path, query: str, params: tuple = ()) -> sqlite3.Row:
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(query, params).fetchone()
    assert row is not None
    return row


def count_rows(db_path: Path, table: str) -> int:
    return fetch_one(db_path, f"SELECT COUNT(*) AS count FROM {table}")["count"]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_fixture_folder(tmp_path: Path) -> Path:
    source_dir = tmp_path / "exports"
    nested_dir = source_dir / "nested"
    nested_dir.mkdir(parents=True)
    shutil.copyfile(CURRENT_FIXTURE, source_dir / "a_current.json")
    shutil.copyfile(BASIC_FIXTURE, nested_dir / "b_basic.json")
    (source_dir / "notes.txt").write_text("not json", encoding="utf-8")
    return source_dir


def test_bulk_import_imports_all_json_files_and_ignores_non_json(tmp_path: Path) -> None:
    source_dir = write_fixture_folder(tmp_path)
    db_path = tmp_path / "range_library_memory.sqlite3"

    summary = bulk_import_source_dir(db_path, source_dir, "fxtm_export")

    assert summary.files_seen == 2
    assert summary.files_imported == 2
    assert summary.files_failed == 0
    assert summary.total_ranges_seen == 4
    assert summary.total_events_seen == 6
    assert count_rows(db_path, "import_runs") == 2


def test_bulk_import_uses_deterministic_sorted_order(tmp_path: Path) -> None:
    source_dir = write_fixture_folder(tmp_path)
    db_path = tmp_path / "range_library_memory.sqlite3"

    summary = bulk_import_source_dir(db_path, source_dir, "fxtm_export")

    assert [Path(path).name for path in summary.imported_files] == ["a_current.json", "b_basic.json"]
    first_run = fetch_one(db_path, "SELECT source_path FROM import_runs ORDER BY id ASC LIMIT 1")
    assert Path(first_run["source_path"]).name == "a_current.json"
    assert [path.name for path in json_files(source_dir)] == ["a_current.json", "b_basic.json"]


def test_bulk_import_continues_after_bad_json_and_reports_failure(tmp_path: Path) -> None:
    source_dir = write_fixture_folder(tmp_path)
    (source_dir / "bad.json").write_text("{not valid json", encoding="utf-8")
    db_path = tmp_path / "range_library_memory.sqlite3"

    summary = bulk_import_source_dir(db_path, source_dir, "fxtm_export")

    assert summary.files_seen == 3
    assert summary.files_imported == 2
    assert summary.files_failed == 1
    assert Path(summary.failed_files[0].source_path).name == "bad.json"
    assert "Expecting property name" in summary.failed_files[0].error
    assert count_rows(db_path, "raw_ranges") == 4


def test_bulk_import_leaves_source_files_unchanged(tmp_path: Path) -> None:
    source_dir = write_fixture_folder(tmp_path)
    source_hashes = {path: sha256(path) for path in source_dir.rglob("*") if path.is_file()}

    bulk_import_source_dir(tmp_path / "range_library_memory.sqlite3", source_dir, "fxtm_export")

    assert {path: sha256(path) for path in source_hashes} == source_hashes


def test_bulk_import_missing_source_dir_fails_cleanly(tmp_path: Path) -> None:
    missing = tmp_path / "missing"

    with pytest.raises(FileNotFoundError, match="Source directory does not exist"):
        bulk_import_source_dir(tmp_path / "range_library_memory.sqlite3", missing, "fxtm_export")

    with pytest.raises(SystemExit):
        main(["bulk-import", "--source-dir", str(missing), "--source-kind", "fxtm_export", "--db-path", str(tmp_path / "db.sqlite3")])
    assert not (tmp_path / "db.sqlite3").exists()


def test_bulk_import_cli_json_output_works(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source_dir = write_fixture_folder(tmp_path)
    db_path = tmp_path / "range_library_memory.sqlite3"

    result = main(
        [
            "bulk-import",
            "--source-dir",
            str(source_dir),
            "--source-kind",
            "fxtm_export",
            "--db-path",
            str(db_path),
            "--json",
        ]
    )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["files_seen"] == 2
    assert payload["files_imported"] == 2
    assert payload["files_failed"] == 0


def test_export_cases_from_local_db_writes_sanitized_analyst_packages(tmp_path: Path) -> None:
    source_db = tmp_path / "source.sqlite3"
    output_dir = tmp_path / "exports"
    with sqlite3.connect(source_db) as connection:
        connection.execute(
            """
            CREATE TABLE raw_mapping_cases (
                case_id TEXT PRIMARY KEY,
                symbol TEXT,
                case_name TEXT,
                base_timeframe TEXT,
                price_scale_default INTEGER,
                status TEXT,
                notes TEXT,
                schema_version TEXT,
                created_at_utc_ms INTEGER,
                updated_at_utc_ms INTEGER
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE raw_mapping_events (
                event_id TEXT PRIMARY KEY,
                case_id TEXT,
                symbol TEXT,
                timeframe TEXT,
                candle_time_utc_ms INTEGER,
                price REAL,
                event_type TEXT,
                event_side TEXT,
                source TEXT,
                created_order INTEGER,
                is_deleted INTEGER,
                raw_payload_json TEXT
            )
            """
        )
        connection.execute(
            "CREATE TABLE map_ranges (id INTEGER PRIMARY KEY, raw_case_id TEXT, case_ref TEXT, symbol TEXT, timeframe TEXT, range_high_price REAL, range_low_price REAL)"
        )
        connection.execute(
            "CREATE TABLE map_events (id INTEGER PRIMARY KEY, raw_case_id TEXT, case_ref TEXT, symbol TEXT, timeframe TEXT, event_type TEXT, time TEXT, price REAL)"
        )
        connection.execute(
            "INSERT INTO raw_mapping_cases VALUES (?,?,?,?,?,?,?,?,?,?)",
            ("case-one", "XAUUSD", "Case One", "D1", 100, "ACTIVE", "", "raw_mapping_v1", 1, 2),
        )
        connection.execute(
            "INSERT INTO raw_mapping_events VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            ("raw-1", "case-one", "XAUUSD", "D1", 1780488000000, 2450.25, "SET_ANCHOR", "HIGH", "manual", 1, 0, "{}"),
        )
        connection.execute(
            "INSERT INTO map_ranges VALUES (?,?,?,?,?,?,?)",
            (1, "case-one", "raw:case-one", "XAUUSD", "D1", 2450.25, 2388.75),
        )
        connection.execute(
            "INSERT INTO map_events VALUES (?,?,?,?,?,?,?,?)",
            (1, "case-one", "raw:case-one", "XAUUSD", "D1", "RANGE_HIGH", "2026-06-03T12:00:00Z", 2450.25),
        )

    exported = export_cases(source_db=source_db, output_dir=output_dir, symbol="XAUUSD")

    assert len(exported) == 1
    payload = json.loads(exported[0].output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "analyst_input_v1"
    assert payload["case_refs"] == ["raw:case-one"]
    assert payload["data"]["ranges"][0]["raw_case_id"] == "case-one"
    assert payload["data"]["events"][0]["event_type"] == "RANGE_HIGH"
    assert payload["data"]["raw_ledgers"]["raw:case-one"]["sequence_by_intent"][0]["event_id"] == "raw-1"
    assert payload["source"]["source_db"] == "local_source_db"
    assert str(source_db) not in exported[0].output_path.read_text(encoding="utf-8")


def test_export_cases_discovers_map_only_case_refs(tmp_path: Path) -> None:
    source_db = tmp_path / "source.sqlite3"
    output_dir = tmp_path / "exports"
    with sqlite3.connect(source_db) as connection:
        connection.execute(
            "CREATE TABLE map_ranges (id INTEGER PRIMARY KEY, case_ref TEXT, symbol TEXT, timeframe TEXT, range_high_price REAL, range_low_price REAL)"
        )
        connection.execute(
            "CREATE TABLE map_events (id INTEGER PRIMARY KEY, case_ref TEXT, symbol TEXT, timeframe TEXT, event_type TEXT, time TEXT, price REAL)"
        )
        connection.execute(
            "INSERT INTO map_ranges VALUES (?,?,?,?,?,?)",
            (1, "raw:map-only-case", "XAUUSD", "D1", 2450.25, 2388.75),
        )
        connection.execute(
            "INSERT INTO map_ranges VALUES (?,?,?,?,?,?)",
            (2, "raw:map-only-case", "XAUUSD", "H4", 2432.5, 2401.25),
        )
        connection.execute(
            "INSERT INTO map_events VALUES (?,?,?,?,?,?,?)",
            (1, "raw:map-only-case", "XAUUSD", "D1", "RANGE_HIGH", "2026-06-03T12:00:00Z", 2450.25),
        )

    exported = export_cases(source_db=source_db, output_dir=output_dir, symbol="XAUUSD")

    assert len(exported) == 1
    assert exported[0].case_ref == "raw:map-only-case"
    payload_text = exported[0].output_path.read_text(encoding="utf-8")
    payload = json.loads(payload_text)
    assert payload["schema_version"] == "analyst_input_v1"
    assert payload["case_refs"] == ["raw:map-only-case"]
    assert len(payload["data"]["ranges"]) == 2
    assert len(payload["data"]["events"]) == 1
    assert payload["data"]["raw_ledgers"] == {}
    assert payload["source"]["source_db"] == "local_source_db"
    assert str(source_db) not in payload_text


def test_export_cases_discovers_map_only_raw_case_ids(tmp_path: Path) -> None:
    source_db = tmp_path / "source.sqlite3"
    output_dir = tmp_path / "exports"
    with sqlite3.connect(source_db) as connection:
        connection.execute(
            "CREATE TABLE map_ranges (id INTEGER PRIMARY KEY, raw_case_id TEXT, symbol TEXT, timeframe TEXT, range_high_price REAL, range_low_price REAL)"
        )
        connection.execute(
            "CREATE TABLE map_events (id INTEGER PRIMARY KEY, raw_case_id TEXT, symbol TEXT, timeframe TEXT, event_type TEXT, time TEXT, price REAL)"
        )
        connection.execute(
            "INSERT INTO map_ranges VALUES (?,?,?,?,?,?)",
            (1, "raw-id-only", "XAUUSD", "D1", 2450.25, 2388.75),
        )
        connection.execute(
            "INSERT INTO map_events VALUES (?,?,?,?,?,?,?)",
            (1, "raw-id-only", "XAUUSD", "D1", "RANGE_LOW", "2026-06-02T12:00:00Z", 2388.75),
        )

    exported = export_cases(source_db=source_db, output_dir=output_dir, symbol="XAUUSD")

    assert len(exported) == 1
    payload = json.loads(exported[0].output_path.read_text(encoding="utf-8"))
    assert payload["case_refs"] == ["raw:raw-id-only"]
    assert payload["data"]["ranges"][0]["raw_case_id"] == "raw-id-only"
    assert payload["data"]["events"][0]["event_type"] == "RANGE_LOW"
    assert payload["data"]["raw_ledgers"] == {}


def test_export_command_has_no_hardcoded_credentials() -> None:
    source = (PYTHON_DIR / "range_library_memory" / "export_cases.py").read_text(encoding="utf-8").lower()

    forbidden = ("api01", "password", "passwd", "secret", "token", "credential", "vps_base_url")
    assert all(value not in source for value in forbidden)


def test_no_generated_sqlite_db_file_committed() -> None:
    generated_databases = [
        path
        for pattern in ("*.sqlite", "*.sqlite3", "*.db")
        for path in Path(__file__).resolve().parents[1].rglob(pattern)
    ]

    assert generated_databases == []
