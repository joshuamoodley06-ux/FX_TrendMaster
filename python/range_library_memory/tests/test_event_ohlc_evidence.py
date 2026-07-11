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
from range_library_memory.event_ohlc_evidence import build_event_ohlc_evidence, summarize_event_ohlc
from range_library_memory.schema import init_schema
from range_library_memory.weekly_family_coverage import analyze_weekly_family_coverage


def memory_db(tmp_path: Path) -> Path:
    db = tmp_path / "memory.sqlite3"
    init_schema(db)
    with sqlite3.connect(db) as connection:
        connection.execute(
            """
            INSERT INTO import_runs (id, run_uuid, source_path, source_kind, started_at_utc, status)
            VALUES (1, 'run', 'fixture', 'fixture', '2026-01-01T00:00:00Z', 'completed')
            """
        )
    return db


def source_db(tmp_path: Path) -> Path:
    db = tmp_path / "market_memory.db"
    with sqlite3.connect(db) as connection:
        connection.execute(
            """
            CREATE TABLE candles (
                symbol TEXT, timeframe TEXT, time TEXT,
                open REAL, high REAL, low REAL, close REAL,
                volume REAL, source TEXT
            )
            """
        )
        connection.execute("CREATE TABLE map_ranges (id INTEGER PRIMARY KEY)")
    return db


def add_candle(db: Path, time: str, *, high: float, low: float, close: float, timeframe: str = "D1") -> None:
    with sqlite3.connect(db) as connection:
        connection.execute(
            """
            INSERT INTO candles (symbol, timeframe, time, open, high, low, close, volume, source)
            VALUES ('XAUUSD', ?, ?, 100.0, ?, ?, ?, 1.0, 'fixture')
            """,
            (timeframe, time, high, low, close),
        )


def range_payload(range_id: str = "r1", **overrides) -> dict:
    value = {
        "range_id": range_id,
        "case_ref": "case",
        "symbol": "XAUUSD",
        "structure_layer": "DAILY",
        "source_timeframe": "D1",
        "status": "BROKEN",
        "active_from_time": "2026-01-01T00:00:00Z",
        "inactive_from_time": "2026-01-05T00:00:00Z",
        "range_high_price": 110.0,
        "range_high_time": "2026-01-02T00:00:00Z",
        "range_low_price": 90.0,
        "range_low_time": "2026-01-02T00:00:00Z",
        "broken_by_event_id": "e1",
    }
    value.update(overrides)
    return value


def event_payload(event_id: str = "e1", **overrides) -> dict:
    value = {
        "event_id": event_id,
        "case_ref": "case",
        "symbol": "XAUUSD",
        "structure_layer": "DAILY",
        "source_timeframe": "D1",
        "event_type": "BOS_UP",
        "direction": "UP",
        "event_time": "2026-01-04T00:00:00Z",
        "event_price": 111.0,
        "break_level_price": 110.0,
        "active_range_id": "r1",
        "range_id": "r1",
    }
    value.update(overrides)
    return value


def add_range(db: Path, payload: dict, source_id: str | None = None) -> None:
    source = source_id or payload["range_id"]
    with sqlite3.connect(db) as connection:
        connection.execute(
            """
            INSERT INTO raw_ranges (
                import_run_id, source_record_id, symbol, timeframe, range_type,
                start_time_utc, end_time_utc, high, low, raw_payload_json,
                payload_sha256, created_at_utc
            ) VALUES (1, ?, 'XAUUSD', ?, ?, ?, ?, ?, ?, ?, ?, '2026-01-01T00:00:00Z')
            """,
            (
                source,
                payload["source_timeframe"],
                payload["structure_layer"],
                payload.get("active_from_time"),
                payload.get("inactive_from_time"),
                payload.get("range_high_price"),
                payload.get("range_low_price"),
                json.dumps(payload, sort_keys=True),
                f"sha-range-{source}-{payload.get('inactive_from_time')}",
            ),
        )


def add_event(db: Path, payload: dict, source_id: str | None = None) -> None:
    source = source_id or payload["event_id"]
    with sqlite3.connect(db) as connection:
        connection.execute(
            """
            INSERT INTO raw_events (
                import_run_id, source_record_id, event_type, event_time_utc, price,
                raw_payload_json, payload_sha256, created_at_utc
            ) VALUES (1, ?, ?, ?, ?, ?, ?, '2026-01-01T00:00:00Z')
            """,
            (
                source,
                payload["event_type"],
                payload.get("event_time"),
                payload.get("event_price"),
                json.dumps(payload, sort_keys=True),
                f"sha-event-{source}-{payload.get('event_time')}",
            ),
        )


