from __future__ import annotations

from range_library_memory.doctrine_packages import weekly_movement_classification


class FakeContext:
    def __init__(
        self,
        depth_entry: dict | None,
        next_bos_entry: dict | None = None,
        candles: list[dict] | None = None,
    ) -> None:
        self._depth_entry = depth_entry
        self._next_bos_entry = next_bos_entry
        self._candles = candles or []

    def selected_ranges(self, *, layer: str | None = None):
        assert layer == "WEEKLY"
        return ({"id": "range-1"},)

    def approved_memory(self, canonical_range_id: str):
        if canonical_range_id == "range-1":
            return (
                {"weekly_reclaim_depth": self._depth_entry}
                if self._depth_entry is not None
                else {}
            )
        if canonical_range_id == "range-2":
            return (
                {"weekly_structure": self._next_bos_entry}
                if self._next_bos_entry is not None
                else {}
            )
        return {}

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


def _depth(**payload) -> dict:
    base = {
        "depth_status": "RETRACED_INTO_RANGE",
        "source_bos_direction": "BOS_UP",
        "source_bos_time": "2024-01-07T00:00:00Z",
        "range2_id": "range-2",
        "range2_opposite_anchor_price": 2353.06,
        "range2_continuation_anchor_price": 2450.01,
        "reclaim_depth_price": 96.95,
        "reclaim_depth_percent": 56.14,
    }
    base.update(payload)
    return {"processing_status": "COMPLETE", "payload": base}


def _bos(
    direction: str = "BOS_UP",
    time: str = "2024-02-04T00:00:00Z",
    *,
    processing_status: str = "COMPLETE",
) -> dict:
    return {
        "processing_status": processing_status,
        "payload": {
            "bos_direction": direction,
            "bos_time": time if processing_status == "COMPLETE" else None,
        },
    }


def _result(context: FakeContext) -> dict:
    return weekly_movement_classification.run(context)["outputs"][0]


def test_preserves_ct_pt_ct_order_until_next_bos() -> None:
    candles = [
        _candle("2024-01-07T00:00:00Z", 100, 112, 98, 110),  # source BOS candle
        _candle("2024-01-14T00:00:00Z", 110, 111, 101, 103),  # CT
        _candle("2024-01-21T00:00:00Z", 103, 116, 101, 114),  # PT
        _candle("2024-01-28T00:00:00Z", 114, 115, 104, 106),  # CT
        _candle("2024-02-04T00:00:00Z", 106, 125, 105, 122),  # next BOS
    ]
    result = _result(FakeContext(_depth(), _bos(), candles))
    payload = result["payload"]

    assert result["processing_status"] == "COMPLETE"
    assert payload["movement_path"] == "CT 1W -> PT 1W -> CT 1W -> BOS_UP"
    assert payload["movement_sequence"] == (
        "COUNTERTREND_THEN_PROTREND_THEN_COUNTERTREND"
    )
    assert payload["movement_leg_count"] == 3
    assert payload["countertrend_leg_count"] == 2
    assert payload["protrend_leg_count"] == 1
    assert payload["countertrend_weeks"] == 2
    assert payload["protrend_weeks"] == 1
    assert payload["next_bos_direction"] == "BOS_UP"
    assert payload["next_bos_time"] == "2024-02-04T00:00:00Z"
    assert [leg["code"] for leg in payload["movement_legs"]] == ["CT", "PT", "CT"]
    assert [leg["weeks"] for leg in payload["movement_legs"]] == [1, 1, 1]


