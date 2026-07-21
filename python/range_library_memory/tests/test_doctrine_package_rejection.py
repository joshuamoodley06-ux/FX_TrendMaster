from __future__ import annotations

import sqlite3
from pathlib import Path

from range_library_memory.doctrine_pipeline import review_sample, run_version, show_script
from range_library_memory.tests.doctrine_package_test_support import (
    CASE_REF,
    SYMBOL,
    approve_all,
    create_analysis_db,
    insert_package,
    package_source,
    stored_master_map,
)


def test_rejected_candidate_preserves_previous_approved_package(tmp_path: Path) -> None:
    analysis_db = tmp_path / "analysis.sqlite"
    candle_db = tmp_path / "candles.sqlite"
    create_analysis_db(analysis_db)
    candle_db.touch()
    approved = insert_package(analysis_db, package_source("1", "approved-v1"), "1")
    approved_run = run_version(
        analysis_db,
        version_id=approved["version_id"],
        case_ref=CASE_REF,
        symbol=SYMBOL,
        source_db=candle_db,
    )
    approve_all(analysis_db, approved_run)

    candidate = insert_package(analysis_db, package_source("2", "candidate-v2"), "2")
    candidate_run = run_version(
        analysis_db,
        version_id=candidate["version_id"],
        case_ref=CASE_REF,
        symbol=SYMBOL,
        source_db=candle_db,
    )
    sample = candidate_run["samples"][0]
    review_sample(
        analysis_db,
        run_id=candidate_run["run"]["run_id"],
        canonical_range_id=sample["canonical_range_id"],
        decision="REJECTED",
    )
    script = show_script(analysis_db, "weekly_structure")
    assert script["status"] == "APPROVED"
    assert script["current_approved_version_id"] == approved["version_id"]
    with sqlite3.connect(analysis_db) as con:
        active_versions = {
            row[0]
            for row in con.execute(
                "SELECT DISTINCT version_id FROM doctrine_enrichments WHERE active=1"
            )
        }
    assert active_versions == {approved["version_id"]}
    payload = stored_master_map(analysis_db)["trusted_root"]["children"][0]["analysis_enrichments"]["weekly_structure"]["payload"]
    assert payload["logic_label"] == "approved-v1"
