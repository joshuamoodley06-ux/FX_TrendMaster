from __future__ import annotations

from range_library_memory.doctrine_packages import weekly_reclaim


class FakeContext:
    def __init__(self, ranges: list[dict], memory: dict[str, dict], candles: list[dict]) -> None:
        self._ranges = ranges
        self._memory = memory
        self._candles = candles

    def selected_ranges(self, *, layer: str | None = None):
        assert layer == "WEEKLY"
        return tuple(self._ranges)

    def approved_memory(self, canonical_range_id: str):
        return self._memory.get(canonical_range_id, {})

    def latest_candle_time(self, timeframe: str):
        assert timeframe == "W1"
        return self._candles[-1]["time"] if self._candles else None

    def load_candles(self, *, timeframe: str, start_time: str, end_time: str):
        assert timeframe == "W1"
        return tuple(self._candles)


def _range(identity: str, *, high: float = 100, low: float = 90) -> dict:
    return {
        "id": identity,
        "range_high": high,
        "range_low": low,
        "structure_layer": "WEEKLY",
    }


def _bos(
    *,
    direction: str,
    defined_at: str,
    bos_time: str,
) -> dict:
    return {
        "weekly_structure": {
            "version_label": "2",
            "payload": {
                "range_defined_at": defined_at,
                "bos_direction": direction,
                "bos_time": bos_time,
            },
        }
    }


def test_bullish_bos_reclaims_on_exact_wick_touch_of_old_high() -> None:
    context = FakeContext(
        [_range("weekly-a")],
        {
            "weekly-a": _bos(
                direction="BOS_UP",
                defined_at="2026-01-05T00:00:00Z",
                bos_time="2026-01-12T00:00:00Z",
            )
        },
        [
            {"time": "2026-01-19T00:00:00Z", "open": 105, "high": 110, "low": 101, "close": 107},
            {"time": "2026-01-26T00:00:00Z", "open": 107, "high": 111, "low": 100, "close": 109},
        ],
    )

    result = weekly_reclaim.run(context)["outputs"][0]

    assert result["processing_status"] == "COMPLETE"
    assert result["payload"]["reclaim_status"] == "RECLAIMED"
    assert result["payload"]["reclaim_boundary"] == 100
    assert result["payload"]["reclaim_time"] == "2026-01-26T00:00:00Z"
    assert result["payload"]["weeks_to_reclaim"] == 2
    assert result["payload"]["candles_scanned"] == 2


def test_bearish_bos_reclaims_on_exact_wick_touch_of_old_low() -> None:
    context = FakeContext(
        [_range("weekly-a")],
        {
            "weekly-a": _bos(
                direction="BOS_DOWN",
                defined_at="2026-01-05T00:00:00Z",
                bos_time="2026-01-12T00:00:00Z",
            )
        },
        [
            {"time": "2026-01-19T00:00:00Z", "open": 85, "high": 89, "low": 80, "close": 83},
            {"time": "2026-01-26T00:00:00Z", "open": 83, "high": 90, "low": 79, "close": 82},
        ],
    )

    result = weekly_reclaim.run(context)["outputs"][0]

    assert result["processing_status"] == "COMPLETE"
    assert result["payload"]["reclaim_status"] == "RECLAIMED"
    assert result["payload"]["reclaim_boundary"] == 90
    assert result["payload"]["reclaim_time"] == "2026-01-26T00:00:00Z"
    assert result["payload"]["weeks_to_reclaim"] == 2


def test_new_later_weekly_bos_before_reclaim_marks_old_range_abandoned() -> None:
    context = FakeContext(
        [_range("weekly-a"), _range("weekly-b", high=120, low=100)],
        {
            "weekly-a": _bos(
                direction="BOS_UP",
                defined_at="2026-01-05T00:00:00Z",
                bos_time="2026-01-12T00:00:00Z",
            ),
            "weekly-b": _bos(
                direction="BOS_UP",
                defined_at="2026-01-26T00:00:00Z",
                bos_time="2026-02-09T00:00:00Z",
            ),
        },
        [
            {"time": "2026-01-19T00:00:00Z", "open": 105, "high": 111, "low": 101, "close": 108},
            {"time": "2026-01-26T00:00:00Z", "open": 108, "high": 115, "low": 102, "close": 112},
            {"time": "2026-02-02T00:00:00Z", "open": 112, "high": 119, "low": 103, "close": 117},
            {"time": "2026-02-09T00:00:00Z", "open": 117, "high": 121, "low": 104, "close": 120},
        ],
    )

    result = weekly_reclaim.run(context)["outputs"][0]

    assert result["processing_status"] == "COMPLETE"
    assert result["payload"]["reclaim_status"] == "ABANDONED"
    assert result["payload"]["next_bos_range_id"] == "weekly-b"
    assert result["payload"]["next_bos_time"] == "2026-02-09T00:00:00Z"
    assert result["payload"]["weeks_to_abandonment"] == 4
    assert result["payload"]["reason_codes"] == ["NEW_WEEKLY_BOS_BEFORE_RECLAIM"]


def test_no_reclaim_and_no_new_bos_remains_pending() -> None:
    context = FakeContext(
        [_range("weekly-a")],
        {
            "weekly-a": _bos(
                direction="BOS_UP",
                defined_at="2026-01-05T00:00:00Z",
                bos_time="2026-01-12T00:00:00Z",
            )
        },
        [
            {"time": "2026-01-19T00:00:00Z", "open": 105, "high": 111, "low": 101, "close": 108},
            {"time": "2026-01-26T00:00:00Z", "open": 108, "high": 115, "low": 102, "close": 112},
        ],
    )

    result = weekly_reclaim.run(context)["outputs"][0]

    assert result["processing_status"] == "PENDING"
    assert result["payload"]["reclaim_status"] == "PENDING"
    assert result["payload"]["candles_scanned"] == 2
    assert result["payload"]["weeks_to_reclaim"] is None
    assert result["payload"]["reason_codes"] == ["RECLAIM_NOT_YET_PROVEN"]
