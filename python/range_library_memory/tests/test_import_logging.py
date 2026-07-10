from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from range_library_memory.cli import main
from range_library_memory.importer import import_source, raw_payload_json

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
BASIC_FIXTURE = FIXTURE_DIR / "basic_import.json"
INVALID_FIXTURE = FIXTURE_DIR / "invalid_import.json"


def fetch_one(db_path: Path, query: str, params: tuple = ()) -> sqlite3.Row:
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(query, params).fetchone()
    assert row is not None
    return row


def fetch_all(db_path: Path, query: str, params: tuple = ()) -> list[sqlite3.Row]:
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        return connection.execute(query, params).fetchall()


def count_rows(db_path: Path, table: str) -> int:
    return fetch_one(db_path, f"SELECT COUNT(*) AS count FROM {table}")["count"]


def test_import_creates_import_runs_row(tmp_path: Path) -> None:
    db_path = tmp_path / "range_library_memory.sqlite3"

    summary = import_source(db_path, BASIC_FIXTURE, "fixture")

    row = fetch_one(db_path, "SELECT * FROM import_runs WHERE id = ?", (summary.import_run_id,))
    assert row["run_uuid"] == summary.run_uuid
    assert row["source_path"] == str(BASIC_FIXTURE)
    assert row["source_kind"] == "fixture"
    assert row["status"] == "completed"
    assert row["started_at_utc"] is not None
    assert row["finished_at_utc"] is not None


def test_import_stores_source_sha256(tmp_path: Path) -> None:
    db_path = tmp_path / "range_library_memory.sqlite3"
    expected_hash = hashlib.sha256(BASIC_FIXTURE.read_bytes()).hexdigest()

    import_source(db_path, BASIC_FIXTURE, "fixture")

    row = fetch_one(db_path, "SELECT source_sha256 FROM import_runs")
    assert row["source_sha256"] == expected_hash


def test_import_stores_raw_range_payload_json_unchanged(tmp_path: Path) -> None:
    db_path = tmp_path / "range_library_memory.sqlite3"
    fixture_payload = json.loads(BASIC_FIXTURE.read_text(encoding="utf-8"))
    expected_range = fixture_payload["ranges"][0]

    import_source(db_path, BASIC_FIXTURE, "fixture")

    row = fetch_one(
        db_path,
        "SELECT raw_payload_json, payload_sha256, symbol, timeframe, range_type FROM raw_ranges WHERE source_record_id = ?",
        ("range-1",),
    )
    assert json.loads(row["raw_payload_json"]) == expected_range
    assert row["payload_sha256"] == hashlib.sha256(raw_payload_json(expected_range).encode("utf-8")).hexdigest()
    assert row["symbol"] == "XAUUSD"
    assert row["timeframe"] == "D1"
    assert row["range_type"] == "external"


def test_import_stores_raw_event_payload_json_unchanged(tmp_path: Path) -> None:
    db_path = tmp_path / "range_library_memory.sqlite3"
    fixture_payload = json.loads(BASIC_FIXTURE.read_text(encoding="utf-8"))
    expected_event = fixture_payload["events"][0]

    import_source(db_path, BASIC_FIXTURE, "fixture")

    row = fetch_one(
        db_path,
        """
        SELECT raw_events.raw_payload_json,
               raw_events.payload_sha256,
               raw_events.event_type,
               raw_events.price,
               raw_events.raw_range_id
        FROM raw_events
        WHERE raw_events.source_record_id = ?
        """,
        ("event-1",),
    )
    assert json.loads(row["raw_payload_json"]) == expected_event
    assert row["payload_sha256"] == hashlib.sha256(raw_payload_json(expected_event).encode("utf-8")).hexdigest()
    assert row["event_type"] == "touch"
    assert row["price"] == 2050.0
    assert row["raw_range_id"] is not None


def test_import_writes_range_import_results_counts(tmp_path: Path) -> None:
    db_path = tmp_path / "range_library_memory.sqlite3"

    summary = import_source(db_path, BASIC_FIXTURE, "fixture")

    row = fetch_one(
        db_path,
        "SELECT * FROM range_import_results WHERE import_run_id = ?",
        (summary.import_run_id,),
    )
    assert row["ranges_seen"] == 2
    assert row["ranges_inserted"] == 2
    assert row["ranges_reused"] == 0
    assert row["events_seen"] == 2
    assert row["events_inserted"] == 2
    assert row["events_reused"] == 0
    assert row["validation_issue_count"] == 0
    assert row["duplicate_candidate_count"] == 0
    assert json.loads(row["summary_json"])["ranges_seen"] == 2


def test_reimport_same_fixture_creates_new_run_and_reuses_payload_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "range_library_memory.sqlite3"

    first = import_source(db_path, BASIC_FIXTURE, "fixture")
    second = import_source(db_path, BASIC_FIXTURE, "fixture")

    assert first.import_run_id != second.import_run_id
    assert count_rows(db_path, "import_runs") == 2
    assert count_rows(db_path, "raw_ranges") == 2
    assert count_rows(db_path, "raw_events") == 2

    second_results = fetch_one(
        db_path,
        "SELECT * FROM range_import_results WHERE import_run_id = ?",
        (second.import_run_id,),
    )
    assert second_results["ranges_seen"] == 2
    assert second_results["ranges_inserted"] == 0
    assert second_results["ranges_reused"] == 2
    assert second_results["events_seen"] == 2
    assert second_results["events_inserted"] == 0
    assert second_results["events_reused"] == 2


def test_failed_import_still_records_failed_import_run(tmp_path: Path) -> None:
    db_path = tmp_path / "range_library_memory.sqlite3"
    expected_hash = hashlib.sha256(INVALID_FIXTURE.read_bytes()).hexdigest()

    with pytest.raises(ValueError):
        import_source(db_path, INVALID_FIXTURE, "fixture")

    row = fetch_one(db_path, "SELECT status, notes, finished_at_utc, source_sha256 FROM import_runs")
    assert row["status"] == "failed"
    assert row["source_sha256"] == expected_hash
    assert "ranges must be a list" in row["notes"]
    assert row["finished_at_utc"] is not None
    assert count_rows(db_path, "range_import_results") == 0


def test_cli_import_works(tmp_path: Path) -> None:
    db_path = tmp_path / "range_library_memory.sqlite3"

    result = main(
        [
            "import",
            "--source",
            str(BASIC_FIXTURE),
            "--source-kind",
            "fixture",
            "--db-path",
            str(db_path),
        ]
    )

    assert result == 0
    assert count_rows(db_path, "import_runs") == 1
    assert count_rows(db_path, "raw_ranges") == 2
    assert count_rows(db_path, "raw_events") == 2


def test_no_generated_database_file_in_fixtures() -> None:
    generated_databases = [
        path
        for pattern in ("*.sqlite", "*.sqlite3", "*.db")
        for path in (Path(__file__).resolve().parents[1]).rglob(pattern)
    ]

    assert generated_databases == []
