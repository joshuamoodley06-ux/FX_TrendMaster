from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from range_library_memory.cli import main
from range_library_memory.importer import import_source

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
CURRENT_FIXTURE = FIXTURE_DIR / "current_fxtm_export_smoke.json"


def fetch_one(db_path: Path, query: str, params: tuple = ()) -> sqlite3.Row:
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(query, params).fetchone()
    assert row is not None
    return row


def count_rows(db_path: Path, table: str) -> int:
    return fetch_one(db_path, f"SELECT COUNT(*) AS count FROM {table}")["count"]


def test_current_fixture_imports_successfully_with_fxtm_export_kind(tmp_path: Path) -> None:
    db_path = tmp_path / "range_library_memory.sqlite3"

    summary = import_source(db_path, CURRENT_FIXTURE, "fxtm_export")

    assert summary.ranges_seen == 2
    assert summary.events_seen == 4
    assert summary.validation_issue_count == 0
    run = fetch_one(db_path, "SELECT source_kind, status FROM import_runs WHERE id = ?", (summary.import_run_id,))
    assert run["source_kind"] == "fxtm_export"
    assert run["status"] == "completed"


def test_current_fixture_range_and_event_counts_are_stored(tmp_path: Path) -> None:
    db_path = tmp_path / "range_library_memory.sqlite3"

    summary = import_source(db_path, CURRENT_FIXTURE, "fxtm_export")

    result = fetch_one(
        db_path,
        "SELECT ranges_seen, ranges_inserted, events_seen, events_inserted FROM range_import_results WHERE import_run_id = ?",
        (summary.import_run_id,),
    )
    assert result["ranges_seen"] == 2
    assert result["ranges_inserted"] == 2
    assert result["events_seen"] == 4
    assert result["events_inserted"] == 4
    assert count_rows(db_path, "raw_ranges") == 2
    assert count_rows(db_path, "raw_events") == 4


def test_current_fixture_helper_fields_are_extracted(tmp_path: Path) -> None:
    db_path = tmp_path / "range_library_memory.sqlite3"

    import_source(db_path, CURRENT_FIXTURE, "fxtm_export")

    raw_range = fetch_one(db_path, "SELECT * FROM raw_ranges WHERE source_record_id = ?", ("101",))
    map_event = fetch_one(db_path, "SELECT * FROM raw_events WHERE source_record_id = ?", ("map-event-current-1",))
    ledger_event = fetch_one(db_path, "SELECT * FROM raw_events WHERE source_record_id = ?", ("raw-current-1",))
    assert raw_range["symbol"] == "XAUUSD"
    assert raw_range["timeframe"] == "D1"
    assert raw_range["range_type"] == "DAILY"
    assert raw_range["start_time_utc"] == "2026-06-01T00:00:00.000Z"
    assert raw_range["end_time_utc"] == "2026-06-05T00:00:00.000Z"
    assert raw_range["high"] == 2450.25
    assert raw_range["low"] == 2388.75
    assert map_event["event_type"] == "RANGE_HIGH"
    assert map_event["event_time_utc"] == "2026-06-03T12:00:00.000Z"
    assert map_event["price"] == 2450.25
    assert map_event["raw_range_id"] is not None
    assert ledger_event["event_type"] == "SET_ANCHOR"
    assert ledger_event["event_time_utc"] == "2026-06-03T12:00:00Z"
    assert ledger_event["price"] == 2450.25
    assert ledger_event["raw_range_id"] is not None


def test_current_fixture_raw_payload_json_preserves_original_objects(tmp_path: Path) -> None:
    db_path = tmp_path / "range_library_memory.sqlite3"
    payload = json.loads(CURRENT_FIXTURE.read_text(encoding="utf-8"))

    import_source(db_path, CURRENT_FIXTURE, "fxtm_export")

    raw_range = fetch_one(db_path, "SELECT raw_payload_json FROM raw_ranges WHERE source_record_id = ?", ("101",))
    raw_event = fetch_one(db_path, "SELECT raw_payload_json FROM raw_events WHERE source_record_id = ?", ("raw-current-1",))
    assert json.loads(raw_range["raw_payload_json"]) == payload["data"]["ranges"][0]
    assert (
        json.loads(raw_event["raw_payload_json"])
        == payload["data"]["raw_ledgers"]["raw:sanitized-raw"]["sequence_by_intent"][0]
    )


def test_current_fixture_cli_import_works(tmp_path: Path) -> None:
    db_path = tmp_path / "range_library_memory.sqlite3"

    result = main(["import", "--source", str(CURRENT_FIXTURE), "--source-kind", "fxtm_export", "--db-path", str(db_path)])

    assert result == 0
    assert count_rows(db_path, "raw_ranges") == 2
    assert count_rows(db_path, "raw_events") == 4


def test_no_generated_sqlite_db_file_committed() -> None:
    generated_databases = [
        path
        for pattern in ("*.sqlite", "*.sqlite3", "*.db")
        for path in Path(__file__).resolve().parents[1].rglob(pattern)
    ]

    assert generated_databases == []
