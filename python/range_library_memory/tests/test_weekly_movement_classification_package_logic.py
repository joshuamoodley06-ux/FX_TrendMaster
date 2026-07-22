from __future__ import annotations

from range_library_memory.doctrine_packages import weekly_movement_classification


class FakeContext:
    def __init__(self, depth_entry: dict | None, candles: list[dict] | None = None) -> None:
        self._depth_entry = depth_entry
        self._candles = candles or []

    def selected_ranges(self, *, layer: str | None = None):
        assert layer == "WEEKLY"
        return ({"id": "range-1"},)

    def approved_memory(self, canonical_range_id: str):
        assert canonical_range_id == "range-1"
        if self._depth_entry is None:
            return {}
        return {"weekly_reclaim_depth": self._depth_entry}

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


def _entry(**payload) -> dict:
    base = {
        "depth_status": "RETRACED_INTO_RANGE",
        "source_bos_direction": "BOS_UP",
        "source_bos_time": "2024-01-07T00:00:00Z",
        "range2_id": "range-2",
        "range2_anchor_sequence": "OPPOSITE_THEN_CONTINUATION",
        "range2_opposite_anchor_price": 2353.06,
        "range2_opposite_anchor_time": "2024-01-21T00:00:00Z",
        "range2_continuation_anchor_price": 2450.01,
        "range2_continuation_anchor_time": "2024-01-28T00:00:00Z",
        "range2_completed_at": "2024-01-28T00:00:00Z",
        "reclaim_depth_price": 96.95,
        "reclaim_depth_percent": 56.14,
    }
    base.update(payload)
    return {"processing_status": "COMPLETE", "payload": base}


def _result(context: FakeContext) -> dict:
    return weekly_movement_classification.run(context)["outputs"][0]


def test_bos_up_counts_two_bearish_countertrend_candles_then_one_bullish_protrend() -> None:
    candles = [
        _candle("2024-01-07T00:00:00Z", 100, 112, 98, 110),
        _candle("2024-01-14T00:00:00Z", 110, 111, 101, 103),
        _candle("2024-01-21T00:00:00Z", 103, 105, 94, 96),
        _candle("2024-01-28T00:00:00Z", 96, 116, 95, 114),
    ]
    result = _result(FakeContext(_entry(), candles))
    payload = result["payload"]

    assert result["processing_status"] == "COMPLETE"
    assert payload["movement_sequence"] == "COUNTERTREND_THEN_PROTREND"
    assert payload["countertrend_classification"] == "COUNTERTREND_RETRACEMENT"
    assert payload["countertrend_direction"] == "DOWN"
    assert payload["countertrend_distance"] == 96.95
    assert payload["countertrend_depth_percent"] == 56.14
    assert payload["countertrend_weeks"] == 2
    assert payload["protrend_direction"] == "UP"
    assert payload["protrend_distance"] == 96.95
    assert payload["protrend_weeks"] == 1


def test_bos_down_counts_bearish_protrend_then_two_bullish_countertrend_candles() -> None:
    candles = [
        _candle("2024-01-07T00:00:00Z", 110, 112, 96, 98),
        _candle("2024-01-14T00:00:00Z", 98, 99, 88, 90),
        _candle("2024-01-21T00:00:00Z", 90, 101, 89, 99),
        _candle("2024-01-28T00:00:00Z", 99, 111, 97, 108),
    ]
    result = _result(FakeContext(_entry(
        source_bos_direction="BOS_DOWN",
        range2_anchor_sequence="CONTINUATION_THEN_OPPOSITE",
        range2_opposite_anchor_price=5092.91,
        range2_opposite_anchor_time="2024-01-28T00:00:00Z",
        range2_continuation_anchor_price=4271.64,
        range2_continuation_anchor_time="2024-01-14T00:00:00Z",
        range2_completed_at="2024-01-28T00:00:00Z",
        reclaim_depth_price=496.81,
        reclaim_depth_percent=37.4,
    ), candles))
    payload = result["payload"]

    assert payload["movement_sequence"] == "PROTREND_THEN_COUNTERTREND"
    assert payload["countertrend_direction"] == "UP"
    assert payload["countertrend_distance"] == 496.81
    assert payload["countertrend_weeks"] == 2
    assert payload["protrend_direction"] == "DOWN"
    assert payload["protrend_distance"] == 821.27
    assert payload["protrend_weeks"] == 1


