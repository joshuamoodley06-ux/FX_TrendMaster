from __future__ import annotations

from pathlib import Path

import pytest

from range_library_memory import doctrine_pipeline
from range_library_memory.doctrine_packages import weekly_extreme_rejection_destination


def test_extreme_rejection_runtime_requires_latest_approved_profile_package(tmp_path: Path) -> None:
    database = tmp_path / "analysis.sqlite3"
    source_database = tmp_path / "candles.sqlite3"
    database.touch()
    source_database.touch()

    source = Path(weekly_extreme_rejection_destination.__file__).read_text(
        encoding="utf-8"
    )
    package = doctrine_pipeline.insert_script(
        database,
        script_key="weekly_extreme_rejection_destination",
        display_name="Weekly Extreme Rejection Destination",
        version_label="1",
        source_code=source,
        adapter_key="doctrine_package_v1",
        execution_order=60,
    )

    with pytest.raises(
        doctrine_pipeline.DoctrinePipelineError,
        match="requires the latest approved Weekly Profile Classification package memory",
    ):
        doctrine_pipeline.run_version(
            database,
            version_id=package["version_id"],
            case_ref="CASE",
            symbol="XAUUSD",
            source_db=source_database,
        )
