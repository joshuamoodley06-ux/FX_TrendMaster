"""Weekly reclaim depth doctrine package.

This package consumes approved weekly_structure and weekly_reclaim memory. It
measures the deepest W1 wick reached after reclaim, expressed as both price
movement and percentage of the old Weekly range. It does not hardcode shallow
or deep labels.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Mapping

FXTM_DOCTRINE_CONTRACT = "fxtm_doctrine_package_v1"
SCRIPT_KEY = "weekly_reclaim_depth"
VERSION_LABEL = "1"
ADAPTER_KEY = "doctrine_package_v1"
EXECUTION_ORDER = 30


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


def _output(node: Mapping[str, Any], status: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "canonical_range_id": str(node.get("id") or ""),
        "processing_status": status,
        "payload": payload,
    }


def _memory_payload(context: Any, canonical_range_id: str, key: str) -> dict[str, Any] | None:
    memory = context.approved_memory(canonical_range_id)
    if not isinstance(memory, Mapping):
        return None
    entry = memory.get(key)
    if not isinstance(entry, Mapping):
        return None
    payload = entry.get("payload")
    return dict(payload) if isinstance(payload, Mapping) else None


def _base_payload() -> dict[str, Any]:
    return {
        "depth_status": "PENDING",
        "source_bos_direction": None,
        "reclaim_time": None,
        "measurement_end_time": None,
        "reclaim_boundary": None,
        "deepest_wick_price": None,
        "deepest_wick_time": None,
        "reclaim_depth_price": None,
        "reclaim_depth_percent": None,
        "old_opposite_external_touched": False,
        "old_opposite_external_exceeded": False,
        "weeks_observed": 0,
        "reason_codes": [],
    }


def run(context: Any) -> dict[str, list[dict[str, Any]]]:
    outputs: list[dict[str, Any]] = []
    latest_text = context.latest_candle_time("W1")
    latest_time = _time(latest_text)

    for raw_node in context.selected_ranges(layer="WEEKLY"):
        node = dict(raw_node)
        payload = _base_payload()
        canonical_id = str(node.get("id") or "")
        bos = _memory_payload(context, canonical_id, "weekly_structure")
        reclaim = _memory_payload(context, canonical_id, "weekly_reclaim")

        if bos is None or reclaim is None:
            payload["reason_codes"] = ["APPROVED_WEEKLY_MEMORY_MISSING"]
            outputs.append(_output(node, "PENDING", payload))
            continue

        reclaim_status = str(reclaim.get("reclaim_status") or "").upper()
        if reclaim_status == "ABANDONED":
            payload.update({
                "depth_status": "NOT_APPLICABLE_ABANDONED",
                "source_bos_direction": str(bos.get("bos_direction") or "").upper() or None,
                "reason_codes": ["RANGE_ABANDONED_BEFORE_RECLAIM"],
            })
            outputs.append(_output(node, "COMPLETE", payload))
            continue
        if reclaim_status != "RECLAIMED":
            payload["reason_codes"] = ["RECLAIM_NOT_YET_APPROVED"]
            outputs.append(_output(node, "PENDING", payload))
            continue

        direction = str(bos.get("bos_direction") or "").upper()
        reclaim_time = _time(reclaim.get("reclaim_time"))
        next_bos_time = _time(reclaim.get("next_bos_time"))
        high = _number(node.get("range_high"))
        low = _number(node.get("range_low"))
        boundary = _number(reclaim.get("reclaim_boundary"))

        if direction not in {"BOS_UP", "BOS_DOWN"} or reclaim_time is None:
            payload["reason_codes"] = ["APPROVED_RECLAIM_MEMORY_INCOMPLETE"]
            outputs.append(_output(node, "NEEDS_REVIEW", payload))
            continue
        if high is None or low is None or high <= low:
            payload["reason_codes"] = ["INVALID_RANGE_PRICES"]
            outputs.append(_output(node, "NEEDS_REVIEW", payload))
            continue

        expected_boundary = high if direction == "BOS_UP" else low
        if boundary is None:
            boundary = expected_boundary
        if boundary != expected_boundary:
            payload["reason_codes"] = ["RECLAIM_BOUNDARY_CONFLICTS_WITH_WEEKLY_RANGE"]
            outputs.append(_output(node, "NEEDS_REVIEW", payload))
            continue
        if latest_time is None or latest_time < reclaim_time:
            payload["reason_codes"] = ["NO_W1_CANDLES_FROM_RECLAIM"]
            outputs.append(_output(node, "PENDING", payload))
            continue

        end_time = min(latest_time, next_bos_time) if next_bos_time is not None else latest_time
        candles = sorted(
            (
                candle for candle in context.load_candles(
                    timeframe="W1",
                    start_time=_stamp(reclaim_time),
                    end_time=_stamp(end_time),
                )
                if (candle_time := _time(candle.get("time"))) is not None
                and reclaim_time <= candle_time <= end_time
            ),
            key=lambda candle: _time(candle.get("time")) or end_time,
        )
        if not candles:
            payload["reason_codes"] = ["RECLAIM_CANDLE_NOT_AVAILABLE"]
            outputs.append(_output(node, "NEEDS_REVIEW", payload))
            continue

        if direction == "BOS_UP":
            deepest = min(candles, key=lambda candle: float(candle["low"]))
            deepest_price = float(deepest["low"])
            depth_price = max(0.0, boundary - deepest_price)
            touched = deepest_price <= low
            exceeded = deepest_price < low
        else:
            deepest = max(candles, key=lambda candle: float(candle["high"]))
            deepest_price = float(deepest["high"])
            depth_price = max(0.0, deepest_price - boundary)
            touched = deepest_price >= high
            exceeded = deepest_price > high

        range_size = high - low
        payload.update({
            "depth_status": "MEASURED",
            "source_bos_direction": direction,
            "reclaim_time": _stamp(reclaim_time),
            "measurement_end_time": _stamp(end_time),
            "reclaim_boundary": boundary,
            "deepest_wick_price": deepest_price,
            "deepest_wick_time": str(deepest["time"]),
            "reclaim_depth_price": depth_price,
            "reclaim_depth_percent": round((depth_price / range_size) * 100.0, 8),
            "old_opposite_external_touched": touched,
            "old_opposite_external_exceeded": exceeded,
            "weeks_observed": len(candles),
        })
        outputs.append(_output(node, "COMPLETE", payload))

    return {"outputs": outputs}
