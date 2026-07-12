from __future__ import annotations

import sqlite3
from pathlib import Path

from range_library_memory.daily_trend_relationship import (
    build_daily_trend_relationships,
    summarize_daily_trend_relationships,
)
from range_library_memory.schema import init_schema


def make_db(
    tmp_path: Path,
    *,
    daily_id: str = "10",
    daily_state: str = "RECLAIMED",
    parent_membership: str = "VALID",
    parent_link_status: str | None = "VALID",
    daily_t0: str = "2026-01-11T00:00:00Z",
    daily_t1: str | None = "2026-01-16T00:00:00Z",
    daily_direction: str | None = "UP",
    daily_as_of: str = "2026-02-01T00:00:00Z",
    weekly_state: str = "CONFIRMED_UP",
    weekly_break: str | None = "2026-01-10T00:00:00Z",
    weekly_confirmed: str | None = "2026-01-15T00:00:00Z",
    weekly_as_of: str = "2026-02-01T00:00:00Z",
) -> Path:
    db = tmp_path / "memory.sqlite3"
    init_schema(db)
    with sqlite3.connect(db) as con:
        con.execute(
            "INSERT INTO import_runs(id,run_uuid,source_path,source_kind,started_at_utc,status) "
            "VALUES(1,'r','x','fixture','2026-01-01T00:00:00Z','completed')"
        )
        con.execute(
            """INSERT INTO daily_range_timelines(
               built_at_utc,import_run_id,case_ref,symbol,source_timeframe,daily_range_source_id,
               raw_range_id,raw_status,t0_formation_time,t1_break_time,t1_break_direction,
               current_daily_state,parent_weekly_source_id,parent_link_status,
               parent_membership_state,observation_status,resolution_status,resolution_confidence,
               reason_codes_json,as_of_time,created_at_utc,updated_at_utc
               ) VALUES(
               '2026-02-01T00:00:00Z',1,'case','XAUUSD','D1',?,1,'BROKEN',?,?,?, ?,
               '20',?,?, 'OBSERVED','RESOLVED','high','[]',?,
               '2026-02-01T00:00:00Z','2026-02-01T00:00:00Z')""",
            (
                daily_id,
                daily_t0,
                daily_t1,
                daily_direction,
                daily_state,
                parent_link_status,
                parent_membership,
                daily_as_of,
            ),
        )
        direction = "UP" if weekly_state.endswith("UP") else "DOWN" if weekly_state.endswith("DOWN") else None
        con.execute(
            """INSERT INTO weekly_direction_contexts(
               built_at_utc,import_run_id,case_ref,symbol,source_timeframe,weekly_range_source_id,
               raw_range_id,raw_status,creation_link_source,creation_old_weekly_source_id,
               creation_event_source_id,creation_break_direction,creation_break_time,
               creation_break_level,creation_break_kind,creation_reclaim_time,creation_reclaim_kind,
               pending_from_time,confirmed_from_time,current_direction_state,observation_status,
               resolution_status,resolution_confidence,reason_codes_json,as_of_time,
               created_at_utc,updated_at_utc
               ) VALUES(
               '2026-02-01T00:00:00Z',1,'case','XAUUSD','W1','20',2,'ACTIVE','EXPLICIT','19','100',
               ?,?,100,'WICK',?,'WICK',?,?,?,'OBSERVED','RESOLVED','high','[]',?,
               '2026-02-01T00:00:00Z','2026-02-01T00:00:00Z')""",
            (
                direction,
                weekly_break,
                weekly_confirmed,
                weekly_break,
                weekly_confirmed,
                weekly_state,
                weekly_as_of,
            ),
        )
    return db


def get_row(db: Path, daily_id: str = "10") -> sqlite3.Row:
    with sqlite3.connect(db) as con:
        con.row_factory = sqlite3.Row
        row = con.execute(
            "SELECT * FROM daily_trend_relationships WHERE daily_range_source_id=?",
            (daily_id,),
        ).fetchone()
    assert row
    return row


