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
from range_library_memory.schema import init_schema
from range_library_memory.source_market_db import SourceMarketDbError, load_candles, open_source_market_db
from range_library_memory.weekly_family_coverage import (
    WeeklyFamilyCoverageError,
    analyze_weekly_family_coverage,
    format_weekly_family_coverage,
)


def create_memory_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "range_library_memory.sqlite3"
    init_schema(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO import_runs (
                id, run_uuid, source_path, source_kind, started_at_utc, status
            ) VALUES (1, 'run-1', 'fixture.json', 'fixture', '2026-01-01T00:00:00Z', 'completed')
            """
        )
    return db_path


def create_source_db(tmp_path: Path, *, include_candles: bool = True, include_map_ranges: bool = True) -> Path:
    db_path = tmp_path / "market_memory.db"
    with sqlite3.connect(db_path) as connection:
        if include_candles:
            connection.execute(
                """
                CREATE TABLE candles (
                    symbol TEXT,
                    timeframe TEXT,
                    time TEXT,
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL,
                    volume REAL,
                    source TEXT
                )
                """
            )
        if include_map_ranges:
            connection.execute(
                """
                CREATE TABLE map_ranges (
                    id INTEGER PRIMARY KEY,
                    parent_link_status TEXT
                )
                """
            )
            connection.execute("INSERT INTO map_ranges (id, parent_link_status) VALUES (433, 'LEGACY_WRONG')")
    return db_path


def add_candles(source_db: Path, dates: list[str]) -> None:
    with sqlite3.connect(source_db) as connection:
        connection.executemany(
            """
            INSERT INTO candles (symbol, timeframe, time, open, high, low, close, volume, source)
            VALUES ('XAUUSD', 'D1', ?, 2000.0, 2010.0, 1990.0, 2005.0, 100.0, 'fixture')
            """,
            [(date,) for date in dates],
        )


def add_range(db_path: Path, source_id: str, payload: dict) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO raw_ranges (
                import_run_id, source_record_id, symbol, timeframe, range_type,
                start_time_utc, end_time_utc, high, low, raw_payload_json,
                payload_sha256, created_at_utc
            ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '2026-01-01T00:00:00Z')
            """,
            (
                source_id,
                payload.get("symbol", "XAUUSD"),
                payload.get("source_timeframe"),
                payload.get("structure_layer"),
                payload.get("range_start_time"),
                payload.get("range_end_time"),
                payload.get("range_high_price"),
                payload.get("range_low_price"),
                json.dumps(payload, sort_keys=True),
                f"sha-{source_id}",
            ),
        )


def add_raw_range_version(db_path: Path, source_id: str, payload: dict) -> None:
    add_range(db_path, source_id, payload)


