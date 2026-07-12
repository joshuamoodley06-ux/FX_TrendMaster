from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from range_library_memory.importer import import_source
from range_library_memory.parent_child import build_parent_child
from range_library_memory.parent_conflict_resolver import resolve_parent_conflicts


def write_source(tmp_path: Path, name: str, ranges: list[dict]) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps({"ranges": ranges}), encoding="utf-8")
    return path


def weekly_range(range_id: str = "weekly-1", **overrides) -> dict:
    value = {
        "range_id": range_id,
        "case_ref": "case:one",
        "symbol": "XAUUSD",
        "structure_layer": "WEEKLY",
        "source_timeframe": "W1",
        "range_start_time": "2026-01-01T00:00:00Z",
        "range_end_time": "2026-01-15T00:00:00Z",
        "range_high_time": "2026-01-11T00:00:00Z",
        "range_low_time": "2026-01-12T00:00:00Z",
        "active_from_time": "2026-01-12T00:00:00Z",
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
        "range_start_time": "2026-01-13T00:00:00Z",
        "range_end_time": "2026-01-14T00:00:00Z",
        "range_high_time": "2026-01-14T00:00:00Z",
        "range_low_time": "2026-01-13T00:00:00Z",
        "active_from_time": "2026-01-14T00:00:00Z",
        "range_high_price": 2050.0,
        "range_low_price": 2025.0,
        "status": "ACTIVE",
    }
    value.update(overrides)
    return value


def imported_db(tmp_path: Path, ranges: list[dict]) -> Path:
    db = tmp_path / "memory.sqlite3"
    import_source(
        db,
        write_source(tmp_path, "ranges.json", ranges),
        "fixture",
    )
    return db


def latest_relationship(db: Path, child_id: str = "daily-1") -> sqlite3.Row:
    with sqlite3.connect(db) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """
            SELECT *
            FROM parent_child_relationships
            WHERE child_range_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (child_id,),
        ).fetchone()
    assert row is not None
    return row


def test_existing_valid_parent_is_preferred_when_new_overlap_appears(
    tmp_path: Path,
) -> None:
    db = imported_db(
        tmp_path,
        [weekly_range("weekly-1"), daily_range()],
    )
    build_parent_child(
        db,
        parent_layer="WEEKLY",
        child_layer="DAILY",
    )
    assert latest_relationship(db)["parent_range_id"] == "weekly-1"
    assert latest_relationship(db)["link_status"] == "VALID"

    import_source(
        db,
        write_source(
            tmp_path,
            "later.json",
            [
                weekly_range(
                    "weekly-2",
                    range_high_price=2110.0,
                    range_low_price=1990.0,
                )
            ],
        ),
        "fixture",
    )

    resolve_parent_conflicts(db)
    row = latest_relationship(db)

    assert row["parent_range_id"] == "weekly-1"
    assert row["link_status"] == "VALID"
    assert str(row["link_source"]).startswith("resolver_existing")


def test_existing_review_parent_is_not_dropped_for_one_alternative(
    tmp_path: Path,
) -> None:
    db = imported_db(
        tmp_path,
        [
            weekly_range("weekly-1", status="BROKEN"),
            weekly_range(
                "weekly-2",
                range_high_price=2110.0,
                range_low_price=1990.0,
            ),
            daily_range(parent_range_id="weekly-1"),
        ],
    )
    build_parent_child(
        db,
        parent_layer="WEEKLY",
        child_layer="DAILY",
    )
    assert latest_relationship(db)["link_status"] == "NEEDS_REVIEW"

    resolve_parent_conflicts(db)
    row = latest_relationship(db)

    assert row["parent_range_id"] == "weekly-1"
    assert row["link_status"] == "NEEDS_REVIEW"
    assert "weekly-2" in row["notes"]


def test_child_span_overlapping_weekly_formation_is_not_demoted(
    tmp_path: Path,
) -> None:
    db = imported_db(
        tmp_path,
        [
            weekly_range(),
            daily_range(
                range_start_time="2026-01-08T00:00:00Z",
                range_end_time="2026-01-13T00:00:00Z",
                range_high_time="2026-01-09T00:00:00Z",
                range_low_time="2026-01-08T00:00:00Z",
                active_from_time="2026-01-09T00:00:00Z",
            ),
        ],
    )
    build_parent_child(
        db,
        parent_layer="WEEKLY",
        child_layer="DAILY",
    )
    assert latest_relationship(db)["link_status"] == "VALID"

    resolve_parent_conflicts(db)
    row = latest_relationship(db)

    assert row["parent_range_id"] == "weekly-1"
    assert row["link_status"] == "VALID"


def test_existing_conflict_does_not_become_an_arbitrary_parent(
    tmp_path: Path,
) -> None:
    db = imported_db(
        tmp_path,
        [
            weekly_range("weekly-1"),
            weekly_range(
                "weekly-2",
                range_high_price=2110.0,
                range_low_price=1990.0,
            ),
            daily_range(),
        ],
    )
    build_parent_child(
        db,
        parent_layer="WEEKLY",
        child_layer="DAILY",
    )
    assert latest_relationship(db)["link_status"] == "CONFLICT"

    resolve_parent_conflicts(db)
    row = latest_relationship(db)

    assert row["link_status"] == "CONFLICT"
    assert row["parent_range_id"] is None
