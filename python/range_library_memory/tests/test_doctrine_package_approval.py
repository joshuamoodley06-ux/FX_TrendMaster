from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from range_library_memory.doctrine_package_storage import package_file_path
from range_library_memory.doctrine_pipeline import run_active_pipeline, run_version, show_script
from range_library_memory.tests.doctrine_package_test_support import (
    CASE_REF,
    SYMBOL,
    approve_all,
    create_analysis_db,
    insert_package,
    package_source,
    stored_master_map,
)


def test_five_approvals_promote_package_and_future_pipeline_uses_exact_source(tmp_path: Path) -> None:
    analysis_db = tmp_path / "analysis.sqlite"
    candle_db = tmp_path / "candles.sqlite"
    create_analysis_db(analysis_db)
    candle_db.touch()
    source = package_source("1", "approved-v1")
    inserted = insert_package(analysis_db, source, "1")
    candidate = run_version(
        analysis_db,
        version_id=inserted["version_id"],
        case_ref=CASE_REF,
        symbol=SYMBOL,
        source_db=candle_db,
    )
    approve_all(analysis_db, candidate)
    script = show_script(analysis_db, "weekly_structure")
    assert script["status"] == "APPROVED"
    assert script["current_approved_version_id"] == inserted["version_id"]
    master = stored_master_map(analysis_db)
    enriched = master["trusted_root"]["children"][0]["analysis_enrichments"]["weekly_structure"]
    assert enriched["payload"]["logic_label"] == "approved-v1"

    package_path = package_file_path(
        analysis_db,
        script_key="weekly_structure",
        content_hash=inserted["content_hash"],
    )
    package_path.write_text("raise RuntimeError('tampered')\n", encoding="utf-8")
    master["structural_content_hash"] = "structure-v2"
    with sqlite3.connect(analysis_db) as con:
        con.execute(
            "UPDATE master_map_outputs SET output_json=? WHERE symbol=?",
            (json.dumps(master, sort_keys=True), SYMBOL),
        )
    summary = run_active_pipeline(
        analysis_db,
        case_ref=CASE_REF,
        symbol=SYMBOL,
        source_db=candle_db,
    )
    assert summary["active_scripts"] == 1
    assert summary["processed"] == 6
    assert "tampered" not in package_path.read_text(encoding="utf-8")
