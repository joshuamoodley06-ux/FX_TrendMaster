from __future__ import annotations

from range_library_memory.doctrine_packages import weekly_movement_classification


class FakeContext:
    def __init__(
        self,
        memories: dict[str, dict],
        candles: list[dict] | None = None,
    ) -> None:
        self._memories = memories
        self._candles = candles or []

    def selected_ranges(self, *, layer: str | None = None):
        assert layer == "WEEKLY"
        return tuple({"id": identity} for identity in self._memories)

    def approved_memory(self, canonical_range_id: str):
        return self._memories.get(canonical_range_id, {})

    def load_candles(self, *, timeframe: str, start_time: str, end_time: str):
        assert timeframe == "W1"
        assert start_time
        assert end_time
        return tuple(self._candles)


def _candle(time: str, open_price: float, high: float, low: float, close: float) -> dict:
    return {
        "time": time,
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
    }


def _entry(payload: dict, processing: str = "COMPLETE") -> dict:
    return {"processing_status": processing, "payload": payload}


def _bos(direction: str, time: str, processing: str = "COMPLETE") -> dict:
    return _entry({"bos_direction": direction, "bos_time": time}, processing)


def _pending_depth() -> dict:
    return _entry({"depth_status": "PENDING"}, "PENDING")


def _complete_depth(**overrides) -> dict:
    payload = {
        "depth_status": "RETRACED_INTO_RANGE",
        "range2_id": "range-2",
        "range2_opposite_anchor_price": 2353.06,
        "range2_continuation_anchor_price": 2450.01,
        "reclaim_depth_price": 96.95,
        "reclaim_depth_percent": 56.14,
    }
    payload.update(overrides)
    return _entry(payload)


def _result(context: FakeContext, identity: str = "range-1") -> dict:
    outputs = weekly_movement_classification.run(context)["outputs"]
    return next(row for row in outputs if row["canonical_range_id"] == identity)


def test_movement_count_starts_at_bos_while_reclaim_depth_is_still_pending() -> None:
    memories = {
        "range-1": {
            "weekly_structure": _bos("BOS_UP", "2024-01-07T00:00:00Z"),
            "weekly_reclaim_depth": _pending_depth(),
        },
        "range-2": {
            "weekly_structure": _bos("BOS_UP", "2024-02-04T00:00:00Z"),
        },
    }
    candles = [
        _candle("2024-01-07T00:00:00Z", 100, 112, 98, 110),
        _candle("2024-01-14T00:00:00Z", 110, 111, 101, 103),
        _candle("2024-01-21T00:00:00Z", 103, 113, 102, 111),
        _candle("2024-01-28T00:00:00Z", 111, 112, 99, 101),
        _candle("2024-02-04T00:00:00Z", 101, 125, 100, 120),
    ]

    result = _result(FakeContext(memories, candles))
    payload = result["payload"]

    assert result["processing_status"] == "COMPLETE"
    assert payload["movement_path"] == "CT 1W -> PT 1W -> CT 1W -> BOS_UP"
    assert payload["movement_sequence"] == (
        "COUNTERTREND_THEN_PROTREND_THEN_COUNTERTREND"
    )
    assert payload["countertrend_leg_count"] == 2
    assert payload["countertrend_weeks"] == 2
    assert payload["protrend_leg_count"] == 1
    assert payload["protrend_weeks"] == 1
    assert payload["countertrend_classification"] == "COUNTERTREND_LEG_DEPTH_PENDING"
    assert payload["reclaim_depth_status"] == "PENDING"
    assert payload["countertrend_distance"] is None
    assert payload["countertrend_depth_percent"] is None
    assert payload["protrend_distance"] is None
    assert payload["next_bos_time"] == "2024-02-04T00:00:00Z"
    assert payload["range2_id"] == "range-2"


def test_complete_depth_enriches_an_already_counted_movement_path() -> None:
    memories = {
        "range-1": {
            "weekly_structure": _bos("BOS_UP", "2024-01-07T00:00:00Z"),
            "weekly_reclaim_depth": _complete_depth(),
        },
        "range-2": {
            "weekly_structure": _bos("BOS_UP", "2024-01-28T00:00:00Z"),
        },
    }
    candles = [
        _candle("2024-01-07T00:00:00Z", 100, 112, 98, 110),
        _candle("2024-01-14T00:00:00Z", 110, 111, 101, 103),
        _candle("2024-01-21T00:00:00Z", 103, 113, 102, 111),
        _candle("2024-01-28T00:00:00Z", 111, 125, 109, 120),
    ]

    result = _result(FakeContext(memories, candles))
    payload = result["payload"]

    assert result["processing_status"] == "COMPLETE"
    assert payload["movement_path"] == "CT 1W -> PT 1W -> BOS_UP"
    assert payload["countertrend_classification"] == "COUNTERTREND_RETRACEMENT"
    assert payload["reclaim_depth_status"] == "RETRACED_INTO_RANGE"
    assert payload["countertrend_distance"] == 96.95
    assert payload["countertrend_depth_percent"] == 56.14
    assert payload["protrend_distance"] == 96.95


