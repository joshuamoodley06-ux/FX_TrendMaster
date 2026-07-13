from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from range_library_memory.importer import import_source
from range_library_memory.parent_conflict_resolver import resolve_parent_conflicts
from range_library_memory.structure_review_queue import (
    build_structure_review_queue,
    list_structure_review_queue,
)


def weekly_range(range_id: str, case_ref: str, high: float, low: float) -> dict:
    return {
        "range_id": range_id,
        "case_ref": case_ref,
        "symbol": "XAUUSD",
        "structure_layer": "WEEKLY",
        "source_timeframe": "W1",
        "range_high_time": "2026-01-01T00:00:00Z",
        "range_low_time": "2026-01-02T00:00:00Z",
        "active_from_time": "2026-01-02T00:00:00Z",
        "range_high_price": high,
        "range_low_price": low,
        "status": "ACTIVE",
    }


def daily_range(range_id: str, case_ref: str, high: float, low: float) -> dict:
    return {
        "range_id": range_id,
        "case_ref": case_ref,
        "symbol": "XAUUSD",
        "structure_layer": "DAILY",
        "source_timeframe": "D1",
        "range_high_time": "2026-06-17T00:00:00Z",
        "range_low_time": "2026-06-11T00:00:00Z",
        "active_from_time": "2026-06-17T00:00:00Z",
        "range_high_price": high,
        "range_low_price": low,
        "status": "ACTIVE",
    }


def build_duplicate_case_db(tmp_path: Path) -> Path:
    source = tmp_path / "duplicate-cases.json"
    source.write_text(
        json.dumps(
            {
                "ranges": [
                    weekly_range("419", "case:old-copy", 2100.0, 2000.0),
                    weekly_range("425", "case:old-copy", 2120.0, 1990.0),
                    daily_range("420", "case:old-copy", 2050.0, 2020.0),
                    weekly_range("455", "case:live", 3100.0, 3000.0),
                    weekly_range("488", "case:live", 3120.0, 2990.0),
                    weekly_range("535", "case:live", 3300.0, 3200.0),
                    daily_range("420", "case:live", 3050.0, 3020.0),
                ]
            }
        ),
        encoding="utf-8",
    )
    db = tmp_path / "memory.sqlite3"
    import_source(db, source, "fixture")
    return db


def relationship_rows(db: Path) -> list[sqlite3.Row]:
    with sqlite3.connect(db) as connection:
        connection.row_factory = sqlite3.Row
        return connection.execute(
            "SELECT * FROM parent_child_relationships "
            "WHERE child_range_id='420' ORDER BY case_ref"
        ).fetchall()


def test_duplicate_case_range_ids_are_resolved_inside_their_own_case(tmp_path: Path) -> None:
    db = build_duplicate_case_db(tmp_path)

    summary = resolve_parent_conflicts(db)
    rows = relationship_rows(db)

    assert summary["rows_built"] == 2
    assert [(row["case_ref"], row["link_status"]) for row in rows] == [
        ("case:live", "CONFLICT"),
        ("case:old-copy", "CONFLICT"),
    ]

    build_structure_review_queue(db)
    live = list_structure_review_queue(
        db, case_ref="case:live", item_type="PARENT_CONFLICT"
    )
    old = list_structure_review_queue(
        db, case_ref="case:old-copy", item_type="PARENT_CONFLICT"
    )

    assert len(live) == 1
    assert live[0]["range_source_id"] == "420"
    assert live[0]["candidate_range_ids"] == ["455", "488"]
    assert len(old) == 1
    assert old[0]["range_source_id"] == "420"
    assert old[0]["candidate_range_ids"] == ["419", "425"]
    assert live[0]["review_key"] != old[0]["review_key"]


def test_scoped_rebuild_does_not_delete_same_range_id_from_another_case(tmp_path: Path) -> None:
    db = build_duplicate_case_db(tmp_path)
    resolve_parent_conflicts(db)

    resolve_parent_conflicts(db, case_ref="case:old-copy", daily_source_id="420")
    rows = relationship_rows(db)

    assert len(rows) == 2
    assert {row["case_ref"] for row in rows} == {"case:live", "case:old-copy"}
