from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from range_library_memory.schema import init_schema
from range_library_memory.weekly_direction_context import build_weekly_direction_contexts


def make_db(tmp_path: Path) -> Path:
    db = tmp_path / "memory.sqlite3"
    init_schema(db)
    old_payload = {
        "case_ref": "case",
        "symbol": "XAUUSD",
        "structure_layer": "WEEKLY",
        "status": "BROKEN",
        "range_high_price": 110,
        "range_low_price": 90,
    }
    new_payload = {
        "case_ref": "case",
        "symbol": "XAUUSD",
        "structure_layer": "WEEKLY",
        "status": "ACTIVE",
        "range_high_price": 120,
        "range_low_price": 100,
    }
    with sqlite3.connect(db) as connection:
        connection.execute(
            "INSERT INTO import_runs(id,run_uuid,source_path,source_kind,started_at_utc,status) "
            "VALUES(1,'r','x','fixture','2026-01-01T00:00:00Z','completed')"
        )
        for source_id, payload, high, low in (
            ("10", old_payload, 110, 90),
            ("20", new_payload, 120, 100),
        ):
            connection.execute(
                """INSERT INTO raw_ranges(
                   import_run_id,source_record_id,symbol,timeframe,range_type,start_time_utc,
                   high,low,raw_payload_json,payload_sha256,created_at_utc
                   ) VALUES(1,?,'XAUUSD','W1','WEEKLY','2026-01-01T00:00:00Z',?,?,?,'sha',
                            '2026-01-01T00:00:00Z')""",
                (source_id, high, low, json.dumps(payload)),
            )
        add_candidate(
            connection,
            old_id="10",
            event_id="100",
            boundary=110,
            break_time="2026-01-10T00:00:00Z",
            reclaim_time="2026-01-15T00:00:00Z",
            old_t0="2025-12-08T00:00:00Z",
        )
        insert_phase(
            connection,
            source_id="20",
            raw_range_id=2,
            high=120,
            low=100,
            t0="2026-01-12T00:00:00Z",
            status="ACTIVE",
            state="ACTIVE_PRE_BREAK",
        )
    return db


def insert_phase(
    connection: sqlite3.Connection,
    *,
    source_id: str,
    raw_range_id: int,
    high: float,
    low: float,
    t0: str,
    status: str,
    state: str,
) -> None:
    connection.execute(
        """INSERT OR REPLACE INTO weekly_phase_sequences(
           built_at_utc,import_run_id,case_ref,symbol,source_timeframe,weekly_range_source_id,
           raw_range_id,raw_status,range_high,range_low,t0_formation_time,
           same_candle_break_reclaim,current_phase_state,current_phase_start_time,
           current_phase_age_days,observation_status,resolution_status,resolution_confidence,
           reason_codes_json,as_of_time,created_at_utc,updated_at_utc
           ) VALUES(
           '2026-02-01T00:00:00Z',1,'case','XAUUSD','W1',?,?,?,?,?, ?,0,?,?,1,
           'OBSERVED','RESOLVED','high','[]','2026-02-01T00:00:00Z',
           '2026-02-01T00:00:00Z','2026-02-01T00:00:00Z')""",
        (source_id, raw_range_id, status, high, low, t0, state, t0),
    )


