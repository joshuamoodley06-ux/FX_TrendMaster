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


def test_depth_review_prioritizes_both_anchor_stories_then_distinct_outcomes() -> None:
    outputs = [
        _row(
            "weekly-1",
            range2_anchor_sequence="OPPOSITE_THEN_CONTINUATION",
            depth_status="RETRACED_INTO_RANGE",
        ),
        _row(
            "weekly-2",
            range2_anchor_sequence="CONTINUATION_THEN_OPPOSITE",
            depth_status="NO_RETRACEMENT",
        ),
        _row(
            "weekly-3",
            range2_anchor_sequence="SAME_W1",
            depth_status="BOUNDARY_TOUCH",
        ),
        _row(
            "weekly-4",
            range2_anchor_sequence="OPPOSITE_THEN_CONTINUATION",
            depth_status="TOUCHED_OLD_OPPOSITE",
        ),
        _row(
            "weekly-5",
            range2_anchor_sequence="CONTINUATION_THEN_OPPOSITE",
            depth_status="EXCEEDED_OLD_OPPOSITE",
        ),
        _row("weekly-6", status="PENDING", depth_status="PENDING"),
    ]

    samples = _review_samples(doctrine_pipeline, "weekly_reclaim_depth", outputs)

    assert [row["canonical_range_id"] for row in samples] == [
        "weekly-1",
        "weekly-2",
        "weekly-3",
        "weekly-4",
        "weekly-5",
    ]
    assert [row["payload"]["range2_anchor_sequence"] for row in samples[:3]] == [
        "OPPOSITE_THEN_CONTINUATION",
        "CONTINUATION_THEN_OPPOSITE",
        "SAME_W1",
    ]


def test_movement_review_includes_alternating_roles_and_depth_pending_story() -> None:
    outputs = [
        _row(
            "weekly-1",
            movement_path="CT 1W -> PT 1W -> BOS_UP",
            movement_leg_count=2,
            movement_legs=[{"code": "CT"}, {"code": "PT"}],
            reclaim_depth_status="RETRACED_INTO_RANGE",
            countertrend_classification="COUNTERTREND_RETRACEMENT",
        ),
        _row(
            "weekly-2",
            movement_path="PT 1W -> CT 1W -> BOS_DOWN",
            movement_leg_count=2,
            movement_legs=[{"code": "PT"}, {"code": "CT"}],
            reclaim_depth_status="NO_RETRACEMENT",
            countertrend_classification="NO_RANGE1_RETRACEMENT",
        ),
        _row(
            "weekly-3",
            movement_path="CT 1W -> PT 1W -> CT 1W -> BOS_UP",
            movement_leg_count=3,
            movement_legs=[{"code": "CT"}, {"code": "PT"}, {"code": "CT"}],
            reclaim_depth_status="BOUNDARY_TOUCH",
            countertrend_classification="BOUNDARY_TOUCH",
        ),
        _row(
            "weekly-4",
            movement_path="CT 2W -> PT 1W -> BOS_UP",
            movement_leg_count=2,
            movement_legs=[{"code": "CT"}, {"code": "PT"}],
            reclaim_depth_status="PENDING",
            countertrend_classification="COUNTERTREND_LEG_DEPTH_PENDING",
        ),
        _row(
            "weekly-5",
            movement_path="PT 1W -> CT 1W -> PT 1W -> BOS_DOWN",
            movement_leg_count=3,
            movement_legs=[{"code": "PT"}, {"code": "CT"}, {"code": "PT"}],
            reclaim_depth_status="RETRACED_INTO_RANGE",
            countertrend_classification="COUNTERTREND_RETRACEMENT",
        ),
        _row(
            "weekly-6",
            movement_path="PT 1W -> BOS_DOWN",
            movement_leg_count=1,
            movement_legs=[{"code": "PT"}],
            reclaim_depth_status="RETRACED_INTO_RANGE",
            countertrend_classification="COUNTERTREND_RETRACEMENT",
        ),
    ]

    samples = _review_samples(
        doctrine_pipeline,
        "weekly_movement_classification",
        outputs,
    )

    assert [row["canonical_range_id"] for row in samples] == [
        "weekly-3",
        "weekly-1",
        "weekly-2",
        "weekly-4",
        "weekly-5",
    ]
    assert samples[3]["payload"]["reclaim_depth_status"] == "PENDING"


def test_profile_review_prioritizes_all_profiles_and_abandonment_override() -> None:
    outputs = [
        _row(
            "weekly-1",
            profile_classification="S&R",
            classification_basis="RECLAIM_DEPTH",
        ),
        _row(
            "weekly-2",
            profile_classification="S&R>FP",
            classification_basis="RECLAIM_DEPTH",
        ),
        _row(
            "weekly-3",
            profile_classification="S&D",
            classification_basis="RECLAIM_DEPTH",
        ),
        _row(
            "weekly-4",
            profile_classification="S&R",
            classification_basis="ABND_SAME_DIRECTION_BOS",
        ),
        _row(
            "weekly-5",
            status="PENDING",
            profile_classification=None,
            classification_basis=None,
        ),
        _row(
            "weekly-6",
            profile_classification="S&D",
            classification_basis="RECLAIM_DEPTH",
        ),
    ]

    samples = _review_samples(
        doctrine_pipeline,
        "weekly_profile_classification",
        outputs,
    )

    assert [row["canonical_range_id"] for row in samples] == [
        "weekly-1",
        "weekly-2",
        "weekly-3",
        "weekly-4",
        "weekly-5",
    ]
