"""Track where price travels after a confirmed Weekly extreme-zone rejection.

Range geometry:

* discount extreme: 0% through 25%;
* fair price: 50%;
* premium extreme: 75% through 100%.

A discount rejection requires price to trade at or below the 25% boundary and
close back above it. A premium rejection requires price to trade at or above
the 75% boundary and close back below it.

Each confirmed rejection is followed until either:

* the opposite external is reached;
* price later breaks through the origin external; or
* available W1 data ends, leaving the journey pending.

The rejection candle may prove a destination only through its close. From the
next W1 onward, wick touches count. This avoids inventing intrawweek ordering
from one OHLC candle.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Mapping

FXTM_DOCTRINE_CONTRACT = "fxtm_doctrine_package_v1"
SCRIPT_KEY = "weekly_extreme_rejection_destination"
VERSION_LABEL = "1"
ADAPTER_KEY = "doctrine_package_v1"
EXECUTION_ORDER = 60

_EPSILON = 1e-9
_DESTINATION_RANK = {
    "NO_FOLLOW_THROUGH": 0,
    "FAIR_PRICE": 1,
    "OPPOSITE_EXTREME": 2,
    "OPPOSITE_EXTERNAL": 3,
}


def _time(value: Any) -> datetime | None:
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


def _stamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


def _output(node: Mapping[str, Any], status: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "canonical_range_id": str(node.get("id") or ""),
        "processing_status": status,
        "payload": payload,
    }


def _base_payload() -> dict[str, Any]:
    return {
        "rejection_event_count": 0,
        "completed_event_count": 0,
        "pending_event_count": 0,
        "primary_origin_zone": None,
        "primary_rejection_time": None,
        "primary_rejection_price": None,
        "primary_maximum_destination": None,
        "primary_journey_status": None,
        "primary_fair_price_reached": None,
        "primary_weeks_to_fair_price": None,
        "primary_opposite_extreme_reached": None,
        "primary_weeks_to_opposite_extreme": None,
        "primary_opposite_external_reached": None,
        "primary_weeks_to_opposite_external": None,
        "primary_terminal_reason": None,
        "rejection_events": [],
        "reason_codes": [],
    }


def _maximum_destination(
    *,
    fair_price_reached: bool,
    opposite_extreme_reached: bool,
    opposite_external_reached: bool,
) -> str:
    if opposite_external_reached:
        return "OPPOSITE_EXTERNAL"
    if opposite_extreme_reached:
        return "OPPOSITE_EXTREME"
    if fair_price_reached:
        return "FAIR_PRICE"
    return "NO_FOLLOW_THROUGH"


def _touches_up(candle: Mapping[str, Any], level: float) -> bool:
    high = _number(candle.get("high"))
    return high is not None and high + _EPSILON >= level


def _touches_down(candle: Mapping[str, Any], level: float) -> bool:
    low = _number(candle.get("low"))
    return low is not None and low - _EPSILON <= level


def _journey(
    candles: list[dict[str, Any]],
    *,
    rejection_index: int,
    origin_zone: str,
    range_low: float,
    range_high: float,
    fair_price: float,
    discount_ceiling: float,
    premium_floor: float,
) -> dict[str, Any]:
    rejection = candles[rejection_index]
    rejection_time = _time(rejection.get("time"))
    close = _number(rejection.get("close"))
    assert rejection_time is not None and close is not None

    discount_origin = origin_zone == "DISCOUNT_EXTREME"
    if discount_origin:
        fair_reached = close + _EPSILON >= fair_price
        opposite_extreme_reached = close + _EPSILON >= premium_floor
        opposite_external_reached = close + _EPSILON >= range_high
    else:
        fair_reached = close - _EPSILON <= fair_price
        opposite_extreme_reached = close - _EPSILON <= discount_ceiling
        opposite_external_reached = close - _EPSILON <= range_low

    weeks_to_fair = 0 if fair_reached else None
    weeks_to_opposite_extreme = 0 if opposite_extreme_reached else None
    weeks_to_opposite_external = 0 if opposite_external_reached else None
    fair_time = _stamp(rejection_time) if fair_reached else None
    opposite_extreme_time = _stamp(rejection_time) if opposite_extreme_reached else None
    opposite_external_time = _stamp(rejection_time) if opposite_external_reached else None

    journey_status = "COMPLETE" if opposite_external_reached else "PENDING"
    terminal_reason = "OPPOSITE_EXTERNAL_REACHED" if opposite_external_reached else "DATA_WINDOW_OPEN"
    terminal_time = _stamp(rejection_time) if opposite_external_reached else None
    candles_observed = 1

    for future_index in range(rejection_index + 1, len(candles)):
        if journey_status != "PENDING":
            break
        candle = candles[future_index]
        candle_time = _time(candle.get("time"))
        high = _number(candle.get("high"))
        low = _number(candle.get("low"))
        if candle_time is None or high is None or low is None:
            journey_status = "NEEDS_REVIEW"
            terminal_reason = "INVALID_W1_OHLC_IN_DESTINATION_WINDOW"
            terminal_time = _stamp(candle_time) if candle_time else None
            break

        candles_observed += 1
        weeks = future_index - rejection_index
        if discount_origin:
            origin_external_broken = low < range_low - _EPSILON
            new_fair = not fair_reached and high + _EPSILON >= fair_price
            new_opposite_extreme = (
                not opposite_extreme_reached and high + _EPSILON >= premium_floor
            )
            new_opposite_external = (
                not opposite_external_reached and high + _EPSILON >= range_high
            )
        else:
            origin_external_broken = high > range_high + _EPSILON
            new_fair = not fair_reached and low - _EPSILON <= fair_price
            new_opposite_extreme = (
                not opposite_extreme_reached and low - _EPSILON <= discount_ceiling
            )
            new_opposite_external = (
                not opposite_external_reached and low - _EPSILON <= range_low
            )

        # A W1 touching both the origin external and a newly reached destination
        # cannot prove which side happened first from OHLC alone.
        if origin_external_broken and (new_fair or new_opposite_extreme or new_opposite_external):
            journey_status = "NEEDS_REVIEW"
            terminal_reason = "BOTH_DIRECTIONS_TOUCHED_SAME_W1"
            terminal_time = _stamp(candle_time)
            break

        if origin_external_broken:
            journey_status = "COMPLETE"
            terminal_reason = "ORIGIN_EXTERNAL_BROKEN"
            terminal_time = _stamp(candle_time)
            break

        if new_fair:
            fair_reached = True
            weeks_to_fair = weeks
            fair_time = _stamp(candle_time)
        if new_opposite_extreme:
            opposite_extreme_reached = True
            weeks_to_opposite_extreme = weeks
            opposite_extreme_time = _stamp(candle_time)
        if new_opposite_external:
            opposite_external_reached = True
            weeks_to_opposite_external = weeks
            opposite_external_time = _stamp(candle_time)
            journey_status = "COMPLETE"
            terminal_reason = "OPPOSITE_EXTERNAL_REACHED"
            terminal_time = _stamp(candle_time)

    return {
        "origin_zone": origin_zone,
        "rejection_time": _stamp(rejection_time),
        "rejection_price": round(
            float(rejection["low"] if discount_origin else rejection["high"]), 8
        ),
        "rejection_close": round(close, 8),
        "journey_status": journey_status,
        "maximum_destination": _maximum_destination(
            fair_price_reached=fair_reached,
            opposite_extreme_reached=opposite_extreme_reached,
            opposite_external_reached=opposite_external_reached,
        ),
        "fair_price_reached": fair_reached,
        "fair_price_time": fair_time,
        "weeks_to_fair_price": weeks_to_fair,
        "opposite_extreme_reached": opposite_extreme_reached,
        "opposite_extreme_time": opposite_extreme_time,
        "weeks_to_opposite_extreme": weeks_to_opposite_extreme,
        "opposite_external_reached": opposite_external_reached,
        "opposite_external_time": opposite_external_time,
        "weeks_to_opposite_external": weeks_to_opposite_external,
        "terminal_reason": terminal_reason,
        "terminal_time": terminal_time,
        "candles_observed": candles_observed,
    }


def _primary_event(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not events:
        return None
    completed = [event for event in events if event["journey_status"] == "COMPLETE"]
    pool = completed or events
    return min(pool, key=lambda event: (event["rejection_time"], event["origin_zone"]))


def run(context: Any) -> dict[str, list[dict[str, Any]]]:
    outputs: list[dict[str, Any]] = []
    latest = _time(context.latest_candle_time("W1"))

    for raw_node in context.selected_ranges(layer="WEEKLY"):
        node = dict(raw_node)
        payload = _base_payload()
        high = _number(node.get("range_high"))
        low = _number(node.get("range_low"))
        high_time = _time(node.get("range_high_time"))
        low_time = _time(node.get("range_low_time"))

        if high is None or low is None or high <= low:
            payload["reason_codes"] = ["INVALID_RANGE_PRICES"]
            outputs.append(_output(node, "NEEDS_REVIEW", payload))
            continue
        if high_time is None or low_time is None:
            payload["reason_codes"] = ["MISSING_OR_INVALID_ANCHOR_TIME"]
            outputs.append(_output(node, "NEEDS_REVIEW", payload))
            continue

        defined_at = max(high_time, low_time)
        if latest is None or latest <= defined_at:
            payload["reason_codes"] = ["NO_W1_CANDLES_AFTER_RANGE_DEFINED"]
            outputs.append(_output(node, "PENDING", payload))
            continue

        range_size = high - low
        discount_ceiling = low + (range_size * 0.25)
        fair_price = low + (range_size * 0.50)
        premium_floor = low + (range_size * 0.75)

        loaded = [dict(candle) for candle in context.load_candles(
            timeframe="W1",
            start_time=_stamp(defined_at),
            end_time=_stamp(latest),
        )]
        candles = sorted(
            (
                candle for candle in loaded
                if (candle_time := _time(candle.get("time"))) is not None
                and candle_time > defined_at
            ),
            key=lambda candle: _time(candle.get("time")),
        )
        if not candles:
            payload["reason_codes"] = ["NO_W1_CANDLES_AFTER_RANGE_DEFINED"]
            outputs.append(_output(node, "PENDING", payload))
            continue

        events: list[dict[str, Any]] = []
        ambiguous_rejections: list[str] = []
        invalid_ohlc = False
        for index, candle in enumerate(candles):
            candle_time = _time(candle.get("time"))
            candle_high = _number(candle.get("high"))
            candle_low = _number(candle.get("low"))
            candle_close = _number(candle.get("close"))
            candle_open = _number(candle.get("open"))
            if (
                candle_time is None
                or candle_high is None
                or candle_low is None
                or candle_close is None
                or candle_open is None
                or candle_high + _EPSILON < max(candle_open, candle_close)
                or candle_low - _EPSILON > min(candle_open, candle_close)
            ):
                invalid_ohlc = True
                break

            discount_rejection = (
                candle_low - _EPSILON <= discount_ceiling
                and candle_close > discount_ceiling + _EPSILON
            )
            premium_rejection = (
                candle_high + _EPSILON >= premium_floor
                and candle_close < premium_floor - _EPSILON
            )

            if discount_rejection and premium_rejection:
                ambiguous_rejections.append(_stamp(candle_time))
                continue
            if not discount_rejection and not premium_rejection:
                continue

            origin = "DISCOUNT_EXTREME" if discount_rejection else "PREMIUM_EXTREME"
            events.append(_journey(
                candles,
                rejection_index=index,
                origin_zone=origin,
                range_low=low,
                range_high=high,
                fair_price=fair_price,
                discount_ceiling=discount_ceiling,
                premium_floor=premium_floor,
            ))

        if invalid_ohlc:
            payload["reason_codes"] = ["INVALID_W1_OHLC_IN_RANGE_WINDOW"]
            outputs.append(_output(node, "NEEDS_REVIEW", payload))
            continue

        payload["rejection_events"] = events
        payload["rejection_event_count"] = len(events)
        payload["completed_event_count"] = sum(
            event["journey_status"] == "COMPLETE" for event in events
        )
        payload["pending_event_count"] = sum(
            event["journey_status"] == "PENDING" for event in events
        )

        primary = _primary_event(events)
        if primary is not None:
            payload.update({
                "primary_origin_zone": primary["origin_zone"],
                "primary_rejection_time": primary["rejection_time"],
                "primary_rejection_price": primary["rejection_price"],
                "primary_maximum_destination": primary["maximum_destination"],
                "primary_journey_status": primary["journey_status"],
                "primary_fair_price_reached": primary["fair_price_reached"],
                "primary_weeks_to_fair_price": primary["weeks_to_fair_price"],
                "primary_opposite_extreme_reached": primary["opposite_extreme_reached"],
                "primary_weeks_to_opposite_extreme": primary["weeks_to_opposite_extreme"],
                "primary_opposite_external_reached": primary["opposite_external_reached"],
                "primary_weeks_to_opposite_external": primary["weeks_to_opposite_external"],
                "primary_terminal_reason": primary["terminal_reason"],
            })

        journey_review = any(
            event["journey_status"] == "NEEDS_REVIEW" for event in events
        )
        if ambiguous_rejections or journey_review:
            reasons: list[str] = []
            if ambiguous_rejections:
                reasons.append("BOTH_EXTREMES_REJECTED_SAME_W1")
                reasons.extend(f"AMBIGUOUS_REJECTION_{time}" for time in ambiguous_rejections)
            if journey_review:
                reasons.append("DESTINATION_ORDER_NEEDS_REVIEW")
            payload["reason_codes"] = reasons
            outputs.append(_output(node, "NEEDS_REVIEW", payload))
            continue

        if not events:
            payload["reason_codes"] = ["NO_CONFIRMED_EXTREME_REJECTION"]
            outputs.append(_output(node, "PENDING", payload))
            continue

        if any(event["journey_status"] == "PENDING" for event in events):
            payload["reason_codes"] = ["ONE_OR_MORE_REJECTION_JOURNEYS_STILL_OPEN"]
            outputs.append(_output(node, "PENDING", payload))
            continue

        payload["reason_codes"] = ["EXTREME_REJECTION_DESTINATIONS_COMPLETE"]
        outputs.append(_output(node, "COMPLETE", payload))

    return {"outputs": outputs}
