from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from range_library_memory.master_map import build_master_map
from range_library_memory.schema import init_schema


def dump(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def test_incomplete_active_snapshots_merge_into_confirmed_broken_range(tmp_path: Path) -> None:
    db = tmp_path / "library.sqlite3"
    init_schema(db)
    cases = ("case:418", "case:431", "case:453", "case:455")
    ids = ("418", "431", "453", "455")
    statuses = ("BROKEN", "ACTIVE", "ACTIVE", "BROKEN")
    with sqlite3.connect(db) as con:
        con.execute("""
          INSERT INTO import_runs(run_uuid,source_path,source_kind,started_at_utc,status)
          VALUES('run','fixture.json','fixture','2026-07-13T00:00:00Z','completed')
        """)
        for source_id, case_ref, status in zip(ids, cases, statuses):
            payload = {
                "range_id": source_id, "case_ref": case_ref, "symbol": "XAUUSD",
                "structure_layer": "WEEKLY", "source_timeframe": "W1",
                "range_high_price": 5598.08, "range_low_price": 4274.60,
                "range_high_time": "2026-01-25T00:00:00Z",
                "range_low_time": "2025-12-28T00:00:00Z",
                "active_from_time": "2026-01-25T00:00:00Z", "status": status,
            }
            if status == "BROKEN":
                payload.update({
                    "inactive_from_time": "2026-03-22T00:00:00Z",
                    "direction_of_break": "DOWN",
                })
            raw = dump(payload)
            con.execute("""
              INSERT INTO raw_ranges(
                import_run_id,source_record_id,symbol,timeframe,range_type,start_time_utc,
                end_time_utc,high,low,raw_payload_json,payload_sha256,created_at_utc
              ) VALUES(1,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                source_id, "XAUUSD", "W1", "WEEKLY", "2026-01-25T00:00:00Z",
                payload.get("inactive_from_time"), 5598.08, 4274.60, raw, digest(raw),
                "2026-07-13T00:00:00Z",
            ))
        for raw_range_id, event_id, case_ref, source_id in (
            (1, "1527", "case:418", "418"), (4, "1811", "case:455", "455")
        ):
            payload = {
                "event_id": event_id, "case_ref": case_ref,
                "event_type": "BOS_DOWN", "event_time_utc": "2026-03-22T00:00:00Z",
                "price": 4098.74, "active_range_id": source_id,
                "source_timeframe": "W1",
            }
            raw = dump(payload)
            con.execute("""
              INSERT INTO raw_events(
                import_run_id,raw_range_id,source_record_id,event_type,event_time_utc,
                price,raw_payload_json,payload_sha256,created_at_utc
              ) VALUES(1,?,?,?,?,?,?,?,?)
            """, (
                raw_range_id, event_id, "BOS_DOWN", "2026-03-22T00:00:00Z",
                4098.74, raw, digest(raw), "2026-07-13T00:00:00Z",
            ))
        con.commit()

    source_db = tmp_path / "market.sqlite3"
    with sqlite3.connect(source_db) as con:
        con.execute("CREATE TABLE candles(symbol TEXT,timeframe TEXT,time TEXT,high REAL,low REAL)")
        con.execute(
            "INSERT INTO candles VALUES('XAUUSD','D1','2026.03.23 00:00',4300,4098.74)"
        )
        con.commit()

    result = build_master_map(
        db, source_db=source_db, built_at_utc="2026-07-13T00:00:00Z",
        build_id="lifecycle-test",
    )
    weekly = result["root"]["children"][0]
    assert len(result["root"]["children"]) == 1
    assert weekly["source_count"] == 4
    assert weekly["status"] == "BROKEN"
    assert weekly["inactive_from_time"] == "2026-03-23T00:00:00Z"
    assert weekly["direction_of_break"] == "DOWN"
    assert weekly["lifecycle_history"] == ["ACTIVE", "BROKEN"]
    assert weekly["navigation_status"] == "TRUSTED"
    assert weekly["statistics_status"] == "ELIGIBLE"
    states = {
        row["source_record_id"]: row["snapshot_status"]
        for row in weekly["snapshot_lifecycle"]
    }
    assert states == {"418": "BROKEN", "431": "PENDING", "453": "PENDING", "455": "BROKEN"}
    assert not any(
        item["entity_kind"] == "RANGE" and weekly["id"] in item["canonical_ids"]
        for item in result["review_items"]
    )
    report = next(
        row for row in result["lifecycle_evidence_report"]
        if weekly["id"] in row["canonical_ids"]
    )
    assert report["automatic_reconciliation"] == "APPLIED_EXACT_BOUNDARY_LIFECYCLE_RULE"