def add_candidate(
    connection: sqlite3.Connection,
    *,
    old_id: str,
    event_id: str,
    boundary: float,
    break_time: str,
    reclaim_time: str,
    old_t0: str,
) -> None:
    insert_phase(
        connection,
        source_id=old_id,
        raw_range_id=1,
        high=boundary,
        low=90,
        t0=old_t0,
        status="BROKEN",
        state="RECLAIMED",
    )
    connection.execute(
        """INSERT INTO event_ohlc_evidence(
           built_at_utc,import_run_id,case_ref,symbol,structure_layer,source_timeframe,
           range_source_id,event_source_id,event_type,direction,range_formation_time,
           boundary_type,boundary_price,boundary_anchor_time,mapped_new_range_id,
           transition_status,transition_reason_codes_json,evidence_status,reason_codes_json,
           resolution_status,resolution_confidence,effective_break_time,effective_break_kind,
           as_of_time,created_at_utc,updated_at_utc
           ) VALUES(
           '2026-02-01T00:00:00Z',1,'case','XAUUSD','WEEKLY','W1',?,?,'BOS_UP','UP',?,
           'RANGE_BOUNDARY',?,'2025-12-08T00:00:00Z',NULL,'VALID','[]','MATCH','[]',
           'MAPPED_CONFIRMED','high',?,'WICK','2026-02-01T00:00:00Z',
           '2026-02-01T00:00:00Z','2026-02-01T00:00:00Z')""",
        (old_id, event_id, old_t0, boundary, break_time),
    )
    connection.execute(
        """INSERT OR REPLACE INTO weekly_break_reclaim_lifecycles(
           built_at_utc,import_run_id,case_ref,symbol,source_timeframe,weekly_range_source_id,
           raw_range_id,range_high,range_low,range_height,break_direction,break_level,break_time,
           break_kind,supporting_event_source_id,supporting_evidence_id,abandoned_from_time,
           effective_reclaim_time,effective_reclaim_kind,same_candle_close_reclaim,
           current_state,observation_status,resolution_status,resolution_confidence,
           reason_codes_json,as_of_time,created_at_utc,updated_at_utc
           ) VALUES(
           '2026-02-01T00:00:00Z',1,'case','XAUUSD','W1',?,1,?,90,20,'UP',?,?,'WICK',?,1,?,
           ?,'WICK',0,'RECLAIMED','OBSERVED','RESOLVED','high','[]','2026-02-01T00:00:00Z',
           '2026-02-01T00:00:00Z','2026-02-01T00:00:00Z')""",
        (old_id, boundary, boundary, break_time, event_id, break_time, reclaim_time),
    )


def get_row(db: Path) -> sqlite3.Row:
    with sqlite3.connect(db) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT * FROM weekly_direction_contexts WHERE weekly_range_source_id='20'"
        ).fetchone()
    assert row
    return row


def test_unique_chronology_and_ohlc_candidate_resolves_missing_link(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    summary = build_weekly_direction_contexts(db, weekly_source_id="20")
    row = get_row(db)
    assert row["creation_link_source"] == "OHLC_DERIVED"
    assert row["creation_old_weekly_source_id"] == "10"
    assert row["current_direction_state"] == "CONFIRMED_UP"
    assert "CREATION_LINK_DERIVED_FROM_CHRONOLOGY_AND_OHLC" in row["reason_codes_json"]
    assert summary["derived_link_count"] == 1


def test_multiple_compatible_creation_chains_require_review(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    with sqlite3.connect(db) as connection:
        second_old = {
            "case_ref": "case",
            "symbol": "XAUUSD",
            "structure_layer": "WEEKLY",
            "status": "BROKEN",
            "range_high_price": 115,
            "range_low_price": 95,
        }
        connection.execute(
            """INSERT INTO raw_ranges(
               import_run_id,source_record_id,symbol,timeframe,range_type,start_time_utc,
               high,low,raw_payload_json,payload_sha256,created_at_utc
               ) VALUES(1,'11','XAUUSD','W1','WEEKLY','2026-01-01T00:00:00Z',115,95,?,'sha',
                        '2026-01-01T00:00:00Z')""",
            (json.dumps(second_old),),
        )
        add_candidate(
            connection,
            old_id="11",
            event_id="101",
            boundary=115,
            break_time="2026-01-11T00:00:00Z",
            reclaim_time="2026-01-16T00:00:00Z",
            old_t0="2025-12-15T00:00:00Z",
        )
    build_weekly_direction_contexts(db, weekly_source_id="20")
    row = get_row(db)
    assert row["creation_link_source"] == "OHLC_DERIVED"
    assert row["current_direction_state"] == "NEEDS_REVIEW"
    assert "AMBIGUOUS_CREATION_CANDIDATES" in row["reason_codes_json"]


def test_break_level_outside_new_weekly_is_not_linked(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    with sqlite3.connect(db) as connection:
        connection.execute("UPDATE event_ohlc_evidence SET boundary_price=130")
        connection.execute("UPDATE weekly_break_reclaim_lifecycles SET break_level=130")
    build_weekly_direction_contexts(db, weekly_source_id="20")
    row = get_row(db)
    assert row["current_direction_state"] == "UNRESOLVED"
    assert row["creation_link_source"] == "NONE"


def test_direct_mapped_creation_link_remains_preferred(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    with sqlite3.connect(db) as connection:
        connection.execute("UPDATE event_ohlc_evidence SET mapped_new_range_id='20'")
    build_weekly_direction_contexts(db, weekly_source_id="20")
    row = get_row(db)
    assert row["creation_link_source"] == "EVIDENCE_DERIVED"
    assert row["current_direction_state"] == "CONFIRMED_UP"