def fetch_one(db: Path, query: str, params: tuple = ()) -> sqlite3.Row:
    with sqlite3.connect(db) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(query, params).fetchone()
    assert row is not None
    return row


def count_rows(db: Path, table: str) -> int:
    return fetch_one(db, f"SELECT COUNT(*) AS count FROM {table}")["count"]


def build_basic_up_case(tmp_path: Path) -> tuple[Path, Path]:
    rlm = memory_db(tmp_path)
    source = source_db(tmp_path)
    add_range(rlm, range_payload())
    add_event(rlm, event_payload())
    add_candle(source, "2026.01.02 00:00", high=110.0, low=95.0, close=100.0)
    add_candle(source, "2026.01.03 00:00", high=110.5, low=96.0, close=109.0)
    add_candle(source, "2026.01.04 00:00", high=111.0, low=97.0, close=111.0)
    return rlm, source


def test_bos_up_uses_range_high_as_canonical_boundary(tmp_path: Path) -> None:
    rlm, source = build_basic_up_case(tmp_path)
    build_event_ohlc_evidence(rlm, source_db=source, range_source_id="r1")

    row = fetch_one(rlm, "SELECT * FROM event_ohlc_evidence")

    assert row["boundary_type"] == "RANGE_HIGH"
    assert row["boundary_price"] == 110.0


def test_bos_down_uses_range_low_as_canonical_boundary(tmp_path: Path) -> None:
    rlm = memory_db(tmp_path)
    source = source_db(tmp_path)
    add_range(rlm, range_payload(range_low_price=90.0))
    add_event(
        rlm,
        event_payload(event_type="BOS_DOWN", direction="DOWN", event_price=89.0, break_level_price=90.0),
    )
    add_candle(source, "2026.01.04 00:00", high=100.0, low=89.0, close=91.0)
    build_event_ohlc_evidence(rlm, source_db=source, range_source_id="r1")

    row = fetch_one(rlm, "SELECT * FROM event_ohlc_evidence")

    assert row["boundary_type"] == "RANGE_LOW"
    assert row["boundary_price"] == 90.0


def test_event_break_level_price_never_overrides_range_boundary(tmp_path: Path) -> None:
    rlm, source = build_basic_up_case(tmp_path)
    add_event(rlm, event_payload(event_id="e2", break_level_price=999.0), source_id="e2")
    build_event_ohlc_evidence(rlm, source_db=source, event_source_id="e2")

    row = fetch_one(rlm, "SELECT * FROM event_ohlc_evidence WHERE event_source_id = 'e2'")

    assert row["boundary_price"] == 110.0
    assert "MAPPED_BREAK_LEVEL_DIFFERS_FROM_RANGE_BOUNDARY" in row["reason_codes_json"]


def test_valid_mapped_wick_breach_produces_match(tmp_path: Path) -> None:
    rlm, source = build_basic_up_case(tmp_path)
    add_event(rlm, event_payload(event_id="e0", event_time="2026-01-03T00:00:00Z", event_price=110.5), source_id="e0")
    build_event_ohlc_evidence(rlm, source_db=source, event_source_id="e0")

    row = fetch_one(rlm, "SELECT * FROM event_ohlc_evidence WHERE event_source_id = 'e0'")

    assert row["evidence_status"] == "MATCH"
    assert row["resolution_status"] == "MAPPED_CONFIRMED"
    assert row["effective_break_time"] == "2026-01-03T00:00:00Z"


def test_valid_mapped_close_breach_records_wick_and_close(tmp_path: Path) -> None:
    rlm, source = build_basic_up_case(tmp_path)
    build_event_ohlc_evidence(rlm, source_db=source, range_source_id="r1")

    row = fetch_one(rlm, "SELECT * FROM event_ohlc_evidence")

    assert row["first_wick_breach_time"] == "2026-01-03T00:00:00Z"
    assert row["first_close_breach_time"] == "2026-01-04T00:00:00Z"


def test_event_before_range_formation_produces_invalid_chronology(tmp_path: Path) -> None:
    rlm, source = build_basic_up_case(tmp_path)
    add_event(rlm, event_payload(event_id="eearly", event_time="2026-01-01T00:00:00Z"), source_id="eearly")
    build_event_ohlc_evidence(rlm, source_db=source, event_source_id="eearly")

    row = fetch_one(rlm, "SELECT * FROM event_ohlc_evidence WHERE event_source_id = 'eearly'")

    assert row["evidence_status"] == "INVALID_CHRONOLOGY"
    assert "EVENT_PRECEDES_RANGE_FORMATION" in row["reason_codes_json"]


