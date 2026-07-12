from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "python"))

from range_library_memory.cli import main
from range_library_memory.schema import init_schema
from range_library_memory.weekly_phase_sequence import build_weekly_phase_sequences


def fixture(tmp_path: Path, *, status: str = "ACTIVE", high_time: str | None = "2026-01-02T00:00:00Z",
            low_time: str | None = "2026-01-03T00:00:00Z", active: str | None = "2026-01-01T00:00:00Z") -> tuple[Path, Path]:
    memory, source = tmp_path / "memory.sqlite3", tmp_path / "source.sqlite3"
    init_schema(memory)
    payload = {"range_id":"w1","case_ref":"case","symbol":"XAUUSD","structure_layer":"WEEKLY","source_timeframe":"W1",
               "status":status,"active_from_time":active,"range_high_price":110,"range_low_price":90,
               "range_high_time":high_time,"range_low_time":low_time}
    with sqlite3.connect(memory) as con:
        con.execute("INSERT INTO import_runs(id,run_uuid,source_path,source_kind,started_at_utc,status) VALUES(1,'r','x','x','2026-01-01T00:00:00Z','completed')")
        con.execute("""INSERT INTO raw_ranges(import_run_id,source_record_id,symbol,timeframe,range_type,start_time_utc,high,low,raw_payload_json,payload_sha256,created_at_utc)
            VALUES(1,'w1','XAUUSD','W1','WEEKLY','2026-01-01T00:00:00Z',110,90,?,'sha','2026-01-01T00:00:00Z')""", (json.dumps(payload),))
    with sqlite3.connect(source) as con:
        con.execute("CREATE TABLE candles(symbol TEXT,timeframe TEXT,time TEXT,open REAL,high REAL,low REAL,close REAL,volume REAL,source TEXT)")
        con.execute("CREATE TABLE map_ranges(id INTEGER PRIMARY KEY)")
        for day in (5, 12, 19, 26):
            con.execute("INSERT INTO candles VALUES('XAUUSD','W1',?,100,111,89,100,1,'fixture')", (f"2026.01.{day:02d} 00:00",))
    return memory, source


def add_reclaim(memory: Path, *, state: str, break_time: str = "2026-01-05T00:00:00Z", reclaim_time: str | None = None) -> None:
    with sqlite3.connect(memory) as con:
        con.execute("""INSERT INTO weekly_break_reclaim_lifecycles(
          built_at_utc,import_run_id,case_ref,symbol,source_timeframe,weekly_range_source_id,raw_range_id,range_high,range_low,range_height,
          break_direction,break_level,break_time,break_kind,effective_reclaim_time,effective_reclaim_kind,current_state,observation_status,
          resolution_status,resolution_confidence,reason_codes_json,as_of_time,created_at_utc,updated_at_utc)
          VALUES('2026-01-26T00:00:00Z',1,'case','XAUUSD','W1','w1',1,110,90,20,'UP',110,?,'WICK',?,? ,?,?,'RESOLVED','high','[]','2026-01-26T00:00:00Z','2026-01-26T00:00:00Z','2026-01-26T00:00:00Z')""",
          (break_time, reclaim_time, "WICK" if reclaim_time else None, state, "OBSERVED" if reclaim_time else "CENSORED"))


def getrow(memory: Path) -> sqlite3.Row:
    with sqlite3.connect(memory) as con:
        con.row_factory = sqlite3.Row
        row = con.execute("SELECT * FROM weekly_phase_sequences WHERE weekly_range_source_id='w1'").fetchone()
    assert row
    return row


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_t0_later_anchor_and_active_time(tmp_path: Path) -> None:
    memory, source = fixture(tmp_path, active="2026-01-04T00:00:00Z")
    build_weekly_phase_sequences(memory, source_db=source)
    row = getrow(memory)
    assert row["t0_formation_time"] == "2026-01-04T00:00:00Z"
    assert row["current_phase_state"] == "ACTIVE_PRE_BREAK"
    assert row["current_phase_age_days"] == 22


def test_missing_each_anchor_is_incomplete(tmp_path: Path) -> None:
    for key in ("high_time", "low_time"):
        folder = tmp_path / key; folder.mkdir()
        memory, source = fixture(folder, **{key: None})
        build_weekly_phase_sequences(memory, source_db=source)
        assert getrow(memory)["current_phase_state"] == "INCOMPLETE_RANGE"
        assert "MISSING_RANGE_ANCHOR_TIME" in getrow(memory)["reason_codes_json"]


def test_raw_broken_without_factual_break_needs_review(tmp_path: Path) -> None:
    memory, source = fixture(tmp_path, status="BROKEN")
    build_weekly_phase_sequences(memory, source_db=source)
    assert getrow(memory)["current_phase_state"] == "NEEDS_REVIEW"
    assert "RAW_BROKEN_WITHOUT_FACTUAL_BREAK" in getrow(memory)["reason_codes_json"]


