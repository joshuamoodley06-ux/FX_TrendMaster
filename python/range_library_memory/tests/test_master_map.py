from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from range_library_memory.master_map import build_master_map, load_master_map_output
from range_library_memory.schema import init_schema


def range_payload(
    range_id: str,
    case_ref: str,
    layer: str,
    timeframe: str,
    high: float,
    low: float,
    high_time: str,
    low_time: str,
    active_from: str,
    *,
    parent_range_id: str | None = None,
) -> dict:
    payload = {
        "range_id": range_id,
        "case_ref": case_ref,
        "symbol": "XAUUSD",
        "structure_layer": layer,
        "source_timeframe": timeframe,
        "range_high_price": high,
        "range_low_price": low,
        "range_high_time": high_time,
        "range_low_time": low_time,
        "active_from_time": active_from,
        "status": "ACTIVE",
    }
    if parent_range_id is not None:
        payload["parent_range_id"] = parent_range_id
    return payload


def event_payload(
    event_id: str,
    event_type: str,
    event_time: str,
    price: float,
    range_id: str,
) -> dict:
    # Deliberately omit case_ref. Master Map must recover case identity from the
    # linked raw range before resolving identical source IDs across cases.
    return {
        "event_id": event_id,
        "event_type": event_type,
        "event_time_utc": event_time,
        "price": price,
        "active_range_id": range_id,
    }


def seed_db(
    tmp_path: Path,
    ranges: list[dict],
    events: list[tuple[dict, int]],
) -> Path:
    db = tmp_path / "range-library.sqlite3"
    init_schema(db)
    with sqlite3.connect(db) as connection:
        connection.execute(
            """
            INSERT INTO import_runs (
                run_uuid, source_path, source_kind, started_at_utc, status
            ) VALUES ('fixture-run', 'fixture.json', 'fixture', '2026-07-13T00:00:00Z', 'completed')
            """
        )
        for payload in ranges:
            raw_json = deterministic_json(payload)
            connection.execute(
                """
                INSERT INTO raw_ranges (
                    import_run_id, source_record_id, symbol, timeframe, range_type,
                    start_time_utc, end_time_utc, high, low, raw_payload_json,
                    payload_sha256, created_at_utc
                ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '2026-07-13T00:00:00Z')
                """,
                (
                    str(payload["range_id"]),
                    payload["symbol"],
                    payload["source_timeframe"],
                    payload["structure_layer"],
                    payload["active_from_time"],
                    payload.get("inactive_from_time"),
                    payload["range_high_price"],
                    payload["range_low_price"],
                    raw_json,
                    sha256(raw_json),
                ),
            )
        for payload, raw_range_id in events:
            raw_json = deterministic_json(payload)
            connection.execute(
                """
                INSERT INTO raw_events (
                    import_run_id, raw_range_id, source_record_id, event_type,
                    event_time_utc, price, raw_payload_json, payload_sha256,
                    created_at_utc
                ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, '2026-07-13T00:00:00Z')
                """,
                (
                    raw_range_id,
                    str(payload["event_id"]),
                    payload["event_type"],
                    payload["event_time_utc"],
                    payload["price"],
                    raw_json,
                    sha256(raw_json),
                ),
            )
        connection.commit()
    return db


def raw_digest(db: Path) -> tuple[int, int, str]:
    with sqlite3.connect(db) as connection:
        range_rows = connection.execute(
            "SELECT id, raw_payload_json, payload_sha256 FROM raw_ranges ORDER BY id"
        ).fetchall()
        event_rows = connection.execute(
            "SELECT id, raw_payload_json, payload_sha256 FROM raw_events ORDER BY id"
        ).fetchall()
    return (
        len(range_rows),
        len(event_rows),
        sha256(deterministic_json([range_rows, event_rows])),
    )


