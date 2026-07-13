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
    status: str = "ACTIVE",
    inactive_from: str | None = None,
    created_at: str = "2026-07-01T00:00:00Z",
    updated_at: str = "2026-07-01T00:00:00Z",
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
        "status": status,
        "created_at": created_at,
        "updated_at": updated_at,
    }
    if inactive_from is not None:
        payload["inactive_from_time"] = inactive_from
    if parent_range_id is not None:
        payload["parent_range_id"] = parent_range_id
    return payload


def event_payload(event_id: str, event_type: str, event_time: str, price: float, range_id: str) -> dict:
    return {
        "event_id": event_id,
        "event_type": event_type,
        "event_time_utc": event_time,
        "price": price,
        "active_range_id": range_id,
    }


def seed_db(tmp_path: Path, ranges: list[dict], events: list[tuple[dict, int]]) -> Path:
    db = tmp_path / "range-library.sqlite3"
    init_schema(db)
    with sqlite3.connect(db) as connection:
        connection.execute(
            """
            INSERT INTO import_runs (
                run_uuid, source_path, source_kind, started_at_utc, finished_at_utc, status
            ) VALUES ('fixture-run', 'fixture.json', 'fixture',
                      '2026-07-13T00:00:00Z', '2026-07-13T00:01:00Z', 'completed')
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
                    str(payload["range_id"]), payload["symbol"], payload["source_timeframe"],
                    payload["structure_layer"], payload["active_from_time"],
                    payload.get("inactive_from_time"), payload["range_high_price"],
                    payload["range_low_price"], raw_json, sha256(raw_json),
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
                    raw_range_id, str(payload["event_id"]), payload["event_type"],
                    payload["event_time_utc"], payload["price"], raw_json, sha256(raw_json),
                ),
            )
        connection.commit()
    return db


def raw_digest(db: Path) -> tuple[int, int, str]:
    with sqlite3.connect(db) as connection:
        range_rows = connection.execute("SELECT id,raw_payload_json,payload_sha256 FROM raw_ranges ORDER BY id").fetchall()
        event_rows = connection.execute("SELECT id,raw_payload_json,payload_sha256 FROM raw_events ORDER BY id").fetchall()
    return len(range_rows), len(event_rows), sha256(deterministic_json([range_rows, event_rows]))


def find_source_node(root: dict, source_id: str) -> dict | None:
    stack = [*root.get("children", []), *root.get("unlinked_review_children", [])]
    while stack:
        node = stack.pop()
        if any(ref["source_record_id"] == source_id for ref in node.get("source_refs", [])):
            return node
        stack.extend(node.get("children", []))
    return None


def test_exact_cross_case_duplicates_build_one_xauusd_hierarchy(tmp_path: Path) -> None:
    ranges: list[dict] = []
    for case_ref in ("case:old-copy", "case:live"):
        ranges.extend([
            range_payload("500", case_ref, "WEEKLY", "W1", 2500, 2000,
                          "2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z", "2026-01-02T00:00:00Z"),
            range_payload("501", case_ref, "DAILY", "D1", 2400, 2100,
                          "2026-02-01T00:00:00Z", "2026-02-02T00:00:00Z", "2026-02-02T00:00:00Z", parent_range_id="500"),
            range_payload("502", case_ref, "INTRADAY", "H4", 2300, 2200,
                          "2026-02-03T00:00:00Z", "2026-02-04T00:00:00Z", "2026-02-04T00:00:00Z", parent_range_id="501"),
        ])
    events = [
        (event_payload("900", "BOS_UP", "2026-02-05T00:00:00Z", 2401, "501"), 2),
        (event_payload("900", "BOS_UP", "2026-02-05T00:00:00Z", 2401, "501"), 5),
    ]
    db = seed_db(tmp_path, ranges, events)
    before = raw_digest(db)
    result = build_master_map(db, output_path=tmp_path / "map.json", built_at_utc="2026-07-13T00:00:00Z")
    assert raw_digest(db) == before
    assert result["statistics"]["canonical_ranges_before_review_exclusion"] == 3
    assert result["statistics"]["exact_range_duplicates_collapsed"] == 3
    assert result["statistics"]["canonical_events_before_review_exclusion"] == 1
    assert result["statistics"]["exact_event_duplicates_collapsed"] == 1
    assert result["statistics"]["comparison_eligible_ranges"] == 3
    weekly = result["root"]["children"][0]
    daily = weekly["children"][0]
    intraday = daily["children"][0]
    assert [weekly["navigation_status"], daily["navigation_status"], intraday["navigation_status"]] == ["TRUSTED"] * 3
    assert load_master_map_output(db)["structural_content_hash"] == result["structural_content_hash"]


def test_june_2026_duplicate_id_conflict_is_reviewable_and_excluded(tmp_path: Path) -> None:
    ranges = [
        range_payload("419", "case:old-copy", "WEEKLY", "W1", 2100, 2000,
                      "2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z", "2026-01-02T00:00:00Z"),
        range_payload("455", "case:live", "WEEKLY", "W1", 3100, 3000,
                      "2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z", "2026-01-02T00:00:00Z"),
        range_payload("420", "case:old-copy", "DAILY", "D1", 2050, 2020,
                      "2026-06-17T00:00:00Z", "2026-06-11T00:00:00Z", "2026-06-17T00:00:00Z", parent_range_id="419"),
        range_payload("420", "case:live", "DAILY", "D1", 3050, 3020,
                      "2026-06-17T00:00:00Z", "2026-06-11T00:00:00Z", "2026-06-17T00:00:00Z", parent_range_id="455"),
    ]
    db = seed_db(tmp_path, ranges, [])
    result = build_master_map(db, built_at_utc="2026-07-13T00:00:00Z")
    review = next(item for item in result["review_items"] if "DUPLICATED_SOURCE_ID_CONFLICT" in item["reason_codes"])
    assert review["source_record_ids"] == ["420"]
    assert result["statistics"]["comparison_eligible_ranges"] == 2
    assert result["statistics"]["review_visible_ranges_by_layer"]["DAILY"] == 2
    assert all(find_source_node(result["review_root"], "420") is not None for _ in [0])


def test_same_source_id_in_clearly_different_periods_stays_separate(tmp_path: Path) -> None:
    ranges = [
        range_payload("700", "case:old", "WEEKLY", "W1", 2100, 2000,
                      "2024-01-01T00:00:00Z", "2024-01-02T00:00:00Z", "2024-01-02T00:00:00Z"),
        range_payload("700", "case:new", "WEEKLY", "W1", 3100, 3000,
                      "2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z", "2026-01-02T00:00:00Z"),
    ]
    db = seed_db(tmp_path, ranges, [])
    result = build_master_map(db, built_at_utc="2026-07-13T00:00:00Z")
    assert len(result["root"]["children"]) == 2
    assert result["statistics"]["comparison_eligible_ranges"] == 2


def test_valid_intraday_remains_review_visible_but_statistically_excluded_when_daily_is_reviewed(tmp_path: Path) -> None:
    ranges = [
        range_payload("100", "case:a", "WEEKLY", "W1", 3000, 2000,
                      "2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z", "2026-01-02T00:00:00Z"),
        range_payload("100", "case:b", "WEEKLY", "W1", 3000, 2000,
                      "2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z", "2026-01-02T00:00:00Z"),
        range_payload("200", "case:a", "DAILY", "D1", 2800, 2200,
                      "2026-02-01T00:00:00Z", "2026-02-02T00:00:00Z", "2026-02-02T00:00:00Z", parent_range_id="100", status="ACTIVE", updated_at="2026-03-01T00:00:00Z"),
        range_payload("201", "case:b", "DAILY", "D1", 2800, 2200,
                      "2026-02-01T00:00:00Z", "2026-02-02T00:00:00Z", "2026-02-02T00:00:00Z", parent_range_id="100", status="BROKEN", inactive_from="2026-03-10T00:00:00Z", updated_at="2026-03-11T00:00:00Z"),
        range_payload("300", "case:a", "INTRADAY", "H4", 2600, 2300,
                      "2026-02-03T00:00:00Z", "2026-02-04T00:00:00Z", "2026-02-04T00:00:00Z", parent_range_id="200"),
    ]
    db = seed_db(tmp_path, ranges, [])
    result = build_master_map(db, built_at_utc="2026-07-13T00:00:00Z")
    daily = find_source_node(result["review_root"], "200")
    assert daily is not None
    assert {ref["source_record_id"] for ref in daily["source_refs"]} == {"200", "201"}
    intraday = find_source_node(result["review_root"], "300")
    assert intraday is not None
    assert intraday["navigation_status"] == "REVIEW"
    assert intraday["statistics_status"] == "EXCLUDED"
    assert intraday["ancestor_review_status"] == "ANCESTOR_NEEDS_REVIEW"
    assert intraday["direct_parent_link_status"] == "VALID"
    assert result["statistics"]["comparison_eligible_ranges"] == 1
    assert result["statistics"]["review_visible_ranges_by_layer"] == {"WEEKLY": 0, "DAILY": 1, "INTRADAY": 1}


def test_structural_content_hash_is_stable_across_runtime_metadata(tmp_path: Path) -> None:
    db = seed_db(tmp_path, [range_payload("1", "case:a", "WEEKLY", "W1", 2, 1,
                                                  "2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z", "2026-01-02T00:00:00Z")], [])
    first = build_master_map(db, built_at_utc="2026-07-13T00:00:00Z", build_id="build-a")
    second = build_master_map(db, built_at_utc="2026-07-14T00:00:00Z", build_id="build-b")
    assert first["build_id"] != second["build_id"]
    assert first["built_at_utc"] != second["built_at_utc"]
    assert first["structural_content_hash"] == second["structural_content_hash"]
    assert deterministic_json(first) != deterministic_json(second)


def test_exact_boundary_lifecycle_disagreement_forms_one_reviewed_identity_without_break_evidence(tmp_path: Path) -> None:
    ranges = [
        range_payload("418", "case:old", "WEEKLY", "W1", 5598.08, 4274.6,
                      "2026-01-25T00:00:00Z", "2025-12-28T00:00:00Z", "2025-12-28T00:00:00Z", status="ACTIVE", updated_at="2026-06-20T00:00:00Z"),
        range_payload("455", "case:new", "WEEKLY", "W1", 5598.08, 4274.6,
                      "2026-01-25T00:00:00Z", "2025-12-28T00:00:00Z", "2025-12-28T00:00:00Z", status="BROKEN", inactive_from="2026-03-22T00:00:00Z", updated_at="2026-07-03T00:00:00Z"),
    ]
    db = seed_db(tmp_path, ranges, [])
    result = build_master_map(db, built_at_utc="2026-07-13T00:00:00Z")
    nodes = result["root"]["children"]
    assert len(nodes) == 1
    node = nodes[0]
    assert node["source_count"] == 2
    assert {ref["source_record_id"] for ref in node["source_refs"]} == {"418", "455"}
    assert node["navigation_status"] == "REVIEW"
    assert node["statistics_status"] == "EXCLUDED"
    assert result["statistics"]["comparison_eligible_ranges"] == 0
    evidence = result["lifecycle_evidence_report"][0]
    assert evidence["automatic_reconciliation"] == "NOT_APPLIED"
    assert evidence["chronology_assessment"]["status"] == "CHRONOLOGICAL_TRANSITION_CANDIDATE"
    assert any(
        "EXACT_BOUNDARY_LIFECYCLE_UNRESOLVED" in item["reason_codes"]
        for item in result["review_items"]
    )


def deterministic_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
