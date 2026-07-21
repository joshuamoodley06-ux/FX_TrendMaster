from __future__ import annotations

from range_library_memory.doctrine_packages import weekly_reclaim_depth


class FakeContext:
    def __init__(self, memory: dict, candles: list[dict]) -> None:
        self._memory = memory
        self._candles = candles

    def selected_ranges(self, *, layer: str | None = None):
        assert layer == "WEEKLY"
        return ({
            "id": "weekly-a",
            "structure_layer": "WEEKLY",
            "range_high": 100,
            "range_low": 90,
        },)

    def approved_memory(self, canonical_range_id: str):
        assert canonical_range_id == "weekly-a"
        return self._memory

    def latest_candle_time(self, timeframe: str):
        assert timeframe == "W1"
        return self._candles[-1]["time"] if self._candles else None

    def load_candles(self, *, timeframe: str, start_time: str, end_time: str):
        assert timeframe == "W1"
        return tuple(self._candles)


def _memory(
    *,
    direction: str,
    reclaim_status: str = "RECLAIMED",
    reclaim_time: str = "2026-01-12T00:00:00Z",
    next_bos_time: str | None = None,
) -> dict:
    boundary = 100 if direction == "BOS_UP" else 90
    return {
        "weekly_structure": {
            "payload": {
                "bos_direction": direction,
                "bos_time": "2026-01-05T00:00:00Z",
            }
        },
        "weekly_reclaim": {
            "payload": {
                "reclaim_status": reclaim_status,
                "reclaim_time": reclaim_time if reclaim_status == "RECLAIMED" else None,
                "reclaim_boundary": boundary,
                "next_bos_time": next_bos_time,
            }
        },
    }


def test_bullish_reclaim_depth_is_continuous_percentage_of_old_weekly_range() -> None:
    context = FakeContext(
        _memory(direction="BOS_UP"),
        [
            {"time": "2026-01-12T00:00:00Z", "open": 105, "high": 108, "low": 99, "close": 104},
            {"time": "2026-01-19T00:00:00Z", "open": 104, "high": 106, "low": 95, "close": 101},
            {"time": "2026-01-26T00:00:00Z", "open": 101, "high": 109, "low": 97, "close": 107},
        ],
    )

    result = weekly_reclaim_depth.run(context)["outputs"][0]

    assert result["processing_status"] == "COMPLETE"
    assert result["payload"]["depth_status"] == "MEASURED"
    assert result["payload"]["deepest_wick_price"] == 95
    assert result["payload"]["deepest_wick_time"] == "2026-01-19T00:00:00Z"
    assert result["payload"]["reclaim_depth_price"] == 5
    assert result["payload"]["reclaim_depth_percent"] == 50
    assert result["payload"]["weeks_observed"] == 3


def test_bearish_reclaim_depth_measures_up_from_old_low() -> None:
    context = FakeContext(
        _memory(direction="BOS_DOWN"),
        [
            {"time": "2026-01-12T00:00:00Z", "open": 85, "high": 91, "low": 80, "close": 84},
            {"time": "2026-01-19T00:00:00Z", "open": 84, "high": 96, "low": 82, "close": 90},
        ],
    )

    result = weekly_reclaim_depth.run(context)["outputs"][0]

    assert result["processing_status"] == "COMPLETE"
    assert result["payload"]["deepest_wick_price"] == 96
    assert result["payload"]["reclaim_depth_price"] == 6
    assert result["payload"]["reclaim_depth_percent"] == 60


def test_depth_can_exceed_one_hundred_percent_when_old_opposite_external_breaks() -> None:
    context = FakeContext(
        _memory(direction="BOS_UP"),
        [
            {"time": "2026-01-12T00:00:00Z", "open": 105, "high": 108, "low": 99, "close": 104},
            {"time": "2026-01-19T00:00:00Z", "open": 104, "high": 106, "low": 89, "close": 93},
        ],
    )

    result = weekly_reclaim_depth.run(context)["outputs"][0]

    assert result["payload"]["reclaim_depth_percent"] == 110
    assert result["payload"]["old_opposite_external_touched"] is True
    assert result["payload"]["old_opposite_external_exceeded"] is True


def test_measurement_stops_at_next_weekly_bos() -> None:
    context = FakeContext(
        _memory(direction="BOS_UP", next_bos_time="2026-01-19T00:00:00Z"),
        [
            {"time": "2026-01-12T00:00:00Z", "open": 105, "high": 108, "low": 99, "close": 104},
            {"time": "2026-01-19T00:00:00Z", "open": 104, "high": 106, "low": 95, "close": 101},
            {"time": "2026-01-26T00:00:00Z", "open": 101, "high": 103, "low": 89, "close": 92},
        ],
    )

    result = weekly_reclaim_depth.run(context)["outputs"][0]

    assert result["payload"]["measurement_end_time"] == "2026-01-19T00:00:00Z"
    assert result["payload"]["deepest_wick_price"] == 95
    assert result["payload"]["reclaim_depth_percent"] == 50
    assert result["payload"]["weeks_observed"] == 2


def test_abandoned_before_reclaim_has_no_depth_measurement() -> None:
    context = FakeContext(
        _memory(direction="BOS_UP", reclaim_status="ABANDONED"),
        [{"time": "2026-01-19T00:00:00Z", "open": 105, "high": 110, "low": 101, "close": 108}],
    )

    result = weekly_reclaim_depth.run(context)["outputs"][0]

    assert result["processing_status"] == "COMPLETE"
    assert result["payload"]["depth_status"] == "NOT_APPLICABLE_ABANDONED"
    assert result["payload"]["reclaim_depth_percent"] is None
