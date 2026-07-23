"""Pure draft classifiers for Daily doctrine research.

This module is deliberately disconnected from the FXTM doctrine runtime. Functions
accept plain mappings/lists and return plain dictionaries so doctrine can be reviewed
and tested before any application integration.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Iterable, Mapping, Sequence

PROFILE_SR = "S&R"
PROFILE_SR_FP = "S&R>FP"
PROFILE_SD = "S&D"


def parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result and result not in (float("inf"), float("-inf")) else None


def candle_direction(candle: Mapping[str, Any]) -> str:
    opened = number(candle.get("open"))
    closed = number(candle.get("close"))
    if opened is None or closed is None:
        return "UNRESOLVED"
    if closed > opened:
        return "UP"
    if closed < opened:
        return "DOWN"
    return "DOJI"


def anchor_direction(range_row: Mapping[str, Any]) -> str:
    high_time = parse_time(range_row.get("range_high_time"))
    low_time = parse_time(range_row.get("range_low_time"))
    if high_time is None or low_time is None:
        return "UNRESOLVED"
    if high_time == low_time:
        return "SAME_D1"
    return "UP" if low_time < high_time else "DOWN"


def classify_profile(depth_percent: Any, *, reclaim_status: str | None = None,
                     source_bos_direction: str | None = None,
                     next_bos_direction: str | None = None) -> dict[str, Any]:
    reclaim = str(reclaim_status or "").upper()
    source = str(source_bos_direction or "").upper()
    nxt = str(next_bos_direction or "").upper()
    if reclaim == "ABANDONED" and source in {"BOS_UP", "BOS_DOWN"} and source == nxt:
        return {
            "processing_status": "COMPLETE",
            "profile": PROFILE_SR,
            "classification_basis": "ABANDONED_CONTINUATION_OVERRIDE",
        }

    depth = number(depth_percent)
    if depth is None:
        return {
            "processing_status": "PENDING",
            "profile": None,
            "classification_basis": "DEPTH_UNAVAILABLE",
        }
    if depth < 38.2:
        profile = PROFILE_SR
    elif depth <= 50.0:
        profile = PROFILE_SR_FP
    else:
        profile = PROFILE_SD
    return {
        "processing_status": "COMPLETE",
        "profile": profile,
        "classification_basis": "RECLAIM_DEPTH",
        "depth_percent": depth,
    }


def weekly_zone(price: Any, weekly_low: Any, weekly_high: Any) -> dict[str, Any]:
    value = number(price)
    low = number(weekly_low)
    high = number(weekly_high)
    if value is None or low is None or high is None or high <= low:
        return {"zone": "UNRESOLVED", "position_percent": None}
    position = ((value - low) / (high - low)) * 100.0
    if position < 0:
        zone = "EXTERNAL_LOW"
    elif position <= 25:
        zone = "DISCOUNT_EXTREME"
    elif position < 50:
        zone = "DISCOUNT"
    elif position == 50:
        zone = "FAIR_PRICE"
    elif position < 75:
        zone = "PREMIUM"
    elif position <= 100:
        zone = "PREMIUM_EXTREME"
    else:
        zone = "EXTERNAL_HIGH"
    return {"zone": zone, "position_percent": position}


def classify_pro_counter(weekly_bos_direction: str, daily_direction: str) -> dict[str, Any]:
    weekly = str(weekly_bos_direction or "").upper()
    daily = str(daily_direction or "").upper()
    if weekly not in {"BOS_UP", "BOS_DOWN"}:
        return {"processing_status": "PENDING", "classification": None, "reason": "WEEKLY_BOS_UNAVAILABLE"}
    if daily in {"UNRESOLVED", "SAME_D1", "DOJI", ""}:
        return {"processing_status": "NEEDS_REVIEW", "classification": None, "reason": "DAILY_DIRECTION_UNRESOLVED"}
    expected = "UP" if weekly == "BOS_UP" else "DOWN"
    return {
        "processing_status": "COMPLETE",
        "classification": "PRO_TREND" if daily == expected else "COUNTER_TREND",
        "weekly_bos_direction": weekly,
        "daily_direction": daily,
    }


def detect_bos(candles: Sequence[Mapping[str, Any]], *, range_high: Any, range_low: Any,
               after_time: Any = None) -> dict[str, Any]:
    high_boundary = number(range_high)
    low_boundary = number(range_low)
    after = parse_time(after_time)
    if high_boundary is None or low_boundary is None or high_boundary <= low_boundary:
        return {"processing_status": "NEEDS_REVIEW", "bos_direction": None, "reason": "INVALID_RANGE_BOUNDARIES"}

    for candle in candles:
        time = parse_time(candle.get("time"))
        if time is None or (after is not None and time <= after):
            continue
        high = number(candle.get("high"))
        low = number(candle.get("low"))
        if high is None or low is None:
            continue
        up = high > high_boundary
        down = low < low_boundary
        if up and down:
            return {
                "processing_status": "NEEDS_REVIEW",
                "bos_direction": None,
                "bos_time": candle.get("time"),
                "reason": "BOTH_BOUNDARIES_BREACHED_SAME_D1",
            }
        if up or down:
            return {
                "processing_status": "COMPLETE",
                "bos_direction": "BOS_UP" if up else "BOS_DOWN",
                "bos_time": candle.get("time"),
                "bos_price": high if up else low,
                "reason": "FIRST_LATER_D1_WICK_BREAK",
            }
    return {"processing_status": "PENDING", "bos_direction": None, "reason": "NO_LATER_D1_BOS"}


def classify_first_range_transition(*, weekly_low: Any, weekly_high: Any,
                                    weekly_bos_direction: str,
                                    daily_range: Mapping[str, Any]) -> dict[str, Any]:
    low = number(weekly_low)
    high = number(weekly_high)
    daily_high = number(daily_range.get("range_high") or daily_range.get("range_high_price"))
    daily_low = number(daily_range.get("range_low") or daily_range.get("range_low_price"))
    if None in {low, high, daily_high, daily_low} or high <= low or daily_high < daily_low:
        return {"processing_status": "NEEDS_REVIEW", "classification": "UNRESOLVED", "reason": "BOUNDARIES_UNAVAILABLE"}

    weekly = str(weekly_bos_direction or "").upper()
    if weekly == "BOS_UP":
        touched_external = daily_high > high
        returned_internal = daily_low < high
    elif weekly == "BOS_DOWN":
        touched_external = daily_low < low
        returned_internal = daily_high > low
    else:
        return {"processing_status": "PENDING", "classification": "UNRESOLVED", "reason": "WEEKLY_BOS_UNAVAILABLE"}

    if touched_external and returned_internal:
        classification = "WEEKLY_EXTERNAL_TO_INTERNAL"
    elif touched_external:
        classification = "WEEKLY_EXTERNAL_CONTINUATION"
    else:
        classification = "WEEKLY_INTERNAL_FIRST_RANGE"
    return {
        "processing_status": "COMPLETE",
        "classification": classification,
        "weekly_bos_direction": weekly,
        "daily_direction": anchor_direction(daily_range),
    }


def classify_first_daily_after_weekly_rejection(*, weekly_low: Any, weekly_high: Any,
                                                rejection_origin: str,
                                                rejection_time: Any,
                                                daily_ranges: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    origin = str(rejection_origin or "").upper()
    rejection_at = parse_time(rejection_time)
    if origin not in {"DISCOUNT", "PREMIUM", "DISCOUNT_EXTREME", "PREMIUM_EXTREME"}:
        return {"processing_status": "NEEDS_REVIEW", "reason": "WEEKLY_REJECTION_ORIGIN_UNRESOLVED"}
    if rejection_at is None:
        return {"processing_status": "PENDING", "reason": "WEEKLY_REJECTION_TIME_UNAVAILABLE"}

    eligible: list[Mapping[str, Any]] = []
    for row in daily_ranges:
        created = parse_time(row.get("active_from_time") or row.get("daily_created_time"))
        if created is not None and created >= rejection_at:
            eligible.append(row)
    eligible.sort(key=lambda row: (parse_time(row.get("active_from_time") or row.get("daily_created_time")) or datetime.max.replace(tzinfo=UTC), str(row.get("id") or row.get("range_id") or "")))
    if not eligible:
        return {"processing_status": "PENDING", "reason": "NO_DAILY_RANGE_AFTER_WEEKLY_REJECTION"}

    first = eligible[0]
    direction = anchor_direction(first)
    expected = "UP" if origin.startswith("DISCOUNT") else "DOWN"
    return {
        "processing_status": "COMPLETE" if direction not in {"UNRESOLVED", "SAME_D1"} else "NEEDS_REVIEW",
        "weekly_rejection_origin": origin,
        "first_daily_range_id": str(first.get("id") or first.get("range_id") or ""),
        "first_daily_direction": direction,
        "delivery_away_from_rejected_extreme": direction == expected,
        "first_daily_start_zone": weekly_zone(
            first.get("range_low") if expected == "UP" else first.get("range_high"),
            weekly_low,
            weekly_high,
        )["zone"],
    }


def profile_streaks(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(rows, key=lambda row: (
        parse_time(row.get("active_from_time") or row.get("completed_at")) or datetime.max.replace(tzinfo=UTC),
        str(row.get("daily_range_id") or row.get("id") or ""),
    ))
    streaks: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    def close_current(termination: str, next_profile: str | None = None) -> None:
        nonlocal current
        if current is None:
            return
        current["termination_reason"] = termination
        current["termination_profile"] = next_profile
        current["open_at_freeze"] = termination == "DATA_END"
        streaks.append(current)
        current = None

    for row in ordered:
        profile = str(row.get("profile") or row.get("profile_classification") or "").upper()
        range_id = str(row.get("daily_range_id") or row.get("id") or "")
        time = row.get("active_from_time") or row.get("completed_at")
        if profile not in {PROFILE_SR.upper(), PROFILE_SR_FP.upper(), PROFILE_SD.upper()}:
            close_current("UNRESOLVED_PROFILE_BOUNDARY")
            continue
        canonical_profile = {PROFILE_SR.upper(): PROFILE_SR, PROFILE_SR_FP.upper(): PROFILE_SR_FP, PROFILE_SD.upper(): PROFILE_SD}[profile]
        if current is None:
            current = {
                "profile": canonical_profile,
                "start_daily_range_id": range_id,
                "end_daily_range_id": range_id,
                "range_count": 1,
                "start_time": time,
                "end_time": time,
            }
        elif current["profile"] == canonical_profile:
            current["end_daily_range_id"] = range_id
            current["end_time"] = time
            current["range_count"] += 1
        else:
            close_current("PROFILE_CHANGED", canonical_profile)
            current = {
                "profile": canonical_profile,
                "start_daily_range_id": range_id,
                "end_daily_range_id": range_id,
                "range_count": 1,
                "start_time": time,
                "end_time": time,
            }
    close_current("DATA_END")
    return streaks


def detect_pdh_pdl_sweeps(candles: Sequence[Mapping[str, Any]], *, weekly_low: Any,
                          weekly_high: Any) -> list[dict[str, Any]]:
    ordered = sorted(candles, key=lambda row: parse_time(row.get("time")) or datetime.max.replace(tzinfo=UTC))
    events: list[dict[str, Any]] = []
    for previous, current in zip(ordered, ordered[1:]):
        prev_high = number(previous.get("high"))
        prev_low = number(previous.get("low"))
        high = number(current.get("high"))
        low = number(current.get("low"))
        close = number(current.get("close"))
        if None in {prev_high, prev_low, high, low, close}:
            continue

        pdl_swept = low < prev_low and close > prev_low
        pdh_swept = high > prev_high and close < prev_high
        if not pdl_swept and not pdh_swept:
            continue
        if pdl_swept and pdh_swept:
            events.append({
                "processing_status": "NEEDS_REVIEW",
                "sweep_time": current.get("time"),
                "sweep_type": "BOTH",
                "reason": "PDH_AND_PDL_SWEPT_SAME_D1",
            })
            continue

        sweep_type = "PDL_SWEEP" if pdl_swept else "PDH_SWEEP"
        sweep_price = low if pdl_swept else high
        location = weekly_zone(sweep_price, weekly_low, weekly_high)
        allowed = {"DISCOUNT_EXTREME", "EXTERNAL_LOW"} if pdl_swept else {"PREMIUM_EXTREME", "EXTERNAL_HIGH"}
        events.append({
            "processing_status": "COMPLETE",
            "sweep_type": sweep_type,
            "sweep_time": current.get("time"),
            "previous_daily_level": prev_low if pdl_swept else prev_high,
            "sweep_price": sweep_price,
            "close": close,
            "weekly_location": location["zone"],
            "weekly_position_percent": location["position_percent"],
            "location_valid": location["zone"] in allowed,
            "reversal_direction": "UP" if pdl_swept else "DOWN",
            "classification": "VALID_EXTREME_REVERSAL_SWEEP" if location["zone"] in allowed else "SWEEP_OUTSIDE_REQUIRED_LOCATION",
        })
    return events