def test_groups_only_consecutive_candles_into_one_leg() -> None:
    candles = [
        _candle("2024-01-07T00:00:00Z", 100, 112, 98, 110),
        _candle("2024-01-14T00:00:00Z", 110, 111, 101, 103),
        _candle("2024-01-21T00:00:00Z", 103, 105, 94, 96),
        _candle("2024-01-28T00:00:00Z", 96, 116, 95, 114),
        _candle("2024-02-04T00:00:00Z", 114, 125, 110, 122),
    ]
    result = _result(FakeContext(_depth(), _bos(), candles))
    payload = result["payload"]

    assert payload["movement_path"] == "CT 2W -> PT 1W -> BOS_UP"
    assert payload["movement_leg_count"] == 2
    assert payload["countertrend_leg_count"] == 1
    assert payload["countertrend_weeks"] == 2
    assert payload["protrend_weeks"] == 1
    assert payload["movement_legs"][0]["start_time"] == "2024-01-14T00:00:00Z"
    assert payload["movement_legs"][0]["end_time"] == "2024-01-21T00:00:00Z"


def test_bos_down_reverses_countertrend_and_protrend_candle_roles() -> None:
    candles = [
        _candle("2024-01-07T00:00:00Z", 110, 112, 96, 98),
        _candle("2024-01-14T00:00:00Z", 98, 99, 88, 90),   # PT
        _candle("2024-01-21T00:00:00Z", 90, 101, 89, 99),  # CT
        _candle("2024-01-28T00:00:00Z", 99, 111, 97, 108), # CT
        _candle("2024-02-04T00:00:00Z", 108, 109, 84, 88), # next BOS
    ]
    result = _result(FakeContext(
        _depth(
            source_bos_direction="BOS_DOWN",
            range2_opposite_anchor_price=5092.91,
            range2_continuation_anchor_price=4271.64,
            reclaim_depth_price=496.81,
            reclaim_depth_percent=37.4,
        ),
        _bos("BOS_DOWN"),
        candles,
    ))
    payload = result["payload"]

    assert payload["movement_path"] == "PT 1W -> CT 2W -> BOS_DOWN"
    assert payload["countertrend_direction"] == "UP"
    assert payload["protrend_direction"] == "DOWN"
    assert payload["countertrend_weeks"] == 2
    assert payload["protrend_weeks"] == 1


def test_no_retracement_keeps_zero_depth_but_preserves_ordered_path() -> None:
    candles = [
        _candle("2024-01-07T00:00:00Z", 100, 112, 98, 110),
        _candle("2024-01-14T00:00:00Z", 110, 111, 101, 103),
        _candle("2024-01-21T00:00:00Z", 103, 116, 101, 114),
        _candle("2024-01-28T00:00:00Z", 114, 125, 110, 122),
    ]
    result = _result(FakeContext(
        _depth(
            depth_status="NO_RETRACEMENT",
            range2_opposite_anchor_price=3579.48,
            range2_continuation_anchor_price=4381.25,
            reclaim_depth_price=0,
            reclaim_depth_percent=0,
        ),
        _bos(time="2024-01-28T00:00:00Z"),
        candles,
    ))
    payload = result["payload"]

    assert payload["movement_path"] == "CT 1W -> PT 1W -> BOS_UP"
    assert payload["countertrend_classification"] == "NO_RANGE1_RETRACEMENT"
    assert payload["countertrend_distance"] == 0
    assert payload["countertrend_depth_percent"] == 0
    assert payload["protrend_distance"] == 801.77


def test_next_range_without_complete_bos_remains_pending() -> None:
    result = _result(FakeContext(
        _depth(),
        _bos(processing_status="PENDING"),
        [],
    ))

    assert result["processing_status"] == "PENDING"
    assert result["payload"]["reason_codes"] == ["RANGE2_BOS_STILL_PENDING"]


def test_doji_inside_movement_chapter_requires_review() -> None:
    candles = [
        _candle("2024-01-07T00:00:00Z", 100, 112, 98, 110),
        _candle("2024-01-14T00:00:00Z", 105, 115, 95, 105),
        _candle("2024-01-21T00:00:00Z", 105, 120, 100, 118),
    ]
    result = _result(FakeContext(
        _depth(),
        _bos(time="2024-01-21T00:00:00Z"),
        candles,
    ))

    assert result["processing_status"] == "NEEDS_REVIEW"
    assert result["payload"]["reason_codes"] == [
        "DOJI_W1_MOVEMENT_ROLE_NOT_DEFINED"
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
