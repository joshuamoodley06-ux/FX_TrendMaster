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


def fetch_all(db_path: Path, query: str, params: tuple = ()) -> list[sqlite3.Row]:
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        return connection.execute(query, params).fetchall()


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
        "range_end_time": "2026-01-15T00:00:00Z",
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


def relationship(db_path: Path) -> sqlite3.Row:
    return fetch_one(db_path, "SELECT * FROM parent_child_relationships")


def test_parent_child_schema_initializes_table(tmp_path: Path) -> None:
    db_path = tmp_path / "range_library_memory.sqlite3"

    init_schema(db_path)

    row = fetch_one(
        db_path,
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'parent_child_relationships'",
    )
    assert row["name"] == "parent_child_relationships"


def test_explicit_valid_weekly_parent_links_to_daily_child(tmp_path: Path) -> None:
    db_path = imported_db(tmp_path, [weekly_range(), daily_range(parent_range_id="weekly-1")])

    summary = build_parent_child(db_path, parent_layer="WEEKLY", child_layer="DAILY")

    row = relationship(db_path)
    assert summary["relationships_created"] == 1
    assert row["relationship_type"] == "weekly_daily"
    assert row["link_source"] == "explicit"
    assert row["link_status"] == "VALID"
    assert row["link_confidence"] == "high"
    assert row["review_status"] == "open"
    assert row["parent_range_id"] == "weekly-1"
    assert row["child_range_id"] == "daily-1"


def test_explicit_parent_reference_is_preferred_over_inferred_overlap(tmp_path: Path) -> None:
    db_path = imported_db(
        tmp_path,
        [
            weekly_range("weekly-1", range_high_price=2100.0, range_low_price=2000.0),
            weekly_range("weekly-2", range_high_price=2110.0, range_low_price=1990.0),
            daily_range(parent_range_id="weekly-1"),
        ],
    )

    build_parent_child(db_path, parent_layer="WEEKLY", child_layer="DAILY")

    row = relationship(db_path)
    assert row["parent_range_id"] == "weekly-1"
    assert row["link_source"] == "explicit"
    assert row["link_status"] == "VALID"


def test_explicit_inferred_disagreement_becomes_needs_review(tmp_path: Path) -> None:
    explicit = weekly_range("weekly-explicit", range_high_price=2100.0, range_low_price=2000.0)
    inferred = weekly_range("weekly-inferred", range_high_price=1900.0, range_low_price=1800.0)
    child = daily_range(parent_range_id="weekly-explicit", range_high_price=1850.0, range_low_price=1825.0)
    db_path = imported_db(tmp_path, [explicit, inferred, child])

    build_parent_child(db_path, parent_layer="WEEKLY", child_layer="DAILY")

    row = relationship(db_path)
    assert row["parent_range_id"] == "weekly-explicit"
    assert row["link_status"] == "NEEDS_REVIEW"
    assert "disagree" in row["notes"]


def test_missing_parent_with_no_valid_candidate_becomes_orphan(tmp_path: Path) -> None:
    db_path = imported_db(tmp_path, [daily_range()])

    build_parent_child(db_path, parent_layer="WEEKLY", child_layer="DAILY")

    row = relationship(db_path)
    assert row["link_status"] == "ORPHAN"
    assert row["parent_range_id"] is None
    assert row["link_source"] == "inferred"


def test_multiple_inferred_candidates_become_conflict(tmp_path: Path) -> None:
    db_path = imported_db(tmp_path, [weekly_range("weekly-1"), weekly_range("weekly-2"), daily_range()])

    build_parent_child(db_path, parent_layer="WEEKLY", child_layer="DAILY")

    row = relationship(db_path)
    assert row["link_status"] == "CONFLICT"
    assert "Multiple equally plausible" in row["notes"]


