"""Classify the two structural movements that create the next Weekly range.

This package consumes approved Weekly Reclaim Depth memory. It does not detect
new anchors, rebuild ranges, or recalculate Fib depth.

Weekly candle direction supplies the movement evidence:

* bullish W1 path: Open -> Low -> Close -> High;
* bearish W1 path: Open -> High -> Close -> Low.

For BOS Up, bearish candles are countertrend and bullish candles are protrend.
For BOS Down, bullish candles are countertrend and bearish candles are protrend.

Range 2 anchor chronology still defines the structural movement windows. When
both Range 2 anchors belong to the same W1 candle, that candle's OHLC direction
resolves the likely intrawweek order instead of reporting zero movement merely
because both mapped anchor timestamps are equal.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Mapping

FXTM_DOCTRINE_CONTRACT = "fxtm_doctrine_package_v1"
SCRIPT_KEY = "weekly_movement_classification"
VERSION_LABEL = "2"
ADAPTER_KEY = "doctrine_package_v1"
EXECUTION_ORDER = 40


_COMPLETE_DEPTH_STATES = {
    "NO_RETRACEMENT",
    "BOUNDARY_TOUCH",
    "RETRACED_INTO_RANGE",
    "TOUCHED_OLD_OPPOSITE",
    "EXCEEDED_OLD_OPPOSITE",
}
_EPSILON = 1e-9


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


def _memory_entry(
    context: Any,
    canonical_range_id: str,
    key: str,
) -> tuple[dict[str, Any] | None, str]:
    memory = context.approved_memory(canonical_range_id)
    if not isinstance(memory, Mapping):
        return None, "MISSING"
    entry = memory.get(key)
    if not isinstance(entry, Mapping):
        return None, "MISSING"
    payload = entry.get("payload")
    if not isinstance(payload, Mapping):
        return None, "MISSING"
    return dict(payload), str(entry.get("processing_status") or "").upper()


def _output(node: Mapping[str, Any], status: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "canonical_range_id": str(node.get("id") or ""),
        "processing_status": status,
        "payload": payload,
    }


def _base_payload() -> dict[str, Any]:
    # Keep the candidate card intentionally small. Detailed anchor geometry stays
    # in Weekly Reclaim Depth rather than being copied into this script.
    return {
        "movement_sequence": None,
        "source_bos_direction": None,
        "countertrend_classification": None,
        "countertrend_direction": None,
        "countertrend_distance": None,
        "countertrend_depth_percent": None,
        "countertrend_weeks": None,
        "protrend_direction": None,
        "protrend_distance": None,
        "protrend_weeks": None,
        "source_range1_id": None,
        "range2_id": None,
        "reason_codes": [],
    }


def _countertrend_classification(depth_status: str) -> str:
    if depth_status == "NO_RETRACEMENT":
        return "NO_RANGE1_RETRACEMENT"
    if depth_status == "BOUNDARY_TOUCH":
        return "BOUNDARY_TOUCH"
    return "COUNTERTREND_RETRACEMENT"


def _candle_direction(candle: Mapping[str, Any]) -> str:
    open_price = _number(candle.get("open"))
    high = _number(candle.get("high"))
    low = _number(candle.get("low"))
    close = _number(candle.get("close"))
    if None in {open_price, high, low, close}:
        return "INVALID"
    if high + _EPSILON < max(open_price, close) or low - _EPSILON > min(open_price, close):
        return "INVALID"
    if close > open_price + _EPSILON:
        return "BULLISH"
    if close < open_price - _EPSILON:
        return "BEARISH"
    return "DOJI"


def _movement_directions(bos_direction: str) -> tuple[str, str, str, str]:
    if bos_direction == "BOS_UP":
        return "BEARISH", "BULLISH", "DOWN", "UP"
    return "BULLISH", "BEARISH", "UP", "DOWN"


def _sequence_from_anchor_order(anchor_sequence: str) -> str:
    if anchor_sequence == "OPPOSITE_THEN_CONTINUATION":
        return "COUNTERTREND_THEN_PROTREND"
    if anchor_sequence == "CONTINUATION_THEN_OPPOSITE":
        return "PROTREND_THEN_COUNTERTREND"
    return "SAME_W1_MOVEMENTS"


def _same_w1_sequence(bos_direction: str, candle_direction: str) -> str | None:
    """Resolve same-W1 anchor order from the user's OHLC path doctrine."""
    if candle_direction == "BULLISH":
        # Open -> Low -> Close -> High.
        return (
            "COUNTERTREND_THEN_PROTREND"
            if bos_direction == "BOS_UP"
            else "PROTREND_THEN_COUNTERTREND"
        )
    if candle_direction == "BEARISH":
        # Open -> High -> Close -> Low.
        return (
            "PROTREND_THEN_COUNTERTREND"
            if bos_direction == "BOS_UP"
            else "COUNTERTREND_THEN_PROTREND"
        )
    return None


