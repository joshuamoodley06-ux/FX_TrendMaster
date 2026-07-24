from __future__ import annotations

import sqlite3

from range_library_memory import doctrine_pipeline
from range_library_memory.tests.doctrine_package_test_support import (
    CASE_REF,
    SYMBOL,
    approve_all,
    create_analysis_db,
    insert_package,
    package_source,
)


def _dependent_source() -> str:
    return '''FXTM_DOCTRINE_CONTRACT = "fxtm_doctrine_package_v1"
SCRIPT_KEY = "weekly_reclaim"
VERSION_LABEL = "1"
ADAPTER_KEY = "doctrine_package_v1"
EXECUTION_ORDER = 20


def run(context):
    return {"outputs": [
        {
            "canonical_range_id": node["id"],
            "processing_status": "PENDING",
            "payload": {"reclaim_status": "PENDING"},
        }
        for node in context.selected_ranges(layer="WEEKLY")
    ]}
'''


def test_dependent_run_is_not_reused_when_approved_parent_memory_changes(tmp_path) -> None:
    analysis_db = tmp_path / "analysis.sqlite3"
    source_db = tmp_path / "candles.sqlite3"
    create_analysis_db(analysis_db)
    sqlite3.connect(source_db).close()

    bos = insert_package(
        analysis_db,
        package_source("2", "bos-parent"),
        "2",
    )
    bos_run = doctrine_pipeline.run_version(
        analysis_db,
        version_id=bos["version_id"],
        case_ref=CASE_REF,
        symbol=SYMBOL,
        source_db=source_db,
    )
    approve_all(analysis_db, bos_run)

    reclaim = doctrine_pipeline.insert_script(
        analysis_db,
        script_key="weekly_reclaim",
        display_name="Weekly Reclaim",
        version_label="1",
        source_code=_dependent_source(),
        adapter_key="doctrine_package_v1",
        execution_order=20,
    )
    first = doctrine_pipeline.run_version(
        analysis_db,
        version_id=reclaim["version_id"],
        case_ref=CASE_REF,
        symbol=SYMBOL,
        source_db=source_db,
    )

    with doctrine_pipeline.connect(analysis_db) as connection:
        connection.execute(
            """UPDATE doctrine_enrichments
               SET output_hash='changed-parent-output'
               WHERE version_id=? AND canonical_range_id='weekly-0'""",
            (bos["version_id"],),
        )
        connection.commit()

    second = doctrine_pipeline.run_version(
        analysis_db,
        version_id=reclaim["version_id"],
        case_ref=CASE_REF,
        symbol=SYMBOL,
        source_db=source_db,
    )

    assert first["reused"] is False
    assert second["reused"] is False
    assert first["run"]["run_id"] != second["run"]["run_id"]
    assert first["run"]["input_structural_hash"] != second["run"]["input_structural_hash"]
