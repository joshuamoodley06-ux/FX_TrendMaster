from __future__ import annotations

from range_library_memory import doctrine_pipeline
from range_library_memory.doctrine_package_registry_run import _review_samples


def _row(identity: str, *, status: str = "COMPLETE", **payload) -> dict:
    return {
        "canonical_range_id": identity,
        "processing_status": status,
        "payload": payload,
    }


def test_daily_coverage_review_prioritizes_each_coverage_state() -> None:
    outputs = [
        _row("weekly-1", coverage_status="COMPLETE"),
        _row("weekly-2", coverage_status="PARTIAL"),
        _row("weekly-3", coverage_status="NOT_MAPPED"),
        _row("weekly-4", coverage_status="MAPPING_GAP"),
        _row("weekly-5", status="NEEDS_REVIEW", coverage_status="INVALID_PARENT_LINK"),
        _row("weekly-6", coverage_status="COMPLETE"),
    ]

    samples = _review_samples(
        doctrine_pipeline,
        "daily_mapping_coverage_audit",
        outputs,
    )

    assert [row["payload"]["coverage_status"] for row in samples] == [
        "NOT_MAPPED",
        "COMPLETE",
        "PARTIAL",
        "MAPPING_GAP",
        "INVALID_PARENT_LINK",
    ]


def test_relationship_review_prioritizes_future_sequence_active_and_gaps() -> None:
    outputs = [
        _row(
            "weekly-1",
            coverage_status="COMPLETE",
            daily_relationship_count=1,
            future_daily_ranges_excluded=0,
            active_daily_range_id="daily-1",
        ),
        _row(
            "weekly-2",
            coverage_status="COMPLETE",
            daily_relationship_count=3,
            future_daily_ranges_excluded=1,
            active_daily_range_id="daily-2",
        ),
        _row(
            "weekly-3",
            coverage_status="NOT_MAPPED",
            daily_relationship_count=0,
            future_daily_ranges_excluded=0,
            active_daily_range_id=None,
        ),
        _row(
            "weekly-4",
            coverage_status="MAPPING_GAP",
            daily_relationship_count=1,
            future_daily_ranges_excluded=0,
            active_daily_range_id=None,
        ),
        _row(
            "weekly-5",
            status="NEEDS_REVIEW",
            coverage_status="INVALID_PARENT_LINK",
            daily_relationship_count=1,
            future_daily_ranges_excluded=0,
            active_daily_range_id=None,
        ),
        _row(
            "weekly-6",
            coverage_status="COMPLETE",
            daily_relationship_count=2,
            future_daily_ranges_excluded=0,
            active_daily_range_id="daily-6",
        ),
    ]

    samples = _review_samples(
        doctrine_pipeline,
        "weekly_daily_relationship_builder",
        outputs,
    )

    assert [row["canonical_range_id"] for row in samples] == [
        "weekly-2",
        "weekly-6",
        "weekly-1",
        "weekly-3",
        "weekly-4",
    ]
