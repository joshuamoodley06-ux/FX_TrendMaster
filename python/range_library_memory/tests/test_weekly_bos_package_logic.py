from __future__ import annotations

from range_library_memory.doctrine_packages import weekly_bos_v1, weekly_bos_v2


class FakeContext:
    def __init__(self, candles: list[dict]) -> None:
        self._candles = candles

    def selected_ranges(self, *, layer: str | None = None):
        assert layer == "WEEKLY"
        return ({
            "id": "weekly-1",
            "range_high": 100,
            "range_low": 90,
            "range_low_time": "2026-01-01T00:00:00Z",
            "range_high_time": "2026-01-05T00:00:00Z",
        },)

    def latest_candle_time(self, timeframe: str):
        assert timeframe == "W1"
        return "2026-01-26T00:00:00Z"

    def load_candles(self, *, timeframe: str, start_time: str, end_time: str):
        assert timeframe == "W1"
        return tuple(self._candles)


def test_weekly_v1_uses_expected_direction_while_v2_uses_first_future_wick() -> None:
    candles = [
        {"time": "2025-12-29T00:00:00Z", "open": 95, "high": 110, "low": 94, "close": 108},
        {"time": "2026-01-12T00:00:00Z", "open": 95, "high": 100, "low": 92, "close": 96},
        {"time": "2026-01-19T00:00:00Z", "open": 96, "high": 99, "low": 89, "close": 91},
        {"time": "2026-01-26T00:00:00Z", "open": 91, "high": 101, "low": 90, "close": 100},
    ]
    v1 = weekly_bos_v1.run(FakeContext(candles))["outputs"][0]
    v2 = weekly_bos_v2.run(FakeContext(candles))["outputs"][0]

    assert v1["processing_status"] == "COMPLETE"
    assert v1["payload"]["bos_direction"] == "BOS_UP"
    assert v1["payload"]["bos_time"] == "2026-01-26T00:00:00Z"

    assert v2["processing_status"] == "COMPLETE"
    assert v2["payload"]["expected_bos_direction"] == "BOS_UP"
    assert v2["payload"]["bos_direction"] == "BOS_DOWN"
    assert v2["payload"]["bos_time"] == "2026-01-19T00:00:00Z"


def test_weekly_wick_beyond_boundary_is_bos_and_exact_touch_is_not() -> None:
    touch_only = [
        {"time": "2026-01-12T00:00:00Z", "open": 95, "high": 100, "low": 92, "close": 96},
    ]
    breached = [
        {"time": "2026-01-12T00:00:00Z", "open": 95, "high": 100.01, "low": 92, "close": 96},
    ]

    pending = weekly_bos_v2.run(FakeContext(touch_only))["outputs"][0]
    complete = weekly_bos_v2.run(FakeContext(breached))["outputs"][0]

    assert pending["processing_status"] == "PENDING"
    assert complete["processing_status"] == "COMPLETE"
    assert complete["payload"]["bos_direction"] == "BOS_UP"


def test_weekly_v2_dual_boundary_wick_requires_review() -> None:
    candles = [
        {"time": "2026-01-12T00:00:00Z", "open": 95, "high": 101, "low": 89, "close": 96},
    ]
    result = weekly_bos_v2.run(FakeContext(candles))["outputs"][0]
    assert result["processing_status"] == "NEEDS_REVIEW"
    assert result["payload"]["reason_codes"] == ["BOTH_BOUNDARIES_BREACHED_SAME_W1"]
