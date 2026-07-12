from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from range_library_memory.daily_range_timeline import (
    build_daily_range_timelines,
    main,
    summarize_daily_range_timelines,
)
from range_library_memory.schema import init_schema


def fixture(
    tmp_path: Path,
    *,
    daily_id: str = "10",
    status: str | None = "ACTIVE",
    high_time: str | None = "2026-01-02T00:00:00Z",
    low_time: str | None = "2026-01-03T00:00:00Z",
    active_time: str | None = "2026-01-01T00:00:00Z",
    high: float = 110,
    low: float = 90,
    parent_status: str | None = "VALID",
    parent_id: str | None = "100",
    weekly_state: str = "RECLAIMED",
    weekly_t0: str = "2025-12-01T00:00:00Z",
    weekly_t1: str | None = "2026-01-10T00:00:00Z",
    weekly_t2: str | None = "2026-01-12T00:00:00Z",
) -> tuple[Path, Path]:
    memory, source = tmp_path / "memory.sqlite3", tmp_path / "source.sqlite3"
    init_schema(memory)
    payload = {
        "range_id": daily_id,
        "case_ref": "case",
        "symbol": "XAUUSD",
        "structure_layer": "DAILY",
        "source_timeframe": "D1",
        "status": status,
        "active_from_time": active_time,
        "range_high_price": high,
        "range_low_price": low,
        "range_high_time": high_time,
        "range_low_time": low_time,
    }
    with sqlite3.connect(memory) as con:
        con.execute(
            "INSERT INTO import_runs(id,run_uuid,source_path,source_kind,started_at_utc,status) "
            "VALUES(1,'r','x','fixture','2026-01-01T00:00:00Z','completed')"
        )
        con.execute(
            """INSERT INTO raw_ranges(
                 import_run_id,source_record_id,symbol,timeframe,range_type,start_time_utc,
                 high,low,raw_payload_json,payload_sha256,created_at_utc
               ) VALUES(1,?,'XAUUSD','D1','DAILY','2026-01-01T00:00:00Z',?,?,?,'sha',
                        '2026-01-01T00:00:00Z')""",
            (daily_id, high, low, json.dumps(payload)),
        )
        if parent_status is not None:
            con.execute(
                """INSERT INTO parent_child_relationships(
                     import_run_id,case_ref,symbol,relationship_type,parent_range_id,child_range_id,
                     parent_layer,child_layer,parent_timeframe,child_timeframe,link_source,link_status,
                     link_confidence,review_status,child_position_in_parent,child_boundary_interaction,
                     child_lifecycle_relationship,notes,created_at_utc,updated_at_utc
                   ) VALUES(1,'case','XAUUSD','weekly_daily',?,?,'WEEKLY','DAILY','W1','D1',
                     'explicit',?,'high','open','inside_fair_price','inside_parent',
                     'formed_during_active_parent','fixture','2026-01-01T00:00:00Z',
                     '2026-01-01T00:00:00Z')""",
                (parent_id, daily_id, parent_status),
            )
        if parent_id:
            con.execute(
                """INSERT INTO weekly_phase_sequences(
                     built_at_utc,import_run_id,case_ref,symbol,source_timeframe,weekly_range_source_id,
                     raw_range_id,raw_status,range_high,range_low,t0_formation_time,t1_break_time,
                     t1_break_direction,t1_break_level,t1_break_kind,t2_reclaim_time,t2_reclaim_kind,
                     same_candle_break_reclaim,formation_to_break_days,break_to_reclaim_days,
                     current_phase_state,current_phase_start_time,current_phase_age_days,
                     observation_status,resolution_status,resolution_confidence,
                     supporting_break_reclaim_id,reason_codes_json,as_of_time,created_at_utc,updated_at_utc
                   ) VALUES(
                     '2026-01-20T00:00:00Z',1,'case','XAUUSD','W1',?,1,'ACTIVE',120,80,?,?,
                     'UP',120,'WICK',?,'WICK',0,1,1,?,'2026-01-12T00:00:00Z',1,
                     'OBSERVED','RESOLVED','high',1,'[]','2026-01-20T00:00:00Z',
                     '2026-01-20T00:00:00Z','2026-01-20T00:00:00Z')""",
                (parent_id, weekly_t0, weekly_t1, weekly_t2, weekly_state),
            )
    with sqlite3.connect(source) as con:
        con.execute(
            "CREATE TABLE candles(symbol TEXT,timeframe TEXT,time TEXT,open REAL,high REAL,"
            "low REAL,close REAL,volume REAL,source TEXT)"
        )
        con.execute("CREATE TABLE map_ranges(id INTEGER PRIMARY KEY)")
    return memory, source


