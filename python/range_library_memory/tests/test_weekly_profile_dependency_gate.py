from __future__ import annotations

from pathlib import Path

import pytest

from range_library_memory import doctrine_pipeline
from range_library_memory.doctrine_packages import weekly_profile_classification


def test_profile_runtime_requires_latest_approved_depth_package(tmp_path: Path) -> None:
    database = tmp_path / "analysis.sqlite3"
    source_database = tmp_path / "candles.sqlite3"
    database.touch()
    source_database.touch()

    source = Path(weekly_profile_classification.__file__).read_text(encoding="utf-8")
    profile = doctrine_pipeline.insert_script(
        database,
        script_key="weekly_profile_classification",
        display_name="Weekly Profile Classification",
        version_label="1",
        source_code=source,
        adapter_key="doctrine_package_v1",
        execution_order=50,
    )

    with pytest.raises(
        doctrine_pipeline.DoctrinePipelineError,
        match="requires the latest approved Weekly Reclaim Depth package memory",
    ):
        doctrine_pipeline.run_version(
            database,
            version_id=profile["version_id"],
            case_ref="CASE",
            symbol="XAUUSD",
            source_db=source_database,
        )
