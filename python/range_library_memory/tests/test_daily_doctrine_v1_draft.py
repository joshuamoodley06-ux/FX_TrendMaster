from python.range_library_memory.drafts.daily_doctrine_v1.approved_weekly_on_daily import (
    calculate_daily_retracement_depth,
    classify_daily_movement,
    detect_daily_extreme_rejections,
    detect_daily_reclaim,
)
from python.range_library_memory.drafts.daily_doctrine_v1.core import (
    classify_first_range_transition,
    classify_pro_counter,
    classify_profile,
    detect_bos,
    detect_pdh_pdl_sweeps,
    profile_streaks,
)


def candle(time, open_, high, low, close):
    return {"time": time, "open": open_, "high": high, "low": low, "close": close}


def test_daily_bos_uses_wick_break_and_exact_touch_does_not_count():
    result = detect_bos(
        [
            candle("2026-01-02T00:00:00Z", 150, 200, 100, 170),
            candle("2026-01-03T00:00:00Z", 170, 200, 120, 180),
            candle("2026-01-04T00:00:00Z", 180, 201, 140, 190),
        ],
        range_high=200,
        range_low=100,
        after_time="2026-01-01T00:00:00Z",
    )
    assert result["bos_direction"] == "BOS_UP"
    assert result["bos_time"] == "2026-01-04T00:00:00Z"


def test_profile_thresholds_and_abandoned_override_match_weekly_doctrine():
    assert classify_profile(38.1)["profile"] == "S&R"
    assert classify_profile(38.2)["profile"] == "S&R>FP"
    assert classify_profile(50)["profile"] == "S&R>FP"
    assert classify_profile(50.1)["profile"] == "S&D"
    override = classify_profile(
        None,
        reclaim_status="ABANDONED",
        source_bos_direction="BOS_UP",
        next_bos_direction="BOS_UP",
    )
    assert override["profile"] == "S&R"
    assert override["classification_basis"] == "ABANDONED_CONTINUATION_OVERRIDE"


def test_first_daily_range_can_classify_weekly_external_to_internal():
    result = classify_first_range_transition(
        weekly_low=100,
        weekly_high=200,
        weekly_bos_direction="BOS_UP",
        daily_range={
            "range_low": 180,
            "range_high": 220,
            "range_low_time": "2026-01-01T00:00:00Z",
            "range_high_time": "2026-01-03T00:00:00Z",
        },
    )
    assert result["classification"] == "WEEKLY_EXTERNAL_TO_INTERNAL"
    assert result["daily_direction"] == "UP"


def test_protrend_countertrend_is_relative_to_weekly_bos():
    assert classify_pro_counter("BOS_UP", "UP")["classification"] == "PRO_TREND"
    assert classify_pro_counter("BOS_UP", "DOWN")["classification"] == "COUNTER_TREND"
    assert classify_pro_counter("BOS_DOWN", "DOWN")["classification"] == "PRO_TREND"


def test_daily_reclaim_allows_same_bos_candle_reclaim():
    result = detect_daily_reclaim(
        candles=[candle("2026-01-02T00:00:00Z", 205, 215, 195, 210)],
        bos_direction="BOS_UP",
        bos_time="2026-01-02T00:00:00Z",
        broken_boundary=200,
    )
    assert result["reclaim_status"] == "RECLAIMED"
    assert result["same_candle_reclaim"] is True
    assert result["days_to_reclaim"] == 0


def test_daily_depth_uses_directional_opposite_anchor():
    result = calculate_daily_retracement_depth(
        source_range={"range_low": 100, "range_high": 200},
        next_range={
            "range_low": 150,
            "range_high": 230,
            "range_low_time": "2026-01-03T00:00:00Z",
            "range_high_time": "2026-01-05T00:00:00Z",
        },
        source_bos_direction="BOS_UP",
    )
    assert result["reclaim_depth_percent"] == 50


def test_daily_movement_merges_consecutive_same_role_candles():
    result = classify_daily_movement(
        source_bos_direction="BOS_UP",
        source_bos_time="2026-01-01T00:00:00Z",
        next_bos_time="2026-01-05T00:00:00Z",
        candles=[
            candle("2026-01-02T00:00:00Z", 10, 12, 9, 11),
            candle("2026-01-03T00:00:00Z", 11, 13, 10, 12),
            candle("2026-01-04T00:00:00Z", 12, 12.5, 9, 10),
            candle("2026-01-05T00:00:00Z", 10, 15, 9, 14),
        ],
    )
    assert result["movement_path"] == "PT 2D -> CT 1D"
    assert result["days_scanned"] == 3


def test_profile_streak_counts_ranges_not_candles():
    streaks = profile_streaks([
        {"daily_range_id": "D1", "active_from_time": "2026-01-01T00:00:00Z", "profile": "S&R"},
        {"daily_range_id": "D2", "active_from_time": "2026-01-02T00:00:00Z", "profile": "S&R"},
        {"daily_range_id": "D3", "active_from_time": "2026-01-03T00:00:00Z", "profile": "S&D"},
    ])
    assert streaks[0]["range_count"] == 2
    assert streaks[0]["termination_reason"] == "PROFILE_CHANGED"
    assert streaks[1]["range_count"] == 1


def test_pdl_sweep_requires_beyond_and_weekly_discount_location():
    events = detect_pdh_pdl_sweeps(
        [
            candle("2026-01-01T00:00:00Z", 125, 140, 120, 130),
            candle("2026-01-02T00:00:00Z", 130, 135, 110, 125),
        ],
        weekly_low=100,
        weekly_high=200,
    )
    assert events[0]["sweep_type"] == "PDL_SWEEP"
    assert events[0]["location_valid"] is True
    assert events[0]["classification"] == "VALID_EXTREME_REVERSAL_SWEEP"


def test_daily_extreme_rejection_tracks_destination_ladder():
    events = detect_daily_extreme_rejections(
        candles=[
            candle("2026-01-01T00:00:00Z", 130, 140, 115, 130),
            candle("2026-01-02T00:00:00Z", 130, 180, 125, 170),
            candle("2026-01-03T00:00:00Z", 170, 205, 160, 200),
        ],
        range_low=100,
        range_high=200,
    )
    assert events[0]["origin_zone"] == "DISCOUNT"
    assert events[0]["maximum_destination"] == "OPPOSITE_EXTERNAL"
    assert events[0]["opposite_external_reached"] is True
