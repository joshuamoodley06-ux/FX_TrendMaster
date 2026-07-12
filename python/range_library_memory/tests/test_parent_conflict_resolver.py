from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from range_library_memory.importer import import_source
from range_library_memory.parent_child import build_parent_child
from range_library_memory.parent_conflict_resolver import (
    main,
    resolve_parent_conflicts,
    summarize_parent_conflicts,
)


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
        "range_high_time": "2026-01-01T00:00:00Z",
        "range_low_time": "2026-01-02T00:00:00Z",
        "active_from_time": "2026-01-02T00:00:00Z",
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
        "range_high_time": "2026-01-10T00:00:00Z",
        "range_low_time": "2026-01-09T00:00:00Z",
        "active_from_time": "2026-01-10T00:00:00Z",
        "range_high_price": 2050.0,
        "range_low_price": 2025.0,
        "status": "ACTIVE",
    }
    value.update(overrides)
    return value


def imported_db(tmp_path: Path, ranges: list[dict]) -> Path:
    db = tmp_path / "memory.sqlite3"
    import_source(db, write_source(tmp_path, "ranges.json", ranges), "fixture")
    return db


def fetch_one(db: Path, query: str, params: tuple = ()) -> sqlite3.Row:
    with sqlite3.connect(db) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(query, params).fetchone()
    assert row is not None
    return row


def count_rows(db: Path, table: str) -> int:
    return int(fetch_one(db, f"SELECT COUNT(*) AS count FROM {table}")["count"])


def latest_relationship(db: Path, child_id: str = "daily-1") -> sqlite3.Row:
    return fetch_one(
        db,
        "SELECT * FROM parent_child_relationships "
        "WHERE child_range_id=? ORDER BY id DESC LIMIT 1",
        (child_id,),
    )


def insert_lifecycle(
    db: Path,
    *,
    range_id: str,
    effective_status: str,
    active: str,
    inactive: str | None,
    resolution_status: str = "OHLC_DERIVED",
) -> None:
    with sqlite3.connect(db) as connection:
        raw = connection.execute(
            "SELECT id, import_run_id, raw_payload_json "
            "FROM raw_ranges WHERE source_record_id=? ORDER BY id DESC LIMIT 1",
            (range_id,),
        ).fetchone()
        assert raw is not None
        payload = json.loads(raw[2])
        now = "2026-03-01T00:00:00Z"
        connection.execute(
            """INSERT INTO resolved_range_lifecycles(
               built_at_utc,import_run_id,case_ref,symbol,structure_layer,source_timeframe,
               range_source_id,raw_range_id,raw_status,raw_active_from_time,
               raw_inactive_from_time,raw_broken_by_event_id,effective_status,
               effective_active_from_time,effective_inactive_from_time,resolution_source,
               resolution_status,resolution_confidence,supporting_event_source_id,
               supporting_evidence_id,reason_codes_json,as_of_time,created_at_utc,updated_at_utc
               ) VALUES(
               ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
               )""",
            (
                now,
                raw[1],
                payload.get("case_ref"),
                payload.get("symbol", "XAUUSD"),
                "WEEKLY",
                "W1",
                range_id,
                raw[0],
                payload.get("status"),
                payload.get("active_from_time"),
                payload.get("inactive_from_time"),
                payload.get("broken_by_event_id"),
                effective_status,
                active,
                inactive,
                "OHLC",
                resolution_status,
                "high",
                "event-1" if inactive else None,
                None,
                "[]",
                now,
                now,
                now,
            ),
        )


def test_factual_lifecycle_confirms_explicit_broken_parent(tmp_path: Path) -> None:
    db = imported_db(
        tmp_path,
        [
            weekly_range(status="BROKEN"),
            daily_range(parent_range_id="weekly-1"),
        ],
    )
    build_parent_child(db, parent_layer="WEEKLY", child_layer="DAILY")
    assert latest_relationship(db)["link_status"] == "NEEDS_REVIEW"

    insert_lifecycle(
        db,
        range_id="weekly-1",
        effective_status="BROKEN",
        active="2026-01-02T00:00:00Z",
        inactive="2026-02-01T00:00:00Z",
    )
    summary = resolve_parent_conflicts(db)
    row = latest_relationship(db)

    assert summary["derived_lifecycle_confirmed_count"] == 1
    assert row["link_status"] == "VALID"
    assert row["link_source"] == "resolver_explicit_lifecycle"
    assert row["parent_range_id"] == "weekly-1"


def test_explicit_parent_after_factual_cutoff_is_not_silently_reassigned(tmp_path: Path) -> None:
    db = imported_db(
        tmp_path,
        [
            weekly_range("weekly-old", status="BROKEN"),
            weekly_range(
                "weekly-new",
                range_high_price=2075.0,
                range_low_price=2000.0,
                active_from_time="2026-01-06T00:00:00Z",
                range_high_time="2026-01-06T00:00:00Z",
                range_low_time="2026-01-07T00:00:00Z",
            ),
            daily_range(parent_range_id="weekly-old"),
        ],
    )
    insert_lifecycle(
        db,
        range_id="weekly-old",
        effective_status="BROKEN",
        active="2026-01-02T00:00:00Z",
        inactive="2026-01-05T00:00:00Z",
    )

    resolve_parent_conflicts(db)
    row = latest_relationship(db)

    assert row["link_status"] == "NEEDS_REVIEW"
    assert row["parent_range_id"] == "weekly-old"
    assert "weekly-new" in row["notes"]
    assert "not confirmed" in row["notes"]


