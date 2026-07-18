from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from range_library_memory.weekly_chronology_bos import build_weekly_chronology_bos


def write_source_db(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE candles (
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            time TEXT NOT NULL,
            open REAL NOT NULL,
            high REAL NOT NULL,
            low REAL NOT NULL,
            close REAL NOT NULL,
            volume REAL,
            source TEXT
        );
        CREATE TABLE map_ranges (id INTEGER PRIMARY KEY);
        """
    )
    connection.executemany(
        "INSERT INTO candles(symbol,timeframe,time,open,high,low,close,volume,source) VALUES (?,?,?,?,?,?,?,?,?)",
        [
            ("XAUUSD", "W1", "2026-01-05T00:00:00Z", 1900, 1950, 1880, 1930, 1, "test"),
            ("XAUUSD", "W1", "2026-01-12T00:00:00Z", 1930, 2000, 1920, 1980, 1, "test"),
            # Exact touch is not a breach.
            ("XAUUSD", "W1", "2026-01-19T00:00:00Z", 1980, 2000, 1960, 1990, 1, "test"),
            # First strict breach of the ending RH boundary.
            ("XAUUSD", "W1", "2026-01-26T00:00:00Z", 1990, 2012, 1970, 2005, 1, "test"),
            ("XAUUSD", "W1", "2026-02-02T00:00:00Z", 2005, 2020, 1940, 1955, 1, "test"),
            ("XAUUSD", "W1", "2026-02-09T00:00:00Z", 1955, 1980, 1900, 1920, 1, "test"),
        ],
    )
    connection.commit()
    connection.close()


def range_node(
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
        "active_from_time": max(high_time, low_time),
        "inactive_from_time": None,
        "direction_of_break": direction,
        "status": "ACTIVE",
        "children": [],
        "source_refs": [],
        "navigation_status": "TRUSTED",
        "statistics_status": "ELIGIBLE",
        "ancestor_review_status": "CLEAR",
        "direct_parent_link_status": "ROOT",
    }


def symbol_root(children: list[dict]) -> dict:
    return {
        "node_type": "SYMBOL",
        "id": "mm:root:xauusd",
        "label": "XAUUSD",
        "children": children,
        "unlinked_review_children": [],
    }


def write_range_db(path: Path) -> None:
    bullish = range_node(
        "mm:range:weekly-up",
        high=2000,
        low=1880,
        high_time="2026-01-12T00:00:00Z",
        low_time="2026-01-05T00:00:00Z",
    )
    bearish = range_node(
        "mm:range:weekly-down",
        high=2020,
        low=1900,
        high_time="2026-02-02T00:00:00Z",
        low_time="2026-02-09T00:00:00Z",
    )
    master_map = {
        "schema_version": "xauusd_master_map_v0.1",
        "build_id": "test-build",
        "built_at_utc": "2026-02-10T00:00:00Z",
        "symbol": "XAUUSD",
        "structural_content_hash": "structural-hash",
        "root": symbol_root([bullish, bearish]),
        "trusted_root": symbol_root([json.loads(json.dumps(bullish)), json.loads(json.dumps(bearish))]),
        "review_root": symbol_root([]),
        "statistics": {},
    }
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE master_map_outputs (
            symbol TEXT PRIMARY KEY,
            build_id TEXT NOT NULL,
            schema_version TEXT NOT NULL,
            built_at_utc TEXT NOT NULL,
            structural_content_hash TEXT NOT NULL,
            output_json TEXT NOT NULL
        );
        CREATE TABLE master_map_ranges (
            canonical_range_id TEXT PRIMARY KEY,
            canonical_payload_json TEXT NOT NULL
        );
        """
    )
    connection.execute(
        "INSERT INTO master_map_outputs VALUES (?,?,?,?,?,?)",
        ("XAUUSD", "test-build", "xauusd_master_map_v0.1", "2026-02-10T00:00:00Z", "structural-hash", json.dumps(master_map)),
    )
    for node in (bullish, bearish):
        connection.execute(
            "INSERT INTO master_map_ranges VALUES (?,?)",
            (node["id"], json.dumps(node)),
        )
    connection.commit()
    connection.close()


