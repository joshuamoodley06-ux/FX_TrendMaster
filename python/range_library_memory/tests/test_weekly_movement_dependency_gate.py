from __future__ import annotations

from pathlib import Path

import pytest

from range_library_memory import doctrine_pipeline
from range_library_memory.doctrine_packages import weekly_movement_classification


def test_movement_runtime_requires_latest_approved_depth_package(tmp_path: Path) -> None:
    database = tmp_path / "analysis.sqlite3"
    source_database = tmp_path / "candles.sqlite3"
    database.touch()
    source_database.touch()

    source = Path(weekly_movement_classification.__file__).read_text(encoding="utf-8")
    movement = doctrine_pipeline.insert_script(
        database,
        script_key="weekly_movement_classification",
        display_name="Weekly Movement Classification",
        version_label="1",
        source_code=source,
        adapter_key="doctrine_package_v1",
        execution_order=40,
    )

    with pytest.raises(
        doctrine_pipeline.DoctrinePipelineError,
        match="requires the latest approved Weekly Reclaim Depth package memory",
    ):
        doctrine_pipeline.run_version(
            database,
            version_id=movement["version_id"],
            case_ref="CASE",
            symbol="XAUUSD",
            source_db=source_database,
        )
