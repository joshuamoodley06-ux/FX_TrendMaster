from __future__ import annotations

from pathlib import Path

import pytest

from range_library_memory import doctrine_pipeline


def _seed_legacy_bos(database: Path) -> None:
    stamp = doctrine_pipeline.now()
    with doctrine_pipeline.connect(database) as connection:
        doctrine_pipeline.ensure_schema(connection)
        connection.execute(
            "INSERT INTO doctrine_scripts VALUES (?,?,?,?,?,'APPROVED',?,?,?)",
            (
                "legacy-script",
                "weekly_structure",
                "Weekly Script 1",
                "legacy",
                10,
                "legacy-version",
                stamp,
                stamp,
            ),
        )
        connection.execute(
            "INSERT INTO doctrine_script_versions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                "legacy-version",
                "legacy-script",
                "1",
                "legacy-hash",
                "# legacy\n",
                "weekly_chronology_bos_v1",
                doctrine_pipeline.CONTRACT,
                doctrine_pipeline.CONTRACT,
                stamp,
                stamp,
                None,
            ),
        )
        connection.commit()


def _reclaim_source() -> str:
    return '''FXTM_DOCTRINE_CONTRACT = "fxtm_doctrine_package_v1"
SCRIPT_KEY = "weekly_reclaim"
VERSION_LABEL = "1"
ADAPTER_KEY = "doctrine_package_v1"
EXECUTION_ORDER = 20


def run(context):
    return {"outputs": []}
'''


def test_legacy_bos_does_not_unlock_new_weekly_package_chain(tmp_path) -> None:
    database = tmp_path / "analysis.sqlite3"
    database.touch()
    _seed_legacy_bos(database)

    scripts = doctrine_pipeline.list_scripts(database)
    bos = next(row for row in scripts if row["script_key"] == "weekly_structure")

    assert bos["package_dependency_ready"] is False
    assert bos["current_approved_version_id"] is None
    assert bos["doctrine_state"]["current_approved_version_id"] == "legacy-version"


def test_reclaim_runtime_rejects_legacy_bos_dependency(tmp_path) -> None:
    database = tmp_path / "analysis.sqlite3"
    source_database = tmp_path / "candles.sqlite3"
    database.touch()
    source_database.touch()
    _seed_legacy_bos(database)

    reclaim = doctrine_pipeline.insert_script(
        database,
        script_key="weekly_reclaim",
        display_name="Weekly Reclaim",
        version_label="1",
        source_code=_reclaim_source(),
        adapter_key="doctrine_package_v1",
        execution_order=20,
    )

    with pytest.raises(
        doctrine_pipeline.DoctrinePipelineError,
        match="requires approved Weekly BOS package memory",
    ):
        doctrine_pipeline.run_version(
            database,
            version_id=reclaim["version_id"],
            case_ref="CASE",
            symbol="XAUUSD",
            source_db=source_database,
        )
