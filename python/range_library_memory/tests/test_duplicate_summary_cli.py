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
from range_library_memory.duplicate_summary import summarize_duplicates
from range_library_memory.importer import import_source
from range_library_memory.schema import init_schema

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
BASIC_FIXTURE = FIXTURE_DIR / "basic_import.json"
CHANGED_FIXTURE = FIXTURE_DIR / "duplicate_changed_payload.json"


def fetch_one(db_path: Path, query: str, params: tuple = ()) -> sqlite3.Row:
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(query, params).fetchone()
    assert row is not None
    return row


def candidate_count(db_path: Path) -> int:
    return fetch_one(db_path, "SELECT COUNT(*) AS count FROM duplicate_candidates")["count"]


def status_counts(db_path: Path) -> dict[str, int]:
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT review_status, COUNT(*) AS count FROM duplicate_candidates GROUP BY review_status"
        ).fetchall()
    return {row["review_status"]: row["count"] for row in rows}


def duplicate_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "range_library_memory.sqlite3"
    import_source(db_path, BASIC_FIXTURE, "fixture")
    import_source(db_path, CHANGED_FIXTURE, "fixture")
    with sqlite3.connect(db_path) as connection:
        add_case_ref_to_payloads(connection, "raw_ranges", "symbol = 'XAUUSD'", "case-a")
        add_case_ref_to_payloads(connection, "raw_events", "source_record_id = 'event-1'", "case-a")
        candidate_id = connection.execute(
            "SELECT id FROM duplicate_candidates WHERE rule_code = 'same_event_signature' LIMIT 1"
        ).fetchone()[0]
        connection.execute(
            "UPDATE duplicate_candidates SET review_status = 'ignored' WHERE id = ?",
            (candidate_id,),
        )
        connection.commit()
    return db_path


def add_case_ref_to_payloads(connection: sqlite3.Connection, table: str, where_clause: str, case_ref: str) -> None:
    rows = connection.execute(f"SELECT id, raw_payload_json FROM {table} WHERE {where_clause}").fetchall()
    for row_id, raw_payload_json in rows:
        payload = json.loads(raw_payload_json)
        payload["case_ref"] = case_ref
        connection.execute(
            f"UPDATE {table} SET raw_payload_json = ? WHERE id = ?",
            (json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")), row_id),
        )


def test_duplicate_summary_groups_by_rule_candidate_confidence_status(tmp_path: Path) -> None:
    db_path = duplicate_db(tmp_path)

    summary = summarize_duplicates(db_path)

    groups = {
        (row["rule_code"], row["candidate_type"], row["confidence"], row["status"]): row["count"]
        for row in summary["groups"]
    }
    assert ("same_event_signature", "event", "high", "ignored") in groups
    assert ("same_range_window", "range", "high", "open") in groups
    assert summary["total"] == candidate_count(db_path)


def test_duplicate_summary_supports_case_ref_filter(tmp_path: Path) -> None:
    db_path = duplicate_db(tmp_path)

    summary = summarize_duplicates(db_path, case_ref="case-a")

    assert summary["filters"]["case_ref"] == "case-a"
    assert summary["total"] > 0
    assert summary["total"] < candidate_count(db_path)


def test_duplicate_summary_supports_confidence_filter(tmp_path: Path) -> None:
    db_path = duplicate_db(tmp_path)

    summary = summarize_duplicates(db_path, confidence="high")

    assert summary["groups"]
    assert {row["confidence"] for row in summary["groups"]} == {"high"}


def test_duplicate_summary_supports_candidate_type_filter(tmp_path: Path) -> None:
    db_path = duplicate_db(tmp_path)

    summary = summarize_duplicates(db_path, candidate_type="event")

    assert summary["groups"]
    assert {row["candidate_type"] for row in summary["groups"]} == {"event"}


def test_duplicate_summary_supports_status_filter(tmp_path: Path) -> None:
    db_path = duplicate_db(tmp_path)

    summary = summarize_duplicates(db_path, status="ignored")

    assert summary["groups"]
    assert {row["status"] for row in summary["groups"]} == {"ignored"}


def test_duplicate_summary_json_output_is_deterministic_and_includes_totals(
    tmp_path: Path,
    capsys,
) -> None:
    db_path = duplicate_db(tmp_path)

    result = main(
        [
            "duplicate-summary",
            "--db-path",
            str(db_path),
            "--confidence",
            "high",
            "--json",
        ]
    )

    output = capsys.readouterr().out.strip()
    payload = json.loads(output)
    assert result == 0
    assert output == json.dumps(payload, sort_keys=True, separators=(",", ":"))
    assert payload["filters"] == {
        "candidate_type": None,
        "case_ref": None,
        "confidence": "high",
        "rule_code": None,
        "status": None,
    }
    assert payload["total"] == sum(row["count"] for row in payload["groups"])
    assert payload["groups"] == sorted(
        payload["groups"],
        key=lambda row: (row["rule_code"], row["candidate_type"], row["confidence"], row["status"]),
    )


def test_duplicate_summary_handles_no_duplicate_candidates(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "empty.sqlite3"
    init_schema(db_path)

    result = main(["duplicate-summary", "--db-path", str(db_path)])

    assert result == 0
    assert capsys.readouterr().out.strip() == "No duplicate candidates found."


def test_duplicate_summary_does_not_mutate_duplicate_candidates(tmp_path: Path) -> None:
    db_path = duplicate_db(tmp_path)
    before_count = candidate_count(db_path)
    before_status = status_counts(db_path)

    main(["duplicate-summary", "--db-path", str(db_path)])
    main(["duplicate-summary", "--db-path", str(db_path), "--json"])

    assert candidate_count(db_path) == before_count
    assert status_counts(db_path) == before_status
