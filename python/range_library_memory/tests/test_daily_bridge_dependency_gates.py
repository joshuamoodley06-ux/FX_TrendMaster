from __future__ import annotations

from pathlib import Path

import pytest

from range_library_memory import doctrine_pipeline
from range_library_memory.doctrine_packages import (
    daily_mapping_coverage_audit,
    weekly_daily_relationship_builder,
)


def _insert(
    database: Path,
    *,
    key: str,
    name: str,
    version: str,
    order: int,
    source_module,
) -> dict:
    source = Path(source_module.__file__).read_text(encoding="utf-8")
    return doctrine_pipeline.insert_script(
        database,
        script_key=key,
        display_name=name,
        version_label=version,
        source_code=source,
        adapter_key="doctrine_package_v1",
        execution_order=order,
    )


def test_coverage_runtime_requires_latest_approved_extreme_destination(tmp_path: Path) -> None:
    database = tmp_path / "analysis.sqlite3"
    source_database = tmp_path / "candles.sqlite3"
    database.touch()
    source_database.touch()

    coverage = _insert(
        database,
        key="daily_mapping_coverage_audit",
        name="Daily Mapping Coverage Audit",
        version="1",
        order=70,
        source_module=daily_mapping_coverage_audit,
    )

    with pytest.raises(
        doctrine_pipeline.DoctrinePipelineError,
        match="requires the latest approved Weekly Extreme Rejection Destination package memory",
    ):
        doctrine_pipeline.run_version(
            database,
            version_id=coverage["version_id"],
            case_ref="CASE",
            symbol="XAUUSD",
            source_db=source_database,
        )


def test_relationship_runtime_requires_latest_approved_coverage_audit(tmp_path: Path) -> None:
    database = tmp_path / "analysis.sqlite3"
    source_database = tmp_path / "candles.sqlite3"
    database.touch()
    source_database.touch()

    relationship = _insert(
        database,
        key="weekly_daily_relationship_builder",
        name="Weekly Daily Relationship Builder",
        version="1",
        order=80,
        source_module=weekly_daily_relationship_builder,
    )

    with pytest.raises(
        doctrine_pipeline.DoctrinePipelineError,
        match="requires the latest approved Daily Mapping Coverage Audit package memory",
    ):
        doctrine_pipeline.run_version(
            database,
            version_id=relationship["version_id"],
            case_ref="CASE",
            symbol="XAUUSD",
            source_db=source_database,
        )
