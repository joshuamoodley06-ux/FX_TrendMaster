from __future__ import annotations

import hashlib
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
from range_library_memory.weekly_break_reclaim import build_weekly_break_reclaim, summarize_weekly_break_reclaim


def fixture_dbs(tmp_path: Path, *, direction: str = "UP", break_time: str = "2026-01-05T00:00:00Z") -> tuple[Path, Path]:
    memory = tmp_path / "memory.sqlite3"
    source = tmp_path / "market.sqlite3"
    init_schema(memory)
    payload = {
        "range_id": "w1", "case_ref": "case", "symbol": "XAUUSD", "structure_layer": "WEEKLY",
        "source_timeframe": "W1", "status": "BROKEN", "active_from_time": "2026-01-01T00:00:00Z",
        "range_high_price": 110.0, "range_low_price": 90.0,
        "range_high_time": "2026-01-02T00:00:00Z", "range_low_time": "2026-01-02T00:00:00Z",
    }
    with sqlite3.connect(memory) as con:
        con.execute("INSERT INTO import_runs (id,run_uuid,source_path,source_kind,started_at_utc,status) VALUES (1,'r','x','x','2026-01-01T00:00:00Z','completed')")
        con.execute("""INSERT INTO raw_ranges (import_run_id,source_record_id,symbol,timeframe,range_type,start_time_utc,high,low,raw_payload_json,payload_sha256,created_at_utc)
                       VALUES (1,'w1','XAUUSD','W1','WEEKLY','2026-01-01T00:00:00Z',110,90,?,'sha','2026-01-01T00:00:00Z')""", (json.dumps(payload),))
        event_type = "BOS_UP" if direction == "UP" else "BOS_DOWN"
        boundary = 110.0 if direction == "UP" else 90.0
        con.execute("""INSERT INTO event_ohlc_evidence (
            built_at_utc,import_run_id,case_ref,symbol,structure_layer,source_timeframe,range_source_id,event_source_id,
            raw_range_id,event_type,direction,range_formation_time,boundary_type,boundary_price,boundary_anchor_time,
            transition_status,transition_reason_codes_json,evidence_status,reason_codes_json,resolution_status,
            resolution_confidence,effective_break_time,effective_break_kind,as_of_time,created_at_utc,updated_at_utc)
            VALUES ('2026-01-10T00:00:00Z',1,'case','XAUUSD','WEEKLY','W1','w1','e1',1,?,?,?, ?,?,
            '2026-01-02T00:00:00Z','NOT_PRESENT','[]','MATCH','[]','MAPPED_CONFIRMED','high',?,'WICK','2026-01-20T00:00:00Z','2026-01-10T00:00:00Z','2026-01-10T00:00:00Z')""",
            (event_type, direction, "2026-01-02T00:00:00Z", "RANGE_HIGH" if direction == "UP" else "RANGE_LOW", boundary, break_time))
        evidence_id = con.execute("SELECT id FROM event_ohlc_evidence").fetchone()[0]
        con.execute("""INSERT INTO resolved_range_lifecycles (
            built_at_utc,import_run_id,case_ref,symbol,structure_layer,source_timeframe,range_source_id,raw_range_id,
            raw_status,raw_active_from_time,effective_status,effective_active_from_time,effective_inactive_from_time,
            resolution_source,resolution_status,resolution_confidence,supporting_event_source_id,supporting_evidence_id,
            reason_codes_json,as_of_time,created_at_utc,updated_at_utc)
            VALUES ('2026-01-10T00:00:00Z',1,'case','XAUUSD','WEEKLY','W1','w1',1,'BROKEN','2026-01-01T00:00:00Z',
            'BROKEN','2026-01-01T00:00:00Z',?,'MAPPED_EVENT_AND_OHLC','MAPPED_CONFIRMED','high','e1',?,'[]',
            '2026-01-20T00:00:00Z','2026-01-10T00:00:00Z','2026-01-10T00:00:00Z')""", (break_time, evidence_id))
    with sqlite3.connect(source) as con:
        con.execute("CREATE TABLE candles (symbol TEXT,timeframe TEXT,time TEXT,open REAL,high REAL,low REAL,close REAL,volume REAL,source TEXT)")
        con.execute("CREATE TABLE map_ranges (id INTEGER PRIMARY KEY)")
    return memory, source