def test_explicit_valid_parent_wins_over_other_overlapping_weeklies(tmp_path: Path) -> None:
    db = imported_db(
        tmp_path,
        [
            weekly_range("weekly-1"),
            weekly_range("weekly-2", range_high_price=2110.0, range_low_price=1990.0),
            daily_range(parent_range_id="weekly-1"),
        ],
    )

    resolve_parent_conflicts(db)
    row = latest_relationship(db)

    assert row["link_status"] == "VALID"
    assert row["parent_range_id"] == "weekly-1"
    assert row["link_source"] == "resolver_explicit"


def test_unique_inferred_parent_is_confirmed(tmp_path: Path) -> None:
    db = imported_db(
        tmp_path,
        [
            weekly_range(),
            daily_range(),
        ],
    )

    summary = resolve_parent_conflicts(db)
    row = latest_relationship(db)

    assert summary["inferred_confirmed_count"] == 1
    assert row["link_status"] == "VALID"
    assert row["link_source"] == "resolver_inferred"
    assert row["parent_range_id"] == "weekly-1"


def test_multiple_inferred_parents_remain_conflict_without_arbitrary_choice(tmp_path: Path) -> None:
    db = imported_db(
        tmp_path,
        [
            weekly_range("weekly-1"),
            weekly_range("weekly-2", range_high_price=2110.0, range_low_price=1990.0),
            daily_range(),
        ],
    )

    resolve_parent_conflicts(db)
    row = latest_relationship(db)

    assert row["link_status"] == "CONFLICT"
    assert row["parent_range_id"] is None
    assert "weekly-1" in row["notes"]
    assert "weekly-2" in row["notes"]


def test_no_compatible_weekly_remains_true_orphan(tmp_path: Path) -> None:
    db = imported_db(
        tmp_path,
        [
            weekly_range(range_high_price=1900.0, range_low_price=1800.0),
            daily_range(),
        ],
    )

    resolve_parent_conflicts(db)
    row = latest_relationship(db)

    assert row["link_status"] == "ORPHAN"
    assert row["parent_range_id"] is None


def test_latest_raw_version_is_used_instead_of_stale_import(tmp_path: Path) -> None:
    db = tmp_path / "memory.sqlite3"
    import_source(
        db,
        write_source(
            tmp_path,
            "first.json",
            [
                weekly_range(range_high_price=2100.0, range_low_price=2000.0),
                daily_range(
                    parent_range_id="weekly-1",
                    range_high_price=1850.0,
                    range_low_price=1825.0,
                ),
            ],
        ),
        "fixture",
    )
    import_source(
        db,
        write_source(
            tmp_path,
            "second.json",
            [
                weekly_range(range_high_price=1900.0, range_low_price=1800.0),
                daily_range(
                    parent_range_id="weekly-1",
                    range_high_price=1850.0,
                    range_low_price=1825.0,
                ),
            ],
        ),
        "fixture",
    )

    resolve_parent_conflicts(db)
    row = latest_relationship(db)

    assert row["link_status"] == "VALID"
    assert row["parent_range_id"] == "weekly-1"


def test_scoped_rebuild_is_idempotent_and_preserves_raw_mapping(tmp_path: Path) -> None:
    db = imported_db(
        tmp_path,
        [
            weekly_range("weekly-1", case_ref="case:one"),
            daily_range("daily-1", case_ref="case:one", parent_range_id="weekly-1"),
            weekly_range("weekly-2", case_ref="case:two"),
            daily_range("daily-2", case_ref="case:two", parent_range_id="weekly-2"),
        ],
    )
    before_raw = count_rows(db, "raw_ranges")
    with sqlite3.connect(db) as connection:
        before_payloads = [
            row[0]
            for row in connection.execute(
                "SELECT raw_payload_json FROM raw_ranges ORDER BY id"
            ).fetchall()
        ]

    resolve_parent_conflicts(db)
    resolve_parent_conflicts(db, case_ref="case:one")
    resolve_parent_conflicts(db, case_ref="case:one")

    assert count_rows(db, "raw_ranges") == before_raw
    assert count_rows(db, "parent_child_relationships") == 2
    with sqlite3.connect(db) as connection:
        after_payloads = [
            row[0]
            for row in connection.execute(
                "SELECT raw_payload_json FROM raw_ranges ORDER BY id"
            ).fetchall()
        ]
    assert after_payloads == before_payloads
    assert latest_relationship(db, "daily-2")["link_status"] == "VALID"


def test_module_cli_outputs_deterministic_json(tmp_path: Path, capsys) -> None:
    db = imported_db(tmp_path, [weekly_range(), daily_range()])

    assert main(["resolve", "--db-path", str(db), "--json"]) == 0
    output = capsys.readouterr().out.strip()
    payload = json.loads(output)

    assert output == json.dumps(payload, sort_keys=True, separators=(",", ":"))
    assert payload["valid_count"] == 1
    assert summarize_parent_conflicts(db)["total"] == 1