def candle(source: Path, time: str, *, high: float, low: float, close: float) -> None:
    with sqlite3.connect(source) as con:
        con.execute(
            "INSERT INTO candles VALUES('XAUUSD','D1',?,100,?,?,?,1,'fixture')",
            (time, high, low, close),
        )


def add_break(
    memory: Path,
    *,
    daily_id: str = "10",
    direction: str = "UP",
    break_time: str = "2026-01-05T00:00:00Z",
) -> None:
    event_type = "BOS_UP" if direction == "UP" else "BOS_DOWN"
    boundary = 110 if direction == "UP" else 90
    boundary_type = "RANGE_HIGH" if direction == "UP" else "RANGE_LOW"
    with sqlite3.connect(memory) as con:
        con.execute(
            """INSERT INTO event_ohlc_evidence(
              built_at_utc,import_run_id,case_ref,symbol,structure_layer,source_timeframe,
              range_source_id,event_source_id,raw_range_id,event_type,direction,
              range_formation_time,boundary_type,boundary_price,boundary_anchor_time,
              transition_status,transition_reason_codes_json,evidence_status,reason_codes_json,
              resolution_status,resolution_confidence,effective_break_time,effective_break_kind,
              as_of_time,created_at_utc,updated_at_utc
            ) VALUES(
              '2026-01-20T00:00:00Z',1,'case','XAUUSD','DAILY','D1',?,'e1',1,?,?,
              '2026-01-03T00:00:00Z',?,?,'2026-01-02T00:00:00Z',
              'NOT_PRESENT','[]','MATCH','[]','MAPPED_CONFIRMED','high',?,'WICK',
              '2026-01-20T00:00:00Z','2026-01-20T00:00:00Z','2026-01-20T00:00:00Z')""",
            (daily_id, event_type, direction, boundary_type, boundary, break_time),
        )
        evidence_id = con.execute("SELECT MAX(id) FROM event_ohlc_evidence").fetchone()[0]
        con.execute(
            """INSERT INTO resolved_range_lifecycles(
               built_at_utc,import_run_id,case_ref,symbol,structure_layer,source_timeframe,
               range_source_id,raw_range_id,raw_status,raw_active_from_time,effective_status,
               effective_active_from_time,effective_inactive_from_time,resolution_source,
               resolution_status,resolution_confidence,supporting_event_source_id,
               supporting_evidence_id,reason_codes_json,as_of_time,created_at_utc,updated_at_utc
             ) VALUES(
               '2026-01-20T00:00:00Z',1,'case','XAUUSD','DAILY','D1',?,1,'BROKEN',
               '2026-01-01T00:00:00Z','BROKEN','2026-01-01T00:00:00Z',?,
               'MAPPED_EVENT_AND_OHLC','MAPPED_CONFIRMED','high','e1',?,'[]',
               '2026-01-20T00:00:00Z','2026-01-20T00:00:00Z','2026-01-20T00:00:00Z')""",
            (daily_id, break_time, evidence_id),
        )


def row(memory: Path, source_id: str = "10") -> sqlite3.Row:
    with sqlite3.connect(memory) as con:
        con.row_factory = sqlite3.Row
        result = con.execute(
            "SELECT * FROM daily_range_timelines WHERE daily_range_source_id=?",
            (source_id,),
        ).fetchone()
    assert result
    return result


