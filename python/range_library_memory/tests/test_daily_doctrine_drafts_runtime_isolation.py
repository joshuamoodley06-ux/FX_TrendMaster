from __future__ import annotations

from pathlib import Path

from range_library_memory import doctrine_package_runtime_registry as runtime_registry


def test_daily_doctrine_drafts_are_not_in_the_runtime_bundle_chain() -> None:
    bundled_filenames = [filename for filename, _ in runtime_registry._STRUCTURE_PACKAGE_CHAIN]

    assert bundled_filenames == [
        "weekly_bos.py",
        "weekly_reclaim.py",
        "weekly_reclaim_depth.py",
        "weekly_movement_classification.py",
        "weekly_profile_classification.py",
        "weekly_extreme_rejection_destination.py",
        "daily_mapping_coverage_audit.py",
        "weekly_daily_relationship_builder.py",
    ]
    assert all("doctrine_drafts" not in filename for filename in bundled_filenames)


def test_daily_draft_source_is_physically_outside_production_package_directory() -> None:
    package_dir = Path(runtime_registry.__file__).with_name("doctrine_packages")
    draft_dir = Path(runtime_registry.__file__).with_name("doctrine_drafts") / "daily"

    assert draft_dir != package_dir
    assert draft_dir.parent.name == "doctrine_drafts"
    assert not any((package_dir / name).exists() for name in (
        "daily_structure.py",
        "daily_reclaim.py",
        "daily_reclaim_depth.py",
        "daily_movement_classification.py",
        "daily_profile_classification.py",
        "daily_extreme_rejection_destination.py",
    ))