def add_relationship(
    db_path: Path,
    *,
    parent_id: str = "433",
    child_id: str = "501",
    link_status: str = "VALID",
    link_source: str = "explicit",
    link_confidence: str = "high",
    review_status: str = "open",
) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO parent_child_relationships (
                import_run_id, case_ref, symbol, relationship_type,
                parent_range_id, child_range_id, parent_layer, child_layer,
                parent_timeframe, child_timeframe, link_source, link_status,
                link_confidence, review_status, child_position_in_parent,
                child_boundary_interaction, child_lifecycle_relationship,
                notes, created_at_utc, updated_at_utc
            ) VALUES (
                1, 'case:one', 'XAUUSD', 'weekly_daily',
                ?, ?, 'WEEKLY', 'DAILY',
                'W1', 'D1', ?, ?,
                ?, ?, 'inside_fair_price',
                'inside_parent', 'formed_during_active_parent',
                '', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z'
            )
            """,
            (parent_id, child_id, link_source, link_status, link_confidence, review_status),
        )


def weekly_payload(**overrides) -> dict:
    payload = {
        "range_id": "433",
        "case_ref": "case:one",
        "symbol": "XAUUSD",
        "structure_layer": "WEEKLY",
        "source_timeframe": "W1",
        "range_start_time": "2026-01-01T00:00:00Z",
        "range_end_time": "2026-01-06T00:00:00Z",
        "active_from_time": "2026-01-01T00:00:00Z",
        "inactive_from_time": "2026-01-06T00:00:00Z",
        "range_high_time": "2026-01-02T00:00:00Z",
        "range_low_time": "2026-01-01T00:00:00Z",
        "range_high_price": 2100.0,
        "range_low_price": 2000.0,
        "status": "BROKEN",
        "direction_of_break": "DOWN",
    }
    payload.update(overrides)
    return payload


def daily_payload(range_id: str, *, active: str, inactive: str | None, **overrides) -> dict:
    payload = {
        "range_id": range_id,
        "case_ref": "case:one",
        "symbol": "XAUUSD",
        "structure_layer": "DAILY",
        "source_timeframe": "D1",
        "range_start_time": active,
        "range_end_time": inactive or active,
        "active_from_time": active,
        "inactive_from_time": inactive,
        "range_high_price": 2070.0,
        "range_low_price": 2030.0,
        "status": "BROKEN" if inactive else "ACTIVE",
        "direction_of_break": "UP" if inactive else None,
    }
    payload.update(overrides)
    return payload


def base_full_case(tmp_path: Path) -> tuple[Path, Path]:
    memory_db = create_memory_db(tmp_path)
    source_db = create_source_db(tmp_path)
    add_candles(
        source_db,
        [
            "2026-01-01T00:00:00Z",
            "2026-01-02T00:00:00Z",
            "2026-01-03T00:00:00Z",
            "2026-01-04T00:00:00Z",
            "2026-01-05T00:00:00Z",
            "2026-01-06T00:00:00Z",
        ],
    )
    add_range(memory_db, "433", weekly_payload())
    add_range(memory_db, "501", daily_payload("501", active="2026-01-02T00:00:00Z", inactive="2026-01-04T00:00:00Z"))
    add_range(memory_db, "502", daily_payload("502", active="2026-01-05T00:00:00Z", inactive="2026-01-06T00:00:00Z"))
    add_relationship(memory_db, child_id="501")
    add_relationship(memory_db, child_id="502")
    return memory_db, source_db


def count_rows(db_path: Path, table: str) -> int:
    with sqlite3.connect(db_path) as connection:
        return connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_full_post_formation_daily_coverage(tmp_path: Path) -> None:
    memory_db, source_db = base_full_case(tmp_path)

    report = analyze_weekly_family_coverage(memory_db, source_db=source_db, weekly_source_id="433")

    post = report["windows"]["post_formation"]
    assert post["d1_candle_count"] == 5
    assert post["candle_data_status"] == "AVAILABLE"
    assert post["covered_candle_count"] == 5
    assert post["coverage_status"] == "FULL"
    assert report["post_formation_gaps"] == []


def test_source_adapter_loads_metatrader_timestamps_as_canonical_iso(tmp_path: Path) -> None:
    source_db = create_source_db(tmp_path)
    add_candles(source_db, ["2026.01.02 00:00", "2026.01.03 00:00"])

    with open_source_market_db(source_db) as connection:
        candles = load_candles(
            connection,
            symbol="XAUUSD",
            timeframe="D1",
            start_time="2026-01-02T00:00:00Z",
            end_time="2026-01-03T00:00:00Z",
        )

    assert [candle.time for candle in candles] == ["2026-01-02T00:00:00Z", "2026-01-03T00:00:00Z"]
    assert candles[0].open == 2000.0
    assert candles[0].source == "fixture"


def test_source_adapter_loads_space_separated_iso_timestamps(tmp_path: Path) -> None:
    source_db = create_source_db(tmp_path)
    add_candles(source_db, ["2026-01-02 00:00:00"])

    with open_source_market_db(source_db) as connection:
        candles = load_candles(
            connection,
            symbol="XAUUSD",
            timeframe="D1",
            start_time="2026-01-02T00:00:00Z",
            end_time="2026-01-02T00:00:00Z",
        )

    assert candles[0].time == "2026-01-02T00:00:00Z"


def test_source_adapter_loads_millisecond_iso_timestamps(tmp_path: Path) -> None:
    source_db = create_source_db(tmp_path)
    add_candles(source_db, ["2026-01-02T00:00:00.000Z"])

    with open_source_market_db(source_db) as connection:
        candles = load_candles(
            connection,
            symbol="XAUUSD",
            timeframe="D1",
            start_time="2026-01-02T00:00:00Z",
            end_time="2026-01-02T00:00:00Z",
        )

    assert candles[0].time == "2026-01-02T00:00:00Z"


def test_source_adapter_loads_mixed_supported_timestamp_formats(tmp_path: Path) -> None:
    source_db = create_source_db(tmp_path)
    add_candles(
        source_db,
        [
            "2026.01.03 00:00",
            "2026-01-02 00:00:00",
            "2026-01-04T00:00:00.000Z",
            "2026-01-05T02:00:00+02:00",
        ],
    )

    with open_source_market_db(source_db) as connection:
        candles = load_candles(
            connection,
            symbol="XAUUSD",
            timeframe="D1",
            start_time="2026-01-02T00:00:00Z",
            end_time="2026-01-05T00:00:00Z",
        )

    assert [candle.time for candle in candles] == [
        "2026-01-02T00:00:00Z",
        "2026-01-03T00:00:00Z",
        "2026-01-04T00:00:00Z",
        "2026-01-05T00:00:00Z",
    ]


def test_source_adapter_filters_inclusive_start_and_end_after_parsing(tmp_path: Path) -> None:
    source_db = create_source_db(tmp_path)
    add_candles(source_db, ["2026.01.01 00:00", "2026.01.02 00:00", "2026.01.03 00:00", "2026.01.04 00:00"])

    with open_source_market_db(source_db) as connection:
        candles = load_candles(
            connection,
            symbol="XAUUSD",
            timeframe="D1",
            start_time="2026-01-02T00:00:00Z",
            end_time="2026-01-03T00:00:00Z",
        )

    assert [candle.time for candle in candles] == ["2026-01-02T00:00:00Z", "2026-01-03T00:00:00Z"]


def test_malformed_source_timestamp_fails_with_context(tmp_path: Path) -> None:
    source_db = create_source_db(tmp_path)
    add_candles(source_db, ["not-a-time"])

    with open_source_market_db(source_db) as connection:
        with pytest.raises(SourceMarketDbError, match="symbol=XAUUSD timeframe=D1: not-a-time"):
            load_candles(
                connection,
                symbol="XAUUSD",
                timeframe="D1",
                start_time="2026-01-02T00:00:00Z",
                end_time="2026-01-03T00:00:00Z",
            )


def test_partial_coverage_reports_exact_missing_d1_candle_timestamps(tmp_path: Path) -> None:
    memory_db, source_db = base_full_case(tmp_path)
    with sqlite3.connect(memory_db) as connection:
        connection.execute("DELETE FROM parent_child_relationships WHERE child_range_id = '502'")
        connection.execute("DELETE FROM raw_ranges WHERE source_record_id = '502'")
        connection.execute(
            "UPDATE raw_ranges SET raw_payload_json = ? WHERE source_record_id = '501'",
            (
                json.dumps(
                    daily_payload("501", active="2026-01-02T00:00:00Z", inactive="2026-01-03T00:00:00Z"),
                    sort_keys=True,
                ),
            ),
        )

    report = analyze_weekly_family_coverage(memory_db, source_db=source_db, weekly_source_id="433")

    assert report["windows"]["post_formation"]["coverage_status"] == "PARTIAL"
    assert report["post_formation_gaps"] == [
        {"candle_time": "2026-01-04T00:00:00Z"},
        {"candle_time": "2026-01-05T00:00:00Z"},
        {"candle_time": "2026-01-06T00:00:00Z"},
    ]


def test_overlapping_daily_children_are_reported(tmp_path: Path) -> None:
    memory_db, source_db = base_full_case(tmp_path)
    add_range(memory_db, "503", daily_payload("503", active="2026-01-03T00:00:00Z", inactive="2026-01-05T00:00:00Z"))
    add_relationship(memory_db, child_id="503")

    report = analyze_weekly_family_coverage(memory_db, source_db=source_db, weekly_source_id="433")

    assert report["overlaps"] == [
        {"candle_time": "2026-01-03T00:00:00Z", "child_source_ids": ["501", "503"]},
        {"candle_time": "2026-01-04T00:00:00Z", "child_source_ids": ["501", "503"]},
        {"candle_time": "2026-01-05T00:00:00Z", "child_source_ids": ["502", "503"]},
    ]
    assert report["counts"]["overlap_candles"] == 3


def test_active_weekly_requires_as_of(tmp_path: Path) -> None:
    memory_db, source_db = base_full_case(tmp_path)
    add_range(
        memory_db,
        "419",
        weekly_payload(range_id="419", inactive_from_time=None, status="ACTIVE"),
    )

    with pytest.raises(WeeklyFamilyCoverageError, match="requires --as-of"):
        analyze_weekly_family_coverage(memory_db, source_db=source_db, weekly_source_id="419")


def test_active_daily_child_uses_parent_as_of_cutoff(tmp_path: Path) -> None:
    memory_db = create_memory_db(tmp_path)
    source_db = create_source_db(tmp_path)
    add_candles(
        source_db,
        ["2026-01-02T00:00:00Z", "2026-01-03T00:00:00Z", "2026-01-04T00:00:00Z", "2026-01-05T00:00:00Z"],
    )
    add_range(memory_db, "433", weekly_payload(inactive_from_time=None, status="ACTIVE"))
    add_range(memory_db, "501", daily_payload("501", active="2026-01-03T00:00:00Z", inactive=None))
    add_relationship(memory_db, child_id="501")

    report = analyze_weekly_family_coverage(
        memory_db,
        source_db=source_db,
        weekly_source_id="433",
        as_of="2026-01-05T00:00:00Z",
    )

    assert report["windows"]["post_formation"]["covered_candle_count"] == 3
    assert report["post_formation_gaps"] == [{"candle_time": "2026-01-02T00:00:00Z"}]


def test_weekly_lifecycle_start_after_end_fails(tmp_path: Path) -> None:
    memory_db, source_db = base_full_case(tmp_path)
    with sqlite3.connect(memory_db) as connection:
        connection.execute(
            "UPDATE raw_ranges SET raw_payload_json = ? WHERE source_record_id = '433'",
            (
                json.dumps(
                    weekly_payload(
                        active_from_time="2026-01-07T00:00:00Z",
                        inactive_from_time="2026-01-06T00:00:00Z",
                    ),
                    sort_keys=True,
                ),
            ),
        )

    with pytest.raises(WeeklyFamilyCoverageError, match="Weekly lifecycle start is after end"):
        analyze_weekly_family_coverage(memory_db, source_db=source_db, weekly_source_id="433")


def test_post_formation_start_after_lifecycle_end_fails(tmp_path: Path) -> None:
    memory_db, source_db = base_full_case(tmp_path)
    with sqlite3.connect(memory_db) as connection:
        connection.execute(
            "UPDATE raw_ranges SET raw_payload_json = ? WHERE source_record_id = '433'",
            (
                json.dumps(
                    weekly_payload(
                        inactive_from_time="2026-01-06T00:00:00Z",
                        range_high_time="2026-01-08T00:00:00Z",
                        range_low_time="2026-01-07T00:00:00Z",
                    ),
                    sort_keys=True,
                ),
            ),
        )

    with pytest.raises(WeeklyFamilyCoverageError, match="Weekly post-formation start is after lifecycle end"):
        analyze_weekly_family_coverage(memory_db, source_db=source_db, weekly_source_id="433")


def test_daily_child_active_time_after_inactive_time_fails(tmp_path: Path) -> None:
    memory_db, source_db = base_full_case(tmp_path)
    add_range(
        memory_db,
        "507",
        daily_payload("507", active="2026-06-17T00:00:00Z", inactive="2026-04-28T00:00:00Z"),
    )
    add_relationship(memory_db, child_id="507")

    with pytest.raises(
        WeeklyFamilyCoverageError,
        match="Daily child lifecycle start is after end: 507 2026-06-17T00:00:00Z > 2026-04-28T00:00:00Z",
    ):
        analyze_weekly_family_coverage(memory_db, source_db=source_db, weekly_source_id="433")


def test_zero_candles_reports_no_candles_status(tmp_path: Path) -> None:
    memory_db = create_memory_db(tmp_path)
    source_db = create_source_db(tmp_path)
    add_range(memory_db, "433", weekly_payload())

    report = analyze_weekly_family_coverage(memory_db, source_db=source_db, weekly_source_id="433")

    assert report["windows"]["parent_lifecycle"]["candle_data_status"] == "NO_CANDLES"
    assert report["windows"]["post_formation"]["candle_data_status"] == "NO_CANDLES"
    assert report["windows"]["post_formation"]["coverage_status"] == "NONE"


def test_latest_weekly_raw_range_version_is_used_for_lifecycle(tmp_path: Path) -> None:
    memory_db = create_memory_db(tmp_path)
    source_db = create_source_db(tmp_path)
    add_candles(
        source_db,
        [
            "2026-01-02T00:00:00Z",
            "2026-01-03T00:00:00Z",
            "2026-01-04T00:00:00Z",
            "2026-01-05T00:00:00Z",
        ],
    )
    add_raw_range_version(
        memory_db,
        "433",
        weekly_payload(inactive_from_time="2026-01-03T00:00:00Z", range_end_time="2026-01-03T00:00:00Z"),
    )
    add_raw_range_version(
        memory_db,
        "433",
        weekly_payload(inactive_from_time="2026-01-05T00:00:00Z", range_end_time="2026-01-05T00:00:00Z"),
    )
    add_range(memory_db, "501", daily_payload("501", active="2026-01-02T00:00:00Z", inactive="2026-01-05T00:00:00Z"))
    add_relationship(memory_db, child_id="501")

    report = analyze_weekly_family_coverage(memory_db, source_db=source_db, weekly_source_id="433")

    assert report["windows"]["post_formation"]["end_time"] == "2026-01-05T00:00:00Z"
    assert report["windows"]["post_formation"]["d1_candle_count"] == 4
    assert report["windows"]["post_formation"]["coverage_status"] == "FULL"


def test_latest_daily_raw_range_version_is_used_for_coverage(tmp_path: Path) -> None:
    memory_db, source_db = base_full_case(tmp_path)
    add_raw_range_version(
        memory_db,
        "501",
        daily_payload("501", active="2026-01-02T00:00:00Z", inactive="2026-01-06T00:00:00Z"),
    )
    with sqlite3.connect(memory_db) as connection:
        connection.execute("DELETE FROM parent_child_relationships WHERE child_range_id = '502'")
        connection.execute("DELETE FROM raw_ranges WHERE source_record_id = '502'")

    report = analyze_weekly_family_coverage(memory_db, source_db=source_db, weekly_source_id="433")

    assert report["windows"]["post_formation"]["covered_candle_count"] == 5
    assert report["windows"]["post_formation"]["coverage_status"] == "FULL"


def test_unresolved_linked_daily_child_fails_cleanly(tmp_path: Path) -> None:
    memory_db, source_db = base_full_case(tmp_path)
    add_relationship(memory_db, child_id="missing-daily")

    with pytest.raises(WeeklyFamilyCoverageError, match="missing-daily"):
        analyze_weekly_family_coverage(memory_db, source_db=source_db, weekly_source_id="433")


def test_broken_child_missing_inactive_from_time_fails(tmp_path: Path) -> None:
    memory_db, source_db = base_full_case(tmp_path)
    add_range(
        memory_db,
        "505",
        daily_payload("505", active="2026-01-03T00:00:00Z", inactive=None, status="BROKEN"),
    )
    add_relationship(memory_db, child_id="505")

    with pytest.raises(WeeklyFamilyCoverageError, match="BROKEN Daily child is missing inactive_from_time: 505"):
        analyze_weekly_family_coverage(memory_db, source_db=source_db, weekly_source_id="433")


def test_abandoned_child_missing_inactive_from_time_fails(tmp_path: Path) -> None:
    memory_db, source_db = base_full_case(tmp_path)
    add_range(
        memory_db,
        "506",
        daily_payload("506", active="2026-01-03T00:00:00Z", inactive=None, status="ABANDONED"),
    )
    add_relationship(memory_db, child_id="506")

    with pytest.raises(WeeklyFamilyCoverageError, match="ABANDONED Daily child is missing inactive_from_time: 506"):
        analyze_weekly_family_coverage(memory_db, source_db=source_db, weekly_source_id="433")


def test_weekly_source_id_resolves_through_source_record_id(tmp_path: Path) -> None:
    memory_db, source_db = base_full_case(tmp_path)

    report = analyze_weekly_family_coverage(memory_db, source_db=source_db, weekly_source_id="433")

    assert report["weekly_source_id"] == "433"


def test_legacy_source_parent_link_status_does_not_override_relationship(tmp_path: Path) -> None:
    memory_db, source_db = base_full_case(tmp_path)

    report = analyze_weekly_family_coverage(memory_db, source_db=source_db, weekly_source_id="433")

    assert report["counts"]["valid_children"] == 2
    assert all(child["link_status"] == "VALID" for child in report["children"])


def test_needs_review_child_appears_in_output(tmp_path: Path) -> None:
    memory_db, source_db = base_full_case(tmp_path)
    add_range(memory_db, "504", daily_payload("504", active="2026-01-06T00:00:00Z", inactive="2026-01-06T00:00:00Z"))
    add_relationship(memory_db, child_id="504", link_status="NEEDS_REVIEW", link_confidence="medium")

    report = analyze_weekly_family_coverage(memory_db, source_db=source_db, weekly_source_id="433")

    assert report["counts"]["needs_review_children"] == 1
    assert any(child["child_source_id"] == "504" and child["link_status"] == "NEEDS_REVIEW" for child in report["children"])


def test_missing_source_database_fails_cleanly(tmp_path: Path) -> None:
    memory_db, _source_db = base_full_case(tmp_path)

    with pytest.raises(WeeklyFamilyCoverageError, match="Source database does not exist"):
        analyze_weekly_family_coverage(memory_db, source_db=tmp_path / "missing.db", weekly_source_id="433")


def test_missing_candles_table_fails_cleanly(tmp_path: Path) -> None:
    memory_db = create_memory_db(tmp_path)
    source_db = create_source_db(tmp_path, include_candles=False)
    add_range(memory_db, "433", weekly_payload())

    with pytest.raises(WeeklyFamilyCoverageError, match="missing required table: candles"):
        analyze_weekly_family_coverage(memory_db, source_db=source_db, weekly_source_id="433")


def test_missing_map_ranges_table_fails_cleanly(tmp_path: Path) -> None:
    memory_db = create_memory_db(tmp_path)
    source_db = create_source_db(tmp_path, include_map_ranges=False)
    add_candles(source_db, ["2026-01-02T00:00:00Z"])
    add_range(memory_db, "433", weekly_payload())

    with pytest.raises(WeeklyFamilyCoverageError, match="missing required table: map_ranges"):
        analyze_weekly_family_coverage(memory_db, source_db=source_db, weekly_source_id="433")


def test_source_database_remains_unchanged(tmp_path: Path) -> None:
    memory_db, source_db = base_full_case(tmp_path)
    before = count_rows(source_db, "candles")

    analyze_weekly_family_coverage(memory_db, source_db=source_db, weekly_source_id="433")

    assert count_rows(source_db, "candles") == before


def test_range_library_raw_and_relationship_rows_remain_unchanged(tmp_path: Path) -> None:
    memory_db, source_db = base_full_case(tmp_path)
    before_ranges = count_rows(memory_db, "raw_ranges")
    before_relationships = count_rows(memory_db, "parent_child_relationships")

    analyze_weekly_family_coverage(memory_db, source_db=source_db, weekly_source_id="433")

    assert count_rows(memory_db, "raw_ranges") == before_ranges
    assert count_rows(memory_db, "parent_child_relationships") == before_relationships


def test_deterministic_json_output(tmp_path: Path) -> None:
    memory_db, source_db = base_full_case(tmp_path)

    first = format_weekly_family_coverage(
        analyze_weekly_family_coverage(memory_db, source_db=source_db, weekly_source_id="433"),
        as_json=True,
    )
    second = format_weekly_family_coverage(
        analyze_weekly_family_coverage(memory_db, source_db=source_db, weekly_source_id="433"),
        as_json=True,
    )

    assert first == second


def test_weekly_family_coverage_cli_success_and_failure_paths(tmp_path: Path, capsys) -> None:
    memory_db, source_db = base_full_case(tmp_path)

    assert main(
        [
            "weekly-family-coverage",
            "--db-path",
            str(memory_db),
            "--source-db",
            str(source_db),
            "--weekly-source-id",
            "433",
            "--json",
        ]
    ) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["schema_version"] == "weekly_family_coverage_v0.1"

    with pytest.raises(SystemExit):
        main(
            [
                "weekly-family-coverage",
                "--db-path",
                str(memory_db),
                "--source-db",
                str(tmp_path / "missing.db"),
                "--weekly-source-id",
                "433",
            ]
        )
