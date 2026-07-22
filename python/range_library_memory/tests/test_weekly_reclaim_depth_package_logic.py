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
) -> dict:
    return {
        "id": identity,
        "structure_layer": "WEEKLY",
        "range_high": high,
        "range_low": low,
        "range_high_time": high_time,
        "range_low_time": low_time,
    }


def _memory(
    *,
    direction: str,
    chronology: str,
    defined_at: str,
    bos_time: str | None,
    reclaim_status: str = "RECLAIMED",
    reclaim_abbreviation: str = "RECL",
    reclaim_time: str | None = "2026-02-02T00:00:00Z",
    weeks_to_reclaim: int | None = 3,
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


def _output(result: dict, identity: str) -> dict:
    return next(row for row in result["outputs"] if row["canonical_range_id"] == identity)


def test_bos_up_measures_range2_rl_against_range1_fib() -> None:
    ranges = [
        _range(
            "weekly-1", high=100, low=90,
            high_time="2026-01-05T00:00:00Z", low_time="2025-12-01T00:00:00Z",
        ),
        _range(
            "weekly-2", high=110, low=92,
            high_time="2026-01-26T00:00:00Z", low_time="2026-01-05T00:00:00Z",
        ),
    ]
    memory = {
        "weekly-1": _memory(
            direction="BOS_UP", chronology="RL_TO_RH",
            defined_at="2026-01-05T00:00:00Z", bos_time="2026-01-12T00:00:00Z",
        ),
        "weekly-2": _memory(
            direction="BOS_UP", chronology="RL_TO_RH",
            defined_at="2026-01-26T00:00:00Z", bos_time=None,
            processing_status="PENDING", reclaim_status="PENDING",
            reclaim_abbreviation="PEND", reclaim_time=None, weeks_to_reclaim=None,
        ),
    }

    row = _output(weekly_reclaim_depth.run(FakeContext(ranges, memory)), "weekly-1")

    assert row["processing_status"] == "COMPLETE"
    payload = row["payload"]
    assert payload["range2_id"] == "weekly-2"
    assert payload["fib_zero_price"] == 100
    assert payload["fib_one_price"] == 90
    assert payload["range2_opposite_anchor_type"] == "RL"
    assert payload["range2_opposite_anchor_price"] == 92
    assert payload["range2_opposite_anchor_time"] == "2026-01-05T00:00:00Z"
    assert payload["range2_continuation_anchor_type"] == "RH"
    assert payload["range2_continuation_anchor_price"] == 110
    assert payload["reclaim_depth_price"] == 8
    assert payload["reclaim_depth_ratio"] == 0.8
    assert payload["reclaim_depth_percent"] == 80
    assert payload["weeks_bos_to_range2_definition"] == 2
    assert payload["range2_formation_weeks"] == 3


def test_bos_down_measures_range2_rh_against_range1_fib() -> None:
    ranges = [
        _range(
            "weekly-1", high=100, low=90,
            high_time="2025-12-01T00:00:00Z", low_time="2026-01-05T00:00:00Z",
        ),
        _range(
            "weekly-2", high=98, low=80,
            high_time="2026-01-05T00:00:00Z", low_time="2026-01-26T00:00:00Z",
        ),
    ]
    memory = {
        "weekly-1": _memory(
            direction="BOS_DOWN", chronology="RH_TO_RL",
            defined_at="2026-01-05T00:00:00Z", bos_time="2026-01-12T00:00:00Z",
        ),
        "weekly-2": _memory(
            direction="BOS_DOWN", chronology="RH_TO_RL",
            defined_at="2026-01-26T00:00:00Z", bos_time=None,
            processing_status="PENDING", reclaim_status="PENDING",
            reclaim_abbreviation="PEND", reclaim_time=None, weeks_to_reclaim=None,
        ),
    }

    row = _output(weekly_reclaim_depth.run(FakeContext(ranges, memory)), "weekly-1")

    payload = row["payload"]
    assert payload["fib_zero_price"] == 90
    assert payload["fib_one_price"] == 100
    assert payload["range2_opposite_anchor_type"] == "RH"
    assert payload["range2_opposite_anchor_price"] == 98
    assert payload["range2_continuation_anchor_type"] == "RL"
    assert payload["reclaim_depth_percent"] == 80


def test_range2_depth_is_not_clamped_above_one_hundred_percent() -> None:
    ranges = [
        _range(
            "weekly-1", high=100, low=90,
            high_time="2026-01-05T00:00:00Z", low_time="2025-12-01T00:00:00Z",
        ),
        _range(
            "weekly-2", high=110, low=88,
            high_time="2026-01-26T00:00:00Z", low_time="2026-01-05T00:00:00Z",
        ),
    ]
    memory = {
        "weekly-1": _memory(
            direction="BOS_UP", chronology="RL_TO_RH",
            defined_at="2026-01-05T00:00:00Z", bos_time="2026-01-12T00:00:00Z",
        ),
        "weekly-2": _memory(
            direction="BOS_UP", chronology="RL_TO_RH",
            defined_at="2026-01-26T00:00:00Z", bos_time=None,
            processing_status="PENDING", reclaim_status="PENDING",
            reclaim_abbreviation="PEND", reclaim_time=None, weeks_to_reclaim=None,
        ),
    }

    payload = _output(
        weekly_reclaim_depth.run(FakeContext(ranges, memory)), "weekly-1"
    )["payload"]

    assert payload["reclaim_depth_percent"] == 120
    assert payload["old_opposite_external_touched"] is True
    assert payload["old_opposite_external_exceeded"] is True


def test_abandoned_then_reclaimed_context_does_not_block_range2_depth() -> None:
    ranges = [
        _range(
            "weekly-1", high=100, low=90,
            high_time="2026-01-05T00:00:00Z", low_time="2025-12-01T00:00:00Z",
        ),
        _range(
            "weekly-2", high=110, low=95,
            high_time="2026-01-26T00:00:00Z", low_time="2026-01-05T00:00:00Z",
        ),
    ]
    memory = {
        "weekly-1": _memory(
            direction="BOS_UP", chronology="RL_TO_RH",
            defined_at="2026-01-05T00:00:00Z", bos_time="2026-01-12T00:00:00Z",
            reclaim_status="ABANDONED_THEN_RECLAIMED",
            reclaim_abbreviation="ABND→RECL",
            reclaim_time="2026-03-02T00:00:00Z", weeks_to_reclaim=7,
        ),
        "weekly-2": _memory(
            direction="BOS_UP", chronology="RL_TO_RH",
            defined_at="2026-01-26T00:00:00Z", bos_time=None,
            processing_status="PENDING", reclaim_status="PENDING",
            reclaim_abbreviation="PEND", reclaim_time=None, weeks_to_reclaim=None,
        ),
    }

    row = _output(weekly_reclaim_depth.run(FakeContext(ranges, memory)), "weekly-1")

    assert row["processing_status"] == "COMPLETE"
    assert row["payload"]["source_reclaim_abbreviation"] == "ABND→RECL"
    assert row["payload"]["source_weeks_to_reclaim"] == 7
    assert row["payload"]["reclaim_depth_percent"] == 50


def test_no_later_mapped_range_keeps_depth_pending() -> None:
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
    assert row["payload"]["reason_codes"] == ["RANGE2_NOT_YET_MAPPED"]