def test_t0_active_parent_phase_and_sequence(tmp_path: Path) -> None:
    memory, source = fixture(tmp_path, active_time="2026-01-04T00:00:00Z")
    candle(source, "2026.01.04 00:00", high=105, low=95, close=100)
    candle(source, "2026.01.20 00:00", high=108, low=96, close=103)
    build_daily_range_timelines(memory, source_db=source)
    value = row(memory)
    assert value["t0_formation_time"] == "2026-01-04T00:00:00Z"
    assert value["current_daily_state"] == "ACTIVE_PRE_BREAK"
    assert value["weekly_phase_at_daily_formation"] == "WEEKLY_PRE_BREAK"
    assert value["daily_sequence_in_weekly"] == 1


@pytest.mark.parametrize("field", ["high_time", "low_time"])
def test_missing_anchor_is_incomplete(tmp_path: Path, field: str) -> None:
    memory, source = fixture(tmp_path, **{field: None})
    candle(source, "2026.01.20 00:00", high=108, low=96, close=103)
    build_daily_range_timelines(memory, source_db=source)
    assert row(memory)["current_daily_state"] == "INCOMPLETE_RANGE"


def test_missing_status_and_raw_broken_without_break(tmp_path: Path) -> None:
    for folder_name, status, reason in (
        ("missing", None, "MISSING_RAW_STATUS"),
        ("broken", "BROKEN", "RAW_BROKEN_WITHOUT_FACTUAL_BREAK"),
    ):
        folder = tmp_path / folder_name
        folder.mkdir()
        memory, source = fixture(folder, status=status)
        candle(source, "2026.01.20 00:00", high=108, low=96, close=103)
        build_daily_range_timelines(memory, source_db=source)
        assert row(memory)["current_daily_state"] == "NEEDS_REVIEW"
        assert reason in row(memory)["reason_codes_json"]


def test_bos_up_wick_then_close_and_depth(tmp_path: Path) -> None:
    memory, source = fixture(tmp_path, status="BROKEN")
    add_break(memory)
    candle(source, "2026.01.05 00:00", high=112, low=111, close=111)
    candle(source, "2026.01.06 00:00", high=114, low=108, close=112)
    candle(source, "2026.01.07 00:00", high=113, low=107, close=109)
    candle(source, "2026.01.20 00:00", high=115, low=105, close=110)
    build_daily_range_timelines(memory, source_db=source)
    value = row(memory)
    assert value["current_daily_state"] == "RECLAIMED"
    assert value["first_wick_reclaim_time"] == "2026-01-06T00:00:00Z"
    assert value["first_close_reclaim_time"] == "2026-01-07T00:00:00Z"
    assert value["t2_reclaim_kind"] == "WICK"
    assert (value["reclaim_depth_price"], value["reclaim_depth_percent_of_range"]) == (2, 10)


def test_bos_down_same_candle_close(tmp_path: Path) -> None:
    memory, source = fixture(tmp_path, status="BROKEN")
    add_break(memory, direction="DOWN")
    candle(source, "2026.01.05 00:00", high=92, low=88, close=91)
    candle(source, "2026.01.20 00:00", high=95, low=89, close=92)
    build_daily_range_timelines(memory, source_db=source)
    value = row(memory)
    assert value["t2_reclaim_kind"] == "WICK_AND_CLOSE"
    assert value["same_candle_close_reclaim"] == 1
    assert value["candles_to_effective_reclaim"] == 0
    assert value["break_to_reclaim_days"] == 0
    assert value["reclaim_depth_price"] == 2


