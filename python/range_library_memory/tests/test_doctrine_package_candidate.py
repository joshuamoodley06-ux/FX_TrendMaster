from __future__ import annotations

import sqlite3
from pathlib import Path

from range_library_memory.doctrine_package_contract import PACKAGE_ADAPTER
from range_library_memory.doctrine_package_storage import package_file_path
from range_library_memory.doctrine_pipeline import run_version
from range_library_memory.tests.doctrine_package_test_support import (
    CASE_REF,
    SYMBOL,
    create_analysis_db,
    insert_package,
    package_source,
)


def test_candidate_runs_exact_source_and_creates_five_inactive_samples(tmp_path: Path) -> None:
    analysis_db = tmp_path / "analysis.sqlite"
    candle_db = tmp_path / "candles.sqlite"
    create_analysis_db(analysis_db)
    candle_db.touch()
    source = package_source("1", "v1")
    inserted = insert_package(analysis_db, source, "1")
    assert inserted["adapter_key"] == PACKAGE_ADAPTER
    package_path = package_file_path(
        analysis_db,
        script_key="weekly_structure",
        content_hash=inserted["content_hash"],
    )
    assert package_path.read_text(encoding="utf-8").strip() == source.strip()
    state = run_version(
        analysis_db,
        version_id=inserted["version_id"],
        case_ref=CASE_REF,
        symbol=SYMBOL,
        source_db=candle_db,
    )
    assert state["run"]["approval_status"] == "PENDING"
    assert state["run"]["publication_status"] == "UNPUBLISHED"
    assert state["run"]["sample_count"] == 5
    assert len(state["samples"]) == 5
    with sqlite3.connect(analysis_db) as con:
        active = con.execute(
            "SELECT COUNT(*) FROM doctrine_enrichments WHERE version_id=? AND active=1",
            (inserted["version_id"],),
        ).fetchone()[0]
    assert active == 0