def test_bos_down_reverses_countertrend_and_protrend_candle_roles() -> None:
    memories = {
        "range-1": {
            "weekly_structure": _bos("BOS_DOWN", "2024-01-07T00:00:00Z"),
            "weekly_reclaim_depth": _pending_depth(),
        },
        "range-2": {
            "weekly_structure": _bos("BOS_DOWN", "2024-01-28T00:00:00Z"),
        },
    }
    candles = [
        _candle("2024-01-07T00:00:00Z", 110, 112, 96, 98),
        _candle("2024-01-14T00:00:00Z", 98, 108, 97, 106),
        _candle("2024-01-21T00:00:00Z", 106, 107, 94, 96),
        _candle("2024-01-28T00:00:00Z", 96, 98, 82, 85),
    ]

    result = _result(FakeContext(memories, candles))

    assert result["payload"]["movement_path"] == "CT 1W -> PT 1W -> BOS_DOWN"
    assert result["payload"]["countertrend_direction"] == "UP"
    assert result["payload"]["protrend_direction"] == "DOWN"


def test_next_bos_candle_is_terminal_and_not_counted_as_a_leg() -> None:
    memories = {
        "range-1": {
            "weekly_structure": _bos("BOS_UP", "2024-01-07T00:00:00Z"),
            "weekly_reclaim_depth": _pending_depth(),
        },
        "range-2": {
            "weekly_structure": _bos("BOS_UP", "2024-01-28T00:00:00Z"),
        },
    }
    candles = [
        _candle("2024-01-07T00:00:00Z", 100, 112, 98, 110),
        _candle("2024-01-14T00:00:00Z", 110, 111, 101, 103),
        _candle("2024-01-21T00:00:00Z", 103, 113, 102, 111),
        _candle("2024-01-28T00:00:00Z", 111, 130, 110, 129),
    ]

    result = _result(FakeContext(memories, candles))

    assert result["payload"]["movement_path"] == "CT 1W -> PT 1W -> BOS_UP"
    assert result["payload"]["protrend_weeks"] == 1
    assert all(
        "2024-01-28T00:00:00Z" not in leg["candle_times"]
        for leg in result["payload"]["movement_legs"]
    )


def test_missing_next_bos_keeps_the_chapter_pending() -> None:
    memories = {
        "range-1": {
            "weekly_structure": _bos("BOS_UP", "2024-01-07T00:00:00Z"),
            "weekly_reclaim_depth": _pending_depth(),
        },
        "range-2": {
            "weekly_structure": _entry(
                {"bos_direction": None, "bos_time": None},
                "PENDING",
            ),
        },
    }

    result = _result(FakeContext(memories))

    assert result["processing_status"] == "PENDING"
    assert result["payload"]["reason_codes"] == [
        "NEXT_APPROVED_WEEKLY_BOS_NOT_AVAILABLE"
    ]


def test_doji_inside_a_completed_bos_chapter_requires_review() -> None:
    memories = {
        "range-1": {
            "weekly_structure": _bos("BOS_UP", "2024-01-07T00:00:00Z"),
            "weekly_reclaim_depth": _pending_depth(),
        },
        "range-2": {
            "weekly_structure": _bos("BOS_UP", "2024-01-21T00:00:00Z"),
        },
    }
    candles = [
        _candle("2024-01-07T00:00:00Z", 100, 112, 98, 110),
        _candle("2024-01-14T00:00:00Z", 105, 115, 95, 105),
        _candle("2024-01-21T00:00:00Z", 105, 125, 104, 120),
    ]

    result = _result(FakeContext(memories, candles))

    assert result["processing_status"] == "NEEDS_REVIEW"
    assert result["payload"]["reason_codes"] == [
        "DOJI_W1_MOVEMENT_ROLE_NOT_DEFINED"
    ]


def test_missing_source_bos_memory_blocks_the_chapter() -> None:
    memories = {
        "range-1": {
            "weekly_reclaim_depth": _pending_depth(),
        },
        "range-2": {
            "weekly_structure": _bos("BOS_UP", "2024-01-21T00:00:00Z"),
        },
    }

    result = _result(FakeContext(memories))

    assert result["processing_status"] == "PENDING"
    assert result["payload"]["reason_codes"] == [
        "APPROVED_WEEKLY_BOS_MEMORY_MISSING"
    ]
