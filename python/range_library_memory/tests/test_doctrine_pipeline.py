from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from range_library_memory import doctrine_pipeline as pipeline
from range_library_memory.weekly_chronology_bos import SCHEMA_SQL as SCRIPT1_SCHEMA


def make_db(path: Path, count: int = 6, cases: tuple[str, ...] = ("case:live",)) -> tuple[Path, Path]:
    children = []
    for case_ref in cases:
        children.extend(
            {"node_type": "RANGE", "id": f"{case_ref}-weekly-{index}", "children": []}
            for index in range(count)
        )
    root = {"node_type": "SYMBOL", "children": children}
    output = {
        "symbol": "XAUUSD",
        "structural_content_hash": "structure-1",
        "root": root,
        "trusted_root": root,
        "review_root": {"node_type": "SYMBOL", "children": []},
    }
    with sqlite3.connect(path) as con:
        con.execute("CREATE TABLE master_map_outputs(symbol TEXT PRIMARY KEY, output_json TEXT NOT NULL)")
        con.execute("CREATE TABLE master_map_ranges(canonical_range_id TEXT PRIMARY KEY, canonical_payload_json TEXT NOT NULL)")
        con.execute("INSERT INTO master_map_outputs VALUES ('XAUUSD',?)", (json.dumps(output),))
        con.executescript(SCRIPT1_SCHEMA)
        for case_ref in cases:
            for index in range(count):
                canonical_id = f"{case_ref}-weekly-{index}"
                con.execute(
                    "INSERT INTO master_map_ranges VALUES (?,?)",
                    (canonical_id, json.dumps({"node_type": "RANGE", "id": canonical_id, "children": []})),
                )
                chronology = "RL_TO_RH" if index % 2 == 0 else "RH_TO_RL"
                bos = ("BOS_UP", "BOS_DOWN", "PENDING")[index % 3]
                status = "NEEDS_REVIEW" if index == count - 1 else "COMPLETE"
                con.execute(
                    """INSERT INTO weekly_script1_results(
                      canonical_range_id,processing_version,run_id,source_range_ids_json,source_refs_json,
                      source_structural_hash,case_ref,symbol,structure_layer,source_timeframe,
                      chronology_result,bos_direction,candles_scanned,exact_touch_count,
                      exact_touch_examples_json,processing_status,reason_codes_json,result_hash)
                      VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        canonical_id,
                        "weekly_script1_v1",
                        "legacy-run",
                        "[]",
                        "[]",
                        f"input-{case_ref}-{index}",
                        case_ref,
                        "XAUUSD",
                        "WEEKLY",
                        "W1",
                        chronology,
                        bos,
                        10,
                        0,
                        "[]",
                        status,
                        "[]",
                        f"output-{case_ref}-{index}",
                    ),
                )
    candle = path.with_name("candles.sqlite3")
    candle.touch()
    return path, candle


def insert(db: Path, source: str = "adapter: weekly\n") -> dict:
    return pipeline.insert_script(
        db,
        script_key="weekly_structure",
        display_name="Weekly structure",
        version_label="1",
        source_code=source,
        adapter_key=pipeline.WEEKLY_ADAPTER,
        execution_order=10,
    )


def approve_run(db: Path, state: dict) -> None:
    for sample in state["samples"]:
        pipeline.review_sample(
            db,
            run_id=state["run"]["run_id"],
            canonical_range_id=sample["canonical_range_id"],
            decision="APPROVED",
        )


def test_registry_is_persistent_versioned_and_immutable(tmp_path: Path) -> None:
    db, _ = make_db(tmp_path / "range.sqlite3")
    first = insert(db)
    same = insert(db, "adapter: weekly\r\n")
    changed = insert(db, "adapter: weekly\nsetting: changed\n")
    assert first["created"] is True
    assert same["created"] is False
    assert same["version_id"] == first["version_id"]
    assert changed["version_id"] != first["version_id"]
    assert len(pipeline.show_script(db, "weekly_structure")["versions"]) == 2


def test_pending_run_persists_five_varied_samples_and_final_approval_publishes_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, candle = make_db(tmp_path / "range.sqlite3", 6)
    version = insert(db)
    monkeypatch.setattr("range_library_memory.weekly_chronology_bos.build_weekly_chronology_bos", lambda *a, **k: {})
    state = pipeline.run_version(
        db,
        version_id=version["version_id"],
        case_ref="case:live",
        symbol="XAUUSD",
        source_db=candle,
    )
    assert state["run"]["analysed_count"] == 6
    assert len(state["samples"]) == 5
    for sample in state["samples"][:4]:
        progress = pipeline.review_sample(
            db,
            run_id=state["run"]["run_id"],
            canonical_range_id=sample["canonical_range_id"],
            decision="APPROVED",
        )
        assert progress["publication_status"] == "UNPUBLISHED"
    final = pipeline.review_sample(
        db,
        run_id=state["run"]["run_id"],
        canonical_range_id=state["samples"][4]["canonical_range_id"],
        decision="APPROVED",
    )
    duplicate = pipeline.review_sample(
        db,
        run_id=state["run"]["run_id"],
        canonical_range_id=state["samples"][4]["canonical_range_id"],
        decision="APPROVED",
    )
    assert final["publication_status"] == duplicate["publication_status"] == "PUBLISHED"
    with sqlite3.connect(db) as con:
        assert con.execute("SELECT COUNT(*) FROM doctrine_enrichments WHERE active=1").fetchone()[0] == 6
        document = json.loads(
            con.execute("SELECT output_json FROM master_map_outputs WHERE symbol='XAUUSD'").fetchone()[0]
        )
    assert "weekly_structure" in document["trusted_root"]["children"][0]["analysis_enrichments"]


def test_rejection_blocks_new_version_without_disabling_previous_approved_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, candle = make_db(tmp_path / "range.sqlite3", 2)
    first = insert(db)
    monkeypatch.setattr("range_library_memory.weekly_chronology_bos.build_weekly_chronology_bos", lambda *a, **k: {})
    first_state = pipeline.run_version(
        db, version_id=first["version_id"], case_ref="case:live", symbol="XAUUSD", source_db=candle
    )
    approve_run(db, first_state)
    changed = insert(db, "adapter: weekly\nsetting: changed\n")
    changed_state = pipeline.run_version(
        db, version_id=changed["version_id"], case_ref="case:live", symbol="XAUUSD", source_db=candle
    )
    rejected = pipeline.review_sample(
        db,
        run_id=changed_state["run"]["run_id"],
        canonical_range_id=changed_state["samples"][0]["canonical_range_id"],
        decision="REJECTED",
    )
    script = pipeline.list_scripts(db)[0]
    assert rejected["publication_status"] == "UNPUBLISHED"
    assert script["status"] == "APPROVED"
    assert script["current_approved_version_id"] == first["version_id"]


def test_approved_version_auto_publishes_for_another_case_without_reapproval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, candle = make_db(tmp_path / "range.sqlite3", 2, ("case:a", "case:b"))
    version = insert(db)
    monkeypatch.setattr("range_library_memory.weekly_chronology_bos.build_weekly_chronology_bos", lambda *a, **k: {})
    first = pipeline.run_version(
        db, version_id=version["version_id"], case_ref="case:a", symbol="XAUUSD", source_db=candle
    )
    approve_run(db, first)
    second = pipeline.run_version(
        db, version_id=version["version_id"], case_ref="case:b", symbol="XAUUSD", source_db=candle
    )
    assert second["samples"] == []
    assert second["run"]["approval_status"] == "APPROVED"
    assert second["run"]["publication_status"] == "PUBLISHED"
    with sqlite3.connect(db) as con:
        active = con.execute(
            "SELECT COUNT(*) FROM doctrine_enrichments WHERE version_id=? AND active=1",
            (version["version_id"],),
        ).fetchone()[0]
    assert active == 4


def test_approved_pipeline_is_idempotent_and_retired_script_is_excluded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, candle = make_db(tmp_path / "range.sqlite3", 1)
    version = insert(db)
    monkeypatch.setattr("range_library_memory.weekly_chronology_bos.build_weekly_chronology_bos", lambda *a, **k: {})
    state = pipeline.run_version(
        db, version_id=version["version_id"], case_ref="case:live", symbol="XAUUSD", source_db=candle
    )
    approve_run(db, state)
    summary = pipeline.run_active_pipeline(db, case_ref="case:live", symbol="XAUUSD", source_db=candle)
    assert summary["active_scripts"] == 1
    assert summary["skipped_unchanged"] == 1
    assert summary["processed"] == 0
    pipeline.retire_script(db, "weekly_structure")
    assert pipeline.run_active_pipeline(
        db, case_ref="case:live", symbol="XAUUSD", source_db=candle
    )["active_scripts"] == 0