def test_mapped_candle_that_does_not_breach_boundary_is_boundary_not_breached(tmp_path: Path) -> None:
    rlm, source = build_basic_up_case(tmp_path)
    add_event(rlm, event_payload(event_id="enobreach", event_time="2026-01-02T00:00:00Z", event_price=110.0), source_id="enobreach")
    build_event_ohlc_evidence(rlm, source_db=source, event_source_id="enobreach")

    row = fetch_one(rlm, "SELECT * FROM event_ohlc_evidence WHERE event_source_id = 'enobreach'")

    assert row["evidence_status"] == "BOUNDARY_NOT_BREACHED"


def test_actual_later_wick_breach_produces_ohlc_derived(tmp_path: Path) -> None:
    rlm, source = build_basic_up_case(tmp_path)
    add_event(rlm, event_payload(event_id="elate", event_time="2026-01-02T00:00:00Z", event_price=110.0), source_id="elate")
    build_event_ohlc_evidence(rlm, source_db=source, event_source_id="elate")

    row = fetch_one(rlm, "SELECT * FROM event_ohlc_evidence WHERE event_source_id = 'elate'")

    assert row["resolution_status"] == "OHLC_DERIVED"
    assert row["effective_break_time"] == "2026-01-03T00:00:00Z"


def test_actual_earlier_wick_breach_produces_time_mismatch(tmp_path: Path) -> None:
    rlm, source = build_basic_up_case(tmp_path)
    build_event_ohlc_evidence(rlm, source_db=source, range_source_id="r1")

    row = fetch_one(rlm, "SELECT * FROM event_ohlc_evidence")

    assert row["evidence_status"] == "TIME_MISMATCH"
    assert "FIRST_ACTUAL_BREACH_OCCURS_EARLIER" in row["reason_codes_json"]


def test_no_breach_through_as_of_produces_unbroken(tmp_path: Path) -> None:
    rlm = memory_db(tmp_path)
    source = source_db(tmp_path)
    add_range(rlm, range_payload())
    add_event(rlm, event_payload())
    add_candle(source, "2026.01.02 00:00", high=110.0, low=95.0, close=100.0)
    build_event_ohlc_evidence(rlm, source_db=source, range_source_id="r1", as_of="2026-01-02T00:00:00Z")

    row = fetch_one(rlm, "SELECT * FROM event_ohlc_evidence")
    lifecycle = fetch_one(rlm, "SELECT * FROM resolved_range_lifecycles WHERE range_source_id = 'r1'")

    assert row["resolution_status"] == "UNBROKEN_THROUGH_AS_OF"
    assert lifecycle["effective_status"] == "ACTIVE"


def test_missing_candles_produces_missing_data(tmp_path: Path) -> None:
    rlm = memory_db(tmp_path)
    source = source_db(tmp_path)
    add_range(rlm, range_payload())
    add_event(rlm, event_payload())
    build_event_ohlc_evidence(rlm, source_db=source, range_source_id="r1", as_of="2026-01-05T00:00:00Z")

    row = fetch_one(rlm, "SELECT * FROM event_ohlc_evidence")

    assert row["resolution_status"] == "MISSING_DATA"


def test_missing_mapped_range_produces_missing_range(tmp_path: Path) -> None:
    rlm = memory_db(tmp_path)
    source = source_db(tmp_path)
    add_event(rlm, event_payload(active_range_id="missing", range_id="missing"))
    build_event_ohlc_evidence(rlm, source_db=source, event_source_id="e1")

    row = fetch_one(rlm, "SELECT * FROM event_ohlc_evidence")

    assert row["evidence_status"] == "MISSING_RANGE"


def test_boundary_contact_is_distinct_from_wick_and_close(tmp_path: Path) -> None:
    rlm, source = build_basic_up_case(tmp_path)
    build_event_ohlc_evidence(rlm, source_db=source, range_source_id="r1")

    row = fetch_one(rlm, "SELECT * FROM event_ohlc_evidence")

    assert row["first_boundary_contact_time"] == "2026-01-02T00:00:00Z"
    assert row["first_wick_breach_time"] == "2026-01-03T00:00:00Z"
    assert row["first_close_breach_time"] == "2026-01-04T00:00:00Z"


def test_canonical_source_timestamps_are_deterministic(tmp_path: Path) -> None:
    rlm, source = build_basic_up_case(tmp_path)
    build_event_ohlc_evidence(rlm, source_db=source, range_source_id="r1")

    row = fetch_one(rlm, "SELECT * FROM event_ohlc_evidence")

    assert row["first_wick_breach_time"] == "2026-01-03T00:00:00Z"


