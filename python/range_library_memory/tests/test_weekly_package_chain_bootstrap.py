from __future__ import annotations

import sqlite3

from range_library_memory import doctrine_pipeline


EXPECTED_VERSIONS = {
    "weekly_structure": "3",
    "weekly_reclaim": "2",
    "weekly_reclaim_depth": "6",
    "weekly_movement_classification": "4",
    "weekly_profile_classification": "1",
    "weekly_extreme_rejection_destination": "1",
    "daily_mapping_coverage_audit": "2",
    "weekly_daily_relationship_builder": "1",
}


EXPECTED_KEYS = [
    "weekly_structure",
    "weekly_reclaim",
    "weekly_reclaim_depth",
    "weekly_movement_classification",
    "weekly_profile_classification",
    "weekly_extreme_rejection_destination",
    "daily_mapping_coverage_audit",
    "weekly_daily_relationship_builder",
]


def test_legacy_weekly_activation_bootstraps_current_structure_chain(tmp_path) -> None:
    database = tmp_path / "analysis.sqlite3"
    sqlite3.connect(database).close()

    inserted = doctrine_pipeline.insert_script(
        database,
        script_key="weekly_structure",
        display_name="Weekly Script 1",
        version_label="1",
        source_code="# legacy activation shim\n",
        adapter_key="weekly_chronology_bos_v1",
        execution_order=10,
    )

    scripts = doctrine_pipeline.list_scripts(database)
    by_key = {row["script_key"]: row for row in scripts}

    assert inserted["script_key"] == "weekly_structure"
    assert [item["script_key"] for item in inserted["bootstrapped_packages"]] == EXPECTED_KEYS
    assert set(by_key) == set(EXPECTED_VERSIONS)
    assert by_key["weekly_structure"]["execution_order"] == 10
    assert by_key["weekly_reclaim"]["execution_order"] == 20
    assert by_key["weekly_reclaim_depth"]["execution_order"] == 30
    assert by_key["weekly_movement_classification"]["execution_order"] == 40
    assert by_key["weekly_profile_classification"]["execution_order"] == 50
    assert by_key["weekly_extreme_rejection_destination"]["execution_order"] == 60
    assert by_key["daily_mapping_coverage_audit"]["execution_order"] == 70
    assert by_key["weekly_daily_relationship_builder"]["execution_order"] == 80
    for script_key, expected_version in EXPECTED_VERSIONS.items():
        script = by_key[script_key]
        assert script["version_label"] == expected_version
        assert script["latest_version_status"] == "PENDING_APPROVAL"
        state = script["doctrine_state"]
        assert state["script_key"] == script_key
        assert state["versions"][-1]["version_label"] == expected_version
        assert state["runs"] == []


def test_bootstrap_and_script_listing_are_idempotent(tmp_path) -> None:
    database = tmp_path / "analysis.sqlite3"
    sqlite3.connect(database).close()

    first = doctrine_pipeline.insert_script(
        database,
        script_key="weekly_structure",
        display_name="Weekly Script 1",
        version_label="1",
        source_code="# legacy activation shim\n",
        adapter_key="weekly_chronology_bos_v1",
        execution_order=10,
    )
    second = doctrine_pipeline.insert_script(
        database,
        script_key="weekly_structure",
        display_name="Weekly Script 1",
        version_label="1",
        source_code="# legacy activation shim\n",
        adapter_key="weekly_chronology_bos_v1",
        execution_order=10,
    )
    listed_once = doctrine_pipeline.list_scripts(database)
    listed_twice = doctrine_pipeline.list_scripts(database)

    assert [item["script_key"] for item in first["bootstrapped_packages"]] == EXPECTED_KEYS
    assert [item["script_key"] for item in second["bootstrapped_packages"]] == EXPECTED_KEYS
    assert len(listed_once) == 8
    assert len(listed_twice) == 8
    assert {
        row["script_key"]: row["version_label"] for row in listed_twice
    } == EXPECTED_VERSIONS
    for row in listed_twice:
        assert len(row["doctrine_state"]["versions"]) == 1
