from __future__ import annotations

from range_library_memory.doctrine_packages import weekly_profile_classification


class FakeContext:
    def __init__(self, memory: dict) -> None:
        self._memory = memory

    def selected_ranges(self, *, layer: str | None = None):
        assert layer == "WEEKLY"
        return ({"id": "range-1"},)

    def approved_memory(self, canonical_range_id: str):
        assert canonical_range_id == "range-1"
        return self._memory


def _entry(payload: dict, processing_status: str = "COMPLETE") -> dict:
    return {
        "processing_status": processing_status,
        "payload": payload,
    }


def _reclaim(
    *,
    status: str = "RECLAIMED",
    source: str = "BOS_UP",
    next_direction: str = "BOS_UP",
    processing_status: str = "COMPLETE",
) -> dict:
    return _entry({
        "reclaim_status": status,
        "source_bos_direction": source,
        "next_bos_direction": next_direction,
    }, processing_status)


def _depth(percent: float, processing_status: str = "COMPLETE") -> dict:
    return _entry({
        "depth_status": "RETRACED_INTO_RANGE",
        "reclaim_depth_percent": percent,
    }, processing_status)


def _result(memory: dict) -> dict:
    return weekly_profile_classification.run(FakeContext(memory))["outputs"][0]


def test_depth_below_38_2_is_sr() -> None:
    result = _result({
        "weekly_reclaim": _reclaim(),
        "weekly_reclaim_depth": _depth(38.1999),
    })

    assert result["processing_status"] == "COMPLETE"
    assert result["payload"]["profile_classification"] == "S&R"
    assert result["payload"]["classification_basis"] == "RECLAIM_DEPTH"
    assert result["payload"]["reason_codes"] == ["DEPTH_BELOW_38_2"]


def test_exact_38_2_and_exact_50_are_sr_to_fair_price() -> None:
    at_38_2 = _result({
        "weekly_reclaim": _reclaim(),
        "weekly_reclaim_depth": _depth(38.2),
    })
    at_50 = _result({
        "weekly_reclaim": _reclaim(),
        "weekly_reclaim_depth": _depth(50.0),
    })

    for result in (at_38_2, at_50):
        assert result["processing_status"] == "COMPLETE"
        assert result["payload"]["profile_classification"] == "S&R>FP"
        assert result["payload"]["reason_codes"] == ["DEPTH_38_2_TO_50"]


def test_depth_above_50_is_supply_and_demand() -> None:
    result = _result({
        "weekly_reclaim": _reclaim(),
        "weekly_reclaim_depth": _depth(50.0001),
    })

    assert result["processing_status"] == "COMPLETE"
    assert result["payload"]["profile_classification"] == "S&D"
    assert result["payload"]["reason_codes"] == ["DEPTH_ABOVE_50"]


def test_abandoned_range_with_same_direction_bos_overrides_missing_depth_as_sr() -> None:
    result = _result({
        "weekly_reclaim": _reclaim(
            status="ABANDONED",
            source="BOS_DOWN",
            next_direction="BOS_DOWN",
        ),
    })

    assert result["processing_status"] == "COMPLETE"
    assert result["payload"]["profile_classification"] == "S&R"
    assert result["payload"]["classification_basis"] == "ABND_SAME_DIRECTION_BOS"
    assert result["payload"]["reclaim_depth_percent"] is None
    assert result["payload"]["reason_codes"] == [
        "ABANDONED_RANGE_FOLLOWED_BY_SAME_DIRECTION_BOS"
    ]


def test_abandoned_range_with_opposite_direction_bos_stays_pending() -> None:
    result = _result({
        "weekly_reclaim": _reclaim(
            status="ABANDONED",
            source="BOS_UP",
            next_direction="BOS_DOWN",
        ),
    })

    assert result["processing_status"] == "PENDING"
    assert result["payload"]["profile_classification"] is None
    assert result["payload"]["reason_codes"] == [
        "ABANDONED_RANGE_WITHOUT_SAME_DIRECTION_BOS_OVERRIDE"
    ]


def test_depth_review_blocks_profile_without_override() -> None:
    result = _result({
        "weekly_reclaim": _reclaim(),
        "weekly_reclaim_depth": _entry(
            {"depth_status": "NEEDS_REVIEW", "reclaim_depth_percent": None},
            "NEEDS_REVIEW",
        ),
    })

    assert result["processing_status"] == "NEEDS_REVIEW"
    assert result["payload"]["reason_codes"] == [
        "WEEKLY_RECLAIM_DEPTH_NEEDS_REVIEW"
    ]