def test_wick_only_unknown_pending_and_as_of(tmp_path: Path) -> None:
    memory, source = fixture(tmp_path, status="BROKEN")
    add_break(memory)
    candle(source, "2026.01.05 00:00", high=112, low=108, close=111)
    candle(source, "2026.01.10 00:00", high=114, low=112, close=113)
    candle(source, "2026.01.20 00:00", high=115, low=109, close=112)
    build_daily_range_timelines(memory, source_db=source, as_of="2026-01-10T00:00:00Z")
    value = row(memory)
    assert value["current_daily_state"] == "BREAK_PENDING_RECLAIM"
    assert "SAME_CANDLE_WICK_ORDER_UNKNOWN" in value["reason_codes_json"]
    build_daily_range_timelines(memory, source_db=source, as_of="2026-12-31T00:00:00Z")
    assert row(memory)["as_of_time"] == "2026-01-20T00:00:00Z"
    assert "AS_OF_CAPPED_TO_LATEST_D1_DATA" in row(memory)["reason_codes_json"]


def test_invalid_break_height_and_missing_candles(tmp_path: Path) -> None:
    folder = tmp_path / "chronology"
    folder.mkdir()
    memory, source = fixture(folder, status="BROKEN")
    add_break(memory, break_time="2025-12-01T00:00:00Z")
    candle(source, "2025.12.01 00:00", high=112, low=111, close=111)
    candle(source, "2026.01.20 00:00", high=115, low=110, close=112)
    build_daily_range_timelines(memory, source_db=source)
    assert "BREAK_BEFORE_RANGE_FORMATION" in row(memory)["reason_codes_json"]

    folder = tmp_path / "height"
    folder.mkdir()
    memory, source = fixture(folder, high=100, low=100)
    candle(source, "2026.01.20 00:00", high=105, low=95, close=100)
    build_daily_range_timelines(memory, source_db=source)
    assert "INVALID_RANGE_HEIGHT" in row(memory)["reason_codes_json"]

    folder = tmp_path / "candles"
    folder.mkdir()
    memory, source = fixture(folder)
    build_daily_range_timelines(memory, source_db=source)
    assert row(memory)["current_daily_state"] == "MISSING_CANDLES"


@pytest.mark.parametrize(
    ("link_status", "membership", "phase"),
    [
        ("ORPHAN", "ORPHAN", None),
        ("CONFLICT", "NEEDS_REVIEW", "PARENT_NEEDS_REVIEW"),
        ("NEEDS_REVIEW", "NEEDS_REVIEW", "PARENT_NEEDS_REVIEW"),
    ],
)
def test_parent_review_states_preserve_daily(
    tmp_path: Path,
    link_status: str,
    membership: str,
    phase: str | None,
) -> None:
    memory, source = fixture(tmp_path, parent_status=link_status)
    candle(source, "2026.01.20 00:00", high=108, low=96, close=103)
    build_daily_range_timelines(memory, source_db=source)
    value = row(memory)
    assert value["current_daily_state"] == "ACTIVE_PRE_BREAK"
    assert value["parent_membership_state"] == membership
    assert value["weekly_phase_at_daily_formation"] == phase
    assert value["daily_sequence_in_weekly"] is None


def test_missing_relationship_is_not_inferred(tmp_path: Path) -> None:
    memory, source = fixture(tmp_path, parent_status=None, parent_id=None)
    candle(source, "2026.01.20 00:00", high=108, low=96, close=103)
    build_daily_range_timelines(memory, source_db=source)
    value = row(memory)
    assert value["parent_membership_state"] == "MISSING_RELATIONSHIP"
    assert value["parent_weekly_source_id"] is None


