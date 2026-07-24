from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from range_library_memory.statistics_reports import build_statistics_report

CASE = "case:stats"
SYMBOL = "XAUUSD"


def enrichment(key: str, payload: dict) -> tuple[str, dict]:
    return key, {
        "version_id": f"version-{key}",
        "version_label": "1",
        "adapter_key": "test",
        "output_hash": f"hash-{key}",
        "payload": payload,
    }


def node(
    identity: str,
    layer: str,
    high_time: str,
    low_time: str,
    *,
    children=None,
    enrichments=None,
):
    return {
        "id": identity,
        "node_type": "RANGE",
        "structure_layer": layer,
        "source_timeframe": "W1" if layer == "WEEKLY" else "D1",
        "range_high": 3000,
        "range_low": 2000,
        "range_high_time": high_time,
        "range_low_time": low_time,
        "active_from_time": max(high_time, low_time),
        "inactive_from_time": None,
        "status": "ACTIVE",
        "source_refs": [{"case_ref": CASE, "source_record_id": identity}],
        "navigation_status": "TRUSTED",
        "statistics_status": "ELIGIBLE",
        "analysis_enrichments": dict(enrichments or []),
        "children": children or [],
    }


def create_db(path: Path) -> None:
    weekly_old = node(
        "weekly-old",
        "WEEKLY",
        "2023-02-05T00:00:00Z",
        "2023-01-29T00:00:00Z",
        enrichments=[
            enrichment(
                "weekly_structure",
                {"bos_direction": "BOS_UP", "weeks_to_bos": 3},
            ),
            enrichment(
                "weekly_reclaim",
                {"reclaim_status": "RECLAIMED", "weeks_to_reclaim": 2},
            ),
            enrichment(
                "weekly_profile_classification",
                {"profile_classification": "S&R"},
            ),
        ],
    )
    daily_before_cutoff = node(
        "daily-before",
        "DAILY",
        "2024-10-20T00:00:00Z",
        "2024-10-13T00:00:00Z",
        enrichments=[
            enrichment(
                "daily_structure",
                {"bos_direction": "BOS_DOWN", "days_to_bos": 2},
            )
        ],
    )
    daily_one = node(
        "daily-one",
        "DAILY",
        "2024-11-03T00:00:00Z",
        "2024-10-27T00:00:00Z",
        enrichments=[
            enrichment(
                "daily_structure",
                {"bos_direction": "BOS_UP", "days_to_bos": 2},
            ),
            enrichment(
                "daily_reclaim",
                {"reclaim_status": "RECLAIMED", "days_to_reclaim": 1},
            ),
            enrichment(
                "daily_profile_classification",
                {"profile_classification": "S&R"},
            ),
        ],
    )
    daily_two = node(
        "daily-two",
        "DAILY",
        "2024-11-10T00:00:00Z",
        "2024-11-03T00:00:00Z",
        enrichments=[
            enrichment(
                "daily_structure",
                {"bos_direction": "BOS_DOWN", "days_to_bos": 3},
            ),
            enrichment("daily_reclaim", {"reclaim_status": "PENDING"}),
            enrichment(
                "daily_profile_classification",
                {"profile_classification": "S&D"},
            ),
        ],
    )
    weekly_combined = node(
        "weekly-combined",
        "WEEKLY",
        "2024-11-03T00:00:00Z",
        "2024-10-27T00:00:00Z",
        children=[daily_before_cutoff, daily_one, daily_two],
        enrichments=[
            enrichment(
                "weekly_structure",
                {"bos_direction": "BOS_UP", "weeks_to_bos": 1},
            ),
            enrichment(
                "weekly_reclaim",
                {"reclaim_status": "RECLAIMED", "weeks_to_reclaim": 1},
            ),
            enrichment(
                "weekly_profile_classification",
                {"profile_classification": "S&R>FP"},
            ),
        ],
    )
    output = {
        "schema_version": "xauusd_master_map_v0.1",
        "symbol": SYMBOL,
        "structural_content_hash": "structure-1",
        "trusted_root": {
            "node_type": "SYMBOL",
            "children": [weekly_old, weekly_combined],
        },
        "review_root": {"node_type": "SYMBOL", "children": []},
    }
    with sqlite3.connect(path) as con:
        con.execute(
            "CREATE TABLE master_map_outputs(symbol TEXT PRIMARY KEY,output_json TEXT NOT NULL)"
        )
        con.execute(
            "INSERT INTO master_map_outputs VALUES (?,?)",
            (SYMBOL, json.dumps(output)),
        )
        con.executescript(
            """
            CREATE TABLE doctrine_scripts(
                script_id TEXT PRIMARY KEY,script_key TEXT,display_name TEXT,
                description TEXT,execution_order INTEGER,status TEXT,
                current_approved_version_id TEXT,created_at TEXT,updated_at TEXT);
            CREATE TABLE doctrine_script_versions(
                version_id TEXT PRIMARY KEY,script_id TEXT,version_label TEXT,
                content_hash TEXT,source_code TEXT,adapter_key TEXT,
                input_contract_version TEXT,output_contract_version TEXT,
                created_at TEXT,approved_at TEXT,rejected_at TEXT);
            CREATE TABLE doctrine_range_processing(
                version_id TEXT,canonical_range_id TEXT,case_ref TEXT,symbol TEXT,
                input_record_hash TEXT,output_hash TEXT,processing_status TEXT,
                processed_at TEXT,run_id TEXT);
            CREATE TABLE inherited_doctrine_enrichments(
                target_layer TEXT,target_namespace TEXT,canonical_range_id TEXT,
                symbol TEXT,case_ref TEXT,source_script_key TEXT,
                source_version_id TEXT,source_version_label TEXT,adapter_key TEXT,
                processing_status TEXT,payload_json TEXT,output_hash TEXT,
                active INTEGER,updated_at TEXT);
            """
        )
        weekly_keys = [
            "weekly_structure",
            "weekly_reclaim",
            "weekly_reclaim_depth",
            "weekly_movement_classification",
            "weekly_profile_classification",
            "weekly_extreme_rejection_destination",
        ]
        for order, key in enumerate(weekly_keys, start=1):
            script_id = f"script-{key}"
            version_id = f"version-{key}"
            con.execute(
                "INSERT INTO doctrine_scripts VALUES (?,?,?,?,?,'APPROVED',?,?,?)",
                (
                    script_id,
                    key,
                    key,
                    None,
                    order * 10,
                    version_id,
                    "created",
                    "updated",
                ),
            )
            con.execute(
                "INSERT INTO doctrine_script_versions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    version_id,
                    script_id,
                    "1",
                    "hash",
                    "source",
                    "test",
                    "in",
                    "out",
                    "created",
                    "approved",
                    None,
                ),
            )
            for weekly_id in ("weekly-old", "weekly-combined"):
                status = (
                    "COMPLETE"
                    if key
                    in {
                        "weekly_structure",
                        "weekly_reclaim",
                        "weekly_profile_classification",
                    }
                    else "PENDING"
                )
                con.execute(
                    "INSERT INTO doctrine_range_processing VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        version_id,
                        weekly_id,
                        CASE,
                        SYMBOL,
                        "input",
                        "output",
                        status,
                        "2026-07-24T00:00:00Z",
                        "run",
                    ),
                )
        daily_keys = [
            key.replace("weekly_", "daily_", 1) for key in weekly_keys
        ]
        for daily_id in ("daily-one", "daily-two"):
            for key in daily_keys:
                status = (
                    "COMPLETE"
                    if key in {"daily_structure", "daily_profile_classification"}
                    else "PENDING"
                )
                if daily_id == "daily-two" and key == "daily_structure":
                    status = "NEEDS_REVIEW"
                con.execute(
                    "INSERT INTO inherited_doctrine_enrichments VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        "DAILY",
                        key,
                        daily_id,
                        SYMBOL,
                        CASE,
                        key.replace("daily_", "weekly_", 1),
                        "version",
                        "1",
                        "test",
                        status,
                        "{}",
                        "hash",
                        1,
                        "2026-07-24T00:00:00Z",
                    ),
                )


