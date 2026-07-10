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
REAL_FIXTURE = FIXTURE_DIR / "real_fxtm_export_shape.json"
CHANGED_FIXTURE = FIXTURE_DIR / "duplicate_changed_payload.json"


def fetch_one(db_path: Path, query: str, params: tuple = ()) -> sqlite3.Row:
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(query, params).fetchone()
    assert row is not None
    return row


def count_rows(db_path: Path, table: str) -> int:
    return fetch_one(db_path, f"SELECT COUNT(*) AS count FROM {table}")["count"]


def test_real_shape_fixture_imports_successfully(tmp_path: Path) -> None:
    db_path = tmp_path / "range_library_memory.sqlite3"

    summary = import_source(db_path, REAL_FIXTURE, "fxtm_export")

    assert summary.ranges_seen == 2
    assert summary.events_seen == 4
    assert count_rows(db_path, "import_runs") == 1


def test_real_shape_range_and_event_counts_are_stored(tmp_path: Path) -> None:
    db_path = tmp_path / "range_library_memory.sqlite3"

    summary = import_source(db_path, REAL_FIXTURE, "fxtm_export")

    row = fetch_one(db_path, "SELECT ranges_seen, events_seen FROM range_import_results WHERE import_run_id = ?", (summary.import_run_id,))
    assert row["ranges_seen"] == 2
    assert row["events_seen"] == 4
    assert count_rows(db_path, "raw_ranges") == 2
    assert count_rows(db_path, "raw_events") == 4


def test_real_shape_helper_fields_are_extracted(tmp_path: Path) -> None:
    db_path = tmp_path / "range_library_memory.sqlite3"

    import_source(db_path, REAL_FIXTURE, "fxtm_export")

    raw_range = fetch_one(db_path, "SELECT * FROM raw_ranges WHERE source_record_id = ?", ("range-1",))
    raw_event = fetch_one(db_path, "SELECT * FROM raw_events WHERE source_record_id = ?", ("raw-event-1",))
    assert raw_range["symbol"] == "XAUUSD"
    assert raw_range["timeframe"] == "D1"
    assert raw_range["range_type"] == "DAILY"
    assert raw_range["start_time_utc"] == "2026-01-01T00:00:00.000Z"
    assert raw_range["end_time_utc"] == "2026-01-02T00:00:00.000Z"
    assert raw_range["high"] == 2060.5
    assert raw_range["low"] == 2015.25
    assert raw_event["event_type"] == "SET_ANCHOR"
    assert raw_event["event_time_utc"] == "2026-01-01T13:00:00Z"
    assert raw_event["price"] == 2060.5
    assert raw_event["raw_range_id"] is not None


def test_real_shape_raw_payload_json_matches_original_objects(tmp_path: Path) -> None:
    db_path = tmp_path / "range_library_memory.sqlite3"
    payload = json.loads(REAL_FIXTURE.read_text(encoding="utf-8"))

    import_source(db_path, REAL_FIXTURE, "fxtm_export")

    raw_range = fetch_one(db_path, "SELECT raw_payload_json FROM raw_ranges WHERE source_record_id = ?", ("range-1",))
    raw_event = fetch_one(db_path, "SELECT raw_payload_json FROM raw_events WHERE source_record_id = ?", ("raw-event-1",))
    assert json.loads(raw_range["raw_payload_json"]) == payload["ranges"][0]
    assert json.loads(raw_event["raw_payload_json"]) == payload["rawLedgers"]["raw:case-smoke-1"]["sequence_by_intent"][0]


def test_real_shape_validation_issues_are_recorded_for_odd_fields(tmp_path: Path) -> None:
    db_path = tmp_path / "range_library_memory.sqlite3"

    summary = import_source(db_path, REAL_FIXTURE, "fxtm_export")

    issue = fetch_one(
        db_path,
        "SELECT issue_code FROM validation_issues WHERE issue_code = 'missing_end_time'",
    )
    assert issue["issue_code"] == "missing_end_time"
    assert summary.validation_issue_count > 0


def test_duplicate_logic_still_works_after_real_shape_import(tmp_path: Path) -> None:
    db_path = tmp_path / "range_library_memory.sqlite3"

    import_source(db_path, REAL_FIXTURE, "fxtm_export")
    summary = import_source(db_path, CHANGED_FIXTURE, "fixture")

    candidate = fetch_one(
        db_path,
        "SELECT rule_code FROM duplicate_candidates WHERE rule_code = 'same_source_record_id'",
    )
    assert candidate["rule_code"] == "same_source_record_id"
    assert summary.duplicate_candidate_count > 0


def test_real_shape_cli_import_works(tmp_path: Path) -> None:
    db_path = tmp_path / "range_library_memory.sqlite3"

    result = main(["import", "--source", str(REAL_FIXTURE), "--source-kind", "fxtm_export", "--db-path", str(db_path)])

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
