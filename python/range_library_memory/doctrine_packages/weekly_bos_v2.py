"""Weekly BOS package v2.

Each Weekly range is analysed forward from the time both anchors are known.
The first future W1 wick beyond RH or RL establishes BOS. Mapping gaps do not
stop the scan. A candle breaching both boundaries is held for review.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

FXTM_DOCTRINE_CONTRACT = "fxtm_doctrine_package_v1"
SCRIPT_KEY = "weekly_structure"
VERSION_LABEL = "2"
ADAPTER_KEY = "doctrine_package_v1"
EXECUTION_ORDER = 10


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


def _output(node: dict[str, Any], status: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "canonical_range_id": str(node.get("id") or ""),
        "processing_status": status,
        "payload": payload,
    }


def run(context: Any) -> dict[str, list[dict[str, Any]]]:
    outputs: list[dict[str, Any]] = []
    latest = context.latest_candle_time("W1")
    latest_time = _time(latest)

    for node in context.selected_ranges(layer="WEEKLY"):
        high = _number(node.get("range_high"))
        low = _number(node.get("range_low"))
        high_time = _time(node.get("range_high_time"))
        low_time = _time(node.get("range_low_time"))
        payload: dict[str, Any] = {
            "chronology": "PENDING",
            "range_defined_at": None,
            "expected_bos_direction": None,
            "bos_direction": None,
            "bos_time": None,
            "bos_price": None,
            "candles_scanned": 0,
            "reason_codes": [],
        }

        if high is None or low is None or high <= low:
            payload["reason_codes"] = ["INVALID_RANGE_PRICES"]
            outputs.append(_output(node, "NEEDS_REVIEW", payload))
            continue
        if high_time is None or low_time is None:
            payload["reason_codes"] = ["MISSING_OR_INVALID_ANCHOR_TIME"]
            outputs.append(_output(node, "NEEDS_REVIEW", payload))
            continue
        if high_time == low_time:
            payload["reason_codes"] = ["EQUAL_ANCHOR_TIMES"]
            outputs.append(_output(node, "NEEDS_REVIEW", payload))
            continue

        if low_time < high_time:
            chronology = "RL_TO_RH"
            defined_at = high_time
            expected = "BOS_UP"
        else:
            chronology = "RH_TO_RL"
            defined_at = low_time
            expected = "BOS_DOWN"

        payload.update({
            "chronology": chronology,
            "range_defined_at": defined_at.isoformat().replace("+00:00", "Z"),
            "expected_bos_direction": expected,
        })

        if latest_time is None or latest_time <= defined_at:
            payload["reason_codes"] = ["NO_W1_CANDLES_AFTER_RANGE_DEFINED"]
            outputs.append(_output(node, "PENDING", payload))
            continue

        candles = [
            candle for candle in context.load_candles(
                timeframe="W1",
                start_time=payload["range_defined_at"],
                end_time=str(latest),
            )
            if (_time(candle.get("time")) or defined_at) > defined_at
        ]
        payload["candles_scanned"] = len(candles)

        completed = False
        for candle in candles:
            broke_up = float(candle["high"]) > high
            broke_down = float(candle["low"]) < low
            if not broke_up and not broke_down:
                continue
            if broke_up and broke_down:
                payload.update({
                    "bos_time": candle["time"],
                    "reason_codes": ["BOTH_BOUNDARIES_BREACHED_SAME_W1"],
                })
                outputs.append(_output(node, "NEEDS_REVIEW", payload))
                completed = True
                break

            direction = "BOS_UP" if broke_up else "BOS_DOWN"
            payload.update({
                "bos_direction": direction,
                "bos_time": candle["time"],
                "bos_price": float(candle["high"] if broke_up else candle["low"]),
            })
            outputs.append(_output(node, "COMPLETE", payload))
            completed = True
            break

        if not completed:
            payload["reason_codes"] = ["WEEKLY_BOS_NOT_FOUND"]
            outputs.append(_output(node, "PENDING", payload))

    return {"outputs": outputs}
