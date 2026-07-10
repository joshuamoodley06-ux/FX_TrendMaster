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
CHANGED_FIXTURE = FIXTURE_DIR / "duplicate_changed_payload.json"


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


def rule_codes(db_path: Path) -> set[str]:
    return {row["rule_code"] for row in fetch_all(db_path, "SELECT rule_code FROM duplicate_candidates")}


def test_exact_reimport_reuses_raw_rows_without_self_candidates(tmp_path: Path) -> None:
    db_path = tmp_path / "range_library_memory.sqlite3"

    import_source(db_path, BASIC_FIXTURE, "fixture")
    second = import_source(db_path, BASIC_FIXTURE, "fixture")

    assert count_rows(db_path, "raw_ranges") == 2
    assert count_rows(db_path, "raw_events") == 2
    assert second.duplicate_candidate_count == 0


def test_same_source_record_id_candidate_for_changed_payload(tmp_path: Path) -> None:
    db_path = tmp_path / "range_library_memory.sqlite3"

    import_source(db_path, BASIC_FIXTURE, "fixture")
    import_source(db_path, CHANGED_FIXTURE, "fixture")

    row = fetch_one(
        db_path,
        """
        SELECT candidate_type, confidence
        FROM duplicate_candidates
        WHERE rule_code = 'same_source_record_id'
          AND candidate_type = 'range'
        """,
    )
    assert row["confidence"] == "exact"


def test_exact_payload_hash_candidate_for_existing_duplicate_raw_row(tmp_path: Path) -> None:
    db_path = tmp_path / "range_library_memory.sqlite3"

    import_source(db_path, BASIC_FIXTURE, "fixture")
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO raw_ranges (
                import_run_id,
                source_record_id,
                symbol,
                timeframe,
                range_type,
                start_time_utc,
                end_time_utc,
                high,
                low,
                raw_payload_json,
                payload_sha256,
                created_at_utc
            )
            SELECT import_run_id,
                   source_record_id,
                   symbol,
                   timeframe,
                   range_type,
                   start_time_utc,
                   end_time_utc,
                   high,
                   low,
                   raw_payload_json,
                   payload_sha256,
                   created_at_utc
            FROM raw_ranges
            WHERE source_record_id = 'range-1'
            """
        )
        connection.commit()

    import_source(db_path, BASIC_FIXTURE, "fixture")

    row = fetch_one(
        db_path,
        """
        SELECT candidate_type, confidence
        FROM duplicate_candidates
        WHERE rule_code = 'exact_payload_hash'
          AND candidate_type = 'range'
        """,
    )
    assert row["confidence"] == "exact"


def test_same_range_window_candidate(tmp_path: Path) -> None:
    db_path = tmp_path / "range_library_memory.sqlite3"

    import_source(db_path, BASIC_FIXTURE, "fixture")
    import_source(db_path, CHANGED_FIXTURE, "fixture")

    row = fetch_one(
        db_path,
        """
        SELECT confidence
        FROM duplicate_candidates
        WHERE rule_code = 'same_range_window'
        """,
    )
    assert row["confidence"] == "high"
    assert "same_window_different_payload" in rule_codes(db_path)


def test_same_event_signature_candidate(tmp_path: Path) -> None:
    db_path = tmp_path / "range_library_memory.sqlite3"

    import_source(db_path, BASIC_FIXTURE, "fixture")
    import_source(db_path, CHANGED_FIXTURE, "fixture")

    row = fetch_one(
        db_path,
        """
        SELECT candidate_type, confidence
        FROM duplicate_candidates
        WHERE rule_code = 'same_event_signature'
        """,
    )
    assert row["candidate_type"] == "event"
    assert row["confidence"] == "high"


def test_duplicate_candidate_count_updates_range_import_results(tmp_path: Path) -> None:
    db_path = tmp_path / "range_library_memory.sqlite3"

    import_source(db_path, BASIC_FIXTURE, "fixture")
    second = import_source(db_path, BASIC_FIXTURE, "fixture")

    row = fetch_one(
        db_path,
        "SELECT duplicate_candidate_count, summary_json FROM range_import_results WHERE import_run_id = ?",
        (second.import_run_id,),
    )
    assert row["duplicate_candidate_count"] == second.duplicate_candidate_count
    assert json.loads(row["summary_json"])["duplicate_candidate_count"] == second.duplicate_candidate_count


def test_duplicate_candidates_do_not_change_import_status_by_themselves(tmp_path: Path) -> None:
    db_path = tmp_path / "range_library_memory.sqlite3"

    import_source(db_path, BASIC_FIXTURE, "fixture")
    second = import_source(db_path, CHANGED_FIXTURE, "fixture")

    row = fetch_one(db_path, "SELECT status FROM import_runs WHERE id = ?", (second.import_run_id,))
    assert second.validation_issue_count == 0
    assert second.duplicate_candidate_count > 0
    assert row["status"] == "completed"


def test_duplicate_candidates_are_open_and_not_self_comparisons(tmp_path: Path) -> None:
    db_path = tmp_path / "range_library_memory.sqlite3"

    import_source(db_path, BASIC_FIXTURE, "fixture")
    import_source(db_path, CHANGED_FIXTURE, "fixture")

    rows = fetch_all(db_path, "SELECT * FROM duplicate_candidates")
    assert rows
    assert {row["review_status"] for row in rows} == {"open"}
    for row in rows:
        if row["candidate_type"] == "range":
            assert row["left_raw_range_id"] != row["right_raw_range_id"]
        if row["candidate_type"] == "event":
            assert row["left_raw_event_id"] != row["right_raw_event_id"]


def test_cli_import_reports_duplicate_candidates(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "range_library_memory.sqlite3"

    main(["import", "--source", str(BASIC_FIXTURE), "--source-kind", "fixture", "--db-path", str(db_path)])
    result = main(["import", "--source", str(CHANGED_FIXTURE), "--source-kind", "fixture", "--db-path", str(db_path)])

    output = capsys.readouterr().out
    assert result == 0
    assert "duplicates=" in output
    assert count_rows(db_path, "duplicate_candidates") > 0


def test_no_duplicate_candidate_rows_for_same_pair_rule_import_run(tmp_path: Path) -> None:
    db_path = tmp_path / "range_library_memory.sqlite3"

    import_source(db_path, BASIC_FIXTURE, "fixture")
    second = import_source(db_path, BASIC_FIXTURE, "fixture")

    duplicate_groups = fetch_all(
        db_path,
        """
        SELECT rule_code,
               COALESCE(left_raw_range_id, -1) AS left_range,
               COALESCE(right_raw_range_id, -1) AS right_range,
               COALESCE(left_raw_event_id, -1) AS left_event,
               COALESCE(right_raw_event_id, -1) AS right_event,
               COUNT(*) AS count
        FROM duplicate_candidates
        WHERE import_run_id = ?
        GROUP BY rule_code, left_range, right_range, left_event, right_event
        HAVING COUNT(*) > 1
        """,
        (second.import_run_id,),
    )
    assert duplicate_groups == []


def test_no_generated_sqlite_db_file_committed() -> None:
    generated_databases = [
        path
        for pattern in ("*.sqlite", "*.sqlite3", "*.db")
        for path in Path(__file__).resolve().parents[1].rglob(pattern)
    ]

    assert generated_databases == []
