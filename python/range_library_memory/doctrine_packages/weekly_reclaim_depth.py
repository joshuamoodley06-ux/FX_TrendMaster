"""Weekly Range 2 reclaim-depth doctrine package.

This package consumes approved Weekly BOS and reclaim memory. It does not infer
or build the range lifecycle. It reads the mapped next Weekly range and keeps
two separate structural endpoints:

* depth endpoint: the new opposite anchor created by the reclaim/pullback;
* range completion: the later of the mapped RH and RL anchors.

BOS Up:   W1 RH = 0, W1 RL = 1, measure W2 RL.
BOS Down: W1 RL = 0, W1 RH = 1, measure W2 RH.

The opposite anchor may form before or after the continuation-side anchor. This
supports both common stories:

* opposite anchor first, later continuation anchor completes the range;
* continuation-side anchor already exists, later reclaim creates the opposite
  anchor and completes the range.

Raw Fib values remain stored for audit. Trader-facing values never show a
negative retracement: an opposite Range 2 anchor that remains beyond the broken
boundary is classified as NO_RETRACEMENT with a trading depth of 0%.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Mapping

FXTM_DOCTRINE_CONTRACT = "fxtm_doctrine_package_v1"
SCRIPT_KEY = "weekly_reclaim_depth"
VERSION_LABEL = "6"
ADAPTER_KEY = "doctrine_package_v1"
EXECUTION_ORDER = 30


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


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


def _stamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _week_distance(start: datetime, end: datetime) -> int:
    seconds = max(0.0, (end - start).total_seconds())
    return int(round(seconds / (7 * 24 * 60 * 60)))


def _output(node: Mapping[str, Any], status: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "canonical_range_id": str(node.get("id") or ""),
        "processing_status": status,
        "payload": payload,
    }


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


def _base_payload() -> dict[str, Any]:
    return {
        "depth_status": "PENDING",
        "depth_classification": "PENDING",
        "source_range1_id": None,
        "source_bos_direction": None,
        "source_bos_time": None,
        "source_reclaim_status": None,
        "source_reclaim_abbreviation": None,
        "source_reclaim_time": None,
        "source_weeks_to_reclaim": None,
        "range1_high": None,
        "range1_low": None,
        "range1_size": None,
        "fib_zero_price": None,
        "fib_one_price": None,
        "range2_id": None,
        "range2_defined_at": None,
        "range2_completed_at": None,
        "range2_chronology": None,
        "range2_anchor_sequence": None,
        "range2_selection_rule": None,
        "range2_completion_anchor_type": None,
        "range2_completion_anchor_price": None,
        "range2_completion_anchor_time": None,
        "depth_window_start_time": None,
        "depth_window_end_time": None,
        "range2_opposite_anchor_type": None,
        "range2_opposite_anchor_price": None,
        "range2_opposite_anchor_time": None,
        "range2_continuation_anchor_type": None,
        "range2_continuation_anchor_price": None,
        "range2_continuation_anchor_time": None,
        "reclaim_depth_price": None,
        "reclaim_depth_ratio": None,
        "reclaim_depth_percent": None,
        "raw_reclaim_depth_price": None,
        "raw_reclaim_depth_ratio": None,
        "raw_reclaim_depth_percent": None,
        "boundary_distance_price": None,
        "boundary_position": None,
        "weeks_bos_to_depth_anchor": None,
        "weeks_reclaim_to_depth_anchor": None,
        "weeks_bos_to_range2_completion": None,
        "weeks_reclaim_to_range2_completion": None,
        # Backward-compatible aliases used by the current audit panel.
        "weeks_bos_to_range2_definition": None,
        "weeks_reclaim_to_range2_definition": None,
        "range2_formation_weeks": None,
        "old_opposite_external_touched": False,
        "old_opposite_external_exceeded": False,
        "reason_codes": [],
    }


def _chronology(high_time: datetime, low_time: datetime) -> str:
    if high_time == low_time:
        return "SAME_W1"
    return "RL_TO_RH" if low_time < high_time else "RH_TO_RL"


def _completion_anchor(
    *,
    high_time: datetime,
    low_time: datetime,
    high: float,
    low: float,
) -> tuple[str, float | None, datetime]:
    if high_time > low_time:
        return "RH", high, high_time
    if low_time > high_time:
        return "RL", low, low_time
    return "SAME_W1", None, high_time


def _anchor_sequence(opposite_time: datetime, continuation_time: datetime) -> str:
    if opposite_time < continuation_time:
        return "OPPOSITE_THEN_CONTINUATION"
    if continuation_time < opposite_time:
        return "CONTINUATION_THEN_OPPOSITE"
    return "SAME_W1"


def _trading_depth(
    *,
    direction: str,
    raw_depth_price: float,
    raw_ratio: float,
    range_high: float,
    range_low: float,
    opposite_price: float,
) -> dict[str, Any]:
    """Translate raw Fib geometry into trader-facing depth without losing audit data."""
    if raw_ratio < -_EPSILON:
        distance = abs(raw_depth_price)
        boundary = "ABOVE_BROKEN_RH" if direction == "BOS_UP" else "BELOW_BROKEN_RL"
        broken_label = "RH" if direction == "BOS_UP" else "RL"
        relation = "ABOVE" if direction == "BOS_UP" else "BELOW"
        return {
            "classification": "NO_RETRACEMENT",
            "price": 0.0,
            "ratio": 0.0,
            "percent": 0.0,
            "boundary_distance": distance,
            "boundary_position": boundary,
            "reason_codes": [
                f"RANGE2_OPPOSITE_{distance:.4f}_{relation}_BROKEN_{broken_label}"
            ],
        }
    if abs(raw_ratio) <= _EPSILON:
        return {
            "classification": "BOUNDARY_TOUCH",
            "price": 0.0,
            "ratio": 0.0,
            "percent": 0.0,
            "boundary_distance": 0.0,
            "boundary_position": "AT_BROKEN_RH" if direction == "BOS_UP" else "AT_BROKEN_RL",
            "reason_codes": [],
        }
    if raw_ratio < 1.0 - _EPSILON:
        return {
            "classification": "RETRACED_INTO_RANGE",
            "price": raw_depth_price,
            "ratio": raw_ratio,
            "percent": raw_ratio * 100.0,
            "boundary_distance": raw_depth_price,
            "boundary_position": "INSIDE_RANGE1",
            "reason_codes": [],
        }
    if abs(raw_ratio - 1.0) <= _EPSILON:
        return {
            "classification": "TOUCHED_OLD_OPPOSITE",
            "price": raw_depth_price,
            "ratio": 1.0,
            "percent": 100.0,
            "boundary_distance": 0.0,
            "boundary_position": "AT_OLD_RL" if direction == "BOS_UP" else "AT_OLD_RH",
            "reason_codes": [],
        }
    exceeded_distance = (
        range_low - opposite_price
        if direction == "BOS_UP"
        else opposite_price - range_high
    )
    opposite_label = "RL" if direction == "BOS_UP" else "RH"
    relation = "BELOW" if direction == "BOS_UP" else "ABOVE"
    return {
        "classification": "EXCEEDED_OLD_OPPOSITE",
        "price": raw_depth_price,
        "ratio": raw_ratio,
        "percent": raw_ratio * 100.0,
        "boundary_distance": exceeded_distance,
        "boundary_position": "BELOW_OLD_RL" if direction == "BOS_UP" else "ABOVE_OLD_RH",
        "reason_codes": [
            f"RANGE2_OPPOSITE_{exceeded_distance:.4f}_{relation}_OLD_{opposite_label}"
        ],
    }


def run(context: Any) -> dict[str, list[dict[str, Any]]]:
    nodes = [dict(node) for node in context.selected_ranges(layer="WEEKLY")]
    records: list[dict[str, Any]] = []
    for node in nodes:
        canonical_id = str(node.get("id") or "")
        bos, bos_status = _memory_entry(context, canonical_id, "weekly_structure")
        reclaim, reclaim_status = _memory_entry(context, canonical_id, "weekly_reclaim")
        high_time = _time(node.get("range_high_time"))
        low_time = _time(node.get("range_low_time"))
        high = _number(node.get("range_high"))
        low = _number(node.get("range_low"))
        completion_time = (
            max(high_time, low_time)
            if high_time is not None and low_time is not None
            else None
        )
        records.append({
            "node": node,
            "id": canonical_id,
            "bos": bos,
            "bos_status": bos_status,
            "reclaim": reclaim,
            "reclaim_processing_status": reclaim_status,
            "bos_time": _time((bos or {}).get("bos_time")),
            "bos_direction": str((bos or {}).get("bos_direction") or "").upper(),
            "high": high,
            "low": low,
            "high_time": high_time,
            "low_time": low_time,
            "completion_time": completion_time,
            "chronology": (
                _chronology(high_time, low_time)
                if high_time is not None and low_time is not None
                else "PENDING"
            ),
        })

    outputs: list[dict[str, Any]] = []
    for current in records:
        node = current["node"]
        payload = _base_payload()
        payload["source_range1_id"] = current["id"]
        bos = current["bos"]
        reclaim = current["reclaim"]
        direction = current["bos_direction"]
        bos_time = current["bos_time"]
        high = current["high"]
        low = current["low"]

        if bos is None:
            payload["reason_codes"] = ["APPROVED_WEEKLY_BOS_MEMORY_MISSING"]
            outputs.append(_output(node, "PENDING", payload))
            continue
        if current["bos_status"] not in {"", "COMPLETE"}:
            payload["reason_codes"] = ["WEEKLY_BOS_NOT_COMPLETE"]
            outputs.append(_output(node, "PENDING", payload))
            continue
        if direction not in {"BOS_UP", "BOS_DOWN"} or bos_time is None:
            payload["depth_status"] = "NEEDS_REVIEW"
            payload["depth_classification"] = "NEEDS_REVIEW"
            payload["reason_codes"] = ["APPROVED_WEEKLY_BOS_MEMORY_INCOMPLETE"]
            outputs.append(_output(node, "NEEDS_REVIEW", payload))
            continue
        if high is None or low is None or high <= low:
            payload["depth_status"] = "NEEDS_REVIEW"
            payload["depth_classification"] = "NEEDS_REVIEW"
            payload["reason_codes"] = ["INVALID_RANGE1_PRICES"]
            outputs.append(_output(node, "NEEDS_REVIEW", payload))
            continue

        payload.update({
            "source_bos_direction": direction,
            "source_bos_time": _stamp(bos_time),
            "range1_high": high,
            "range1_low": low,
            "range1_size": high - low,
        })

        if reclaim is None:
            payload["reason_codes"] = ["APPROVED_WEEKLY_RECLAIM_MEMORY_MISSING"]
            outputs.append(_output(node, "PENDING", payload))
            continue

        reclaim_state = str(reclaim.get("reclaim_status") or "").upper()
        reclaim_time = _time(reclaim.get("reclaim_time"))
        payload.update({
            "source_reclaim_status": reclaim.get("reclaim_status"),
            "source_reclaim_abbreviation": reclaim.get("reclaim_abbreviation"),
            "source_reclaim_time": reclaim.get("reclaim_time"),
            "source_weeks_to_reclaim": reclaim.get("weeks_to_reclaim"),
        })

        if current["reclaim_processing_status"] == "NEEDS_REVIEW" or reclaim_state == "NEEDS_REVIEW":
            payload["depth_status"] = "NEEDS_REVIEW"
            payload["depth_classification"] = "NEEDS_REVIEW"
            payload["reason_codes"] = ["WEEKLY_RECLAIM_NEEDS_REVIEW"]
            outputs.append(_output(node, "NEEDS_REVIEW", payload))
            continue
        if reclaim_state in {"PENDING", "ABANDONED", ""} or reclaim_time is None:
            payload["reason_codes"] = ["RANGE2_DEPTH_WAITING_FOR_RECLAIM"]
            outputs.append(_output(node, "PENDING", payload))
            continue

        payload["depth_window_start_time"] = _stamp(reclaim_time)
        payload["range2_selection_rule"] = (
            "FIRST_MAPPED_WEEKLY_RANGE_COMPLETED_AFTER_RECLAIM_WITH_NEW_OPPOSITE_ANCHOR"
        )

        def qualifies(record: Mapping[str, Any]) -> bool:
            if record["id"] == current["id"]:
                return False
            high_time = record["high_time"]
            low_time = record["low_time"]
            completion_time = record["completion_time"]
            if high_time is None or low_time is None or completion_time is None:
                return False
            opposite_time = low_time if direction == "BOS_UP" else high_time
            # The new opposite anchor must belong to this reclaim sequence. The
            # continuation-side anchor may already exist from the BOS leg.
            if opposite_time < reclaim_time:
                return False
            return completion_time >= reclaim_time

        candidates = sorted(
            (record for record in records if qualifies(record)),
            key=lambda record: (
                record["completion_time"],
                record["low_time"] if direction == "BOS_UP" else record["high_time"],
                record["id"],
            ),
        )
        range2 = candidates[0] if candidates else None
        if range2 is None:
            payload["reason_codes"] = ["RANGE2_NOT_YET_MAPPED_AFTER_RECLAIM"]
            outputs.append(_output(node, "PENDING", payload))
            continue

        range2_high = range2["high"]
        range2_low = range2["low"]
        high_time = range2["high_time"]
        low_time = range2["low_time"]
        completion_time = range2["completion_time"]
        if range2_high is None or range2_low is None or range2_high <= range2_low:
            payload["depth_status"] = "NEEDS_REVIEW"
            payload["depth_classification"] = "NEEDS_REVIEW"
            payload["reason_codes"] = ["INVALID_RANGE2_PRICES"]
            outputs.append(_output(node, "NEEDS_REVIEW", payload))
            continue
        if high_time is None or low_time is None or completion_time is None:
            payload["depth_status"] = "NEEDS_REVIEW"
            payload["depth_classification"] = "NEEDS_REVIEW"
            payload["reason_codes"] = ["RANGE2_ANCHOR_TIME_MISSING"]
            outputs.append(_output(node, "NEEDS_REVIEW", payload))
            continue

        if direction == "BOS_UP":
            zero = high
            one = low
            opposite_type = "RL"
            opposite_price = range2_low
            opposite_time = low_time
            continuation_type = "RH"
            continuation_price = range2_high
            continuation_time = high_time
            raw_depth_price = zero - opposite_price
            touched = opposite_price <= low
            exceeded = opposite_price < low
        else:
            zero = low
            one = high
            opposite_type = "RH"
            opposite_price = range2_high
            opposite_time = high_time
            continuation_type = "RL"
            continuation_price = range2_low
            continuation_time = low_time
            raw_depth_price = opposite_price - zero
            touched = opposite_price >= high
            exceeded = opposite_price > high

        completion_type, completion_price, completion_time = _completion_anchor(
            high_time=high_time,
            low_time=low_time,
            high=range2_high,
            low=range2_low,
        )
        raw_ratio = raw_depth_price / (high - low)
        trading = _trading_depth(
            direction=direction,
            raw_depth_price=raw_depth_price,
            raw_ratio=raw_ratio,
            range_high=high,
            range_low=low,
            opposite_price=opposite_price,
        )

        weeks_bos_to_completion = _week_distance(bos_time, completion_time)
        weeks_reclaim_to_completion = _week_distance(reclaim_time, completion_time)
        payload.update({
            "depth_status": trading["classification"],
            "depth_classification": trading["classification"],
            "fib_zero_price": zero,
            "fib_one_price": one,
            "range2_id": range2["id"],
            "range2_defined_at": _stamp(completion_time),
            "range2_completed_at": _stamp(completion_time),
            "range2_chronology": range2["chronology"],
            "range2_anchor_sequence": _anchor_sequence(opposite_time, continuation_time),
            "range2_completion_anchor_type": completion_type,
            "range2_completion_anchor_price": completion_price,
            "range2_completion_anchor_time": _stamp(completion_time),
            "depth_window_end_time": _stamp(opposite_time),
            "range2_opposite_anchor_type": opposite_type,
            "range2_opposite_anchor_price": opposite_price,
            "range2_opposite_anchor_time": _stamp(opposite_time),
            "range2_continuation_anchor_type": continuation_type,
            "range2_continuation_anchor_price": continuation_price,
            "range2_continuation_anchor_time": _stamp(continuation_time),
            "reclaim_depth_price": round(float(trading["price"]), 8),
            "reclaim_depth_ratio": round(float(trading["ratio"]), 8),
            "reclaim_depth_percent": round(float(trading["percent"]), 8),
            "raw_reclaim_depth_price": round(raw_depth_price, 8),
            "raw_reclaim_depth_ratio": round(raw_ratio, 8),
            "raw_reclaim_depth_percent": round(raw_ratio * 100.0, 8),
            "boundary_distance_price": round(float(trading["boundary_distance"]), 8),
            "boundary_position": trading["boundary_position"],
            "weeks_bos_to_depth_anchor": _week_distance(bos_time, opposite_time),
            "weeks_reclaim_to_depth_anchor": _week_distance(reclaim_time, opposite_time),
            "weeks_bos_to_range2_completion": weeks_bos_to_completion,
            "weeks_reclaim_to_range2_completion": weeks_reclaim_to_completion,
            "weeks_bos_to_range2_definition": weeks_bos_to_completion,
            "weeks_reclaim_to_range2_definition": weeks_reclaim_to_completion,
            "range2_formation_weeks": _week_distance(
                min(high_time, low_time), max(high_time, low_time)
            ),
            "old_opposite_external_touched": touched,
            "old_opposite_external_exceeded": exceeded,
            "reason_codes": trading["reason_codes"],
        })
        outputs.append(_output(node, "COMPLETE", payload))

    return {"outputs": outputs}
