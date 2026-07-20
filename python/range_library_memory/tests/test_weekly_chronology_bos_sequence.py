from __future__ import annotations

import copy
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from range_library_memory.weekly_chronology_bos import (
    VERSION,
    build_weekly_chronology_bos,
)


def weekly(
    canonical_id: str,
    *,
    high: float,
    low: float,
    high_time: str,
    low_time: str,
    direction: str | None = None,
) -> dict:
    return {
        "node_type": "RANGE",
        "id": canonical_id,
        "symbol": "XAUUSD",
        "structure_layer": "WEEKLY",
        "source_timeframe": "W1",
        "range_high": high,
        "range_low": low,
        "range_high_time": high_time,
        "range_low_time": low_time,
        "direction_of_break": direction,
        "navigation_status": "TRUSTED",
        "statistics_status": "ELIGIBLE",
        "source_refs": [{
            "raw_id": int(canonical_id.rsplit("-", 1)[-1]),
            "source_record_id": canonical_id,
            "case_ref": "case:live",
        }],
        "children": [],
    }


def symbol_root(children: list[dict], suffix: str = "") -> dict:
    return {
        "node_type": "SYMBOL",
        "id": f"symbol:XAUUSD{suffix}",
        "label": "XAUUSD",
        "children": children,
        "unlinked_review_children": [],
    }


def write_range_db(path: Path, trusted: list[dict]) -> None:
    master_map = {
        "schema_version": "xauusd_master_map_v0.1",
        "build_id": "fixture-build",
        "built_at_utc": "2026-04-01T00:00:00Z",
        "symbol": "XAUUSD",
        "structural_content_hash": "sequential-structural-hash",
        "root": symbol_root(copy.deepcopy(trusted)),
        "trusted_root": symbol_root(copy.deepcopy(trusted), ":trusted"),
        "review_root": symbol_root([], ":review"),
        "statistics": {},
    }
    with closing(sqlite3.connect(path)) as connection:
        connection.executescript(
            """
            CREATE TABLE master_map_outputs (
                symbol TEXT PRIMARY KEY, build_id TEXT NOT NULL, schema_version TEXT NOT NULL,
                built_at_utc TEXT NOT NULL, structural_content_hash TEXT NOT NULL, output_json TEXT NOT NULL
            );
            CREATE TABLE master_map_ranges (
                canonical_range_id TEXT PRIMARY KEY, canonical_payload_json TEXT NOT NULL
            );
            CREATE TABLE raw_ranges (id INTEGER PRIMARY KEY, marker TEXT NOT NULL);
            CREATE TABLE raw_events (id INTEGER PRIMARY KEY, marker TEXT NOT NULL);
            INSERT INTO raw_ranges VALUES (1, 'unchanged');
            INSERT INTO raw_events VALUES (1, 'unchanged');
            """
        )
        connection.execute(
            "INSERT INTO master_map_outputs VALUES (?,?,?,?,?,?)",
            (
                "XAUUSD",
                "fixture-build",
                "xauusd_master_map_v0.1",
                "2026-04-01T00:00:00Z",
                "sequential-structural-hash",
                json.dumps(master_map, sort_keys=True),
            ),
        )
        for item in trusted:
            connection.execute(
                "INSERT INTO master_map_ranges VALUES (?,?)",
                (item["id"], json.dumps(item, sort_keys=True)),
            )
        connection.commit()


def write_source_db(path: Path, candles: list[tuple]) -> None:
    with closing(sqlite3.connect(path)) as connection:
        connection.executescript(
            """
            CREATE TABLE candles (
                symbol TEXT NOT NULL, timeframe TEXT NOT NULL, time TEXT NOT NULL,
                open REAL NOT NULL, high REAL NOT NULL, low REAL NOT NULL, close REAL NOT NULL,
                volume REAL, source TEXT
            );
            """
        )
        connection.executemany(
            "INSERT INTO candles(symbol,timeframe,time,open,high,low,close,volume,source) "
            "VALUES ('XAUUSD','W1',?,?,?,?,?,?, 'fixture')",
            candles,
        )
        connection.commit()