def test_confirmed_matching_daily_is_protrend(tmp_path: Path) -> None:
    db = make_db(tmp_path, daily_direction="UP", weekly_state="CONFIRMED_UP")
    build_daily_trend_relationships(db)
    row = get_row(db)
    assert row["trend_relationship"] == "PROTREND"
    assert row["weekly_direction_at_daily_break"] == "CONFIRMED_UP"
    assert row["weekly_confirmed_direction"] == "UP"


def test_confirmed_opposite_daily_is_countertrend(tmp_path: Path) -> None:
    db = make_db(tmp_path, daily_direction="DOWN", weekly_state="CONFIRMED_UP")
    build_daily_trend_relationships(db)
    assert get_row(db)["trend_relationship"] == "COUNTERTREND"


def test_daily_break_before_weekly_reclaim_is_transition_not_hindsight_protrend(tmp_path: Path) -> None:
    db = make_db(
        tmp_path,
        daily_direction="UP",
        daily_t1="2026-01-12T00:00:00Z",
        weekly_state="CONFIRMED_UP",
        weekly_break="2026-01-10T00:00:00Z",
        weekly_confirmed="2026-01-15T00:00:00Z",
    )
    build_daily_trend_relationships(db)
    row = get_row(db)
    assert row["trend_relationship"] == "TRANSITION"
    assert row["weekly_direction_at_daily_break"] == "PENDING_RECLAIM_UP"
    assert "WEEKLY_RECLAIM_PENDING_AT_DAILY_BREAK" in row["reason_codes_json"]


def test_opposite_daily_during_pending_weekly_is_also_transition(tmp_path: Path) -> None:
    db = make_db(
        tmp_path,
        daily_direction="DOWN",
        daily_t1="2026-01-12T00:00:00Z",
        weekly_state="PENDING_RECLAIM_UP",
        weekly_break="2026-01-10T00:00:00Z",
        weekly_confirmed=None,
    )
    build_daily_trend_relationships(db)
    assert get_row(db)["trend_relationship"] == "TRANSITION"


def test_unresolved_weekly_context_is_transition_for_factual_daily_break(tmp_path: Path) -> None:
    db = make_db(
        tmp_path,
        weekly_state="UNRESOLVED",
        weekly_break=None,
        weekly_confirmed=None,
    )
    build_daily_trend_relationships(db)
    row = get_row(db)
    assert row["trend_relationship"] == "TRANSITION"
    assert row["weekly_direction_at_daily_break"] == "UNRESOLVED"


def test_daily_without_factual_break_is_pending(tmp_path: Path) -> None:
    db = make_db(tmp_path, daily_state="ACTIVE_PRE_BREAK", daily_t1=None, daily_direction=None)
    build_daily_trend_relationships(db)
    row = get_row(db)
    assert row["trend_relationship"] == "PENDING"
    assert row["observation_status"] == "CENSORED"


def test_parent_conflict_needs_review_but_does_not_change_daily_timeline(tmp_path: Path) -> None:
    db = make_db(tmp_path, parent_membership="NEEDS_REVIEW", parent_link_status="CONFLICT")
    with sqlite3.connect(db) as con:
        before = con.execute("SELECT * FROM daily_range_timelines").fetchone()
    build_daily_trend_relationships(db)
    row = get_row(db)
    assert row["trend_relationship"] == "NEEDS_REVIEW"
    assert "PARENT_LINK_NEEDS_REVIEW" in row["reason_codes_json"]
    with sqlite3.connect(db) as con:
        assert con.execute("SELECT * FROM daily_range_timelines").fetchone() == before


def test_weekly_context_review_propagates_review(tmp_path: Path) -> None:
    db = make_db(tmp_path, weekly_state="NEEDS_REVIEW", weekly_break=None, weekly_confirmed=None)
    build_daily_trend_relationships(db)
    assert get_row(db)["trend_relationship"] == "NEEDS_REVIEW"


