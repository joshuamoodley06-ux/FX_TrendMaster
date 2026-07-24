from __future__ import annotations

from range_library_memory.doctrine_packages import weekly_extreme_rejection_destination


class FakeContext:
    def __init__(self, candles: list[dict]) -> None:
        self._candles = candles

    def selected_ranges(self, *, layer: str | None = None):
        assert layer == "WEEKLY"
        return ({
            "id": "range-1",
            "range_low": 0,
            "range_high": 100,
            "range_low_time": "2024-01-01T00:00:00Z",
            "range_high_time": "2024-01-08T00:00:00Z",
        },)

    def latest_candle_time(self, timeframe: str):
        assert timeframe == "W1"
        return self._candles[-1]["time"] if self._candles else None

    def load_candles(self, *, timeframe: str, start_time: str, end_time: str):
        assert timeframe == "W1"
        assert start_time == "2024-01-08T00:00:00Z"
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


def _result(candles: list[dict]) -> dict:
    return weekly_extreme_rejection_destination.run(FakeContext(candles))["outputs"][0]


def _primary(result: dict) -> dict:
    return result["payload"]["rejection_events"][0]


def test_discount_rejection_reaches_fair_price_then_origin_breaks() -> None:
    result = _result([
        _candle("2024-01-15T00:00:00Z", 30, 35, 20, 30),
        _candle("2024-01-22T00:00:00Z", 30, 55, 28, 50),
        _candle("2024-01-29T00:00:00Z", 50, 60, -1, 10),
    ])
    event = _primary(result)

    assert result["processing_status"] == "COMPLETE"
    assert event["origin_zone"] == "DISCOUNT_EXTREME"
    assert event["maximum_destination"] == "FAIR_PRICE"
    assert event["fair_price_reached"] is True
    assert event["weeks_to_fair_price"] == 1
    assert event["opposite_extreme_reached"] is False
    assert event["opposite_external_reached"] is False
    assert event["terminal_reason"] == "ORIGIN_EXTERNAL_BROKEN"


def test_discount_rejection_reaches_opposite_extreme_before_origin_break() -> None:
    result = _result([
        _candle("2024-01-15T00:00:00Z", 30, 35, 20, 30),
        _candle("2024-01-22T00:00:00Z", 30, 80, 28, 70),
        _candle("2024-01-29T00:00:00Z", 70, 72, -2, 10),
    ])
    event = _primary(result)

    assert event["maximum_destination"] == "OPPOSITE_EXTREME"
    assert event["weeks_to_fair_price"] == 1
    assert event["weeks_to_opposite_extreme"] == 1
    assert event["opposite_external_reached"] is False


def test_discount_rejection_reaches_opposite_external() -> None:
    result = _result([
        _candle("2024-01-15T00:00:00Z", 30, 35, 20, 30),
        _candle("2024-01-22T00:00:00Z", 30, 100, 28, 95),
    ])
    event = _primary(result)

    assert result["processing_status"] == "COMPLETE"
    assert event["maximum_destination"] == "OPPOSITE_EXTERNAL"
    assert event["weeks_to_fair_price"] == 1
    assert event["weeks_to_opposite_extreme"] == 1
    assert event["weeks_to_opposite_external"] == 1
    assert event["terminal_reason"] == "OPPOSITE_EXTERNAL_REACHED"


def test_premium_rejection_tracks_down_to_opposite_external() -> None:
    result = _result([
        _candle("2024-01-15T00:00:00Z", 70, 80, 65, 70),
        _candle("2024-01-22T00:00:00Z", 70, 72, 0, 5),
    ])
    event = _primary(result)

    assert event["origin_zone"] == "PREMIUM_EXTREME"
    assert event["rejection_price"] == 80
    assert event["maximum_destination"] == "OPPOSITE_EXTERNAL"
    assert event["weeks_to_fair_price"] == 1
    assert event["weeks_to_opposite_extreme"] == 1
    assert event["weeks_to_opposite_external"] == 1


def test_rejection_candle_close_can_reach_fair_price_at_week_zero() -> None:
    result = _result([
        _candle("2024-01-15T00:00:00Z", 30, 60, 20, 55),
        _candle("2024-01-22T00:00:00Z", 55, 60, -1, 10),
    ])
    event = _primary(result)

    assert event["maximum_destination"] == "FAIR_PRICE"
    assert event["weeks_to_fair_price"] == 0
    assert event["fair_price_time"] == "2024-01-15T00:00:00Z"


def test_exact_zone_boundaries_count_when_close_finishes_outside() -> None:
    result = _result([
        _candle("2024-01-15T00:00:00Z", 25, 30, 25, 26),
        _candle("2024-01-22T00:00:00Z", 26, 40, -1, 10),
        _candle("2024-01-29T00:00:00Z", 75, 75, 70, 74),
        _candle("2024-02-05T00:00:00Z", 74, 101, 70, 90),
    ])

    assert result["payload"]["rejection_event_count"] == 2
    assert [event["origin_zone"] for event in result["payload"]["rejection_events"]] == [
        "DISCOUNT_EXTREME",
        "PREMIUM_EXTREME",
    ]


def test_candle_that_stays_inside_extreme_is_not_a_rejection() -> None:
    result = _result([
        _candle("2024-01-15T00:00:00Z", 20, 24, 10, 20),
        _candle("2024-01-22T00:00:00Z", 80, 90, 76, 80),
    ])

    assert result["processing_status"] == "PENDING"
    assert result["payload"]["rejection_event_count"] == 0
    assert result["payload"]["reason_codes"] == ["NO_CONFIRMED_EXTREME_REJECTION"]


def test_both_extremes_rejected_on_one_w1_requires_review() -> None:
    result = _result([
        _candle("2024-01-15T00:00:00Z", 50, 80, 20, 50),
    ])

    assert result["processing_status"] == "NEEDS_REVIEW"
    assert result["payload"]["rejection_event_count"] == 0
    assert "BOTH_EXTREMES_REJECTED_SAME_W1" in result["payload"]["reason_codes"]


def test_open_journey_remains_pending_but_keeps_current_destination() -> None:
    result = _result([
        _candle("2024-01-15T00:00:00Z", 30, 35, 20, 30),
        _candle("2024-01-22T00:00:00Z", 30, 55, 28, 50),
    ])
    event = _primary(result)

    assert result["processing_status"] == "PENDING"
    assert event["journey_status"] == "PENDING"
    assert event["maximum_destination"] == "FAIR_PRICE"
    assert event["terminal_reason"] == "DATA_WINDOW_OPEN"


def test_new_target_and_origin_external_on_same_w1_requires_review() -> None:
    result = _result([
        _candle("2024-01-15T00:00:00Z", 30, 35, 20, 30),
        _candle("2024-01-22T00:00:00Z", 30, 80, -1, 40),
    ])
    event = _primary(result)

    assert result["processing_status"] == "NEEDS_REVIEW"
    assert event["journey_status"] == "NEEDS_REVIEW"
    assert event["terminal_reason"] == "BOTH_DIRECTIONS_TOUCHED_SAME_W1"
