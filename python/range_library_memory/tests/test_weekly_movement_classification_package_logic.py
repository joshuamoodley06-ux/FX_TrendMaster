from __future__ import annotations

from range_library_memory.doctrine_packages import weekly_movement_classification


class FakeContext:
    def __init__(self, depth_entry: dict | None) -> None:
        self._depth_entry = depth_entry

    def selected_ranges(self, *, layer: str | None = None):
        assert layer == "WEEKLY"
        return ({"id": "range-1"},)

    def approved_memory(self, canonical_range_id: str):
        assert canonical_range_id == "range-1"
        if self._depth_entry is None:
            return {}
        return {"weekly_reclaim_depth": self._depth_entry}


def _entry(**payload) -> dict:
    base = {
        "depth_status": "RETRACED_INTO_RANGE",
        "source_bos_direction": "BOS_UP",
        "source_reclaim_time": "2024-06-16T00:00:00Z",
        "range2_id": "range-2",
        "range2_anchor_sequence": "OPPOSITE_THEN_CONTINUATION",
        "range2_opposite_anchor_price": 2353.06,
        "range2_continuation_anchor_price": 2450.01,
        "reclaim_depth_price": 96.95,
        "reclaim_depth_percent": 56.14,
        "weeks_reclaim_to_depth_anchor": 5,
        "range2_formation_weeks": 4,
    }
    base.update(payload)
    return {"processing_status": "COMPLETE", "payload": base}


def _result(context: FakeContext) -> dict:
    return weekly_movement_classification.run(context)["outputs"][0]


def test_bos_up_classifies_countertrend_then_protrend() -> None:
    result = _result(FakeContext(_entry()))
    payload = result["payload"]

    assert result["processing_status"] == "COMPLETE"
    assert payload["movement_status"] == "CLASSIFIED"
    assert payload["movement_sequence"] == "COUNTERTREND_THEN_PROTREND"
    assert payload["countertrend_classification"] == "COUNTERTREND_RETRACEMENT"
    assert payload["countertrend_direction"] == "DOWN"
    assert payload["countertrend_distance"] == 96.95
    assert payload["countertrend_depth_percent"] == 56.14
    assert payload["countertrend_weeks"] == 5
    assert payload["protrend_classification"] == "PROTREND_CONTINUATION"
    assert payload["protrend_direction"] == "UP"
    assert payload["protrend_distance"] == 96.95
    assert payload["protrend_weeks"] == 4


def test_bos_down_classifies_protrend_then_countertrend_when_anchor_order_is_reversed() -> None:
    result = _result(FakeContext(_entry(
        source_bos_direction="BOS_DOWN",
        range2_anchor_sequence="CONTINUATION_THEN_OPPOSITE",
        range2_opposite_anchor_price=5092.91,
        range2_continuation_anchor_price=4271.64,
        reclaim_depth_price=496.81,
        reclaim_depth_percent=37.4,
        weeks_reclaim_to_depth_anchor=3,
        range2_formation_weeks=7,
    )))
    payload = result["payload"]

    assert payload["movement_sequence"] == "PROTREND_THEN_COUNTERTREND"
    assert payload["countertrend_direction"] == "UP"
    assert payload["countertrend_distance"] == 496.81
    assert payload["countertrend_weeks"] == 3
    assert payload["protrend_direction"] == "DOWN"
    assert payload["protrend_distance"] == 821.27
    assert payload["protrend_weeks"] == 7


def test_no_retracement_remains_zero_without_losing_protrend_leg() -> None:
    result = _result(FakeContext(_entry(
        depth_status="NO_RETRACEMENT",
        range2_opposite_anchor_price=3579.48,
        range2_continuation_anchor_price=4381.25,
        reclaim_depth_price=0,
        reclaim_depth_percent=0,
        weeks_reclaim_to_depth_anchor=17,
        range2_formation_weeks=6,
    )))
    payload = result["payload"]

    assert payload["countertrend_classification"] == "NO_RANGE1_RETRACEMENT"
    assert payload["countertrend_distance"] == 0
    assert payload["countertrend_depth_percent"] == 0
    assert payload["countertrend_weeks"] == 17
    assert payload["protrend_classification"] == "PROTREND_CONTINUATION"
    assert payload["protrend_distance"] == 801.77
    assert payload["protrend_weeks"] == 6


def test_same_w1_keeps_both_movements_but_marks_sequence_unordered() -> None:
    result = _result(FakeContext(_entry(
        range2_anchor_sequence="SAME_W1",
        range2_formation_weeks=0,
    )))
    payload = result["payload"]

    assert result["processing_status"] == "COMPLETE"
    assert payload["movement_sequence"] == "SAME_W1_MOVEMENTS"
    assert payload["protrend_weeks"] == 0
    assert payload["reason_codes"] == [
        "BOTH_MOVEMENTS_WITHIN_SAME_W1_SEQUENCE_UNORDERED"
    ]


def test_missing_or_pending_depth_memory_blocks_classification() -> None:
    missing = _result(FakeContext(None))
    pending = _result(FakeContext({
        "processing_status": "PENDING",
        "payload": {"depth_status": "PENDING"},
    }))

    assert missing["processing_status"] == "PENDING"
    assert missing["payload"]["reason_codes"] == [
        "APPROVED_WEEKLY_RECLAIM_DEPTH_MEMORY_MISSING"
    ]
    assert pending["processing_status"] == "PENDING"
    assert pending["payload"]["reason_codes"] == [
        "WEEKLY_RECLAIM_DEPTH_NOT_COMPLETE"
    ]
