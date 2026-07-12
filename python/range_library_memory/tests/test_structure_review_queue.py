from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from range_library_memory.importer import import_source
from range_library_memory.parent_child import build_parent_child
from range_library_memory.structure_review_queue import (
    ACTION_REQUIRED,
    REFERENCE_ONLY,
    build_structure_review_queue,
    list_structure_review_queue,
    main,
    summarize_structure_review_queue,
)


def write_source(tmp_path: Path, ranges: list[dict]) -> Path:
    path = tmp_path / "ranges.json"
    path.write_text(json.dumps({"ranges": ranges}), encoding="utf-8")
    return path


def weekly_range(range_id: str = "419", **overrides) -> dict:
    value = {
        "range_id": range_id,
        "case_ref": "case:one",
        "symbol": "XAUUSD",
        "structure_layer": "WEEKLY",
        "source_timeframe": "W1",
        "range_high_time": "2026-03-01T00:00:00Z",
        "range_low_time": "2026-03-08T00:00:00Z",
        "active_from_time": "2026-03-08T00:00:00Z",
        "range_start_time": "2026-03-01T00:00:00Z",
        "range_end_time": "2026-06-21T00:00:00Z",
        "range_high_price": 2100.0,
        "range_low_price": 2000.0,
        "status": "ACTIVE",
    }
    value.update(overrides)
    return value


def daily_range(range_id: str = "428", **overrides) -> dict:
    value = {
        "range_id": range_id,
        "case_ref": "case:one",
        "symbol": "XAUUSD",
        "structure_layer": "DAILY",
        "source_timeframe": "D1",
        "range_high_time": "2026-05-04T00:00:00Z",
        "range_low_time": "2026-04-17T00:00:00Z",
        "active_from_time": "2026-05-04T00:00:00Z",
        "range_start_time": "2026-04-17T00:00:00Z",
        "range_end_time": "2026-05-04T00:00:00Z",
        "range_high_price": 2060.0,
        "range_low_price": 2020.0,
        "status": "ACTIVE",
    }
    value.update(overrides)
    return value


def imported_db(tmp_path: Path, ranges: list[dict]) -> Path:
    db = tmp_path / "memory.sqlite3"
    import_source(db, write_source(tmp_path, ranges), "fixture")
    # These tests add their own explicit duplicate candidate when needed.
    # Ignore importer-generated overlap candidates so each fixture tests one root cause.
    with sqlite3.connect(db) as connection:
        connection.execute("UPDATE duplicate_candidates SET review_status='ignored'")
    return db


def raw_range_row(db: Path, source_id: str) -> sqlite3.Row:
    with sqlite3.connect(db) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT * FROM raw_ranges WHERE source_record_id=? ORDER BY id DESC LIMIT 1",
            (source_id,),
        ).fetchone()
    assert row is not None
    return row


def insert_weekly_direction(
    db: Path,
    *,
    weekly_id: str,
    state: str,
    reasons: list[str],
) -> None:
    raw = raw_range_row(db, weekly_id)
    now = "2026-07-12T00:00:00Z"
    with sqlite3.connect(db) as connection:
        connection.execute(
            """
            INSERT INTO weekly_direction_contexts(
                built_at_utc, import_run_id, case_ref, symbol, source_timeframe,
                weekly_range_source_id, raw_range_id, raw_status,
                creation_link_source, current_direction_state, observation_status,
                resolution_status, resolution_confidence, reason_codes_json,
                as_of_time, created_at_utc, updated_at_utc
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                now,
                raw["import_run_id"],
                "case:one",
                "XAUUSD",
                "W1",
                weekly_id,
                raw["id"],
                "ACTIVE",
                "NONE",
                state,
                "INCOMPLETE",
                "UNRESOLVED" if state == "UNRESOLVED" else "NEEDS_REVIEW",
                "low",
                json.dumps(reasons),
                now,
                now,
                now,
            ),
        )


def insert_daily_trend_review(db: Path, *, daily_id: str, weekly_id: str | None) -> None:
    raw = raw_range_row(db, daily_id)
    now = "2026-07-12T00:00:00Z"
    with sqlite3.connect(db) as connection:
        connection.execute(
            """
            INSERT INTO daily_trend_relationships(
                built_at_utc, import_run_id, case_ref, symbol,
                daily_range_source_id, parent_weekly_source_id,
                trend_relationship, observation_status, resolution_status,
                resolution_confidence, reason_codes_json, as_of_time,
                created_at_utc, updated_at_utc
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                now,
                raw["import_run_id"],
                "case:one",
                "XAUUSD",
                daily_id,
                weekly_id,
                "NEEDS_REVIEW",
                "INCOMPLETE",
                "NEEDS_REVIEW",
                "low",
                '["PARENT_CONFLICT"]',
                now,
                now,
                now,
            ),
        )


