"""Build the ordered Weekly movement path between two approved BOS events.

This package consumes approved Weekly Reclaim Depth memory for Range 1 and
approved Weekly BOS memory for the mapped Range 2. It does not detect anchors,
rebuild ranges, or recalculate Fib depth.

Weekly candle direction supplies movement evidence:

* bullish W1 path: Open -> Low -> Close -> High;
* bearish W1 path: Open -> High -> Close -> Low.

For BOS Up, bearish candles are countertrend and bullish candles are protrend.
For BOS Down, bullish candles are countertrend and bearish candles are protrend.

Consecutive candles with the same role form one movement leg. A direction change
starts a new leg. The next approved Range 2 BOS is the terminal event and its
candle is excluded from the preceding movement-leg counts.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Mapping

FXTM_DOCTRINE_CONTRACT = "fxtm_doctrine_package_v1"
SCRIPT_KEY = "weekly_movement_classification"
VERSION_LABEL = "3"
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
    return {
        "movement_path": None,
        "movement_sequence": None,
        "movement_leg_count": None,
        "countertrend_leg_count": None,
        "protrend_leg_count": None,
        "countertrend_weeks": None,
        "protrend_weeks": None,
        "source_bos_direction": None,
        "source_bos_time": None,
        "next_bos_direction": None,
        "next_bos_time": None,
        "countertrend_classification": None,
        "countertrend_direction": None,
        "countertrend_distance": None,
        "countertrend_depth_percent": None,
        "protrend_direction": None,
        "protrend_distance": None,
        "source_range1_id": None,
        "range2_id": None,
        "movement_legs": [],
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


def _movement_role(
    candle: Mapping[str, Any],
    *,
    countertrend_candle_type: str,
    protrend_candle_type: str,
) -> str:
    direction = _candle_direction(candle)
    if direction == countertrend_candle_type:
        return "CT"
    if direction == protrend_candle_type:
        return "PT"
    return direction


def _build_legs(
    candles: list[dict[str, Any]],
    *,
    countertrend_candle_type: str,
    protrend_candle_type: str,
    countertrend_direction: str,
    protrend_direction: str,
) -> list[dict[str, Any]]:
    legs: list[dict[str, Any]] = []
    for candle in candles:
        role = _movement_role(
            candle,
            countertrend_candle_type=countertrend_candle_type,
            protrend_candle_type=protrend_candle_type,
        )
        candle_time = _time(candle.get("time"))
        if role not in {"CT", "PT"} or candle_time is None:
            continue
        if legs and legs[-1]["code"] == role:
            legs[-1]["weeks"] += 1
            legs[-1]["end_time"] = _stamp(candle_time)
            legs[-1]["candle_times"].append(_stamp(candle_time))
            continue
        legs.append({
            "code": role,
            "classification": "COUNTERTREND" if role == "CT" else "PROTREND",
            "direction": countertrend_direction if role == "CT" else protrend_direction,
            "weeks": 1,
            "start_time": _stamp(candle_time),
            "end_time": _stamp(candle_time),
            "candle_times": [_stamp(candle_time)],
        })
    return legs


def _path(legs: list[dict[str, Any]], next_bos_direction: str) -> str:
    tokens = [f"{leg['code']} {leg['weeks']}W" for leg in legs]
    tokens.append(next_bos_direction)
    return " -> ".join(tokens)


def _sequence(legs: list[dict[str, Any]]) -> str:
    return "_THEN_".join(str(leg["classification"]) for leg in legs)


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
        source_bos_direction = str(depth.get("source_bos_direction") or "").upper()
        source_bos_time = _time(depth.get("source_bos_time"))
        range2_id = str(depth.get("range2_id") or "").strip()
        opposite_price = _number(depth.get("range2_opposite_anchor_price"))
        continuation_price = _number(depth.get("range2_continuation_anchor_price"))
        countertrend_distance = _number(depth.get("reclaim_depth_price"))
        countertrend_percent = _number(depth.get("reclaim_depth_percent"))

        payload.update({
            "source_bos_direction": source_bos_direction or None,
            "source_bos_time": _stamp(source_bos_time) if source_bos_time else None,
            "range2_id": range2_id or None,
        })

        if depth_status not in _COMPLETE_DEPTH_STATES:
            payload["reason_codes"] = ["WEEKLY_RECLAIM_DEPTH_STILL_PENDING"]
            outputs.append(_output(node, "PENDING", payload))
            continue
        if source_bos_direction not in {"BOS_UP", "BOS_DOWN"}:
            payload["reason_codes"] = ["SOURCE_BOS_DIRECTION_INVALID"]
            outputs.append(_output(node, "NEEDS_REVIEW", payload))
            continue
        if (
            not range2_id
            or source_bos_time is None
            or opposite_price is None
            or continuation_price is None
            or countertrend_distance is None
            or countertrend_percent is None
        ):
            payload["reason_codes"] = ["WEEKLY_MOVEMENT_INPUTS_INCOMPLETE"]
            outputs.append(_output(node, "NEEDS_REVIEW", payload))
            continue

        next_bos, next_bos_processing = _memory_entry(
            context,
            range2_id,
            "weekly_structure",
        )
        if next_bos is None:
            payload["reason_codes"] = ["APPROVED_RANGE2_BOS_MEMORY_MISSING"]
            outputs.append(_output(node, "PENDING", payload))
            continue
        if next_bos_processing == "NEEDS_REVIEW":
            payload["reason_codes"] = ["RANGE2_BOS_NEEDS_REVIEW"]
            outputs.append(_output(node, "NEEDS_REVIEW", payload))
            continue
        if next_bos_processing not in {"", "COMPLETE"}:
            payload["reason_codes"] = ["RANGE2_BOS_STILL_PENDING"]
            outputs.append(_output(node, "PENDING", payload))
            continue

        next_bos_direction = str(next_bos.get("bos_direction") or "").upper()
        next_bos_time = _time(next_bos.get("bos_time"))
        payload.update({
            "next_bos_direction": next_bos_direction or None,
            "next_bos_time": _stamp(next_bos_time) if next_bos_time else None,
        })
        if next_bos_direction not in {"BOS_UP", "BOS_DOWN"} or next_bos_time is None:
            payload["reason_codes"] = ["RANGE2_BOS_INPUTS_INCOMPLETE"]
            outputs.append(_output(node, "PENDING", payload))
            continue
        if next_bos_time <= source_bos_time:
            payload["reason_codes"] = ["NEXT_BOS_NOT_AFTER_SOURCE_BOS"]
            outputs.append(_output(node, "NEEDS_REVIEW", payload))
            continue

        loaded = [dict(candle) for candle in context.load_candles(
            timeframe="W1",
            start_time=_stamp(source_bos_time),
            end_time=_stamp(next_bos_time),
        )]
        chapter = sorted(
            (
                candle
                for candle in loaded
                if (candle_time := _time(candle.get("time"))) is not None
                and source_bos_time < candle_time < next_bos_time
            ),
            key=lambda candle: _time(candle.get("time")),
        )
        if not chapter:
            payload["reason_codes"] = ["NO_W1_MOVEMENT_CANDLES_BETWEEN_BOS_EVENTS"]
            outputs.append(_output(node, "NEEDS_REVIEW", payload))
            continue

        candle_directions = [_candle_direction(candle) for candle in chapter]
        if "INVALID" in candle_directions:
            payload["reason_codes"] = ["INVALID_W1_OHLC_IN_MOVEMENT_CHAPTER"]
            outputs.append(_output(node, "NEEDS_REVIEW", payload))
            continue
        if "DOJI" in candle_directions:
            payload["reason_codes"] = ["DOJI_W1_MOVEMENT_ROLE_NOT_DEFINED"]
            outputs.append(_output(node, "NEEDS_REVIEW", payload))
            continue

        countertrend_candle_type, protrend_candle_type, countertrend_direction, protrend_direction = (
            _movement_directions(source_bos_direction)
        )
        legs = _build_legs(
            chapter,
            countertrend_candle_type=countertrend_candle_type,
            protrend_candle_type=protrend_candle_type,
            countertrend_direction=countertrend_direction,
            protrend_direction=protrend_direction,
        )
        if not legs:
            payload["reason_codes"] = ["NO_CLASSIFIABLE_W1_MOVEMENT_LEGS"]
            outputs.append(_output(node, "NEEDS_REVIEW", payload))
            continue

        countertrend_weeks = sum(
            int(leg["weeks"]) for leg in legs if leg["code"] == "CT"
        )
        protrend_weeks = sum(
            int(leg["weeks"]) for leg in legs if leg["code"] == "PT"
        )
        countertrend_leg_count = sum(1 for leg in legs if leg["code"] == "CT")
        protrend_leg_count = sum(1 for leg in legs if leg["code"] == "PT")
        protrend_distance = abs(continuation_price - opposite_price)

        payload.update({
            "movement_path": _path(legs, next_bos_direction),
            "movement_sequence": _sequence(legs),
            "movement_leg_count": len(legs),
            "countertrend_leg_count": countertrend_leg_count,
            "protrend_leg_count": protrend_leg_count,
            "countertrend_weeks": countertrend_weeks,
            "protrend_weeks": protrend_weeks,
            "countertrend_classification": _countertrend_classification(depth_status),
            "countertrend_direction": countertrend_direction,
            "countertrend_distance": round(max(0.0, countertrend_distance), 8),
            "countertrend_depth_percent": round(max(0.0, countertrend_percent), 8),
            "protrend_direction": protrend_direction,
            "protrend_distance": round(protrend_distance, 8),
            "movement_legs": legs,
            "reason_codes": [],
        })
        outputs.append(_output(node, "COMPLETE", payload))

    return {"outputs": outputs}
