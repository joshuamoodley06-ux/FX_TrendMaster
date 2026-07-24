from __future__ import annotations

import json
import sqlite3

from range_library_memory import doctrine_pipeline
from range_library_memory.tests.doctrine_package_test_support import (
    CASE_REF,
    SYMBOL,
    create_analysis_db,
    insert_package,
    package_source,
)


def test_short_case_runs_but_cannot_activate_package_before_true_five_of_five(tmp_path) -> None:
    analysis_db = tmp_path / "analysis.sqlite3"
    source_db = tmp_path / "candles.sqlite3"
    create_analysis_db(analysis_db)
    sqlite3.connect(source_db).close()

    with sqlite3.connect(analysis_db) as connection:
        row = connection.execute(
            "SELECT output_json FROM master_map_outputs WHERE symbol=?",
            (SYMBOL,),
        ).fetchone()
        master = json.loads(row[0])
        master["trusted_root"]["children"] = master["trusted_root"]["children"][:3]
        connection.execute(
            "UPDATE master_map_outputs SET output_json=? WHERE symbol=?",
            (json.dumps(master, sort_keys=True), SYMBOL),
        )
        connection.commit()

    inserted = insert_package(
        analysis_db,
        package_source("1", "short-case"),
        "1",
    )
    run = doctrine_pipeline.run_version(
        analysis_db,
        version_id=inserted["version_id"],
        case_ref=CASE_REF,
        symbol=SYMBOL,
        source_db=source_db,
    )

    assert run["run"]["sample_count"] == 3
    assert len(run["samples"]) == 3

    for sample in run["samples"]:
        doctrine_pipeline.review_sample(
            analysis_db,
            run_id=run["run"]["run_id"],
            canonical_range_id=sample["canonical_range_id"],
            decision="APPROVED",
        )

    state = doctrine_pipeline.show_script(analysis_db, "weekly_structure")
    short_run = state["runs"][0]["run"]
    assert state["current_approved_version_id"] is None
    assert state["status"] == "PENDING_APPROVAL"
    assert short_run["approval_status"] == "PENDING"
    assert short_run["approval_count"] == 3
    assert short_run["publication_status"] == "UNPUBLISHED"
