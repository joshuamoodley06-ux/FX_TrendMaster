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
BASIC_FIXTURE = FIXTURE_DIR / "basic_import.json"
VALIDATION_FIXTURE = FIXTURE_DIR / "validation_issues_import.json"


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


def issue_codes(db_path: Path) -> set[str]:
    return {row["issue_code"] for row in fetch_all(db_path, "SELECT issue_code FROM validation_issues")}


def test_valid_fixture_creates_zero_validation_issues(tmp_path: Path) -> None:
    db_path = tmp_path / "range_library_memory.sqlite3"

    summary = import_source(db_path, BASIC_FIXTURE, "fixture")

    assert summary.validation_issue_count == 0
    assert count_rows(db_path, "validation_issues") == 0
    row = fetch_one(db_path, "SELECT status FROM import_runs")
    assert row["status"] == "completed"


def test_invalid_range_creates_validation_issues(tmp_path: Path) -> None:
    db_path = tmp_path / "range_library_memory.sqlite3"

    import_source(db_path, VALIDATION_FIXTURE, "fixture")

    codes = issue_codes(db_path)
    assert "missing_symbol" in codes
    assert "missing_source_record_id" in codes
    assert "missing_timeframe" in codes
    assert "missing_end_time" in codes
    assert "non_numeric_high" in codes
    assert "invalid_range_time_order" in codes
    assert "invalid_range_price_order" in codes

    linked_issue = fetch_one(
        db_path,
        """
        SELECT validation_issues.raw_range_id
        FROM validation_issues
        WHERE issue_code = 'missing_symbol'
        """,
    )
    assert linked_issue["raw_range_id"] is not None


def test_invalid_event_creates_validation_issues(tmp_path: Path) -> None:
    db_path = tmp_path / "range_library_memory.sqlite3"

    import_source(db_path, VALIDATION_FIXTURE, "fixture")

    codes = issue_codes(db_path)
    assert "missing_event_type" in codes
    assert "missing_event_time" in codes
    assert "non_numeric_event_price" in codes
    assert "missing_event_range_reference" in codes
    assert "contradictory_event_range_linkage" in codes

    linked_issue = fetch_one(
        db_path,
        """
        SELECT validation_issues.raw_event_id
        FROM validation_issues
        WHERE issue_code = 'missing_event_type'
        """,
    )
    assert linked_issue["raw_event_id"] is not None


def test_completed_with_issues_status_when_issues_exist(tmp_path: Path) -> None:
    db_path = tmp_path / "range_library_memory.sqlite3"

    summary = import_source(db_path, VALIDATION_FIXTURE, "fixture")

    row = fetch_one(db_path, "SELECT status FROM import_runs WHERE id = ?", (summary.import_run_id,))
    assert row["status"] == "completed_with_issues"
    assert summary.validation_issue_count > 0


def test_validation_issue_count_updates_range_import_results(tmp_path: Path) -> None:
    db_path = tmp_path / "range_library_memory.sqlite3"

    summary = import_source(db_path, VALIDATION_FIXTURE, "fixture")

    row = fetch_one(
        db_path,
        "SELECT validation_issue_count, summary_json FROM range_import_results WHERE import_run_id = ?",
        (summary.import_run_id,),
    )
    assert row["validation_issue_count"] == summary.validation_issue_count
    assert json.loads(row["summary_json"])["validation_issue_count"] == summary.validation_issue_count


def test_reimport_records_issues_again_without_duplicating_raw_payload_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "range_library_memory.sqlite3"

    first = import_source(db_path, VALIDATION_FIXTURE, "fixture")
    second = import_source(db_path, VALIDATION_FIXTURE, "fixture")

    assert first.import_run_id != second.import_run_id
    assert count_rows(db_path, "import_runs") == 2
    assert count_rows(db_path, "raw_ranges") == 2
    assert count_rows(db_path, "raw_events") == 2

    first_issue_count = fetch_one(
        db_path,
        "SELECT COUNT(*) AS count FROM validation_issues WHERE import_run_id = ?",
        (first.import_run_id,),
    )["count"]
    second_issue_count = fetch_one(
        db_path,
        "SELECT COUNT(*) AS count FROM validation_issues WHERE import_run_id = ?",
        (second.import_run_id,),
    )["count"]
    assert first_issue_count == second_issue_count
    assert second_issue_count == second.validation_issue_count


def test_raw_payload_json_remains_unchanged_when_validation_issues_exist(tmp_path: Path) -> None:
    db_path = tmp_path / "range_library_memory.sqlite3"
    fixture_payload = json.loads(VALIDATION_FIXTURE.read_text(encoding="utf-8"))

    import_source(db_path, VALIDATION_FIXTURE, "fixture")

    raw_range = fetch_one(
        db_path,
        "SELECT raw_payload_json FROM raw_ranges WHERE source_record_id = ?",
        ("bad-range-1",),
    )
    raw_event = fetch_one(
        db_path,
        "SELECT raw_payload_json FROM raw_events WHERE source_record_id = ?",
        ("bad-event-1",),
    )
    assert json.loads(raw_range["raw_payload_json"]) == fixture_payload["ranges"][0]
    assert json.loads(raw_event["raw_payload_json"]) == fixture_payload["events"][0]


def test_cli_import_still_works_with_validation_issues(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "range_library_memory.sqlite3"

    result = main(
        [
            "import",
            "--source",
            str(VALIDATION_FIXTURE),
            "--source-kind",
            "fixture",
            "--db-path",
            str(db_path),
        ]
    )

    output = capsys.readouterr().out
    assert result == 0
    assert "issues=" in output
    assert count_rows(db_path, "validation_issues") > 0


def test_no_generated_sqlite_db_file_committed() -> None:
    generated_databases = [
        path
        for pattern in ("*.sqlite", "*.sqlite3", "*.db")
        for path in Path(__file__).resolve().parents[1].rglob(pattern)
    ]

    assert generated_databases == []
