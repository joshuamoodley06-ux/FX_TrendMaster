from __future__ import annotations

import sqlite3

from range_library_memory import doctrine_pipeline


def test_legacy_weekly_activation_bootstraps_all_three_packages(tmp_path) -> None:
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
    assert [item["script_key"] for item in inserted["bootstrapped_packages"]] == [
        "weekly_structure",
        "weekly_reclaim",
        "weekly_reclaim_depth",
    ]
    assert set(by_key) == {
        "weekly_structure",
        "weekly_reclaim",
        "weekly_reclaim_depth",
    }
    assert by_key["weekly_structure"]["execution_order"] == 10
    assert by_key["weekly_reclaim"]["execution_order"] == 20
    assert by_key["weekly_reclaim_depth"]["execution_order"] == 30