def candle(source: Path, time: str, *, high: float, low: float, close: float) -> None:
    with sqlite3.connect(source) as con:
        con.execute("INSERT INTO candles VALUES ('XAUUSD','W1',?,100,?,?,?,1,'fixture')", (time, high, low, close))


def row(memory: Path) -> sqlite3.Row:
    with sqlite3.connect(memory) as con:
        con.row_factory = sqlite3.Row
        result = con.execute("SELECT * FROM weekly_break_reclaim_lifecycles").fetchone()
    assert result is not None
    return result


def test_bos_up_later_wick_only_reclaim_and_depth(tmp_path: Path) -> None:
    memory, source = fixture_dbs(tmp_path)
    candle(source, "2026.01.05 00:00", high=112, low=111, close=111)
    candle(source, "2026.01.12 00:00", high=115, low=108, close=112)
    build_weekly_break_reclaim(memory, source_db=source)
    value = row(memory)
    assert (value["current_state"], value["effective_reclaim_kind"]) == ("RECLAIMED", "WICK")
    assert value["reclaim_depth_price"] == 2.0
    assert value["reclaim_depth_percent_of_range"] == 10.0


def test_bos_down_wick_then_later_close_keeps_separate_times(tmp_path: Path) -> None:
    memory, source = fixture_dbs(tmp_path, direction="DOWN")
    candle(source, "2026.01.05 00:00", high=89, low=88, close=89)
    candle(source, "2026.01.12 00:00", high=92, low=87, close=89)
    candle(source, "2026.01.19 00:00", high=94, low=88, close=91)
    build_weekly_break_reclaim(memory, source_db=source)
    value = row(memory)
    assert value["first_wick_reclaim_time"] == "2026-01-12T00:00:00Z"
    assert value["first_close_reclaim_time"] == "2026-01-19T00:00:00Z"
    assert value["effective_reclaim_kind"] == "WICK"


def test_first_later_candle_wick_and_close(tmp_path: Path) -> None:
    memory, source = fixture_dbs(tmp_path)
    candle(source, "2026.01.05 00:00", high=112, low=111, close=111)
    candle(source, "2026.01.12 00:00", high=114, low=108, close=109)
    build_weekly_break_reclaim(memory, source_db=source)
    assert row(memory)["effective_reclaim_kind"] == "WICK_AND_CLOSE"


def test_same_candle_close_is_zero_candles(tmp_path: Path) -> None:
    memory, source = fixture_dbs(tmp_path)
    candle(source, "2026.01.05 00:00", high=112, low=108, close=109)
    build_weekly_break_reclaim(memory, source_db=source)
    value = row(memory)
    assert value["same_candle_close_reclaim"] == 1
    assert value["effective_reclaim_kind"] == "WICK_AND_CLOSE"
    assert value["first_wick_reclaim_time"] == "2026-01-05T00:00:00Z"
    assert value["first_close_reclaim_time"] == "2026-01-05T00:00:00Z"
    assert value["same_candle_wick_order_status"] == "PROVEN_BY_CLOSE"
    assert value["candles_to_effective_reclaim"] == 0


def test_same_candle_wick_only_is_unknown_then_later_wick(tmp_path: Path) -> None:
    memory, source = fixture_dbs(tmp_path)
    candle(source, "2026.01.05 00:00", high=112, low=108, close=111)
    candle(source, "2026.01.12 00:00", high=113, low=109, close=112)
    build_weekly_break_reclaim(memory, source_db=source)
    value = row(memory)
    assert value["first_wick_reclaim_time"] == "2026-01-12T00:00:00Z"
    assert "SAME_CANDLE_WICK_ORDER_UNKNOWN" in value["reason_codes_json"]


