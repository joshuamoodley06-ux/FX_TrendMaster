from __future__ import annotations

from range_library_memory.doctrine_packages import weekly_reclaim_depth


class FakeContext:
    def __init__(self, ranges: list[dict], memory: dict[str, dict]) -> None:
        self._ranges = ranges
        self._memory = memory

    def selected_ranges(self, *, layer: str | None = None):
        assert layer == "WEEKLY"
        return tuple(self._ranges)

    def approved_memory(self, canonical_range_id: str):
        return self._memory.get(canonical_range_id, {})


def _range(
    identity: str,
    *,
    high: float,
    low: float,
    high_time: str,
    low_time: str,
    active_from_time: str | None = None,
) -> dict:
    return {
        "id": identity,
        "structure_layer": "WEEKLY",
        "range_high": high,
        "range_low": low,
        "range_high_time": high_time,
        "range_low_time": low_time,
        "active_from_time": active_from_time,
    }


def _memory(
    *,
    direction: str,
    chronology: str,
    defined_at: str,
    bos_time: str | None,
    reclaim_status: str = "RECLAIMED",
    reclaim_abbreviation: str = "RECL",
    reclaim_time: str | None = "2026-01-12T00:00:00Z",
    weeks_to_reclaim: int | None = 0,
    processing_status: str = "COMPLETE",
) -> dict:
    return {
        "weekly_structure": {
            "processing_status": processing_status,
            "payload": {
                "chronology": chronology,
                "range_defined_at": defined_at,
                "bos_direction": direction if bos_time else None,
                "bos_time": bos_time,
            },
        },
        "weekly_reclaim": {
            "processing_status": "COMPLETE",
            "payload": {
                "reclaim_status": reclaim_status,
                "reclaim_abbreviation": reclaim_abbreviation,
                "reclaim_time": reclaim_time,
                "weeks_to_reclaim": weeks_to_reclaim,
            },
        },
    }


def _pending_memory(direction: str, chronology: str, defined_at: str) -> dict:
    return _memory(
        direction=direction,
        chronology=chronology,
        defined_at=defined_at,
        bos_time=None,
        processing_status="PENDING",
        reclaim_status="PENDING",
        reclaim_abbreviation="PEND",
        reclaim_time=None,
        weeks_to_reclaim=None,
    )


def _output(result: dict, identity: str) -> dict:
    return next(row for row in result["outputs"] if row["canonical_range_id"] == identity)


def test_bos_up_depth_ends_at_new_rl_and_later_rh_completes_range() -> None:
    ranges = [
        _range(
            "weekly-1", high=100, low=90,
            high_time="2026-01-05T00:00:00Z", low_time="2025-12-01T00:00:00Z",
            active_from_time="2026-01-05T00:00:00Z",
        ),
        _range(
            "weekly-2", high=110, low=95,
            high_time="2026-02-02T00:00:00Z", low_time="2026-01-19T00:00:00Z",
            active_from_time="2026-01-19T00:00:00Z",
        ),
    ]
    memory = {
        "weekly-1": _memory(
            direction="BOS_UP", chronology="RL_TO_RH",
            defined_at="2026-01-05T00:00:00Z", bos_time="2026-01-12T00:00:00Z",
            reclaim_time="2026-01-12T00:00:00Z",
        ),
        "weekly-2": _pending_memory("BOS_UP", "RL_TO_RH", "2026-02-02T00:00:00Z"),
    }

    payload = _output(
        weekly_reclaim_depth.run(FakeContext(ranges, memory)), "weekly-1"
    )["payload"]

    assert payload["range2_id"] == "weekly-2"
    assert payload["range2_selection_rule"] == (
        "FIRST_MAPPED_WEEKLY_RANGE_COMPLETED_AFTER_RECLAIM_WITH_NEW_OPPOSITE_ANCHOR"
    )
    assert payload["range2_chronology"] == "RL_TO_RH"
    assert payload["range2_anchor_sequence"] == "OPPOSITE_THEN_CONTINUATION"
    assert payload["depth_window_start_time"] == "2026-01-12T00:00:00Z"
    assert payload["depth_window_end_time"] == "2026-01-19T00:00:00Z"
    assert payload["range2_opposite_anchor_type"] == "RL"
    assert payload["range2_opposite_anchor_price"] == 95
    assert payload["range2_opposite_anchor_time"] == "2026-01-19T00:00:00Z"
    assert payload["range2_continuation_anchor_type"] == "RH"
    assert payload["range2_continuation_anchor_time"] == "2026-02-02T00:00:00Z"
    assert payload["range2_completion_anchor_type"] == "RH"
    assert payload["range2_completed_at"] == "2026-02-02T00:00:00Z"
    assert payload["range2_defined_at"] == "2026-02-02T00:00:00Z"
    assert payload["reclaim_depth_percent"] == 50
    assert payload["weeks_reclaim_to_depth_anchor"] == 1
    assert payload["weeks_reclaim_to_range2_completion"] == 3
    assert payload["range2_formation_weeks"] == 2