def test_first_strict_boundary_breach_establishes_direction_and_sequence(tmp_path: Path) -> None:
    range_db = tmp_path / "range.sqlite3"
    candle_db = tmp_path / "candles.sqlite3"
    first = weekly(
        "weekly-1",
        high=100,
        low=80,
        high_time="2026-01-05T00:00:00Z",
        low_time="2026-01-12T00:00:00Z",
    )
    second = weekly(
        "weekly-2",
        high=110,
        low=90,
        high_time="2026-03-09T00:00:00Z",
        low_time="2026-03-02T00:00:00Z",
    )
    # Deliberately reversed input order. Canonical order must use the later
    # anchor (range-defined time), not source order or canonical id alone.
    write_range_db(range_db, [second, first])
    write_source_db(candle_db, [
        ("2026-01-12T00:00:00Z", 90, 99, 82, 95, 1),
        # Gap in stored ranges is irrelevant; this first strict low breach owns
        # Weekly 1 and establishes BOS_DOWN despite RH forming first.
        ("2026-02-02T00:00:00Z", 90, 98, 79, 82, 1),
        ("2026-03-09T00:00:00Z", 100, 110, 95, 108, 1),
        ("2026-03-16T00:00:00Z", 108, 112, 96, 111, 1),
    ])

    summary = build_weekly_chronology_bos(
        range_db,
        source_db=candle_db,
        case_ref="case:live",
    )

    assert VERSION == "weekly_script1_v2"
    assert summary["sequence_order"] == "RANGE_DEFINED_AT_ASC"
    assert [row["canonical_range_id"] for row in summary["rows"]] == ["weekly-1", "weekly-2"]
    assert summary["rows"][0]["chronology_result"] == "RH_TO_RL"
    assert summary["rows"][0]["expected_bos_direction"] == "BOS_DOWN"
    assert summary["rows"][0]["bos_direction"] == "BOS_DOWN"
    assert summary["rows"][0]["bos_candle_time"] == "2026-02-02T00:00:00Z"
    assert summary["rows"][1]["bos_direction"] == "BOS_UP"

    with closing(sqlite3.connect(range_db)) as connection:
        connection.row_factory = sqlite3.Row
        output = json.loads(connection.execute(
            "SELECT output_json FROM master_map_outputs WHERE symbol='XAUUSD'"
        ).fetchone()["output_json"])
    projected = output["trusted_root"]["children"]
    assert [node["id"] for node in projected] == ["weekly-1", "weekly-2"]
    assert [node["script1_sequence_index"] for node in projected] == [0, 1]
    assert output["analysis"]["weekly_script1"]["sequence_order"] == "RANGE_DEFINED_AT_ASC"


def test_range_scan_stops_at_next_stored_weekly_and_repeats(tmp_path: Path) -> None:
    range_db = tmp_path / "range.sqlite3"
    candle_db = tmp_path / "candles.sqlite3"
    first = weekly(
        "weekly-1",
        high=100,
        low=80,
        high_time="2026-01-05T00:00:00Z",
        low_time="2026-01-12T00:00:00Z",
    )
    second = weekly(
        "weekly-2",
        high=95,
        low=85,
        high_time="2026-02-02T00:00:00Z",
        low_time="2026-02-09T00:00:00Z",
    )
    write_range_db(range_db, [first, second])
    write_source_db(candle_db, [
        ("2026-01-12T00:00:00Z", 90, 99, 82, 95, 1),
        ("2026-01-19T00:00:00Z", 95, 99, 82, 90, 1),
        ("2026-02-09T00:00:00Z", 90, 94, 86, 88, 1),
        # This belongs to the second stored range. The first range must already
        # have stopped at Weekly 2's defined time.
        ("2026-02-16T00:00:00Z", 88, 94, 84, 85, 1),
        # Later breach of Weekly 1 must never be stolen by Weekly 1.
        ("2026-02-23T00:00:00Z", 85, 101, 79, 90, 1),
    ])

    rows = {
        row["canonical_range_id"]: row
        for row in build_weekly_chronology_bos(
            range_db,
            source_db=candle_db,
            case_ref="case:live",
        )["rows"]
    }

    assert rows["weekly-1"]["processing_status"] == "PENDING"
    assert rows["weekly-1"]["bos_direction"] == "PENDING"
    assert rows["weekly-1"]["reason_codes"] == ["STRICT_BOS_NOT_PROVEN_BEFORE_NEXT_RANGE"]
    assert rows["weekly-2"]["bos_direction"] == "BOS_DOWN"
    assert rows["weekly-2"]["bos_candle_time"] == "2026-02-16T00:00:00Z"


def test_same_w1_candle_breaking_both_boundaries_requires_review(tmp_path: Path) -> None:
    range_db = tmp_path / "range.sqlite3"
    candle_db = tmp_path / "candles.sqlite3"
    item = weekly(
        "weekly-1",
        high=100,
        low=80,
        high_time="2026-01-05T00:00:00Z",
        low_time="2026-01-12T00:00:00Z",
    )
    write_range_db(range_db, [item])
    write_source_db(candle_db, [
        ("2026-01-12T00:00:00Z", 90, 99, 82, 95, 1),
        ("2026-01-19T00:00:00Z", 95, 101, 79, 90, 1),
    ])

    row = build_weekly_chronology_bos(
        range_db,
        source_db=candle_db,
        case_ref="case:live",
    )["rows"][0]

    assert row["processing_status"] == "NEEDS_REVIEW"
    assert row["bos_direction"] == "PENDING"
    assert row["bos_candle_time"] == "2026-01-19T00:00:00Z"
    assert row["reason_codes"] == ["BOTH_BOUNDARIES_BREACHED_SAME_W1"]
