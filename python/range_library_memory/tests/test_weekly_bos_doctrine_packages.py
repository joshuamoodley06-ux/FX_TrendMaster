from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from range_library_memory.doctrine_package_contract import inspect_package
from range_library_memory.doctrine_pipeline import (
    insert_script,
    review_sample,
    run_active_pipeline,
    run_version,
)

CASE_REF = "CASE-WEEKLY-PACKAGES"
SYMBOL = "XAUUSD"
PACKAGE_DIR = Path(__file__).resolve().parents[1] / "doctrine_packages"


def _source(name: str) -> str:
    return (PACKAGE_DIR / name).read_text(encoding="utf-8")


def _master_map() -> dict:
    rows = []
    for index in range(6):
        rows.append({
            "id": f"weekly-{index}",
            "node_type": "RANGE",
            "structure_layer": "WEEKLY",
            "symbol": SYMBOL,
            "range_high": 100 + index,
            "range_low": 90 - index,
            "range_low_time": "2026-01-01T00:00:00Z",
            "range_high_time": "2026-01-05T00:00:00Z",
            "source_refs": [{"case_ref": CASE_REF, "source_record_id": f"weekly-{index}"}],
            "analysis_enrichments": {},
            "children": [],
        })
    return {
        "symbol": SYMBOL,
        "structural_content_hash": "weekly-package-structure-v1",
        "trusted_root": {"id": "trusted", "node_type": "ROOT", "children": rows},
        "review_root": {"id": "review", "node_type": "ROOT", "children": []},
    }


def _analysis_db(path: Path) -> None:
    with sqlite3.connect(path) as con:
        con.execute("CREATE TABLE master_map_outputs(symbol TEXT PRIMARY KEY, output_json TEXT NOT NULL)")
        con.execute(
            "INSERT INTO master_map_outputs(symbol,output_json) VALUES (?,?)",
            (SYMBOL, json.dumps(_master_map(), sort_keys=True)),
        )


def _candle_db(path: Path) -> None:
    with sqlite3.connect(path) as con:
        con.execute(
            """CREATE TABLE candles(
                 symbol TEXT, timeframe TEXT, time TEXT, open REAL, high REAL,
                 low REAL, close REAL, volume REAL, source TEXT)"""
        )
        rows = [
            (SYMBOL, "W1", "2026-01-05T00:00:00Z", 95, 100, 90, 96, 1, "test"),
            (SYMBOL, "W1", "2026-01-12T00:00:00Z", 96, 120, 95, 118, 1, "test"),
            (SYMBOL, "W1", "2026-01-19T00:00:00Z", 118, 119, 70, 75, 1, "test"),
        ]
        con.executemany("INSERT INTO candles VALUES (?,?,?,?,?,?,?,?,?)", rows)


def _insert(db: Path, filename: str, version: str) -> dict:
    return insert_script(
        db,
        script_key="weekly_structure",
        display_name="Weekly BOS",
        version_label=version,
        source_code=_source(filename),
        adapter_key="weekly_chronology_bos_v2",
        execution_order=10,
        description="Ordinary uploadable Weekly doctrine package",
    )


def _approve_all(db: Path, state: dict) -> None:
    assert len(state["samples"]) == 5
    for sample in state["samples"]:
        review_sample(
            db,
            run_id=state["run"]["run_id"],
            canonical_range_id=sample["canonical_range_id"],
            decision="APPROVED",
        )


def test_weekly_v1_and_v2_are_ordinary_versions_of_one_brain_script() -> None:
    v1 = inspect_package(_source("weekly_bos_v1.py"))
    v2 = inspect_package(_source("weekly_bos_v2.py"))
    assert v1.script_key == v2.script_key == "weekly_structure"
    assert v1.adapter_key == v2.adapter_key == "doctrine_package_v1"
    assert (v1.version_label, v2.version_label) == ("1", "2")


def test_v1_approval_then_v2_approval_moves_incremental_memory_pointer(tmp_path: Path) -> None:
    analysis = tmp_path / "analysis.sqlite3"
    candles = tmp_path / "candles.sqlite3"
    _analysis_db(analysis)
    _candle_db(candles)

    v1 = _insert(analysis, "weekly_bos_v1.py", "1")
    v1_run = run_version(
        analysis,
        version_id=v1["version_id"],
        case_ref=CASE_REF,
        symbol=SYMBOL,
        source_db=candles,
    )
    assert v1_run["run"]["approval_status"] == "PENDING"
    assert v1_run["run"]["publication_status"] == "UNPUBLISHED"
    _approve_all(analysis, v1_run)

    with sqlite3.connect(analysis) as con:
        approved_v1 = con.execute(
            "SELECT current_approved_version_id FROM doctrine_scripts WHERE script_key='weekly_structure'"
        ).fetchone()[0]
        assert approved_v1 == v1["version_id"]

    v2 = _insert(analysis, "weekly_bos_v2.py", "2")
    v2_run = run_version(
        analysis,
        version_id=v2["version_id"],
        case_ref=CASE_REF,
        symbol=SYMBOL,
        source_db=candles,
    )
    assert v2_run["run"]["sample_count"] == 5
    assert v2_run["run"]["approval_status"] == "PENDING"

    with sqlite3.connect(analysis) as con:
        still_v1 = con.execute(
            "SELECT current_approved_version_id FROM doctrine_scripts WHERE script_key='weekly_structure'"
        ).fetchone()[0]
        inactive_v2 = con.execute(
            "SELECT COUNT(*) FROM doctrine_enrichments WHERE version_id=? AND active=0",
            (v2["version_id"],),
        ).fetchone()[0]
        assert still_v1 == v1["version_id"]
        assert inactive_v2 == 6

    _approve_all(analysis, v2_run)

    with sqlite3.connect(analysis) as con:
        approved_v2 = con.execute(
            "SELECT current_approved_version_id FROM doctrine_scripts WHERE script_key='weekly_structure'"
        ).fetchone()[0]
        active_v2 = con.execute(
            "SELECT COUNT(*) FROM doctrine_enrichments WHERE version_id=? AND active=1",
            (v2["version_id"],),
        ).fetchone()[0]
        assert approved_v2 == v2["version_id"]
        assert active_v2 == 6

    summary = run_active_pipeline(
        analysis,
        case_ref=CASE_REF,
        symbol=SYMBOL,
        source_db=candles,
    )
    assert summary["active_scripts"] == 1
    assert summary["outputs_published"] == 6