def test_bos_down_story_uses_new_rh_for_depth_then_new_rl_completes_range() -> None:
    ranges = [
        _range(
            "weekly-1", high=100, low=90,
            high_time="2025-12-01T00:00:00Z", low_time="2026-01-05T00:00:00Z",
        ),
        _range(
            "weekly-2", high=98, low=80,
            high_time="2026-01-12T00:00:00Z", low_time="2026-02-02T00:00:00Z",
            active_from_time="2026-01-12T00:00:00Z",
        ),
    ]
    memory = {
        "weekly-1": _memory(
            direction="BOS_DOWN", chronology="RH_TO_RL",
            defined_at="2026-01-05T00:00:00Z", bos_time="2026-01-05T00:00:00Z",
            reclaim_time="2026-01-05T00:00:00Z", weeks_to_reclaim=0,
        ),
        "weekly-2": _pending_memory("BOS_DOWN", "RH_TO_RL", "2026-02-02T00:00:00Z"),
    }

    payload = _output(
        weekly_reclaim_depth.run(FakeContext(ranges, memory)), "weekly-1"
    )["payload"]

    assert payload["fib_zero_price"] == 90
    assert payload["fib_one_price"] == 100
    assert payload["range2_chronology"] == "RH_TO_RL"
    assert payload["range2_anchor_sequence"] == "OPPOSITE_THEN_CONTINUATION"
    assert payload["range2_opposite_anchor_type"] == "RH"
    assert payload["range2_opposite_anchor_price"] == 98
    assert payload["depth_window_end_time"] == "2026-01-12T00:00:00Z"
    assert payload["range2_continuation_anchor_type"] == "RL"
    assert payload["range2_completion_anchor_type"] == "RL"
    assert payload["range2_completed_at"] == "2026-02-02T00:00:00Z"
    assert payload["depth_status"] == "RETRACED_INTO_RANGE"
    assert payload["reclaim_depth_percent"] == 80
    assert payload["weeks_reclaim_to_depth_anchor"] == 1
    assert payload["weeks_reclaim_to_range2_completion"] == 4
    assert payload["range2_formation_weeks"] == 3


def test_reclaim_can_create_opposite_anchor_and_complete_range_after_existing_continuation_anchor() -> None:
    ranges = [
        _range(
            "weekly-1", high=100, low=90,
            high_time="2026-01-05T00:00:00Z", low_time="2025-12-01T00:00:00Z",
        ),
        _range(
            "weekly-2", high=112, low=90,
            high_time="2026-01-05T00:00:00Z", low_time="2026-01-12T00:00:00Z",
            active_from_time="2026-01-05T00:00:00Z",
        ),
    ]
    memory = {
        "weekly-1": _memory(
            direction="BOS_UP", chronology="RL_TO_RH",
            defined_at="2026-01-05T00:00:00Z", bos_time="2026-01-05T00:00:00Z",
            reclaim_time="2026-01-12T00:00:00Z", weeks_to_reclaim=1,
        ),
        "weekly-2": _pending_memory("BOS_UP", "RH_TO_RL", "2026-01-12T00:00:00Z"),
    }

    payload = _output(
        weekly_reclaim_depth.run(FakeContext(ranges, memory)), "weekly-1"
    )["payload"]

    assert payload["range2_chronology"] == "RH_TO_RL"
    assert payload["range2_anchor_sequence"] == "CONTINUATION_THEN_OPPOSITE"
    assert payload["range2_opposite_anchor_type"] == "RL"
    assert payload["range2_opposite_anchor_time"] == "2026-01-12T00:00:00Z"
    assert payload["range2_completion_anchor_type"] == "RL"
    assert payload["range2_completed_at"] == "2026-01-12T00:00:00Z"
    assert payload["weeks_reclaim_to_depth_anchor"] == 0
    assert payload["weeks_reclaim_to_range2_completion"] == 0
    assert payload["depth_status"] == "TOUCHED_OLD_OPPOSITE"
    assert payload["reclaim_depth_percent"] == 100


def test_active_from_time_cannot_pretend_range_is_complete_before_second_anchor() -> None:
    ranges = [
        _range(
            "weekly-1", high=100, low=90,
            high_time="2026-01-05T00:00:00Z", low_time="2025-12-01T00:00:00Z",
        ),
        _range(
            "weekly-2", high=110, low=95,
            high_time="2026-01-25T00:00:00Z", low_time="2026-02-01T00:00:00Z",
            active_from_time="2026-01-25T00:00:00Z",
        ),
    ]
    memory = {
        "weekly-1": _memory(
            direction="BOS_UP", chronology="RL_TO_RH",
            defined_at="2026-01-05T00:00:00Z", bos_time="2025-12-21T00:00:00Z",
            reclaim_time="2025-12-28T00:00:00Z", weeks_to_reclaim=1,
        ),
        "weekly-2": _pending_memory("BOS_UP", "RH_TO_RL", "2026-02-01T00:00:00Z"),
    }

    payload = _output(
        weekly_reclaim_depth.run(FakeContext(ranges, memory)), "weekly-1"
    )["payload"]

    assert payload["range2_defined_at"] == "2026-02-01T00:00:00Z"
    assert payload["range2_completed_at"] == "2026-02-01T00:00:00Z"
    assert payload["range2_completion_anchor_type"] == "RL"
    assert payload["weeks_bos_to_range2_completion"] == 6
    assert payload["weeks_reclaim_to_range2_completion"] == 5
    assert payload["range2_formation_weeks"] == 1


