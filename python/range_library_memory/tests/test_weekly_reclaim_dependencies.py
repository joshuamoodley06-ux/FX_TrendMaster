from __future__ import annotations

from range_library_memory.doctrine_packages import weekly_reclaim


class FakeContext:
    def __init__(self, memory: dict[str, dict], candles: list[dict]) -> None:
        self._memory = memory
        self._candles = candles

    def selected_ranges(self, *, layer: str | None = None):
        assert layer == "WEEKLY"
        return (
            {"id": "weekly-a", "range_high": 100, "range_low": 90},
            {"id": "weekly-b", "range_high": 120, "range_low": 100},
        )

    def approved_memory(self, canonical_range_id: str):
        return self._memory.get(canonical_range_id, {})

    def latest_candle_time(self, timeframe: str):
        assert timeframe == "W1"
        return self._candles[-1]["time"] if self._candles else None

    def load_candles(self, *, timeframe: str, start_time: str, end_time: str):
        assert timeframe == "W1"
        return tuple(self._candles)


def _bos(direction: str, defined_at: str, bos_time: str) -> dict:
    return {
        "weekly_structure": {
            "payload": {
                "range_defined_at": defined_at,
                "bos_direction": direction,
                "bos_time": bos_time,
            }
        }
    }


def test_reclaim_waits_for_approved_weekly_bos_memory() -> None:
    context = FakeContext(
        {},
        [{"time": "2026-01-19T00:00:00Z", "high": 111, "low": 99}],
    )

    result = weekly_reclaim.run(context)["outputs"][0]

    assert result["processing_status"] == "PENDING"
    assert result["payload"]["reason_codes"] == ["APPROVED_WEEKLY_BOS_MEMORY_MISSING"]


def test_same_w1_candle_reclaim_and_new_bos_counts_as_reclaimed() -> None:
    memory = {
        "weekly-a": _bos("BOS_UP", "2026-01-05T00:00:00Z", "2026-01-12T00:00:00Z"),
        "weekly-b": _bos("BOS_UP", "2026-01-26T00:00:00Z", "2026-02-09T00:00:00Z"),
    }
    context = FakeContext(
        memory,
        [
            {"time": "2026-01-19T00:00:00Z", "high": 111, "low": 101},
            {"time": "2026-02-09T00:00:00Z", "high": 121, "low": 100},
        ],
    )

    result = weekly_reclaim.run(context)["outputs"][0]

    assert result["processing_status"] == "COMPLETE"
    assert result["payload"]["reclaim_status"] == "RECLAIMED"
    assert result["payload"]["reclaim_time"] == "2026-02-09T00:00:00Z"
    assert result["payload"]["weeks_to_reclaim"] == 2
