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

CASE_REF = "CASE-WEEKLY-PACKAGE"
SYMBOL = "XAUUSD"
PACKAGE_FILE = Path(__file__).resolve().parents[1] / "doctrine_packages" / "weekly_bos.py"


def _source() -> str:
    return PACKAGE_FILE.read_text(encoding="utf-8")


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


def _insert(db: Path) -> dict:
    return insert_script(
        db,
        script_key="weekly_structure",
        display_name="Weekly BOS",
        version_label="3",
        source_code=_source(),
        adapter_key="doctrine_package_v1",
        execution_order=10,
        description="Single approved Weekly BOS doctrine package",
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


def test_repository_contains_one_weekly_bos_brain_package() -> None:
    metadata = inspect_package(_source())
    assert metadata.script_key == "weekly_structure"
    assert metadata.adapter_key == "doctrine_package_v1"
    assert metadata.version_label == "3"
    assert not (PACKAGE_FILE.parent / "weekly_bos_v1.py").exists()
    assert not (PACKAGE_FILE.parent / "weekly_bos_v2.py").exists()


def test_one_weekly_package_becomes_the_only_active_brain_script(tmp_path: Path) -> None:
    analysis = tmp_path / "analysis.sqlite3"
    candles = tmp_path / "candles.sqlite3"
    _analysis_db(analysis)
    _candle_db(candles)

    version = _insert(analysis)
    candidate = run_version(
        analysis,
        version_id=version["version_id"],
        case_ref=CASE_REF,
        symbol=SYMBOL,
        source_db=candles,
    )
    assert candidate["run"]["approval_status"] == "PENDING"
    assert candidate["run"]["publication_status"] == "UNPUBLISHED"
    assert candidate["run"]["sample_count"] == 5

    with sqlite3.connect(analysis) as con:
        inactive = con.execute(
            "SELECT COUNT(*) FROM doctrine_enrichments WHERE version_id=? AND active=0",
            (version["version_id"],),
        ).fetchone()[0]
        assert inactive == 6

    _approve_all(analysis, candidate)

    with sqlite3.connect(analysis) as con:
        script = con.execute(
            "SELECT status,current_approved_version_id FROM doctrine_scripts WHERE script_key='weekly_structure'"
        ).fetchone()
        active = con.execute(
            "SELECT COUNT(*) FROM doctrine_enrichments WHERE version_id=? AND active=1",
            (version["version_id"],),
        ).fetchone()[0]
        assert script == ("APPROVED", version["version_id"])
        assert active == 6

    summary = run_active_pipeline(
        analysis,
        case_ref=CASE_REF,
        symbol=SYMBOL,
        source_db=candles,
    )
    assert summary["active_scripts"] == 1
    assert summary["outputs_published"] == 6