def test_exact_cross_case_duplicates_build_one_xauusd_hierarchy(tmp_path: Path) -> None:
    ranges: list[dict] = []
    for case_ref in ("case:old-copy", "case:live"):
        ranges.extend(
            [
                range_payload(
                    "500", case_ref, "WEEKLY", "W1", 2500.0, 2000.0,
                    "2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z",
                    "2026-01-02T00:00:00Z",
                ),
                range_payload(
                    "501", case_ref, "DAILY", "D1", 2400.0, 2100.0,
                    "2026-02-01T00:00:00Z", "2026-02-02T00:00:00Z",
                    "2026-02-02T00:00:00Z", parent_range_id="500",
                ),
                range_payload(
                    "502", case_ref, "INTRADAY", "H4", 2300.0, 2200.0,
                    "2026-02-03T00:00:00Z", "2026-02-04T00:00:00Z",
                    "2026-02-04T00:00:00Z", parent_range_id="501",
                ),
            ]
        )
    events = [
        (event_payload("900", "BOS_UP", "2026-02-05T00:00:00Z", 2401.0, "501"), 2),
        (event_payload("900", "BOS_UP", "2026-02-05T00:00:00Z", 2401.0, "501"), 5),
    ]
    db = seed_db(tmp_path, ranges, events)
    before = raw_digest(db)
    output_path = tmp_path / "xauusd-master-map.json"

    result = build_master_map(
        db,
        output_path=output_path,
        built_at_utc="2026-07-13T00:00:00Z",
    )

    assert raw_digest(db) == before
    assert result["symbol"] == "XAUUSD"
    assert result["statistics"]["raw_range_sources"] == 6
    assert result["statistics"]["canonical_ranges_before_review_exclusion"] == 3
    assert result["statistics"]["exact_range_duplicates_collapsed"] == 3
    assert result["statistics"]["canonical_events_before_review_exclusion"] == 1
    assert result["statistics"]["exact_event_duplicates_collapsed"] == 1
    assert result["statistics"]["comparison_eligible_ranges"] == 3
    assert result["statistics"]["comparison_eligible_events"] == 1
    assert result["review_items"] == []

    weekly = result["root"]["children"][0]
    daily = weekly["children"][0]
    intraday = daily["children"][0]
    assert [weekly["structure_layer"], daily["structure_layer"], intraday["structure_layer"]] == [
        "WEEKLY", "DAILY", "INTRADAY"
    ]
    assert weekly["source_count"] == daily["source_count"] == intraday["source_count"] == 2
    assert daily["events"][0]["source_count"] == 2
    assert {ref["case_ref"] for ref in daily["source_refs"]} == {"case:old-copy", "case:live"}
    assert output_path.exists()
    assert load_master_map_output(db)["root"] == result["root"]


def test_june_2026_duplicate_id_conflict_is_reviewable_and_excluded(tmp_path: Path) -> None:
    ranges = [
        range_payload(
            "419", "case:old-copy", "WEEKLY", "W1", 2100.0, 2000.0,
            "2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z", "2026-01-02T00:00:00Z",
        ),
        range_payload(
            "455", "case:live", "WEEKLY", "W1", 3100.0, 3000.0,
            "2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z", "2026-01-02T00:00:00Z",
        ),
        range_payload(
            "420", "case:old-copy", "DAILY", "D1", 2050.0, 2020.0,
            "2026-06-17T00:00:00Z", "2026-06-11T00:00:00Z", "2026-06-17T00:00:00Z",
            parent_range_id="419",
        ),
        range_payload(
            "420", "case:live", "DAILY", "D1", 3050.0, 3020.0,
            "2026-06-17T00:00:00Z", "2026-06-11T00:00:00Z", "2026-06-17T00:00:00Z",
            parent_range_id="455",
        ),
    ]
    db = seed_db(tmp_path, ranges, [])

    result = build_master_map(db, built_at_utc="2026-07-13T00:00:00Z")

    duplicate_review = next(
        item for item in result["review_items"]
        if item["item_type"] == "RANGE_DUPLICATE_CONFLICT"
        and "DUPLICATED_SOURCE_ID_CONFLICT" in item["reason_codes"]
    )
    assert duplicate_review["status"] == "NEEDS_REVIEW"
    assert duplicate_review["excluded_from_statistics"] is True
    assert duplicate_review["source_record_ids"] == ["420"]
    assert duplicate_review["case_refs"] == ["case:live", "case:old-copy"]
    assert result["statistics"]["excluded_range_records"] == 2
    assert result["statistics"]["comparison_eligible_ranges"] == 2
    assert all(node["structure_layer"] == "WEEKLY" for node in result["root"]["children"])

    with sqlite3.connect(db) as connection:
        rows = connection.execute(
            """
            SELECT processing_status, excluded_from_statistics, source_count
            FROM master_map_ranges
            WHERE structure_layer='DAILY'
            ORDER BY canonical_range_id
            """
        ).fetchall()
        source_json_rows = connection.execute(
            """
            SELECT source_refs_json
            FROM master_map_ranges
            WHERE structure_layer='DAILY'
            ORDER BY canonical_range_id
            """
        ).fetchall()
    assert rows == [("NEEDS_REVIEW", 1, 1), ("NEEDS_REVIEW", 1, 1)]
    source_rows = sorted(
        (ref["case_ref"], ref["source_record_id"])
        for row in source_json_rows
        for ref in json.loads(row[0])
    )
    assert source_rows == [("case:live", "420"), ("case:old-copy", "420")]


def test_same_source_id_in_clearly_different_periods_stays_separate(tmp_path: Path) -> None:
    ranges = [
        range_payload(
            "700", "case:old", "WEEKLY", "W1", 2100.0, 2000.0,
            "2024-01-01T00:00:00Z", "2024-01-02T00:00:00Z", "2024-01-02T00:00:00Z",
        ),
        range_payload(
            "700", "case:new", "WEEKLY", "W1", 3100.0, 3000.0,
            "2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z", "2026-01-02T00:00:00Z",
        ),
    ]
    db = seed_db(tmp_path, ranges, [])

    result = build_master_map(db, built_at_utc="2026-07-13T00:00:00Z")

    assert len(result["root"]["children"]) == 2
    assert result["statistics"]["comparison_eligible_ranges"] == 2
    assert not any(item["item_type"] == "RANGE_DUPLICATE_CONFLICT" for item in result["review_items"])


def deterministic_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