def test_builds_chronology_and_first_strict_bos_then_projects_master_map(tmp_path: Path) -> None:
    range_db = tmp_path / "range_library.sqlite3"
    source_db = tmp_path / "market_memory.db"
    write_range_db(range_db)
    write_source_db(source_db)

    summary = build_weekly_chronology_bos(
        range_db,
        source_db=source_db,
        symbol="XAUUSD",
        year=2026,
    )

    assert summary["total"] == 2
    rows = {row["canonical_range_id"]: row for row in summary["rows"]}

    bullish = rows["mm:range:weekly-up"]
    assert bullish["chronology_start_side"] == "RL"
    assert bullish["chronology_end_side"] == "RH"
    assert bullish["bos_direction"] == "UP"
    assert bullish["reclaim_direction"] == "DOWN"
    assert bullish["bos_candle_time"] == "2026-01-26T00:00:00Z"
    assert bullish["bos_breach_price"] == 2012
    assert bullish["analysis_status"] == "COMPLETE"

    bearish = rows["mm:range:weekly-down"]
    assert bearish["chronology_start_side"] == "RH"
    assert bearish["chronology_end_side"] == "RL"
    assert bearish["bos_direction"] == "DOWN"
    assert bearish["reclaim_direction"] == "UP"
    assert bearish["analysis_status"] == "NOT_BREACHED"

    connection = sqlite3.connect(range_db)
    connection.row_factory = sqlite3.Row
    stored = connection.execute(
        "SELECT * FROM weekly_chronology_bos WHERE canonical_range_id = ?",
        ("mm:range:weekly-up",),
    ).fetchone()
    assert stored["analysis_status"] == "COMPLETE"
    assert stored["bos_candle_time"] == "2026-01-26T00:00:00Z"

    output = json.loads(
        connection.execute(
            "SELECT output_json FROM master_map_outputs WHERE symbol = 'XAUUSD'"
        ).fetchone()["output_json"]
    )
    projected = output["trusted_root"]["children"][0]
    assert projected["chronology_start_side"] == "RL"
    assert projected["chronology_end_side"] == "RH"
    assert projected["direction_of_break"] == "UP"
    assert projected["direction_of_break_source"] == "WEEKLY_SCRIPT_1"
    assert projected["script1_bos_time"] == "2026-01-26T00:00:00Z"
    assert output["structural_content_hash"] == "structural-hash"
    assert output["analysis"]["weekly_chronology_bos"]["complete"] == 1
    connection.close()


def test_direction_conflict_is_reviewable_and_does_not_overwrite_master_map(tmp_path: Path) -> None:
    range_db = tmp_path / "range_library.sqlite3"
    source_db = tmp_path / "market_memory.db"
    write_range_db(range_db)
    write_source_db(source_db)

    connection = sqlite3.connect(range_db)
    row = connection.execute("SELECT output_json FROM master_map_outputs WHERE symbol = 'XAUUSD'").fetchone()
    output = json.loads(row[0])
    for root_key in ("root", "trusted_root"):
        output[root_key]["children"][0]["direction_of_break"] = "DOWN"
    connection.execute(
        "UPDATE master_map_outputs SET output_json = ? WHERE symbol = 'XAUUSD'",
        (json.dumps(output),),
    )
    connection.commit()
    connection.close()

    summary = build_weekly_chronology_bos(range_db, source_db=source_db, year=2026)
    bullish = next(row for row in summary["rows"] if row["canonical_range_id"] == "mm:range:weekly-up")
    assert bullish["analysis_status"] == "NEEDS_REVIEW"
    assert "SCRIPT1_DIRECTION_CONFLICTS_WITH_MASTER_MAP" in bullish["reason_codes"]

    connection = sqlite3.connect(range_db)
    stored_output = json.loads(
        connection.execute("SELECT output_json FROM master_map_outputs WHERE symbol = 'XAUUSD'").fetchone()[0]
    )
    assert stored_output["trusted_root"]["children"][0]["direction_of_break"] == "DOWN"
    connection.close()
