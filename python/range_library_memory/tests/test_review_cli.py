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
from range_library_memory.review import list_duplicates, list_issues

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
BASIC_FIXTURE = FIXTURE_DIR / "basic_import.json"
CHANGED_FIXTURE = FIXTURE_DIR / "duplicate_changed_payload.json"
VALIDATION_FIXTURE = FIXTURE_DIR / "validation_issues_import.json"


def fetch_one(db_path: Path, query: str, params: tuple = ()) -> sqlite3.Row:
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(query, params).fetchone()
    assert row is not None
    return row


def row_counts(db_path: Path) -> dict[str, int]:
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


def populated_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "range_library_memory.sqlite3"
    import_source(db_path, BASIC_FIXTURE, "fixture")
    import_source(db_path, VALIDATION_FIXTURE, "fixture")
    import_source(db_path, CHANGED_FIXTURE, "fixture")
    return db_path


def test_list_issues_shows_open_validation_issues(tmp_path: Path) -> None:
    db_path = populated_db(tmp_path)

    issues = list_issues(db_path, status="open", limit=10)

    assert issues
    assert all(issue["resolved_at_utc"] is None for issue in issues)
    assert {"id", "issue_code", "severity", "resolution_notes"}.issubset(issues[0])


def test_resolve_issue_sets_resolved_at_and_notes(tmp_path: Path) -> None:
    db_path = populated_db(tmp_path)
    issue_id = list_issues(db_path, status="open", limit=1)[0]["id"]

    result = main(["resolve-issue", "--db-path", str(db_path), "--issue-id", str(issue_id), "--notes", "reviewed"])

    row = fetch_one(db_path, "SELECT resolved_at_utc, resolution_notes FROM validation_issues WHERE id = ?", (issue_id,))
    assert result == 0
    assert row["resolved_at_utc"] is not None
    assert row["resolution_notes"] == "reviewed"


def test_resolve_issue_does_not_change_raw_row_counts(tmp_path: Path) -> None:
    db_path = populated_db(tmp_path)
    issue_id = list_issues(db_path, status="open", limit=1)[0]["id"]
    before = row_counts(db_path)

    main(["resolve-issue", "--db-path", str(db_path), "--issue-id", str(issue_id), "--notes", "manual"])

    after = row_counts(db_path)
    assert after["raw_ranges"] == before["raw_ranges"]
    assert after["raw_events"] == before["raw_events"]
    assert after["import_runs"] == before["import_runs"]
    assert after["range_import_results"] == before["range_import_results"]


def test_list_duplicates_shows_open_duplicate_candidates(tmp_path: Path) -> None:
    db_path = populated_db(tmp_path)

    duplicates = list_duplicates(db_path, status="open", limit=10)

    assert duplicates
    assert all(candidate["review_status"] == "open" for candidate in duplicates)
    assert {"id", "rule_code", "candidate_type", "review_notes"}.issubset(duplicates[0])


def test_review_duplicate_updates_status_and_notes(tmp_path: Path) -> None:
    db_path = populated_db(tmp_path)
    candidate_id = list_duplicates(db_path, status="open", limit=1)[0]["id"]

    result = main(
        [
            "review-duplicate",
            "--db-path",
            str(db_path),
            "--candidate-id",
            str(candidate_id),
            "--status",
            "confirmed_duplicate",
            "--notes",
            "same source",
        ]
    )

    row = fetch_one(
        db_path,
        "SELECT review_status, review_notes FROM duplicate_candidates WHERE id = ?",
        (candidate_id,),
    )
    assert result == 0
    assert row["review_status"] == "confirmed_duplicate"
    assert row["review_notes"] == "same source"


def test_invalid_duplicate_review_status_is_rejected(tmp_path: Path) -> None:
    db_path = populated_db(tmp_path)
    candidate_id = list_duplicates(db_path, status="open", limit=1)[0]["id"]

    with pytest.raises(SystemExit):
        main(
            [
                "review-duplicate",
                "--db-path",
                str(db_path),
                "--candidate-id",
                str(candidate_id),
                "--status",
                "merge_it",
                "--notes",
                "nope",
            ]
        )


def test_list_commands_support_json(tmp_path: Path, capsys) -> None:
    db_path = populated_db(tmp_path)

    assert main(["list-issues", "--db-path", str(db_path), "--status", "open", "--limit", "2", "--json"]) == 0
    issues_payload = json.loads(capsys.readouterr().out)
    assert len(issues_payload["issues"]) == 2

    assert main(["list-duplicates", "--db-path", str(db_path), "--status", "open", "--limit", "2", "--json"]) == 0
    duplicates_payload = json.loads(capsys.readouterr().out)
    assert len(duplicates_payload["duplicates"]) == 2


def test_missing_db_does_not_get_created(tmp_path: Path) -> None:
    missing_db = tmp_path / "missing" / "range_library_memory.sqlite3"

    commands = [
        ["list-issues", "--db-path", str(missing_db)],
        ["resolve-issue", "--db-path", str(missing_db), "--issue-id", "1", "--notes", "x"],
        ["list-duplicates", "--db-path", str(missing_db)],
        [
            "review-duplicate",
            "--db-path",
            str(missing_db),
            "--candidate-id",
            "1",
            "--status",
            "ignored",
            "--notes",
            "x",
        ],
    ]
    for command in commands:
        with pytest.raises(SystemExit):
            main(command)

    assert not missing_db.exists()


def test_review_commands_do_not_change_protected_row_counts(tmp_path: Path) -> None:
    db_path = populated_db(tmp_path)
    issue_id = list_issues(db_path, status="open", limit=1)[0]["id"]
    candidate_id = list_duplicates(db_path, status="open", limit=1)[0]["id"]
    before = row_counts(db_path)

    main(["resolve-issue", "--db-path", str(db_path), "--issue-id", str(issue_id), "--notes", "manual"])
    main(
        [
            "review-duplicate",
            "--db-path",
            str(db_path),
            "--candidate-id",
            str(candidate_id),
            "--status",
            "ignored",
            "--notes",
            "manual",
        ]
    )

    after = row_counts(db_path)
    assert after == before


def test_no_generated_sqlite_db_file_committed() -> None:
    generated_databases = [
        path
        for pattern in ("*.sqlite", "*.sqlite3", "*.db")
        for path in Path(__file__).resolve().parents[1].rglob(pattern)
    ]

    assert generated_databases == []