def test_pending_and_reclaimed_durations(tmp_path: Path) -> None:
    memory, source = fixture(tmp_path, status="BROKEN"); add_reclaim(memory, state="ABANDONED_PENDING_RECLAIM")
    build_weekly_phase_sequences(memory, source_db=source)
    row = getrow(memory); assert row["current_phase_state"] == "BREAK_PENDING_RECLAIM" and row["current_phase_age_days"] == 21
    with sqlite3.connect(memory) as con: con.execute("DELETE FROM weekly_break_reclaim_lifecycles")
    add_reclaim(memory, state="RECLAIMED", reclaim_time="2026-01-12T00:00:00Z")
    build_weekly_phase_sequences(memory, source_db=source)
    row = getrow(memory)
    assert (row["current_phase_state"], row["formation_to_break_days"], row["break_to_reclaim_days"], row["current_phase_age_days"]) == ("RECLAIMED",2,7,14)


def test_same_candle_and_chronology_failures(tmp_path: Path) -> None:
    memory, source = fixture(tmp_path, status="BROKEN"); add_reclaim(memory, state="RECLAIMED", reclaim_time="2026-01-05T00:00:00Z")
    build_weekly_phase_sequences(memory, source_db=source)
    assert getrow(memory)["same_candle_break_reclaim"] == 1 and getrow(memory)["break_to_reclaim_days"] == 0
    with sqlite3.connect(memory) as con:
        con.execute("UPDATE weekly_break_reclaim_lifecycles SET break_time='2026-01-01T00:00:00Z',effective_reclaim_time='2025-12-31T00:00:00Z'")
    build_weekly_phase_sequences(memory, source_db=source)
    reasons = getrow(memory)["reason_codes_json"]
    assert getrow(memory)["current_phase_state"] == "NEEDS_REVIEW"
    assert "BREAK_BEFORE_RANGE_FORMATION" in reasons and "RECLAIM_BEFORE_BREAK" in reasons


def test_as_of_cap_respect_and_milestone_after_cutoff(tmp_path: Path) -> None:
    memory, source = fixture(tmp_path)
    build_weekly_phase_sequences(memory, source_db=source, as_of="2026-12-01T00:00:00Z")
    row=getrow(memory); assert row["as_of_time"] == "2026-01-26T00:00:00Z" and "AS_OF_CAPPED" in row["reason_codes_json"]
    build_weekly_phase_sequences(memory, source_db=source, as_of="2026-01-12T00:00:00Z")
    assert getrow(memory)["as_of_time"] == "2026-01-12T00:00:00Z"
    with sqlite3.connect(memory) as con: con.execute("UPDATE raw_ranges SET raw_payload_json=json_set(raw_payload_json,'$.range_low_time','2026-01-19T00:00:00Z')")
    build_weekly_phase_sequences(memory, source_db=source, as_of="2026-01-12T00:00:00Z")
    assert "MILESTONE_AFTER_AS_OF" in getrow(memory)["reason_codes_json"]


def test_idempotence_scope_immutability_and_missing_candles(tmp_path: Path) -> None:
    memory, source = fixture(tmp_path)
    before_raw = sqlite3.connect(memory).execute("SELECT raw_payload_json FROM raw_ranges").fetchall(); source_hash=digest(source)
    build_weekly_phase_sequences(memory, source_db=source); build_weekly_phase_sequences(memory, source_db=source)
    with sqlite3.connect(memory) as con:
        assert con.execute("SELECT count(*) FROM weekly_phase_sequences").fetchone()[0] == 1
        con.execute("INSERT INTO weekly_phase_sequences SELECT id+100,built_at_utc,import_run_id,'other','EURUSD',source_timeframe,'other',raw_range_id,raw_status,range_high,range_low,t0_formation_time,t1_break_time,t1_break_direction,t1_break_level,t1_break_kind,t2_reclaim_time,t2_reclaim_kind,same_candle_break_reclaim,formation_to_break_days,break_to_reclaim_days,current_phase_state,current_phase_start_time,current_phase_age_days,observation_status,resolution_status,resolution_confidence,supporting_break_reclaim_id,reason_codes_json,as_of_time,created_at_utc,updated_at_utc FROM weekly_phase_sequences WHERE weekly_range_source_id='w1'")
        other = con.execute("SELECT * FROM weekly_phase_sequences WHERE weekly_range_source_id='other'").fetchone()
    build_weekly_phase_sequences(memory, source_db=source, case_ref="case", symbol="XAUUSD", weekly_source_id="w1")
    with sqlite3.connect(memory) as con:
        assert con.execute("SELECT * FROM weekly_phase_sequences WHERE weekly_range_source_id='other'").fetchone() == other
        assert con.execute("SELECT raw_payload_json FROM raw_ranges").fetchall() == before_raw
    assert digest(source) == source_hash
    with sqlite3.connect(source) as con: con.execute("DELETE FROM candles")
    build_weekly_phase_sequences(memory, source_db=source, weekly_source_id="w1")
    assert getrow(memory)["current_phase_state"] == "MISSING_CANDLES"


def test_cli_json_is_deterministic(tmp_path: Path, capsys) -> None:
    memory, source = fixture(tmp_path)
    args=["build-weekly-phase-sequences","--db-path",str(memory),"--source-db",str(source),"--weekly-source-id","w1","--json"]
    assert main(args)==0; first=capsys.readouterr().out
    assert main(args)==0; second=capsys.readouterr().out
    a,b=json.loads(first),json.loads(second)
    assert a==b
    assert main(["weekly-phase-sequence-summary","--db-path",str(memory),"--state","ACTIVE_PRE_BREAK","--json"])==0
    assert json.loads(capsys.readouterr().out)["total"] == 1
