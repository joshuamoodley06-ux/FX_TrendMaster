from __future__ import annotations

from range_library_memory import doctrine_pipeline
from range_library_memory.doctrine_package_registry_run import _review_samples


def _row(identity: str, *, status: str = "COMPLETE", **payload) -> dict:
    return {
        "canonical_range_id": identity,
        "processing_status": status,
        "payload": payload,
    }


def test_bos_review_prioritizes_same_w1_case_even_when_it_sorts_last() -> None:
    outputs = [
        _row("weekly-1", chronology="RL_TO_RH", bos_direction="BOS_UP"),
        _row("weekly-2", chronology="RH_TO_RL", bos_direction="BOS_DOWN"),
        _row("weekly-9", chronology="SAME_W1", bos_direction="BOS_UP"),
        _row("weekly-3", chronology="RL_TO_RH", bos_direction="BOS_UP"),
        _row("weekly-4", chronology="RH_TO_RL", bos_direction="BOS_DOWN"),
        _row("weekly-5", chronology="RL_TO_RH", bos_direction="BOS_UP"),
    ]

    samples = _review_samples(doctrine_pipeline, "weekly_structure", outputs)

    assert len(samples) == 5
    assert samples[0]["canonical_range_id"] == "weekly-9"
    assert samples[0]["payload"]["chronology"] == "SAME_W1"


def test_reclaim_review_prioritizes_distinct_lifecycle_states() -> None:
    outputs = [
        _row("weekly-1", reclaim_status="RECLAIMED"),
        _row("weekly-2", reclaim_status="ABANDONED"),
        _row("weekly-3", reclaim_status="ABANDONED_THEN_RECLAIMED"),
        _row("weekly-4", status="NEEDS_REVIEW", reclaim_status="NEEDS_REVIEW"),
        _row("weekly-5", status="PENDING", reclaim_status="PENDING"),
        _row("weekly-6", reclaim_status="RECLAIMED"),
    ]

    samples = _review_samples(doctrine_pipeline, "weekly_reclaim", outputs)

    assert [row["payload"]["reclaim_status"] for row in samples] == [
        "RECLAIMED",
        "ABANDONED",
        "ABANDONED_THEN_RECLAIMED",
        "NEEDS_REVIEW",
        "PENDING",
    ]


def test_depth_review_prioritizes_distinct_trader_outcomes() -> None:
    outputs = [
        _row("weekly-1", depth_status="RETRACED_INTO_RANGE"),
        _row("weekly-2", depth_status="NO_RETRACEMENT"),
        _row("weekly-3", depth_status="BOUNDARY_TOUCH"),
        _row("weekly-4", depth_status="EXCEEDED_OLD_OPPOSITE"),
        _row("weekly-5", status="PENDING", depth_status="PENDING"),
        _row("weekly-6", status="NEEDS_REVIEW", depth_status="NEEDS_REVIEW"),
    ]

    samples = _review_samples(doctrine_pipeline, "weekly_reclaim_depth", outputs)

    assert [row["payload"]["depth_status"] for row in samples] == [
        "NO_RETRACEMENT",
        "BOUNDARY_TOUCH",
        "RETRACED_INTO_RANGE",
        "EXCEEDED_OLD_OPPOSITE",
        "PENDING",
    ]