def test_active_weekly_allows_child_beyond_anchor_span(tmp_path: Path) -> None:
    db_path = imported_db(
        tmp_path,
        [
            weekly_range(range_end_time="2026-01-05T00:00:00Z", status="ACTIVE"),
            daily_range(range_start_time="2026-01-20T00:00:00Z", range_end_time="2026-01-21T00:00:00Z"),
        ],
    )

    build_parent_child(db_path, parent_layer="WEEKLY", child_layer="DAILY")

    row = relationship(db_path)
    assert row["link_status"] == "VALID"
    assert row["child_lifecycle_relationship"] == "formed_during_active_parent"


def test_inactive_parent_uses_inactive_from_time_cutoff(tmp_path: Path) -> None:
    db_path = imported_db(
        tmp_path,
        [
            weekly_range(status="BROKEN", inactive_from_time="2026-01-12T00:00:00Z"),
            daily_range(range_start_time="2026-01-20T00:00:00Z", range_end_time="2026-01-21T00:00:00Z"),
        ],
    )

    build_parent_child(db_path, parent_layer="WEEKLY", child_layer="DAILY")

    row = relationship(db_path)
    assert row["link_status"] == "ORPHAN"
    assert row["child_lifecycle_relationship"] == "needs_review"


def test_uncertain_inactive_parent_becomes_needs_review(tmp_path: Path) -> None:
    db_path = imported_db(tmp_path, [weekly_range(status="BROKEN"), daily_range(parent_range_id="weekly-1")])

    build_parent_child(db_path, parent_layer="WEEKLY", child_layer="DAILY")

    row = relationship(db_path)
    assert row["link_status"] == "NEEDS_REVIEW"
    assert row["child_lifecycle_relationship"] == "needs_review"


@pytest.mark.parametrize(
    ("low", "high", "expected"),
    [
        (2005.0, 2020.0, "inside_discount"),
        (2038.0, 2060.0, "inside_fair_price"),
        (2080.0, 2095.0, "inside_premium"),
        (2010.0, 2090.0, "spans_zones"),
        (2110.0, 2120.0, "outside_parent"),
    ],
)
def test_child_position_classification(tmp_path: Path, low: float, high: float, expected: str) -> None:
    db_path = imported_db(tmp_path, [weekly_range(), daily_range(parent_range_id="weekly-1", range_low_price=low, range_high_price=high)])

    build_parent_child(db_path, parent_layer="WEEKLY", child_layer="DAILY")

    row = relationship(db_path)
    assert row["child_position_in_parent"] == expected


@pytest.mark.parametrize(
    ("low", "high", "expected"),
    [
        (2025.0, 2050.0, "inside_parent"),
        (2025.0, 2120.0, "breached_parent_high"),
        (1980.0, 2050.0, "breached_parent_low"),
        (1980.0, 2120.0, "breached_both_sides"),
        (2110.0, 2120.0, "outside_parent"),
        (1980.0, 1990.0, "outside_parent"),
    ],
)
def test_boundary_interaction_classification(tmp_path: Path, low: float, high: float, expected: str) -> None:
    db_path = imported_db(tmp_path, [weekly_range(), daily_range(parent_range_id="weekly-1", range_low_price=low, range_high_price=high)])

    build_parent_child(db_path, parent_layer="WEEKLY", child_layer="DAILY")

    row = relationship(db_path)
    assert row["child_boundary_interaction"] == expected


def test_rerun_is_idempotent_and_raw_rows_remain_unchanged(tmp_path: Path) -> None:
    db_path = imported_db(tmp_path, [weekly_range(), daily_range(parent_range_id="weekly-1")])
    before_ranges = count_rows(db_path, "raw_ranges")
    before_events = count_rows(db_path, "raw_events")
    before_payload = fetch_one(db_path, "SELECT raw_payload_json FROM raw_ranges WHERE source_record_id = 'daily-1'")[
        "raw_payload_json"
    ]

    first = build_parent_child(db_path, parent_layer="WEEKLY", child_layer="DAILY")
    second = build_parent_child(db_path, parent_layer="WEEKLY", child_layer="DAILY")

    assert first["relationships_created"] == 1
    assert second["relationships_created"] == 1
    assert count_rows(db_path, "parent_child_relationships") == 1
    assert count_rows(db_path, "raw_ranges") == before_ranges
    assert count_rows(db_path, "raw_events") == before_events
    after_payload = fetch_one(db_path, "SELECT raw_payload_json FROM raw_ranges WHERE source_record_id = 'daily-1'")[
        "raw_payload_json"
    ]
    assert after_payload == before_payload