def test_first_completed_range_is_selected_and_later_deeper_range_is_ignored() -> None:
    ranges = [
        _range(
            "weekly-1", high=100, low=90,
            high_time="2026-01-05T00:00:00Z", low_time="2025-12-01T00:00:00Z",
        ),
        _range(
            "weekly-2", high=112, low=95,
            high_time="2026-01-26T00:00:00Z", low_time="2026-01-12T00:00:00Z",
        ),
        _range(
            "weekly-3", high=120, low=70,
            high_time="2026-04-06T00:00:00Z", low_time="2026-03-02T00:00:00Z",
        ),
    ]
    memory = {
        "weekly-1": _memory(
            direction="BOS_UP", chronology="RL_TO_RH",
            defined_at="2026-01-05T00:00:00Z", bos_time="2026-01-12T00:00:00Z",
        ),
        "weekly-2": _pending_memory("BOS_UP", "RL_TO_RH", "2026-01-26T00:00:00Z"),
        "weekly-3": _pending_memory("BOS_UP", "RL_TO_RH", "2026-04-06T00:00:00Z"),
    }

    payload = _output(
        weekly_reclaim_depth.run(FakeContext(ranges, memory)), "weekly-1"
    )["payload"]

    assert payload["range2_id"] == "weekly-2"
    assert payload["range2_opposite_anchor_price"] == 95
    assert payload["reclaim_depth_percent"] == 50
    assert payload["range2_completed_at"] == "2026-01-26T00:00:00Z"


def test_no_retracement_is_zero_for_trader_but_raw_value_is_preserved() -> None:
    ranges = [
        _range(
            "weekly-1", high=100, low=90,
            high_time="2026-01-05T00:00:00Z", low_time="2025-12-01T00:00:00Z",
        ),
        _range(
            "weekly-2", high=112, low=102,
            high_time="2026-01-26T00:00:00Z", low_time="2026-01-12T00:00:00Z",
        ),
    ]
    memory = {
        "weekly-1": _memory(
            direction="BOS_UP", chronology="RL_TO_RH",
            defined_at="2026-01-05T00:00:00Z", bos_time="2026-01-12T00:00:00Z",
        ),
        "weekly-2": _pending_memory("BOS_UP", "RL_TO_RH", "2026-01-26T00:00:00Z"),
    }

    payload = _output(
        weekly_reclaim_depth.run(FakeContext(ranges, memory)), "weekly-1"
    )["payload"]

    assert payload["depth_classification"] == "NO_RETRACEMENT"
    assert payload["reclaim_depth_percent"] == 0
    assert payload["raw_reclaim_depth_percent"] == -20
    assert payload["boundary_distance_price"] == 2


def test_abandoned_without_later_reclaim_keeps_depth_pending() -> None:
    ranges = [
        _range(
            "weekly-1", high=100, low=90,
            high_time="2026-01-05T00:00:00Z", low_time="2025-12-01T00:00:00Z",
        ),
        _range(
            "weekly-2", high=110, low=80,
            high_time="2026-01-26T00:00:00Z", low_time="2026-01-19T00:00:00Z",
        ),
    ]
    memory = {
        "weekly-1": _memory(
            direction="BOS_UP", chronology="RL_TO_RH",
            defined_at="2026-01-05T00:00:00Z", bos_time="2026-01-12T00:00:00Z",
            reclaim_status="ABANDONED", reclaim_abbreviation="ABND",
            reclaim_time=None, weeks_to_reclaim=None,
        ),
    }

    row = _output(weekly_reclaim_depth.run(FakeContext(ranges, memory)), "weekly-1")

    assert row["processing_status"] == "PENDING"
    assert row["payload"]["reason_codes"] == ["RANGE2_DEPTH_WAITING_FOR_RECLAIM"]


def test_no_later_mapped_range_after_reclaim_keeps_depth_pending() -> None:
    ranges = [
        _range(
            "weekly-1", high=100, low=90,
            high_time="2026-01-05T00:00:00Z", low_time="2025-12-01T00:00:00Z",
        )
    ]
    memory = {
        "weekly-1": _memory(
            direction="BOS_UP", chronology="RL_TO_RH",
            defined_at="2026-01-05T00:00:00Z", bos_time="2026-01-12T00:00:00Z",
        )
    }

    row = _output(weekly_reclaim_depth.run(FakeContext(ranges, memory)), "weekly-1")

    assert row["processing_status"] == "PENDING"
    assert row["payload"]["depth_status"] == "PENDING"
    assert row["payload"]["reason_codes"] == ["RANGE2_NOT_YET_MAPPED_AFTER_RECLAIM"]