@pytest.mark.parametrize(
    ("daily_time", "weekly_t1", "weekly_t2", "expected"),
    [
        ("2025-11-01T00:00:00Z", "2026-01-10T00:00:00Z", "2026-01-12T00:00:00Z", "BEFORE_WEEKLY_FORMATION"),
        ("2026-01-05T00:00:00Z", "2026-01-10T00:00:00Z", "2026-01-12T00:00:00Z", "WEEKLY_PRE_BREAK"),
        ("2026-01-11T00:00:00Z", "2026-01-10T00:00:00Z", "2026-01-12T00:00:00Z", "WEEKLY_BREAK_TO_RECLAIM"),
        ("2026-01-12T00:00:00Z", "2026-01-10T00:00:00Z", "2026-01-12T00:00:00Z", "WEEKLY_POST_RECLAIM"),
        ("2026-01-10T00:00:00Z", "2026-01-10T00:00:00Z", "2026-01-10T00:00:00Z", "WEEKLY_POST_RECLAIM"),
    ],
)
def test_weekly_phase_placement(
    tmp_path: Path,
    daily_time: str,
    weekly_t1: str,
    weekly_t2: str,
    expected: str,
) -> None:
    memory, source = fixture(
        tmp_path,
        high_time=daily_time,
        low_time=daily_time,
        active_time=None,
        weekly_t1=weekly_t1,
        weekly_t2=weekly_t2,
    )
    candle(source, "2026.01.20 00:00", high=108, low=96, close=103)
    build_daily_range_timelines(memory, source_db=source)
    assert row(memory)["weekly_phase_at_daily_formation"] == expected


def test_sequence_scope_idempotence_and_cli(tmp_path: Path, capsys) -> None:
    memory, source = fixture(tmp_path, daily_id="20", high_time="2026-01-03T00:00:00Z", low_time="2026-01-03T00:00:00Z")
    with sqlite3.connect(memory) as con:
        payload = {
            "range_id": "10", "case_ref": "case", "symbol": "XAUUSD",
            "structure_layer": "DAILY", "source_timeframe": "D1", "status": "ACTIVE",
            "range_high_price": 109, "range_low_price": 91,
            "range_high_time": "2026-01-03T00:00:00Z",
            "range_low_time": "2026-01-03T00:00:00Z",
        }
        con.execute(
            """INSERT INTO raw_ranges(import_run_id,source_record_id,symbol,timeframe,range_type,
               start_time_utc,high,low,raw_payload_json,payload_sha256,created_at_utc)
               VALUES(1,'10','XAUUSD','D1','DAILY','2026-01-01T00:00:00Z',109,91,?,'sha2',
                      '2026-01-01T00:00:00Z')""",
            (json.dumps(payload),),
        )
        con.execute(
            """INSERT INTO parent_child_relationships(
               import_run_id,case_ref,symbol,relationship_type,parent_range_id,child_range_id,
               parent_layer,child_layer,parent_timeframe,child_timeframe,link_source,link_status,
               link_confidence,review_status,child_position_in_parent,child_boundary_interaction,
               child_lifecycle_relationship,created_at_utc,updated_at_utc)
               VALUES(1,'case','XAUUSD','weekly_daily','100','10','WEEKLY','DAILY','W1','D1',
               'explicit','VALID','high','open','inside_fair_price','inside_parent',
               'formed_during_active_parent','2026-01-01T00:00:00Z','2026-01-01T00:00:00Z')"""
        )
    candle(source, "2026.01.20 00:00", high=108, low=96, close=103)
    build_daily_range_timelines(memory, source_db=source)
    assert row(memory, "10")["daily_sequence_in_weekly"] == 1
    assert row(memory, "20")["daily_sequence_in_weekly"] == 2
    with sqlite3.connect(memory) as con:
        other = con.execute("SELECT * FROM daily_range_timelines WHERE daily_range_source_id='20'").fetchone()
    build_daily_range_timelines(memory, source_db=source, daily_source_id="10", weekly_source_id="100")
    with sqlite3.connect(memory) as con:
        assert con.execute("SELECT * FROM daily_range_timelines WHERE daily_range_source_id='20'").fetchone() == other
        assert con.execute("SELECT COUNT(*) FROM daily_range_timelines").fetchone()[0] == 2
    assert summarize_daily_range_timelines(memory, daily_state="ACTIVE_PRE_BREAK")["total"] == 2

    args = ["build-daily-range-timelines", "--db-path", str(memory), "--source-db", str(source), "--json"]
    assert main(args) == 0
    first = capsys.readouterr().out
    assert main(args) == 0
    assert json.loads(first) == json.loads(capsys.readouterr().out)