def _window_candles(
    candles: list[dict[str, Any]],
    *,
    start_exclusive: datetime,
    end_inclusive: datetime,
) -> list[dict[str, Any]]:
    return [
        candle
        for candle in candles
        if (candle_time := _time(candle.get("time"))) is not None
        and start_exclusive < candle_time <= end_inclusive
    ]


def _count_direction(candles: list[dict[str, Any]], wanted: str) -> int:
    return sum(1 for candle in candles if _candle_direction(candle) == wanted)


def run(context: Any) -> dict[str, list[dict[str, Any]]]:
    outputs: list[dict[str, Any]] = []
    for raw_node in context.selected_ranges(layer="WEEKLY"):
        node = dict(raw_node)
        canonical_id = str(node.get("id") or "")
        payload = _base_payload()
        payload["source_range1_id"] = canonical_id

        depth, depth_processing = _memory_entry(
            context,
            canonical_id,
            "weekly_reclaim_depth",
        )
        if depth is None:
            payload["reason_codes"] = ["APPROVED_WEEKLY_RECLAIM_DEPTH_MEMORY_MISSING"]
            outputs.append(_output(node, "PENDING", payload))
            continue
        if depth_processing == "NEEDS_REVIEW":
            payload["reason_codes"] = ["WEEKLY_RECLAIM_DEPTH_NEEDS_REVIEW"]
            outputs.append(_output(node, "NEEDS_REVIEW", payload))
            continue
        if depth_processing not in {"", "COMPLETE"}:
            payload["reason_codes"] = ["WEEKLY_RECLAIM_DEPTH_NOT_COMPLETE"]
            outputs.append(_output(node, "PENDING", payload))
            continue

        depth_status = str(depth.get("depth_status") or "").upper()
        bos_direction = str(depth.get("source_bos_direction") or "").upper()
        anchor_sequence = str(depth.get("range2_anchor_sequence") or "").upper()
        range2_id = str(depth.get("range2_id") or "").strip()
        bos_time = _time(depth.get("source_bos_time"))
        opposite_time = _time(depth.get("range2_opposite_anchor_time"))
        continuation_time = _time(depth.get("range2_continuation_anchor_time"))
        completion_time = _time(
            depth.get("range2_completed_at")
            or depth.get("range2_completion_anchor_time")
        )
        opposite_price = _number(depth.get("range2_opposite_anchor_price"))
        continuation_price = _number(depth.get("range2_continuation_anchor_price"))
        countertrend_distance = _number(depth.get("reclaim_depth_price"))
        countertrend_percent = _number(depth.get("reclaim_depth_percent"))

        payload.update({
            "source_bos_direction": bos_direction or None,
            "range2_id": range2_id or None,
        })

        if depth_status not in _COMPLETE_DEPTH_STATES:
            payload["reason_codes"] = ["WEEKLY_RECLAIM_DEPTH_STILL_PENDING"]
            outputs.append(_output(node, "PENDING", payload))
            continue
        if bos_direction not in {"BOS_UP", "BOS_DOWN"}:
            payload["reason_codes"] = ["SOURCE_BOS_DIRECTION_INVALID"]
            outputs.append(_output(node, "NEEDS_REVIEW", payload))
            continue
        if anchor_sequence not in {
            "OPPOSITE_THEN_CONTINUATION",
            "CONTINUATION_THEN_OPPOSITE",
            "SAME_W1",
        }:
            payload["reason_codes"] = ["RANGE2_ANCHOR_SEQUENCE_INVALID"]
            outputs.append(_output(node, "NEEDS_REVIEW", payload))
            continue
        if (
            not range2_id
            or bos_time is None
            or opposite_time is None
            or continuation_time is None
            or completion_time is None
            or opposite_price is None
            or continuation_price is None
            or countertrend_distance is None
            or countertrend_percent is None
        ):
            payload["reason_codes"] = ["WEEKLY_MOVEMENT_INPUTS_INCOMPLETE"]
            outputs.append(_output(node, "NEEDS_REVIEW", payload))
            continue
        if completion_time < bos_time:
            payload["reason_codes"] = ["RANGE2_COMPLETES_BEFORE_SOURCE_BOS"]
            outputs.append(_output(node, "NEEDS_REVIEW", payload))
            continue

        loaded = [dict(candle) for candle in context.load_candles(
            timeframe="W1",
            start_time=_stamp(bos_time),
            end_time=_stamp(completion_time),
        )]
        candles = sorted(
            (
                candle for candle in loaded
                if _time(candle.get("time")) is not None
            ),
            key=lambda candle: _time(candle.get("time")),
        )
        chapter = _window_candles(
            candles,
            start_exclusive=bos_time,
            end_inclusive=completion_time,
        )
        if not chapter:
            payload["reason_codes"] = ["NO_W1_CANDLES_AFTER_BOS_BEFORE_RANGE2_COMPLETION"]
            outputs.append(_output(node, "NEEDS_REVIEW", payload))
            continue
        if any(_candle_direction(candle) == "INVALID" for candle in chapter):
            payload["reason_codes"] = ["INVALID_W1_OHLC_IN_MOVEMENT_WINDOW"]
            outputs.append(_output(node, "NEEDS_REVIEW", payload))
            continue

        countertrend_candle_type, protrend_candle_type, countertrend_direction, protrend_direction = (
            _movement_directions(bos_direction)
        )

        if anchor_sequence == "OPPOSITE_THEN_CONTINUATION":
            countertrend_window = _window_candles(
                candles,
                start_exclusive=bos_time,
                end_inclusive=opposite_time,
            )
            protrend_window = _window_candles(
                candles,
                start_exclusive=opposite_time,
                end_inclusive=continuation_time,
            )
            movement_sequence = "COUNTERTREND_THEN_PROTREND"
        elif anchor_sequence == "CONTINUATION_THEN_OPPOSITE":
            protrend_window = _window_candles(
                candles,
                start_exclusive=bos_time,
                end_inclusive=continuation_time,
            )
            countertrend_window = _window_candles(
                candles,
                start_exclusive=continuation_time,
                end_inclusive=opposite_time,
            )
            movement_sequence = "PROTREND_THEN_COUNTERTREND"
        else:
            # Both mapped anchors share one W1 candle. Count the actual bullish and
            # bearish candles across the full post-BOS chapter, then use the anchor
            # candle's OHLC path to resolve which side occurred first intrawweek.
            countertrend_window = chapter
            protrend_window = chapter
            anchor_candle = next(
                (
                    candle for candle in chapter
                    if _time(candle.get("time")) == opposite_time
                ),
                None,
            )
            anchor_direction = (
                _candle_direction(anchor_candle)
                if anchor_candle is not None
                else "MISSING"
            )
            movement_sequence = _same_w1_sequence(
                bos_direction,
                anchor_direction,
            )
            if movement_sequence is None:
                payload["reason_codes"] = [
                    "SAME_W1_ORDER_NOT_PROVABLE_FROM_DOJI_OR_MISSING_CANDLE"
                ]
                outputs.append(_output(node, "NEEDS_REVIEW", payload))
                continue

        countertrend_weeks = _count_direction(
            countertrend_window,
            countertrend_candle_type,
        )
        protrend_weeks = _count_direction(
            protrend_window,
            protrend_candle_type,
        )
        protrend_distance = abs(continuation_price - opposite_price)

        payload.update({
            "movement_sequence": movement_sequence,
            "countertrend_classification": _countertrend_classification(depth_status),
            "countertrend_direction": countertrend_direction,
            "countertrend_distance": round(max(0.0, countertrend_distance), 8),
            "countertrend_depth_percent": round(max(0.0, countertrend_percent), 8),
            "countertrend_weeks": countertrend_weeks,
            "protrend_direction": protrend_direction,
            "protrend_distance": round(protrend_distance, 8),
            "protrend_weeks": protrend_weeks,
            "reason_codes": [],
        })
        outputs.append(_output(node, "COMPLETE", payload))

    return {"outputs": outputs}