def test_pending_is_censored_and_respects_as_of(tmp_path: Path) -> None:
    memory, source = fixture_dbs(tmp_path)
    candle(source, "2026.01.05 00:00", high=112, low=111, close=111)
    candle(source, "2026.01.12 00:00", high=114, low=112, close=113)
    candle(source, "2026.01.19 00:00", high=115, low=108, close=109)
    build_weekly_break_reclaim(memory, source_db=source, as_of="2026-01-12T00:00:00Z")
    value = row(memory)
    assert (value["current_state"], value["observation_status"]) == ("ABANDONED_PENDING_RECLAIM", "CENSORED")
    assert value["effective_reclaim_time"] is None


def test_missing_candles_and_missing_break_evidence(tmp_path: Path) -> None:
    memory, source = fixture_dbs(tmp_path)
    build_weekly_break_reclaim(memory, source_db=source, as_of="2026-01-12T00:00:00Z")
    assert row(memory)["current_state"] == "MISSING_CANDLES"
    with sqlite3.connect(memory) as con:
        con.execute("DELETE FROM event_ohlc_evidence"); con.execute("DELETE FROM resolved_range_lifecycles")
    build_weekly_break_reclaim(memory, source_db=source, as_of="2026-01-12T00:00:00Z")
    assert row(memory)["current_state"] == "MISSING_BREAK_EVIDENCE"


def test_invalid_range_height_needs_review(tmp_path: Path) -> None:
    memory, source = fixture_dbs(tmp_path)
    with sqlite3.connect(memory) as con:
        payload = json.loads(con.execute("SELECT raw_payload_json FROM raw_ranges").fetchone()[0])
        payload["range_low_price"] = 110.0
        con.execute("UPDATE raw_ranges SET low=110, raw_payload_json=?", (json.dumps(payload),))
    candle(source, "2026.01.05 00:00", high=112, low=111, close=111)
    build_weekly_break_reclaim(memory, source_db=source)
    assert row(memory)["current_state"] == "NEEDS_REVIEW"


def test_scoped_rebuild_preserves_unrelated_row(tmp_path: Path) -> None:
    memory, source = fixture_dbs(tmp_path)
    candle(source, "2026.01.05 00:00", high=112, low=111, close=111)
    build_weekly_break_reclaim(memory, source_db=source)
    with sqlite3.connect(memory) as con:
        original = dict(zip([d[0] for d in con.execute("SELECT * FROM weekly_break_reclaim_lifecycles").description], con.execute("SELECT * FROM weekly_break_reclaim_lifecycles").fetchone()))
        con.execute("UPDATE weekly_break_reclaim_lifecycles SET weekly_range_source_id='other', case_ref='other' WHERE weekly_range_source_id='w1'")
    build_weekly_break_reclaim(memory, source_db=source, weekly_source_id="w1")
    with sqlite3.connect(memory) as con:
        assert con.execute("SELECT COUNT(*) FROM weekly_break_reclaim_lifecycles WHERE weekly_range_source_id='other'").fetchone()[0] == 1


def test_idempotent_deterministic_cli_and_data_safety(tmp_path: Path, capsys) -> None:
    memory, source = fixture_dbs(tmp_path)
    candle(source, "2026.01.05 00:00", high=112, low=111, close=111)
    raw_hash = hashlib.sha256(memory.read_bytes()).hexdigest()
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    assert main(["build-weekly-break-reclaim", "--db-path", str(memory), "--source-db", str(source), "--json"]) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["rows_built"] == 1
    assert main(["weekly-break-reclaim-summary", "--db-path", str(memory), "--json"]) == 0
    summary1 = capsys.readouterr().out
    assert main(["weekly-break-reclaim-summary", "--db-path", str(memory), "--json"]) == 0
    assert summary1 == capsys.readouterr().out
    assert summarize_weekly_break_reclaim(memory)["total"] == 1
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
    with sqlite3.connect(memory) as con:
        assert con.execute("SELECT COUNT(*) FROM raw_ranges").fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM event_ohlc_evidence").fetchone()[0] == 1