def test_builds_cutoff_safe_exact_parent_report_and_exports(
    tmp_path: Path,
) -> None:
    db = tmp_path / "analysis.sqlite3"
    create_db(db)
    report = build_statistics_report(db, case_ref=CASE, symbol=SYMBOL)

    assert report["overview"]["weekly"]["range_count"] == 2
    assert report["overview"]["daily"]["range_count"] == 2
    assert {
        row["canonical_range_id"] for row in report["daily_rows"]
    } == {"daily-one", "daily-two"}
    assert report["overview"]["parent_child"]["weekly_parent_count"] == 1
    assert report["overview"]["parent_child"]["daily_child_count"] == 2
    assert report["overview"]["parent_child"]["bos_alignment_counts"] == {
        "BOS_ALIGNED": 1,
        "BOS_COUNTER": 1,
    }
    assert report["parent_rows"][0]["weekly_parent_id"] == "weekly-combined"
    assert report["parent_rows"][0]["daily_child_ids"] == [
        "daily-one",
        "daily-two",
    ]
    assert report["overview"]["daily"]["processing_status_counts"] == {
        "NEEDS_REVIEW": 1,
        "PENDING": 1,
    }
    assert report["dataset"]["parent_join_rule"] == "EXACT_MASTER_MAP_HIERARCHY"
    for output in report["exports"].values():
        assert Path(output).exists()