def test_no_retracement_remains_zero_without_losing_ohlc_candle_counts() -> None:
    candles = [
        _candle("2024-01-07T00:00:00Z", 100, 112, 98, 110),
        _candle("2024-01-14T00:00:00Z", 110, 111, 101, 103),
        _candle("2024-01-21T00:00:00Z", 103, 105, 94, 96),
        _candle("2024-01-28T00:00:00Z", 96, 116, 95, 114),
    ]
    result = _result(FakeContext(_entry(
        depth_status="NO_RETRACEMENT",
        range2_opposite_anchor_price=3579.48,
        range2_continuation_anchor_price=4381.25,
        reclaim_depth_price=0,
        reclaim_depth_percent=0,
    ), candles))
    payload = result["payload"]

    assert payload["countertrend_classification"] == "NO_RANGE1_RETRACEMENT"
    assert payload["countertrend_distance"] == 0
    assert payload["countertrend_depth_percent"] == 0
    assert payload["countertrend_weeks"] == 2
    assert payload["protrend_distance"] == 801.77
    assert payload["protrend_weeks"] == 1


def test_same_w1_bearish_anchor_resolves_protrend_then_countertrend_and_counts_two_red_weeks() -> None:
    candles = [
        _candle("2024-01-07T00:00:00Z", 100, 112, 98, 110),
        _candle("2024-01-14T00:00:00Z", 110, 112, 101, 103),
        _candle("2024-01-21T00:00:00Z", 103, 108, 92, 95),
    ]
    result = _result(FakeContext(_entry(
        range2_anchor_sequence="SAME_W1",
        range2_opposite_anchor_time="2024-01-21T00:00:00Z",
        range2_continuation_anchor_time="2024-01-21T00:00:00Z",
        range2_completed_at="2024-01-21T00:00:00Z",
    ), candles))
    payload = result["payload"]

    assert result["processing_status"] == "COMPLETE"
    assert payload["movement_sequence"] == "PROTREND_THEN_COUNTERTREND"
    assert payload["countertrend_weeks"] == 2
    assert payload["protrend_weeks"] == 0
    assert payload["reason_codes"] == []


def test_same_w1_bullish_anchor_resolves_countertrend_then_protrend() -> None:
    candles = [
        _candle("2024-01-07T00:00:00Z", 100, 112, 98, 110),
        _candle("2024-01-14T00:00:00Z", 110, 112, 101, 103),
        _candle("2024-01-21T00:00:00Z", 103, 118, 96, 115),
    ]
    result = _result(FakeContext(_entry(
        range2_anchor_sequence="SAME_W1",
        range2_opposite_anchor_time="2024-01-21T00:00:00Z",
        range2_continuation_anchor_time="2024-01-21T00:00:00Z",
        range2_completed_at="2024-01-21T00:00:00Z",
    ), candles))
    payload = result["payload"]

    assert payload["movement_sequence"] == "COUNTERTREND_THEN_PROTREND"
    assert payload["countertrend_weeks"] == 1
    assert payload["protrend_weeks"] == 1


def test_same_w1_doji_stays_review_only_because_order_is_not_provable() -> None:
    candles = [
        _candle("2024-01-07T00:00:00Z", 100, 112, 98, 110),
        _candle("2024-01-14T00:00:00Z", 105, 115, 95, 105),
    ]
    result = _result(FakeContext(_entry(
        range2_anchor_sequence="SAME_W1",
        range2_opposite_anchor_time="2024-01-14T00:00:00Z",
        range2_continuation_anchor_time="2024-01-14T00:00:00Z",
        range2_completed_at="2024-01-14T00:00:00Z",
    ), candles))

    assert result["processing_status"] == "NEEDS_REVIEW"
    assert result["payload"]["reason_codes"] == [
        "SAME_W1_ORDER_NOT_PROVABLE_FROM_DOJI_OR_MISSING_CANDLE"
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
