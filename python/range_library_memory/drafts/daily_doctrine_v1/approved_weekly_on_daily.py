"""Draft D1 equivalents of approved Weekly doctrine.

Nothing in this module is registered with the production doctrine runtime. It exists
so the Weekly rules can be exercised at Daily resolution before integration.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Mapping, Sequence

from .core import anchor_direction, candle_direction, classify_profile, number, parse_time


def _ordered(candles: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return sorted(candles, key=lambda row: parse_time(row.get("time")) or datetime.max.replace(tzinfo=UTC))


def detect_daily_reclaim(*, candles: Sequence[Mapping[str, Any]], bos_direction: str,
                         bos_time: Any, broken_boundary: Any,
                         next_bos_time: Any = None,
                         next_bos_direction: str | None = None) -> dict[str, Any]:
    direction = str(bos_direction or "").upper()
    boundary = number(broken_boundary)
    source_time = parse_time(bos_time)
    next_time = parse_time(next_bos_time)
    if direction not in {"BOS_UP", "BOS_DOWN"} or boundary is None or source_time is None:
        return {"processing_status": "PENDING", "reclaim_status": None, "reason": "SOURCE_BOS_UNAVAILABLE"}

    rows = _ordered(candles)
    source_index = next((index for index, row in enumerate(rows) if parse_time(row.get("time")) == source_time), None)
    if source_index is None:
        return {"processing_status": "PENDING", "reclaim_status": None, "reason": "SOURCE_BOS_CANDLE_UNAVAILABLE"}

    def reclaims(row: Mapping[str, Any]) -> bool:
        low = number(row.get("low"))
        high = number(row.get("high"))
        return bool(low is not None and low <= boundary) if direction == "BOS_UP" else bool(high is not None and high >= boundary)

    bos_row = rows[source_index]
    if reclaims(bos_row):
        return {
            "processing_status": "COMPLETE",
            "reclaim_status": "RECLAIMED",
            "reclaim_abbreviation": "RECL",
            "reclaim_time": bos_row.get("time"),
            "same_candle_reclaim": True,
            "days_to_reclaim": 0,
        }

    abandoned = False
    abandonment_time = None
    for index, row in enumerate(rows[source_index + 1:], start=1):
        time = parse_time(row.get("time"))
        if time is None:
            continue
        if next_time is not None and time == next_time:
            if reclaims(row):
                return {
                    "processing_status": "NEEDS_REVIEW",
                    "reclaim_status": None,
                    "reason": "NEXT_BOS_AND_RECLAIM_SAME_D1",
                    "reclaim_time": row.get("time"),
                }
            abandoned = True
            abandonment_time = row.get("time")
            continue
        if reclaims(row):
            return {
                "processing_status": "COMPLETE",
                "reclaim_status": "ABANDONED_THEN_RECLAIMED" if abandoned else "RECLAIMED",
                "reclaim_abbreviation": "ABND→RECL" if abandoned else "RECL",
                "reclaim_time": row.get("time"),
                "same_candle_reclaim": False,
                "days_to_reclaim": index,
                "abandonment_time": abandonment_time,
                "next_bos_direction": str(next_bos_direction or "").upper() or None,
            }

    if abandoned or next_time is not None:
        return {
            "processing_status": "COMPLETE",
            "reclaim_status": "ABANDONED",
            "reclaim_abbreviation": "ABND",
            "abandonment_time": abandonment_time or next_bos_time,
            "next_bos_direction": str(next_bos_direction or "").upper() or None,
        }
    return {"processing_status": "PENDING", "reclaim_status": None, "reason": "RECLAIM_NOT_YET_AVAILABLE"}


def calculate_daily_retracement_depth(*, source_range: Mapping[str, Any],
                                      next_range: Mapping[str, Any],
                                      source_bos_direction: str) -> dict[str, Any]:
    high = number(source_range.get("range_high") or source_range.get("range_high_price"))
    low = number(source_range.get("range_low") or source_range.get("range_low_price"))
    next_high = number(next_range.get("range_high") or next_range.get("range_high_price"))
    next_low = number(next_range.get("range_low") or next_range.get("range_low_price"))
    direction = str(source_bos_direction or "").upper()
    if None in {high, low, next_high, next_low} or high <= low or direction not in {"BOS_UP", "BOS_DOWN"}:
        return {"processing_status": "NEEDS_REVIEW", "depth_status": None, "reason": "RANGE_GEOMETRY_UNAVAILABLE"}

    size = high - low
    raw_ratio = (high - next_low) / size if direction == "BOS_UP" else (next_high - low) / size
    raw_percent = raw_ratio * 100.0
    trading_percent = max(0.0, raw_percent)
    return {
        "processing_status": "COMPLETE",
        "depth_status": "NO_RETRACEMENT" if raw_percent < 0 else "MEASURED",
        "source_bos_direction": direction,
        "source_range_high": high,
        "source_range_low": low,
        "source_range_size": size,
        "raw_reclaim_depth_ratio": raw_ratio,
        "raw_reclaim_depth_percent": raw_percent,
        "reclaim_depth_ratio": trading_percent / 100.0,
        "reclaim_depth_percent": trading_percent,
        "next_range_direction": anchor_direction(next_range),
    }


def classify_daily_movement(*, source_bos_direction: str,
                            candles: Sequence[Mapping[str, Any]],
                            source_bos_time: Any,
                            next_bos_time: Any = None) -> dict[str, Any]:
    direction = str(source_bos_direction or "").upper()
    source_time = parse_time(source_bos_time)
    terminal_time = parse_time(next_bos_time)
    if direction not in {"BOS_UP", "BOS_DOWN"} or source_time is None:
        return {"processing_status": "PENDING", "movement_legs": [], "reason": "SOURCE_BOS_UNAVAILABLE"}

    rows = []
    for row in _ordered(candles):
        time = parse_time(row.get("time"))
        if time is None or time <= source_time:
            continue
        if terminal_time is not None and time >= terminal_time:
            break
        rows.append(row)

    legs: list[dict[str, Any]] = []
    for row in rows:
        daily = candle_direction(row)
        if daily in {"DOJI", "UNRESOLVED"}:
            return {
                "processing_status": "NEEDS_REVIEW",
                "movement_legs": legs,
                "reason": "DOJI_OR_INVALID_D1_INSIDE_MOVEMENT",
                "review_time": row.get("time"),
            }
        pro_direction = "UP" if direction == "BOS_UP" else "DOWN"
        role = "PRO_TREND" if daily == pro_direction else "COUNTER_TREND"
        if legs and legs[-1]["role"] == role:
            legs[-1]["day_count"] += 1
            legs[-1]["end_time"] = row.get("time")
        else:
            legs.append({
                "role": role,
                "direction": daily,
                "day_count": 1,
                "start_time": row.get("time"),
                "end_time": row.get("time"),
            })

    return {
        "processing_status": "COMPLETE" if terminal_time is not None else "PENDING",
        "movement_legs": legs,
        "movement_path": " -> ".join(f"{'PT' if leg['role'] == 'PRO_TREND' else 'CT'} {leg['day_count']}D" for leg in legs),
        "pro_trend_leg_count": sum(leg["role"] == "PRO_TREND" for leg in legs),
        "counter_trend_leg_count": sum(leg["role"] == "COUNTER_TREND" for leg in legs),
        "days_scanned": len(rows),
        "reason": "NEXT_APPROVED_DAILY_BOS_NOT_AVAILABLE" if terminal_time is None else "MOVEMENT_CLOSED_BY_NEXT_DAILY_BOS",
    }


def classify_daily_profile(*, depth_percent: Any, reclaim_status: str | None,
                           source_bos_direction: str | None,
                           next_bos_direction: str | None) -> dict[str, Any]:
    return classify_profile(
        depth_percent,
        reclaim_status=reclaim_status,
        source_bos_direction=source_bos_direction,
        next_bos_direction=next_bos_direction,
    )


def detect_daily_extreme_rejections(*, candles: Sequence[Mapping[str, Any]],
                                    range_low: Any, range_high: Any) -> list[dict[str, Any]]:
    low_boundary = number(range_low)
    high_boundary = number(range_high)
    if low_boundary is None or high_boundary is None or high_boundary <= low_boundary:
        return [{"processing_status": "NEEDS_REVIEW", "reason": "INVALID_DAILY_RANGE_GEOMETRY"}]

    size = high_boundary - low_boundary
    discount_25 = low_boundary + size * 0.25
    fair = low_boundary + size * 0.50
    premium_75 = low_boundary + size * 0.75
    rows = _ordered(candles)
    events: list[dict[str, Any]] = []

    for index, row in enumerate(rows):
        high = number(row.get("high"))
        low = number(row.get("low"))
        close = number(row.get("close"))
        if None in {high, low, close}:
            continue
        discount = low <= discount_25 and close > discount_25
        premium = high >= premium_75 and close < premium_75
        if discount and premium:
            events.append({
                "processing_status": "NEEDS_REVIEW",
                "rejection_time": row.get("time"),
                "reason": "BOTH_EXTREMES_REJECTED_SAME_D1",
            })
            continue
        if not discount and not premium:
            continue

        origin = "DISCOUNT" if discount else "PREMIUM"
        destinations = {
            "FAIR_PRICE": fair,
            "OPPOSITE_EXTREME": premium_75 if discount else discount_25,
            "OPPOSITE_EXTERNAL": high_boundary if discount else low_boundary,
        }
        reached = {key: False for key in destinations}
        weeks = {key: None for key in destinations}
        # The rejection candle may prove a destination only through its close.
        for key, price in destinations.items():
            if (discount and close >= price) or (premium and close <= price):
                reached[key] = True
                weeks[key] = 0

        terminal_reason = None
        status = "PENDING"
        for offset, later in enumerate(rows[index + 1:], start=1):
            later_high = number(later.get("high"))
            later_low = number(later.get("low"))
            if later_high is None or later_low is None:
                continue
            origin_broken = later_low < low_boundary if discount else later_high > high_boundary
            newly_reached = []
            for key, price in destinations.items():
                if reached[key]:
                    continue
                if (discount and later_high >= price) or (premium and later_low <= price):
                    newly_reached.append(key)
            if origin_broken and newly_reached:
                status = "NEEDS_REVIEW"
                terminal_reason = "ORIGIN_EXTERNAL_AND_DESTINATION_TOUCHED_SAME_D1"
                break
            for key in newly_reached:
                reached[key] = True
                weeks[key] = offset
            if reached["OPPOSITE_EXTERNAL"]:
                status = "COMPLETE"
                terminal_reason = "OPPOSITE_EXTERNAL_REACHED"
                break
            if origin_broken:
                status = "COMPLETE"
                terminal_reason = "ORIGIN_EXTERNAL_BROKEN"
                break

        maximum = "NO_FOLLOW_THROUGH"
        for key in ("FAIR_PRICE", "OPPOSITE_EXTREME", "OPPOSITE_EXTERNAL"):
            if reached[key]:
                maximum = key
        events.append({
            "processing_status": status,
            "origin_zone": origin,
            "rejection_time": row.get("time"),
            "rejection_price": low if discount else high,
            "rejection_close": close,
            "maximum_destination": maximum,
            "fair_price_reached": reached["FAIR_PRICE"],
            "days_to_fair_price": weeks["FAIR_PRICE"],
            "opposite_extreme_reached": reached["OPPOSITE_EXTREME"],
            "days_to_opposite_extreme": weeks["OPPOSITE_EXTREME"],
            "opposite_external_reached": reached["OPPOSITE_EXTERNAL"],
            "days_to_opposite_external": weeks["OPPOSITE_EXTERNAL"],
            "terminal_reason": terminal_reason or "AVAILABLE_D1_DATA_ENDED",
        })
    return events