def test_snapshot_becomes_stale_when_master_map_changes(tmp_path: Path) -> None:
    from range_library_memory.statistics_reports import (
        apply_persisted_statistics_report_metadata,
    )

    db = tmp_path / "analysis.sqlite3"
    create_db(db)
    build_statistics_report(db, case_ref=CASE, symbol=SYMBOL)
    with sqlite3.connect(db) as con:
        con.row_factory = sqlite3.Row
        master = {"structural_content_hash": "structure-2", "analysis": {}}
        apply_persisted_statistics_report_metadata(
            con,
            master,
            symbol=SYMBOL,
        )
    bucket = master["analysis"]["weekly_daily_statistics_reports"]["by_case"][CASE]
    assert bucket["latest_report"]["stale"] is True
    assert (
        bucket["latest_report"]["current_structural_content_hash"]
        == "structure-2"
    )


def test_reapplies_latest_payload_and_snapshot_history_to_master_map(
    tmp_path: Path,
) -> None:
    from range_library_memory.statistics_reports import (
        apply_persisted_statistics_report_metadata,
    )

    db = tmp_path / "analysis.sqlite3"
    create_db(db)
    report = build_statistics_report(db, case_ref=CASE, symbol=SYMBOL)
    with sqlite3.connect(db) as con:
        con.row_factory = sqlite3.Row
        master = {"structural_content_hash": "structure-1", "analysis": {}}
        summary = apply_persisted_statistics_report_metadata(
            con,
            master,
            symbol=SYMBOL,
        )
    assert summary == {"case_count": 1, "snapshot_count": 1}
    bucket = master["analysis"]["weekly_daily_statistics_reports"]["by_case"][CASE]
    assert bucket["latest_report"]["report_id"] == report["report_id"]
    assert bucket["snapshots"][0]["stale"] is False


def test_unchanged_report_input_reuses_latest_snapshot(tmp_path: Path) -> None:
    db = tmp_path / "analysis.sqlite3"
    create_db(db)
    first = build_statistics_report(db, case_ref=CASE, symbol=SYMBOL)
    second = build_statistics_report(db, case_ref=CASE, symbol=SYMBOL)
    assert second["report_id"] == first["report_id"]
    assert second["reused"] is True
    with sqlite3.connect(db) as con:
        count = con.execute(
            "SELECT COUNT(*) FROM statistics_report_snapshots"
        ).fetchone()[0]
    assert count == 1
