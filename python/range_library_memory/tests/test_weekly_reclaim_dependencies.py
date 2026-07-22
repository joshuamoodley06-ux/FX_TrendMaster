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
            "processing_status": "COMPLETE",
            "payload": {
                "range_defined_at": defined_at,
                "bos_direction": direction,
                "bos_time": bos_time,
                "reason_codes": [],
            },
        }
    }


def test_reclaim_waits_for_approved_weekly_bos_memory() -> None:
    context = FakeContext(
        {},
        [{"time": "2026-01-19T00:00:00Z", "open": 100, "high": 111, "low": 99, "close": 105}],
    )

    result = weekly_reclaim.run(context)["outputs"][0]

    assert result["processing_status"] == "PENDING"
    assert result["payload"]["reason_codes"] == ["APPROVED_WEEKLY_BOS_MEMORY_MISSING"]


def test_reclaim_preserves_valid_pending_bos_as_pending() -> None:
    context = FakeContext(
        {
            "weekly-a": {
                "weekly_structure": {
                    "processing_status": "PENDING",
                    "payload": {
                        "range_defined_at": "2026-01-05T00:00:00Z",
                        "bos_direction": None,
                        "bos_time": None,
                        "reason_codes": ["WEEKLY_BOS_NOT_FOUND"],
                    },
                }
            }
        },
        [{"time": "2026-01-19T00:00:00Z", "open": 95, "high": 99, "low": 91, "close": 96}],
    )

    result = weekly_reclaim.run(context)["outputs"][0]

    assert result["processing_status"] == "PENDING"
    assert result["payload"]["source_bos_processing_status"] == "PENDING"
    assert result["payload"]["reason_codes"] == ["WEEKLY_BOS_STILL_PENDING"]


def test_reclaim_preserves_bos_review_state_instead_of_calling_memory_incomplete() -> None:
    context = FakeContext(
        {
            "weekly-a": {
                "weekly_structure": {
                    "processing_status": "NEEDS_REVIEW",
                    "payload": {
                        "range_defined_at": None,
                        "bos_direction": None,
                        "bos_time": None,
                        "reason_codes": ["BOTH_BOUNDARIES_BREACHED_SAME_W1"],
                    },
                }
            }
        },
        [{"time": "2026-01-19T00:00:00Z", "open": 95, "high": 99, "low": 91, "close": 96}],
    )

    result = weekly_reclaim.run(context)["outputs"][0]

    assert result["processing_status"] == "NEEDS_REVIEW"
    assert result["payload"]["source_bos_processing_status"] == "NEEDS_REVIEW"
    assert result["payload"]["reason_codes"] == ["WEEKLY_BOS_NEEDS_REVIEW"]


def test_reclaim_and_new_bos_on_same_w1_requires_review() -> None:
    memory = {
        "weekly-a": _bos("BOS_UP", "2026-01-05T00:00:00Z", "2026-01-12T00:00:00Z"),
        "weekly-b": _bos("BOS_UP", "2026-01-26T00:00:00Z", "2026-02-09T00:00:00Z"),
    }
    context = FakeContext(
        memory,
        [
            {"time": "2026-01-12T00:00:00Z", "open": 98, "high": 105, "low": 97, "close": 104},
            {"time": "2026-01-19T00:00:00Z", "open": 104, "high": 111, "low": 101, "close": 108},
            {"time": "2026-02-09T00:00:00Z", "open": 108, "high": 121, "low": 100, "close": 120},
        ],
    )

    result = weekly_reclaim.run(context)["outputs"][0]

    assert result["processing_status"] == "NEEDS_REVIEW"
    assert result["payload"]["reclaim_status"] == "NEEDS_REVIEW"
    assert result["payload"]["reclaim_time"] == "2026-02-09T00:00:00Z"
    assert result["payload"]["weeks_to_reclaim"] == 2
    assert result["payload"]["reason_codes"] == [
        "RECLAIM_AND_NEW_BOS_SAME_W1_ORDER_UNKNOWN"
    ]
