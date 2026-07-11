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
from range_library_memory.parent_child import build_parent_child, summarize_parent_child
from range_library_memory.schema import init_schema


def write_source(tmp_path: Path, ranges: list[dict]) -> Path:
    source = tmp_path / "ranges.json"
    source.write_text(json.dumps({"ranges": ranges}, indent=2), encoding="utf-8")
    return source


def fetch_one(db_path: Path, query: str, params: tuple = ()) -> sqlite3.Row:
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(query, params).fetchone()
    assert row is not None
    return row


def count_rows(db_path: Path, table: str) -> int:
    return fetch_one(db_path, f"SELECT COUNT(*) AS count FROM {table}")["count"]


def weekly_range(range_id: str = "weekly-1", **overrides) -> dict:
    value = {
        "range_id": range_id,
        "case_ref": "case:one",
        "symbol": "XAUUSD",
        "structure_layer": "WEEKLY",
        "source_timeframe": "W1",
        "range_start_time": "2026-01-01T00:00:00Z",
        "range_end_time": "2026-01-31T00:00:00Z",
        "range_high_price": 2100.0,
        "range_low_price": 2000.0,
        "status": "ACTIVE",
    }
    value.update(overrides)
    return value


def daily_range(range_id: str = "daily-1", **overrides) -> dict:
    value = {
        "range_id": range_id,
        "case_ref": "case:one",
        "symbol": "XAUUSD",
        "structure_layer": "DAILY",
        "source_timeframe": "D1",
        "range_start_time": "2026-01-10T00:00:00Z",
        "range_end_time": "2026-01-11T00:00:00Z",
        "range_high_price": 2050.0,
        "range_low_price": 2025.0,
        "status": "ACTIVE",
    }
    value.update(overrides)
    return value


def imported_db(tmp_path: Path, ranges: list[dict]) -> Path:
    db_path = tmp_path / "range_library_memory.sqlite3"
    import_source(db_path, write_source(tmp_path, ranges), "fixture")
    return db_path


def test_parent_child_schema_initializes_table(tmp_path: Path) -> None:
    db_path = tmp_path / "range_library_memory.sqlite3"

    init_schema(db_path)

    row = fetch_one(
        db_path,
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'parent_child_relationships'",
    )
    assert row["name"] == "parent_child_relationships"


def test_build_parent_child_creates_valid_weekly_daily_relationship(tmp_path: Path) -> None:
    db_path = imported_db(tmp_path, [weekly_range(), daily_range()])

    summary = build_parent_child(db_path, parent_layer="WEEKLY", child_layer="DAILY")

    row = fetch_one(db_path, "SELECT * FROM parent_child_relationships")
    assert summary["relationships_created"] == 1
    assert row["relationship_type"] == "weekly_daily"
    assert row["link_status"] == "VALID"
    assert row["review_status"] == "open"
    assert row["parent_range_id"] == "weekly-1"
    assert row["child_range_id"] == "daily-1"
    assert row["child_position_in_parent"] == "inside_fair_price"
    assert row["child_boundary_interaction"] == "inside_boundary"


def test_build_parent_child_marks_orphan_when_no_weekly_parent(tmp_path: Path) -> None:
    db_path = imported_db(tmp_path, [daily_range()])

    build_parent_child(db_path, parent_layer="WEEKLY", child_layer="DAILY")

    row = fetch_one(db_path, "SELECT link_status, parent_range_id FROM parent_child_relationships")
    assert row["link_status"] == "ORPHAN"
    assert row["parent_range_id"] is None


def test_build_parent_child_marks_conflict_for_multiple_weekly_parents(tmp_path: Path) -> None:
    db_path = imported_db(tmp_path, [weekly_range("weekly-1"), weekly_range("weekly-2"), daily_range()])

    build_parent_child(db_path, parent_layer="WEEKLY", child_layer="DAILY")

    row = fetch_one(db_path, "SELECT link_status, notes FROM parent_child_relationships")
    assert row["link_status"] == "CONFLICT"
    assert "Multiple possible" in row["notes"]


def test_build_parent_child_marks_needs_review_for_uncertain_parent_lifecycle(tmp_path: Path) -> None:
    parent = weekly_range(status="BROKEN")
    db_path = imported_db(tmp_path, [parent, daily_range()])

    build_parent_child(db_path, parent_layer="WEEKLY", child_layer="DAILY")

    row = fetch_one(db_path, "SELECT link_status, child_lifecycle_relationship FROM parent_child_relationships")
    assert row["link_status"] == "NEEDS_REVIEW"
    assert row["child_lifecycle_relationship"] == "uncertain_parent_cutoff"


def test_build_parent_child_is_idempotent_and_does_not_mutate_raw_ranges(tmp_path: Path) -> None:
    db_path = imported_db(tmp_path, [weekly_range(), daily_range()])
    before_raw_count = count_rows(db_path, "raw_ranges")
    before_payload = fetch_one(db_path, "SELECT raw_payload_json FROM raw_ranges WHERE source_record_id = 'daily-1'")[
        "raw_payload_json"
    ]

    build_parent_child(db_path, parent_layer="WEEKLY", child_layer="DAILY")
    second = build_parent_child(db_path, parent_layer="WEEKLY", child_layer="DAILY")

    assert count_rows(db_path, "parent_child_relationships") == 1
    assert second["relationships_existing"] == 1
    assert count_rows(db_path, "raw_ranges") == before_raw_count
    after_payload = fetch_one(db_path, "SELECT raw_payload_json FROM raw_ranges WHERE source_record_id = 'daily-1'")[
        "raw_payload_json"
    ]
    assert after_payload == before_payload


def test_parent_child_summary_supports_human_and_json_output(tmp_path: Path, capsys) -> None:
    db_path = imported_db(tmp_path, [weekly_range(), daily_range()])
    build_parent_child(db_path, parent_layer="WEEKLY", child_layer="DAILY")

    assert main(["parent-child-summary", "--db-path", str(db_path)]) == 0
    human = capsys.readouterr().out
    assert "relationship_type | link_status | review_status | count" in human
    assert "weekly_daily | VALID | open | 1" in human

    assert main(["parent-child-summary", "--db-path", str(db_path), "--case-ref", "case:one", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["filters"] == {"case_ref": "case:one"}
    assert payload["total"] == 1
    assert payload["groups"][0]["link_status"] == "VALID"


def test_parent_child_summary_handles_empty_db(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "empty.sqlite3"
    init_schema(db_path)

    assert main(["parent-child-summary", "--db-path", str(db_path)]) == 0

    assert capsys.readouterr().out.strip() == "No parent-child relationships found."


def test_build_parent_child_rejects_non_weekly_daily_layers(tmp_path: Path) -> None:
    db_path = imported_db(tmp_path, [weekly_range(), daily_range()])

    with pytest.raises(ValueError):
        build_parent_child(db_path, parent_layer="DAILY", child_layer="INTRADAY")


def test_no_generated_sqlite_db_file_committed() -> None:
    generated_databases = [
        path
        for pattern in ("*.sqlite", "*.sqlite3", "*.db")
        for path in Path(__file__).resolve().parents[1].rglob(pattern)
    ]

    assert generated_databases == []