def test_latest_raw_range_and_event_versions_are_used(tmp_path: Path) -> None:
    rlm, source = build_basic_up_case(tmp_path)
    add_range(rlm, range_payload(range_high_price=120.0), source_id="r1")
    add_event(rlm, event_payload(event_time="2026-01-02T00:00:00Z", event_price=120.0), source_id="e1")
    build_event_ohlc_evidence(rlm, source_db=source, range_source_id="r1")

    row = fetch_one(rlm, "SELECT * FROM event_ohlc_evidence")

    assert row["boundary_price"] == 120.0
    assert row["mapped_event_time"] == "2026-01-02T00:00:00Z"


def test_rebuild_replaces_only_requested_scope(tmp_path: Path) -> None:
    rlm, source = build_basic_up_case(tmp_path)
    add_range(rlm, range_payload(range_id="r2"), source_id="r2")
    add_event(rlm, event_payload(event_id="e2", active_range_id="r2", range_id="r2"), source_id="e2")
    build_event_ohlc_evidence(rlm, source_db=source)
    build_event_ohlc_evidence(rlm, source_db=source, range_source_id="r1")

    assert count_rows(rlm, "event_ohlc_evidence") == 2


def test_raw_ranges_raw_events_and_source_db_remain_unchanged(tmp_path: Path) -> None:
    rlm, source = build_basic_up_case(tmp_path)
    before_range_payload = fetch_one(rlm, "SELECT raw_payload_json FROM raw_ranges WHERE source_record_id = 'r1'")["raw_payload_json"]
    before_event_payload = fetch_one(rlm, "SELECT raw_payload_json FROM raw_events WHERE source_record_id = 'e1'")["raw_payload_json"]
    before_candles = count_rows(source, "candles")
    build_event_ohlc_evidence(rlm, source_db=source, range_source_id="r1")

    assert fetch_one(rlm, "SELECT raw_payload_json FROM raw_ranges WHERE source_record_id = 'r1'")["raw_payload_json"] == before_range_payload
    assert fetch_one(rlm, "SELECT raw_payload_json FROM raw_events WHERE source_record_id = 'e1'")["raw_payload_json"] == before_event_payload
    assert count_rows(source, "candles") == before_candles


def test_invalid_creating_event_produces_invalid_transition_without_deleting_new_range(tmp_path: Path) -> None:
    rlm, source = build_basic_up_case(tmp_path)
    add_range(rlm, range_payload(range_id="r2", old_range_id="r1", created_by_event_id="einvalid"), source_id="r2")
    add_event(
        rlm,
        event_payload(
            event_id="einvalid",
            event_time="2026-01-01T00:00:00Z",
            old_range_id="r1",
            new_range_id="r2",
        ),
        source_id="einvalid",
    )
    build_event_ohlc_evidence(rlm, source_db=source, event_source_id="einvalid")

    row = fetch_one(rlm, "SELECT * FROM event_ohlc_evidence WHERE event_source_id = 'einvalid'")

    assert row["transition_status"] == "INVALID"
    assert "CREATING_EVENT_INVALID" in row["transition_reason_codes_json"]
    assert fetch_one(rlm, "SELECT * FROM raw_ranges WHERE source_record_id = 'r2'")["source_record_id"] == "r2"


