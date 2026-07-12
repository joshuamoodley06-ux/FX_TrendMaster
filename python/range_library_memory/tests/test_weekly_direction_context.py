from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from range_library_memory.schema import init_schema
from range_library_memory.weekly_direction_context import (
    build_weekly_direction_contexts,
    direction_state_at,
    summarize_weekly_direction_contexts,
)


def make_db(
    tmp_path: Path,
    *,
    new_id: str = "20",
    old_id: str = "10",
    event_id: str = "100",
    explicit: bool = True,
    partial: bool = False,
    direction: str = "UP",
    reclaim_state: str = "RECLAIMED",
    reclaim_time: str | None = "2026-01-15T00:00:00Z",
    phase_as_of: str = "2026-02-01T00:00:00Z",
) -> Path:
    db = tmp_path / "memory.sqlite3"
    init_schema(db)
    event_type = "BOS_UP" if direction == "UP" else "BOS_DOWN"
    boundary = 110.0 if direction == "UP" else 90.0
    old_payload = {
        "case_ref": "case",
        "symbol": "XAUUSD",
        "structure_layer": "WEEKLY",
        "status": "BROKEN",
        "range_high_price": 110,
        "range_low_price": 90,
        "range_high_time": "2025-12-01T00:00:00Z",
        "range_low_time": "2025-12-08T00:00:00Z",
    }
    new_payload = {
        "case_ref": "case",
        "symbol": "XAUUSD",
        "structure_layer": "WEEKLY",
        "status": "ACTIVE",
        "range_high_price": 120,
        "range_low_price": 100,
        "range_high_time": "2026-01-12T00:00:00Z",
        "range_low_time": "2026-01-05T00:00:00Z",
    }
    if explicit:
        new_payload["old_range_id"] = old_id
        if not partial:
            new_payload["created_by_event_id"] = event_id
    with sqlite3.connect(db) as con:
        con.execute(
            "INSERT INTO import_runs(id,run_uuid,source_path,source_kind,started_at_utc,status) "
            "VALUES(1,'r','x','fixture','2026-01-01T00:00:00Z','completed')"
        )
        for source_id, payload, high, low in (
            (old_id, old_payload, 110, 90),
            (new_id, new_payload, 120, 100),
        ):
            con.execute(
                """INSERT INTO raw_ranges(
                   import_run_id,source_record_id,symbol,timeframe,range_type,start_time_utc,
                   high,low,raw_payload_json,payload_sha256,created_at_utc
                   ) VALUES(1,?,'XAUUSD','W1','WEEKLY','2026-01-01T00:00:00Z',?,?,?,'sha',
                            '2026-01-01T00:00:00Z')""",
                (source_id, high, low, json.dumps(payload)),
            )
        con.execute(
            """INSERT INTO event_ohlc_evidence(
               built_at_utc,import_run_id,case_ref,symbol,structure_layer,source_timeframe,
               range_source_id,event_source_id,event_type,direction,range_formation_time,
               boundary_type,boundary_price,boundary_anchor_time,mapped_new_range_id,
               transition_status,transition_reason_codes_json,evidence_status,reason_codes_json,
               resolution_status,resolution_confidence,effective_break_time,effective_break_kind,
               as_of_time,created_at_utc,updated_at_utc
               ) VALUES(
               '2026-02-01T00:00:00Z',1,'case','XAUUSD','WEEKLY','W1',?,?,?, ?,
               '2025-12-08T00:00:00Z','RANGE_BOUNDARY',?,'2025-12-08T00:00:00Z',?,
               'VALID','[]','MATCH','[]','MAPPED_CONFIRMED','high','2026-01-10T00:00:00Z','WICK',
               '2026-02-01T00:00:00Z','2026-02-01T00:00:00Z','2026-02-01T00:00:00Z')""",
            (old_id, event_id, event_type, direction, boundary, new_id),
        )
        con.execute(
            """INSERT INTO weekly_break_reclaim_lifecycles(
               built_at_utc,import_run_id,case_ref,symbol,source_timeframe,weekly_range_source_id,
               raw_range_id,range_high,range_low,range_height,break_direction,break_level,break_time,
               break_kind,supporting_event_source_id,supporting_evidence_id,abandoned_from_time,
               effective_reclaim_time,effective_reclaim_kind,same_candle_close_reclaim,
               current_state,observation_status,resolution_status,resolution_confidence,
               reason_codes_json,as_of_time,created_at_utc,updated_at_utc
               ) VALUES(
               '2026-02-01T00:00:00Z',1,'case','XAUUSD','W1',?,1,110,90,20,?,?,
               '2026-01-10T00:00:00Z','WICK',?,1,'2026-01-10T00:00:00Z',?,
               'WICK',0,?,'OBSERVED','RESOLVED','high','[]','2026-02-01T00:00:00Z',
               '2026-02-01T00:00:00Z','2026-02-01T00:00:00Z')""",
            (old_id, direction, boundary, event_id, reclaim_time, reclaim_state),
        )
        con.execute(
            """INSERT INTO weekly_phase_sequences(
               built_at_utc,import_run_id,case_ref,symbol,source_timeframe,weekly_range_source_id,
               raw_range_id,raw_status,range_high,range_low,t0_formation_time,
               same_candle_break_reclaim,current_phase_state,current_phase_start_time,
               current_phase_age_days,observation_status,resolution_status,resolution_confidence,
               reason_codes_json,as_of_time,created_at_utc,updated_at_utc
               ) VALUES(
               '2026-02-01T00:00:00Z',1,'case','XAUUSD','W1',?,2,'ACTIVE',120,100,
               '2026-01-12T00:00:00Z',0,'ACTIVE_PRE_BREAK','2026-01-12T00:00:00Z',1,
               'CENSORED','PENDING','medium','[]',?,'2026-02-01T00:00:00Z',
               '2026-02-01T00:00:00Z')""",
            (new_id, phase_as_of),
        )
    return db


