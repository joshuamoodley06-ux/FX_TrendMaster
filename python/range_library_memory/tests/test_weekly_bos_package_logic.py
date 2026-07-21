from __future__ import annotations

from range_library_memory.doctrine_packages import weekly_bos


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


def test_weekly_bos_uses_first_future_wick_and_counts_only_until_bos() -> None:
    candles = [
        {"time": "2025-12-29T00:00:00Z", "open": 95, "high": 110, "low": 94, "close": 108},
        {"time": "2026-01-12T00:00:00Z", "open": 95, "high": 100, "low": 92, "close": 96},
        {"time": "2026-01-19T00:00:00Z", "open": 96, "high": 99, "low": 89, "close": 91},
        {"time": "2026-01-26T00:00:00Z", "open": 91, "high": 101, "low": 90, "close": 100},
    ]
    result = weekly_bos.run(FakeContext(candles))["outputs"][0]

    assert result["processing_status"] == "COMPLETE"
    assert result["payload"]["expected_bos_direction"] == "BOS_UP"
    assert result["payload"]["bos_direction"] == "BOS_DOWN"
    assert result["payload"]["bos_time"] == "2026-01-19T00:00:00Z"
    assert result["payload"]["candles_scanned"] == 2
    assert result["payload"]["weeks_to_bos"] == 2


def test_weekly_wick_beyond_boundary_is_bos_and_exact_touch_is_not() -> None:
    touch_only = [
        {"time": "2026-01-12T00:00:00Z", "open": 95, "high": 100, "low": 92, "close": 96},
    ]
    breached = [
        {"time": "2026-01-12T00:00:00Z", "open": 95, "high": 100.01, "low": 92, "close": 96},
    ]

    pending = weekly_bos.run(FakeContext(touch_only))["outputs"][0]
    complete = weekly_bos.run(FakeContext(breached))["outputs"][0]

    assert pending["processing_status"] == "PENDING"
    assert pending["payload"]["weeks_to_bos"] is None
    assert complete["processing_status"] == "COMPLETE"
    assert complete["payload"]["bos_direction"] == "BOS_UP"
    assert complete["payload"]["candles_scanned"] == 1
    assert complete["payload"]["weeks_to_bos"] == 1


def test_weekly_dual_boundary_wick_requires_review() -> None:
    candles = [
        {"time": "2026-01-12T00:00:00Z", "open": 95, "high": 101, "low": 89, "close": 96},
    ]
    result = weekly_bos.run(FakeContext(candles))["outputs"][0]
    assert result["processing_status"] == "NEEDS_REVIEW"
    assert result["payload"]["reason_codes"] == ["BOTH_BOUNDARIES_BREACHED_SAME_W1"]
    assert result["payload"]["candles_scanned"] == 1
    assert result["payload"]["weeks_to_bos"] is None