def test_unsupported_layer_pair_fails_cleanly(tmp_path: Path) -> None:
    db_path = imported_db(tmp_path, [weekly_range(), daily_range()])

    with pytest.raises(ValueError, match="Only WEEKLY parent to DAILY child"):
        build_parent_child(db_path, parent_layer="DAILY", child_layer="INTRADAY")

    with pytest.raises(SystemExit):
        main(
            [
                "build-parent-child",
                "--db-path",
                str(db_path),
                "--parent-layer",
                "DAILY",
                "--child-layer",
                "INTRADAY",
            ]
        )


def test_build_parent_child_cli_supports_case_ref(tmp_path: Path) -> None:
    db_path = imported_db(
        tmp_path,
        [
            weekly_range("weekly-1", case_ref="case:one"),
            daily_range("daily-1", case_ref="case:one"),
            weekly_range("weekly-2", case_ref="case:two"),
            daily_range("daily-2", case_ref="case:two"),
        ],
    )

    assert main(
        [
            "build-parent-child",
            "--db-path",
            str(db_path),
            "--parent-layer",
            "WEEKLY",
            "--child-layer",
            "DAILY",
            "--case-ref",
            "case:one",
        ]
    ) == 0

    rows = fetch_all(db_path, "SELECT case_ref FROM parent_child_relationships")
    assert [row["case_ref"] for row in rows] == ["case:one"]


def test_parent_child_summary_human_output_is_deterministic(tmp_path: Path, capsys) -> None:
    db_path = imported_db(
        tmp_path,
        [
            weekly_range("weekly-1", case_ref="case:one"),
            daily_range("daily-1", case_ref="case:one"),
            daily_range("daily-2", case_ref="case:two"),
        ],
    )
    build_parent_child(db_path, parent_layer="WEEKLY", child_layer="DAILY")

    assert main(["parent-child-summary", "--db-path", str(db_path)]) == 0
    output = capsys.readouterr().out.strip()

    assert "case_ref | relationship_type | total | valid | orphan | conflict | needs_review" in output
    assert "case:one | weekly_daily | 1 | 1 | 0 | 0 | 0" in output
    assert "case:two | weekly_daily | 1 | 0 | 1 | 0 | 0" in output
    assert "child_position_in_parent" in output
    assert "child_boundary_interaction" in output
    assert "child_lifecycle_relationship" in output
    assert "link_source" in output


def test_parent_child_summary_json_output_is_deterministic(tmp_path: Path, capsys) -> None:
    db_path = imported_db(tmp_path, [weekly_range(), daily_range()])
    build_parent_child(db_path, parent_layer="WEEKLY", child_layer="DAILY")

    assert main(["parent-child-summary", "--db-path", str(db_path), "--case-ref", "case:one", "--json"]) == 0

    output = capsys.readouterr().out.strip()
    payload = json.loads(output)
    assert output == json.dumps(payload, sort_keys=True, separators=(",", ":"))
    assert payload["filters"] == {"case_ref": "case:one"}
    assert payload["totals"]["relationships"] == 1
    assert payload["by_case"][0]["link_status"] is None if "link_status" in payload["by_case"][0] else True
    assert payload["groups"]["link_source"][0] == {"count": 1, "value": "inferred"}


def test_parent_child_summary_handles_empty_db(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "empty.sqlite3"
    init_schema(db_path)

    assert main(["parent-child-summary", "--db-path", str(db_path)]) == 0

    assert capsys.readouterr().out.strip() == "No parent-child relationships found."


def test_no_generated_sqlite_db_file_committed() -> None:
    generated_databases = [
        path
        for pattern in ("*.sqlite", "*.sqlite3", "*.db")
        for path in Path(__file__).resolve().parents[1].rglob(pattern)
    ]

    assert generated_databases == []