def get_row(db: Path, source_id: str = "20") -> sqlite3.Row:
    with sqlite3.connect(db) as con:
        con.row_factory = sqlite3.Row
        row = con.execute(
            "SELECT * FROM weekly_direction_contexts WHERE weekly_range_source_id=?",
            (source_id,),
        ).fetchone()
    assert row
    return row


def test_explicit_creation_reclaim_confirms_direction_without_hindsight(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    build_weekly_direction_contexts(db)
    row = get_row(db)
    assert row["current_direction_state"] == "CONFIRMED_UP"
    assert row["creation_link_source"] == "EXPLICIT"
    assert row["confirmed_from_time"] == "2026-01-15T00:00:00Z"
    assert direction_state_at(row, "2026-01-09T00:00:00Z") == "UNRESOLVED"
    assert direction_state_at(row, "2026-01-12T00:00:00Z") == "PENDING_RECLAIM_UP"
    assert direction_state_at(row, "2026-01-15T00:00:00Z") == "CONFIRMED_UP"


def test_reclaim_after_requested_as_of_remains_pending(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    build_weekly_direction_contexts(db, as_of="2026-01-12T00:00:00Z")
    row = get_row(db)
    assert row["current_direction_state"] == "PENDING_RECLAIM_UP"
    assert row["confirmed_from_time"] is None
    assert "CREATION_RECLAIM_AFTER_AS_OF" in row["reason_codes_json"]


def test_pending_source_state_stays_pending(tmp_path: Path) -> None:
    db = make_db(tmp_path, direction="DOWN", reclaim_state="ABANDONED_PENDING_RECLAIM", reclaim_time=None)
    build_weekly_direction_contexts(db)
    row = get_row(db)
    assert row["current_direction_state"] == "PENDING_RECLAIM_DOWN"
    assert row["observation_status"] == "CENSORED"


def test_no_creation_link_is_unresolved(tmp_path: Path) -> None:
    db = make_db(tmp_path, explicit=False)
    with sqlite3.connect(db) as con:
        con.execute("UPDATE event_ohlc_evidence SET mapped_new_range_id=NULL")
    build_weekly_direction_contexts(db)
    row = get_row(db)
    assert row["current_direction_state"] == "UNRESOLVED"
    assert "NO_CREATION_LINK" in row["reason_codes_json"]


def test_unique_evidence_can_derive_missing_creation_link(tmp_path: Path) -> None:
    db = make_db(tmp_path, explicit=False)
    build_weekly_direction_contexts(db)
    row = get_row(db)
    assert row["creation_link_source"] == "EVIDENCE_DERIVED"
    assert row["current_direction_state"] == "CONFIRMED_UP"


def test_partial_explicit_link_needs_review(tmp_path: Path) -> None:
    db = make_db(tmp_path, explicit=True, partial=True)
    build_weekly_direction_contexts(db)
    row = get_row(db)
    assert row["current_direction_state"] == "NEEDS_REVIEW"
    assert "PARTIAL_EXPLICIT_CREATION_LINK" in row["reason_codes_json"]


def test_break_reclaim_mismatch_needs_review(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    with sqlite3.connect(db) as con:
        con.execute("UPDATE weekly_break_reclaim_lifecycles SET break_direction='DOWN'")
    build_weekly_direction_contexts(db)
    row = get_row(db)
    assert row["current_direction_state"] == "NEEDS_REVIEW"
    assert "CREATION_BREAK_DIRECTION_MISMATCH" in row["reason_codes_json"]


def test_scoped_rebuild_is_idempotent_and_preserves_unrelated(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    build_weekly_direction_contexts(db)
    with sqlite3.connect(db) as con:
        con.execute(
            """INSERT INTO weekly_direction_contexts(
               built_at_utc,case_ref,symbol,source_timeframe,weekly_range_source_id,
               creation_link_source,current_direction_state,observation_status,resolution_status,
               resolution_confidence,on_status,resolution_confidence,
               reason_codes_json,as_of_time,create'2026-01-01T00:00:00Z','other','EURUSD','W1','999','NONE',
               'UNRESOLVED','INCOMPLETE','UNRESOLVED','low','[]','2026-01-01T00:00:00Z',
               '2026-01-01T00:00:00Z','2026-01-01T00:00:00Z')"""
        )
        unrelated = con.execute(
            "SELECT * FROM weekly_direction_contexts WHERE weekly_range_source_id='999'"
        ).fetchone()
    build_weekly_direction_contexts(db, weekly_source_id="20")
    build_weekly_direction_contexts(db, weekly_source_id="20")
    with sqlite3.connect(db) as con:
        assert con.execute(
            "SELECT COUNT(*) FROM weekly_direction_contexts WHERE weekly_range_source_id='20'"
        ).fetchone()[0] == 1
        assert con.execute(
            "SELECT * FROM weekly_direction_contexts WHERE weekly_range_source_id='999'"
        ).fetchone() == unrelated
    assert summarize_weekly_direction_contexts(db, direction_state="CONFIRMED_UP")["total"] == 1


def test_equivalent_break_event_can_supply_reclaim_without_false_review(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE weekly_break_reclaim_lifecycles SET supporting_event_source_id='101'"
        )
    build_weekly_direction_contexts(db)
    row = get_row(db)
    assert row["current_direction_state"] == "CONFIRMED_UP"
    assert "EQUI,crENT_CREATION_BREAK_EVENT_USED_FOR_RECLAIM" in row["reason_codes_json"]


def test_requested_as_of_after_phase_  ra_is_capped(tmp_path: Path) -> None:
    db = make_db(tmp_path, phase_as_of="2026-02-01T00:00:00Z")
    build_weekly_direction_contexts(db, as_of="2026-12-31T00:00:00Z")
    row = get_row(db)
    assert row["on_confide"] == "2026-02-01T00:00:00Z"
    assert "AS_OF_CAPPED_TO_WEEKLY_PHASE_DATA" in row["reason_codes_json"]