def insert_event_evidence(
    db: Path,
    *,
    range_id: str = "419",
    event_id: str = "1430",
    resolution_status: str = "MISSING_DATA",
    evidence_status: str = "NEEDS_REVIEW",
    transition_status: str = "NEEDS_REVIEW",
    reasons: list[str] | None = None,
) -> None:
    raw = raw_range_row(db, range_id)
    now = "2026-07-12T00:00:00Z"
    with sqlite3.connect(db) as connection:
        connection.execute(
            """
            INSERT INTO event_ohlc_evidence(
                built_at_utc, import_run_id, case_ref, symbol, structure_layer,
                source_timeframe, range_source_id, event_source_id, raw_range_id,
                event_type, direction, range_formation_time, boundary_type,
                boundary_price, boundary_anchor_time, transition_status,
                transition_reason_codes_json, evidence_status, reason_codes_json,
                resolution_status, resolution_confidence, as_of_time,
                created_at_utc, updated_at_utc
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                now,
                raw["import_run_id"],
                "case:one",
                "XAUUSD",
                "WEEKLY",
                "W1",
                range_id,
                event_id,
                raw["id"],
                "BOS_DOWN",
                "DOWN",
                "2026-03-08T00:00:00Z",
                "LOW",
                2000.0,
                "2026-03-08T00:00:00Z",
                transition_status,
                "[]",
                evidence_status,
                json.dumps(reasons or ["MISSING_CANDLES"]),
                resolution_status,
                "low",
                now,
                now,
                now,
            ),
        )


def insert_validation_and_duplicate(db: Path) -> None:
    left = raw_range_row(db, "419")
    right = raw_range_row(db, "425")
    now = "2026-07-12T00:00:00Z"
    with sqlite3.connect(db) as connection:
        connection.execute(
            """
            INSERT INTO validation_issues(
                import_run_id, raw_range_id, severity, issue_code, message,
                field_name, observed_value, created_at_utc
            ) VALUES(?,?,?,?,?,?,?,?)
            """,
            (
                left["import_run_id"],
                left["id"],
                "high",
                "INVALID_CHRONOLOGY",
                "Weekly chronology is invalid.",
                "range_start_time",
                "bad-time",
                now,
            ),
        )
        connection.execute(
            """
            INSERT INTO duplicate_candidates(
                import_run_id, candidate_type, left_raw_range_id,
                right_raw_range_id, rule_code, confidence, reason,
                created_at_utc, review_status
            ) VALUES(?,?,?,?,?,?,?,?,?)
            """,
            (
                left["import_run_id"],
                "range",
                left["id"],
                right["id"],
                "SAME_BOUNDARIES",
                "high",
                "Both Weekly ranges share the same boundaries.",
                now,
                "open",
            ),
        )


def queue_rows(db: Path) -> list[sqlite3.Row]:
    with sqlite3.connect(db) as connection:
        connection.row_factory = sqlite3.Row
        return connection.execute(
            "SELECT * FROM structure_review_queue WHERE is_active=1 ORDER BY priority, item_type"
        ).fetchall()


def test_parent_conflict_lists_all_compatible_weekly_candidates(tmp_path: Path) -> None:
    db = imported_db(
        tmp_path,
        [
            weekly_range("419"),
            weekly_range(
                "425",
                range_high_price=2120.0,
                range_low_price=1980.0,
                range_high_time="2026-04-05T00:00:00Z",
                range_low_time="2026-04-12T00:00:00Z",
                active_from_time="2026-04-12T00:00:00Z",
            ),
            daily_range("428"),
        ],
    )
    build_parent_child(db, parent_layer="WEEKLY", child_layer="DAILY")

    result = build_structure_review_queue(db)
    items = list_structure_review_queue(db)

    assert result["action_required_count"] == 1
    assert len(items) == 1
    assert items[0]["item_type"] == "PARENT_CONFLICT"
    assert items[0]["range_source_id"] == "428"
    assert items[0]["candidate_range_ids"] == ["419", "425"]
    assert "419" in items[0]["trader_summary"]
    assert "425" in items[0]["trader_summary"]


def test_parent_conflict_suppresses_duplicate_daily_trend_symptom(tmp_path: Path) -> None:
    db = imported_db(
        tmp_path,
        [weekly_range("419"), weekly_range("425"), daily_range("428")],
    )
    build_parent_child(db, parent_layer="WEEKLY", child_layer="DAILY")
    insert_daily_trend_review(db, daily_id="428", weekly_id="419")

    build_structure_review_queue(db)
    types = [item["item_type"] for item in list_structure_review_queue(db)]

    assert types == ["PARENT_CONFLICT"]


def test_unresolved_weekly_creation_is_reference_only_fragment_context(tmp_path: Path) -> None:
    db = imported_db(tmp_path, [weekly_range("353")])
    insert_weekly_direction(
        db,
        weekly_id="353",
        state="UNRESOLVED",
        reasons=["NO_CREATION_LINK"],
    )

    result = build_structure_review_queue(db)
    item = list_structure_review_queue(db)[0]

    assert result["reference_only_count"] == 1
    assert item["actionability"] == REFERENCE_ONLY
    assert item["item_type"] == "WEEKLY_CREATION_CONTEXT_UNAVAILABLE"
    assert "fragmented" in item["trader_summary"].lower()


def test_weekly_creation_needs_review_is_actionable(tmp_path: Path) -> None:
    db = imported_db(tmp_path, [weekly_range("392")])
    insert_weekly_direction(
        db,
        weekly_id="392",
        state="NEEDS_REVIEW",
        reasons=["AMBIGUOUS_CREATION_CANDIDATES"],
    )

    build_structure_review_queue(db)
    item = list_structure_review_queue(db)[0]

    assert item["actionability"] == ACTION_REQUIRED
    assert item["severity"] == "HIGH"
    assert item["item_type"] == "WEEKLY_CREATION_REVIEW"
    assert item["reason_codes"] == ["AMBIGUOUS_CREATION_CANDIDATES"]


def test_missing_event_candles_becomes_high_priority_root_cause(tmp_path: Path) -> None:
    db = imported_db(tmp_path, [weekly_range("419")])
    insert_event_evidence(db)

    build_structure_review_queue(db)
    item = list_structure_review_queue(db)[0]

    assert item["item_type"] == "MISSING_CANDLE_EVIDENCE"
    assert item["severity"] == "HIGH"
    assert item["event_source_id"] == "1430"
    assert "sync" in item["suggested_action"].lower()


def test_validation_and_duplicate_sources_join_the_same_queue(tmp_path: Path) -> None:
    db = imported_db(tmp_path, [weekly_range("419"), weekly_range("425")])
    insert_validation_and_duplicate(db)

    result = build_structure_review_queue(db)
    items = list_structure_review_queue(db)
    types = {item["item_type"] for item in items}

    assert result["rows_built"] == 2
    assert types == {"VALIDATION_ISSUE", "DUPLICATE_CANDIDATE"}
    duplicate = next(item for item in items if item["item_type"] == "DUPLICATE_CANDIDATE")
    assert duplicate["candidate_range_ids"] == ["419", "425"]


def test_daily_trend_review_is_used_only_when_no_clearer_root_cause_exists(tmp_path: Path) -> None:
    db = imported_db(tmp_path, [weekly_range("419"), daily_range("428")])
    insert_daily_trend_review(db, daily_id="428", weekly_id="419")

    build_structure_review_queue(db)
    item = list_structure_review_queue(db)[0]

    assert item["item_type"] == "DAILY_TREND_REVIEW"
    assert item["range_source_id"] == "428"


def test_rebuild_marks_cleared_items_inactive_without_deleting_history(tmp_path: Path) -> None:
    db = imported_db(
        tmp_path,
        [weekly_range("419"), weekly_range("425"), daily_range("428")],
    )
    build_parent_child(db, parent_layer="WEEKLY", child_layer="DAILY")
    build_structure_review_queue(db)
    assert len(list_structure_review_queue(db)) == 1

    with sqlite3.connect(db) as connection:
        connection.execute("DELETE FROM parent_child_relationships")

    build_structure_review_queue(db)

    assert list_structure_review_queue(db) == []
    with sqlite3.connect(db) as connection:
        row = connection.execute(
            "SELECT is_active FROM structure_review_queue WHERE review_key='parent:428'"
        ).fetchone()
    assert row == (0,)


def test_rebuild_is_idempotent_preserves_first_seen_and_raw_mapping(tmp_path: Path) -> None:
    db = imported_db(tmp_path, [weekly_range("419")])
    insert_weekly_direction(
        db,
        weekly_id="419",
        state="UNRESOLVED",
        reasons=["NO_CREATION_LINK"],
    )
    with sqlite3.connect(db) as connection:
        raw_before = connection.execute(
            "SELECT raw_payload_json FROM raw_ranges ORDER BY id"
        ).fetchall()

    build_structure_review_queue(db)
    with sqlite3.connect(db) as connection:
        first_seen = connection.execute(
            "SELECT first_seen_at_utc FROM structure_review_queue"
        ).fetchone()[0]

    build_structure_review_queue(db)
    with sqlite3.connect(db) as connection:
        row = connection.execute(
            "SELECT COUNT(*), first_seen_at_utc, is_active FROM structure_review_queue"
        ).fetchone()
        raw_after = connection.execute(
            "SELECT raw_payload_json FROM raw_ranges ORDER BY id"
        ).fetchall()

    assert row == (1, first_seen, 1)
    assert raw_after == raw_before


def test_summary_filters_and_module_cli_are_deterministic(tmp_path: Path, capsys) -> None:
    db = imported_db(tmp_path, [weekly_range("353")])
    insert_weekly_direction(
        db,
        weekly_id="353",
        state="UNRESOLVED",
        reasons=["NO_CREATION_LINK"],
    )

    assert main(["build", "--db-path", str(db), "--json"]) == 0
    build_output = capsys.readouterr().out.strip()
    build_payload = json.loads(build_output)
    assert build_output == json.dumps(build_payload, sort_keys=True, separators=(",", ":"))

    assert main(
        [
            "summary",
            "--db-path",
            str(db),
            "--actionability",
            REFERENCE_ONLY,
            "--json",
        ]
    ) == 0
    summary_output = capsys.readouterr().out.strip()
    summary_payload = json.loads(summary_output)
    assert summary_output == json.dumps(summary_payload, sort_keys=True, separators=(",", ":"))
    assert summary_payload["totals"]["reference_only"] == 1

    assert main(["list", "--db-path", str(db), "--json"]) == 0
    list_output = capsys.readouterr().out.strip()
    list_payload = json.loads(list_output)
    assert list_output == json.dumps(list_payload, sort_keys=True, separators=(",", ":"))
    assert list_payload["items"][0]["range_source_id"] == "353"

    direct = summarize_structure_review_queue(db, structure_layer="weekly")
    assert direct["totals"]["active"] == 1
