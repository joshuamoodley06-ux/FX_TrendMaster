from __future__ import annotations

from range_library_memory.doctrine_pipeline import (
    review_sample,
    run_active_pipeline,
    run_version,
    show_script,
)
from range_library_memory.tests.doctrine_package_test_support import (
    CASE_REF,
    SYMBOL,
    approve_all,
    create_analysis_db,
    insert_package,
    package_source,
)


def test_review_refresh_preserves_prior_approved_run_while_candidate_is_pending(tmp_path) -> None:
    analysis_db = tmp_path / "analysis.sqlite3"
    candle_db = tmp_path / "candles.sqlite3"
    create_analysis_db(analysis_db)
    candle_db.touch()

    approved = insert_package(
        analysis_db,
        package_source("1", "approved-v1"),
        "1",
    )
    approved_run = run_version(
        analysis_db,
        version_id=approved["version_id"],
        case_ref=CASE_REF,
        symbol=SYMBOL,
        source_db=candle_db,
    )
    approve_all(analysis_db, approved_run)

    candidate = insert_package(
        analysis_db,
        package_source("2", "candidate-v2"),
        "2",
    )
    candidate_run = run_version(
        analysis_db,
        version_id=candidate["version_id"],
        case_ref=CASE_REF,
        symbol=SYMBOL,
        source_db=candle_db,
    )
    first_sample = candidate_run["samples"][0]
    review_sample(
        analysis_db,
        run_id=candidate_run["run"]["run_id"],
        canonical_range_id=first_sample["canonical_range_id"],
        decision="APPROVED",
    )

    summary = run_active_pipeline(
        analysis_db,
        case_ref=CASE_REF,
        symbol=SYMBOL,
        source_db=candle_db,
    )

    assert summary["active_scripts"] == 1
    assert summary["processed"] == 0
    assert summary["skipped_unchanged"] == 6

    refreshed = run_version(
        analysis_db,
        version_id=approved["version_id"],
        case_ref=CASE_REF,
        symbol=SYMBOL,
        source_db=candle_db,
    )
    assert refreshed["reused"] is True
    assert refreshed["preserved_prior_approved"] is True
    assert refreshed["run"]["version_id"] == approved["version_id"]

    state = show_script(analysis_db, "weekly_structure")
    candidate_state = next(
        item for item in state["runs"]
        if item["run"]["version_id"] == candidate["version_id"]
    )
    decisions = {
        sample["canonical_range_id"]: sample["decision"]
        for sample in candidate_state["samples"]
    }
    assert decisions[first_sample["canonical_range_id"]] == "APPROVED"
    assert state["current_approved_version_id"] == approved["version_id"]