def test_weekly_family_coverage_uses_resolved_lifecycle_when_available(tmp_path: Path) -> None:
    rlm = memory_db(tmp_path)
    source = source_db(tmp_path)
    for day in range(1, 8):
        add_candle(source, f"2026.01.0{day} 00:00", high=120.0, low=80.0, close=100.0)
    add_range(
        rlm,
        range_payload(
            range_id="w1",
            structure_layer="WEEKLY",
            source_timeframe="W1",
            active_from_time="2026-01-01T00:00:00Z",
            inactive_from_time="2026-01-07T00:00:00Z",
            range_high_time="2026-01-02T00:00:00Z",
            range_low_time="2026-01-02T00:00:00Z",
        ),
        source_id="w1",
    )
    add_range(
        rlm,
        range_payload(range_id="d1", active_from_time="2026-01-03T00:00:00Z", inactive_from_time="2026-01-02T00:00:00Z"),
        source_id="d1",
    )
    with sqlite3.connect(rlm) as connection:
        connection.execute(
            """
            INSERT INTO parent_child_relationships (
                import_run_id, case_ref, symbol, relationship_type, parent_range_id, child_range_id,
                parent_layer, child_layer, parent_timeframe, child_timeframe, link_source, link_status,
                link_confidence, review_status, child_position_in_parent, child_boundary_interaction,
                child_lifecycle_relationship, created_at_utc, updated_at_utc
            ) VALUES (1, 'case', 'XAUUSD', 'weekly_daily', 'w1', 'd1', 'WEEKLY', 'DAILY', 'W1', 'D1',
              'explicit', 'VALID', 'high', 'open', 'inside_fair_price', 'inside_parent',
              'formed_during_active_parent', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')
            """
        )
        connection.execute(
            """
            INSERT INTO resolved_range_lifecycles (
                built_at_utc, import_run_id, case_ref, symbol, structure_layer, source_timeframe, range_source_id,
                raw_range_id, raw_status, raw_active_from_time, raw_inactive_from_time, effective_status,
                effective_active_from_time, effective_inactive_from_time, resolution_source, resolution_status,
                resolution_confidence, reason_codes_json, as_of_time, created_at_utc, updated_at_utc
            ) VALUES ('2026-01-01T00:00:00Z', 1, 'case', 'XAUUSD', 'DAILY', 'D1', 'd1',
                2, 'BROKEN', '2026-01-03T00:00:00Z', '2026-01-02T00:00:00Z', 'BROKEN',
                '2026-01-03T00:00:00Z', '2026-01-06T00:00:00Z', 'OHLC', 'OHLC_DERIVED',
                'medium', '[]', '2026-01-07T00:00:00Z', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')
            """
        )

    report = analyze_weekly_family_coverage(rlm, source_db=source, weekly_source_id="w1")

    assert report["children"][0]["raw_inactive_from_time"] == "2026-01-02T00:00:00Z"
    assert report["children"][0]["effective_inactive_from_time"] == "2026-01-06T00:00:00Z"
    assert report["windows"]["post_formation"]["coverage_status"] == "PARTIAL"


def test_weekly_family_coverage_strict_raw_fallback_still_fails(tmp_path: Path) -> None:
    rlm, source = build_basic_up_case(tmp_path)
    add_range(
        rlm,
        range_payload(
            range_id="w1",
            structure_layer="WEEKLY",
            source_timeframe="W1",
            active_from_time="2026-01-01T00:00:00Z",
            inactive_from_time="2026-01-07T00:00:00Z",
            range_high_time="2026-01-02T00:00:00Z",
            range_low_time="2026-01-02T00:00:00Z",
        ),
        source_id="w1",
    )
    add_range(rlm, range_payload(range_id="d1", active_from_time="2026-01-04T00:00:00Z", inactive_from_time="2026-01-03T00:00:00Z"), source_id="d1")
    with sqlite3.connect(rlm) as connection:
        connection.execute(
            """
            INSERT INTO parent_child_relationships (
                import_run_id, case_ref, symbol, relationship_type, parent_range_id, child_range_id,
                parent_layer, child_layer, parent_timeframe, child_timeframe, link_source, link_status,
                link_confidence, review_status, child_position_in_parent, child_boundary_interaction,
                child_lifecycle_relationship, created_at_utc, updated_at_utc
            ) VALUES (1, 'case', 'XAUUSD', 'weekly_daily', 'w1', 'd1', 'WEEKLY', 'DAILY', 'W1', 'D1',
              'explicit', 'VALID', 'high', 'open', 'inside_fair_price', 'inside_parent',
              'formed_during_active_parent', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')
            """
        )

    with pytest.raises(Exception, match="Daily child lifecycle start is after end"):
        analyze_weekly_family_coverage(rlm, source_db=source, weekly_source_id="w1")


def test_summary_json_and_cli_paths_are_deterministic(tmp_path: Path, capsys) -> None:
    rlm, source = build_basic_up_case(tmp_path)
    assert main(
        [
            "build-event-ohlc-evidence",
            "--db-path",
            str(rlm),
            "--source-db",
            str(source),
            "--range-source-id",
            "r1",
            "--json",
        ]
    ) == 0
    build_output = json.loads(capsys.readouterr().out)
    assert build_output["events_processed"] == 1
    assert main(["event-ohlc-summary", "--db-path", str(rlm), "--range-source-id", "r1", "--json"]) == 0
    first = capsys.readouterr().out
    assert main(["event-ohlc-summary", "--db-path", str(rlm), "--range-source-id", "r1", "--json"]) == 0
    second = capsys.readouterr().out
    assert first == second
    assert summarize_event_ohlc(rlm, range_source_id="r1")["events_processed"] == 1


def test_cli_failure_path_is_clean(tmp_path: Path) -> None:
    rlm, _source = build_basic_up_case(tmp_path)
    with pytest.raises(SystemExit):
        main(["build-event-ohlc-evidence", "--db-path", str(rlm), "--source-db", str(tmp_path / "missing.db")])