def test_context_change_between_daily_formation_and_break_is_recorded(tmp_path: Path) -> None:
    db = make_db(
        tmp_path,
        daily_t0="2026-01-12T00:00:00Z",
        daily_t1="2026-01-16T00:00:00Z",
        weekly_state="CONFIRMED_UP",
        weekly_break="2026-01-10T00:00:00Z",
        weekly_confirmed="2026-01-15T00:00:00Z",
    )
    build_daily_trend_relationships(db)
    row = get_row(db)
    assert row["weekly_direction_at_daily_formation"] == "PENDING_RECLAIM_UP"
    assert row["weekly_direction_at_daily_break"] == "CONFIRMED_UP"
    assert row["weekly_context_changed_during_daily"] == 1


def test_requested_as_of_before_daily_break_returns_pending(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    build_daily_trend_relationships(db, as_of="2026-01-14T00:00:00Z")
    row = get_row(db)
    assert row["trend_relationship"] == "PENDING"
    assert row["daily_t0_formation_time"] == "2026-01-11T00:00:00Z"
    assert row["daily_t1_break_time"] is None
    assert row["daily_break_direction"] is None
    assert row["classification_time"] is None
    assert "DAILY_BREAK_AFTER_AS_OF" in row["reason_codes_json"]


def test_scoped_rebuild_is_idempotent_and_preserves_unrelated(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    build_daily_trend_relationships(db)
    with sqlite3.connect(db) as con:
        con.execute(
            """INSERT INTO daily_trend_relationships(
               built_at_utc,case_ref,symbol,daily_range_source_id,parent_weekly_source_id,
               trend_relationship,observation_status,resolution_status,resolution_confidence,
               reason_codes_json,as_of_time,created_at_utc,updated_at_utc
               ) VALUES('2026-01-01T00:00:00Z','other','EURUSD','999','888','PENDING',
               'CENSORED','PENDING','low','[]','2026-01-01T00:00:00Z',
               '2026-01-01T00:00:00Z','2026-01-01T00:00:00Z')"""
        )
        unrelated = con.execute(
            "SELECT * FROM daily_trend_relationships WHERE daily_range_source_id='999'"
        ).fetchone()
    build_daily_trend_relationships(db, daily_source_id="10", weekly_source_id="20")
    build_daily_trend_relationships(db, daily_source_id="10", weekly_source_id="20")
    with sqlite3.connect(db) as con:
        assert con.execute(
            "SELECT COUNT(*) FROM daily_trend_relationships WHERE daily_range_source_id='10'"
        ).fetchone()[0] == 1
        assert con.execute(
            "SELECT * FROM daily_trend_relationships WHERE daily_range_source_id='999'"
        ).fetchone() == unrelated
    assert summarize_daily_trend_relationships(db, trend_relationship="PROTREND")["total"] == 1


def test_daily_break_before_weekly_creation_break_is_transition_unresolved(tmp_path: Path) -> None:
    db = make_db(
        tmp_path,
        daily_t0="2026-01-05T00:00:00Z",
        daily_t1="2026-01-08T00:00:00Z",
        weekly_state="CONFIRMED_UP",
        weekly_break="2026-01-10T00:00:00Z",
        weekly_confirmed="2026-01-15T00:00:00Z",
    )
    build_daily_trend_relationships(db)
    row = get_row(db)
    assert row["trend_relationship"] == "TRANSITION"
    assert row["weekly_direction_at_daily_break"] == "UNRESOLVED"


def test_requested_as_of_before_daily_formation_hides_future_milestones(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    build_daily_trend_relationships(db, as_of="2026-01-05T00:00:00Z")
    row = get_row(db)
    assert row["trend_relationship"] == "PENDING"
    assert row["daily_t0_formation_time"] is None
    assert row["daily_t1_break_time"] is None
    assert row["daily_break_direction"] is None
    assert row["classification_time"] is None
    assert "DAILY_NOT_FORMED_AS_OF" in row["reason_codes_json"]
