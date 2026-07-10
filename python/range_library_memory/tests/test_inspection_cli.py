from __future__ import annotations

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
from range_library_memory.importer import import_source
from range_library_memory.inspection import list_runs, show_run

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
BASIC_FIXTURE = FIXTURE_DIR / "basic_import.json"
CHANGED_FIXTURE = FIXTURE_DIR / "duplicate_changed_payload.json"
VALIDATION_FIXTURE = FIXTURE_DIR / "validation_issues_import.json"


def fetch_counts(db_path: Path) -> dict[str, int]:
    tables = (
        "import_runs",
        "raw_ranges",
        "raw_events",
        "range_import_results",
        "validation_issues",
        "duplicate_candidates",
    )
    with sqlite3.connect(db_path) as connection:
        return {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in tables
        }


def populated_db(tmp_path: Path) -> tuple[Path, int, int, int]:
    db_path = tmp_path / "range_library_memory.sqlite3"
    first = import_source(db_path, BASIC_FIXTURE, "fixture")
    second = import_source(db_path, VALIDATION_FIXTURE, "fixture")
    third = import_source(db_path, CHANGED_FIXTURE, "fixture")
    return db_path, first.import_run_id, second.import_run_id, third.import_run_id


def test_list_runs_returns_recent_runs(tmp_path: Path) -> None:
    db_path, first_id, _, third_id = populated_db(tmp_path)

    runs = list_runs(db_path, limit=10)

    assert len(runs) == 3
    assert {run["id"] for run in runs} == {first_id, first_id + 1, third_id}
    assert all("source_path" in run for run in runs)
    assert all("duplicate_candidate_count" in run for run in runs)


def test_list_runs_respects_limit(tmp_path: Path) -> None:
    db_path, _, _, _ = populated_db(tmp_path)

    runs = list_runs(db_path, limit=2)

    assert len(runs) == 2


def test_list_runs_json_output_is_valid_json(tmp_path: Path, capsys) -> None:
    db_path, _, _, _ = populated_db(tmp_path)

    result = main(["list-runs", "--db-path", str(db_path), "--limit", "2", "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert result == 0
    assert len(payload["runs"]) == 2
    assert "run_uuid" in payload["runs"][0]


def test_show_run_returns_import_metadata_and_counts(tmp_path: Path) -> None:
    db_path, first_id, _, _ = populated_db(tmp_path)

    details = show_run(db_path, import_run_id=first_id)

    assert details["import_run"]["id"] == first_id
    assert details["import_run"]["source_kind"] == "fixture"
    assert details["range_import_results"]["ranges_seen"] == 2
    assert details["range_import_results"]["events_seen"] == 2


def test_show_run_groups_validation_issue_codes(tmp_path: Path) -> None:
    db_path, _, validation_run_id, _ = populated_db(tmp_path)

    details = show_run(db_path, import_run_id=validation_run_id)

    issue_codes = {row["issue_code"] for row in details["validation_issues_by_code"]}
    assert "missing_symbol" in issue_codes
    assert "missing_event_type" in issue_codes


def test_show_run_groups_duplicate_candidate_rule_codes(tmp_path: Path) -> None:
    db_path, _, _, duplicate_run_id = populated_db(tmp_path)

    details = show_run(db_path, import_run_id=duplicate_run_id)

    rule_codes = {row["rule_code"] for row in details["duplicate_candidates_by_rule"]}
    assert "same_source_record_id" in rule_codes
    assert "same_event_signature" in rule_codes


def test_show_run_json_output_is_valid_json(tmp_path: Path, capsys) -> None:
    db_path, first_id, _, _ = populated_db(tmp_path)

    result = main(["show-run", "--db-path", str(db_path), "--import-run-id", str(first_id), "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert result == 0
    assert payload["import_run"]["id"] == first_id
    assert "raw_payload_json" not in json.dumps(payload)


def test_inspection_commands_do_not_create_missing_db_files(tmp_path: Path) -> None:
    missing_db = tmp_path / "missing" / "range_library_memory.sqlite3"

    with pytest.raises(SystemExit):
        main(["list-runs", "--db-path", str(missing_db)])
    with pytest.raises(SystemExit):
        main(["show-run", "--db-path", str(missing_db), "--import-run-id", "1"])

    assert not missing_db.exists()


def test_inspection_commands_do_not_change_row_counts(tmp_path: Path, capsys) -> None:
    db_path, first_id, _, _ = populated_db(tmp_path)
    before = fetch_counts(db_path)

    assert main(["list-runs", "--db-path", str(db_path), "--limit", "5"]) == 0
    assert main(["show-run", "--db-path", str(db_path), "--import-run-id", str(first_id)]) == 0
    capsys.readouterr()

    assert fetch_counts(db_path) == before


def test_no_generated_sqlite_db_file_committed() -> None:
    generated_databases = [
        path
        for pattern in ("*.sqlite", "*.sqlite3", "*.db")
        for path in Path(__file__).resolve().parents[1].rglob(pattern)
    ]

    assert generated_databases == []
