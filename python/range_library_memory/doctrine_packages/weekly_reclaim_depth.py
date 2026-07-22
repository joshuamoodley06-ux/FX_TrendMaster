"""Weekly Range 2 reclaim-depth doctrine package.

This package consumes approved Weekly BOS and reclaim memory. It does not scan
later candles for an arbitrary deepest wick. Instead it identifies the next
mapped Weekly range and measures that Range 2 opposite anchor as a Fibonacci
retracement of Range 1:

BOS Up:   W1 RH = 0, W1 RL = 1, measure W2 RL.
BOS Down: W1 RL = 0, W1 RH = 1, measure W2 RH.

The ratio is not clamped, so values below 0 or above 1 remain truthful.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Mapping

FXTM_DOCTRINE_CONTRACT = "fxtm_doctrine_package_v1"
SCRIPT_KEY = "weekly_reclaim_depth"
VERSION_LABEL = "3"
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
        "range2_chronology": None,
        "range2_opposite_anchor_type": None,
        "range2_opposite_anchor_price": None,
        "range2_opposite_anchor_time": None,
        "range2_continuation_anchor_type": None,
        "range2_continuation_anchor_price": None,
        "range2_continuation_anchor_time": None,
        "reclaim_depth_price": None,
        "reclaim_depth_ratio": None,
        "reclaim_depth_percent": None,
        "weeks_bos_to_range2_definition": None,
        "range2_formation_weeks": None,
        "old_opposite_external_touched": False,
        "old_opposite_external_exceeded": False,
        "reason_codes": [],
    }


def _chronology(payload: Mapping[str, Any], high_time: datetime, low_time: datetime) -> str:
    explicit = str(payload.get("chronology") or "").upper()
    if explicit in {"RL_TO_RH", "RH_TO_RL", "SAME_W1"}:
        return explicit
    if high_time == low_time:
        return "SAME_W1"
    return "RL_TO_RH" if low_time < high_time else "RH_TO_RL"


def run(context: Any) -> dict[str, list[dict[str, Any]]]:
    nodes = [dict(node) for node in context.selected_ranges(layer="WEEKLY")]
    records: list[dict[str, Any]] = []
    for node in nodes:
        canonical_id = str(node.get("id") or "")
        bos, bos_status = _memory_entry(context, canonical_id, "weekly_structure")
        reclaim, reclaim_status = _memory_entry(context, canonical_id, "weekly_reclaim")
        high_time = _time(node.get("range_high_time"))
        low_time = _time(node.get("range_low_time"))
        defined_at = _time((bos or {}).get("range_defined_at"))
        if defined_at is None and high_time is not None and low_time is not None:
            defined_at = max(high_time, low_time)
        records.append({
            "node": node,
            "id": canonical_id,
            "bos": bos,
            "bos_status": bos_status,
            "reclaim": reclaim,
            "reclaim_processing_status": reclaim_status,
            "bos_time": _time((bos or {}).get("bos_time")),
            "bos_direction": str((bos or {}).get("bos_direction") or "").upper(),
            "defined_at": defined_at,
            "high_time": high_time,
            "low_time": low_time,
            "chronology": (
                _chronology(bos or {}, high_time, low_time)
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
        high = _number(node.get("range_high"))
        low = _number(node.get("range_low"))

        if bos is None:
            payload["reason_codes"] = ["APPROVED_WEEKLY_BOS_MEMORY_MISSING"]
            outputs.append(_output(node, "PENDING", payload))
            continue
        if current["bos_status"] not in {"", "COMPLETE"}:
            payload["reason_codes"] = ["WEEKLY_BOS_NOT_COMPLETE"]
            outputs.append(_output(node, "PENDING", payload))
            continue
        if direction not in {"BOS_UP", "BOS_DOWN"} or bos_time is None:
            payload["reason_codes"] = ["APPROVED_WEEKLY_BOS_MEMORY_INCOMPLETE"]
            outputs.append(_output(node, "NEEDS_REVIEW", payload))
            continue
        if high is None or low is None or high <= low:
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
        if reclaim is not None:
            payload.update({
                "source_reclaim_status": reclaim.get("reclaim_status"),
                "source_reclaim_abbreviation": reclaim.get("reclaim_abbreviation"),
                "source_reclaim_time": reclaim.get("reclaim_time"),
                "source_weeks_to_reclaim": reclaim.get("weeks_to_reclaim"),
            })

        wanted = {"RL_TO_RH", "SAME_W1"} if direction == "BOS_UP" else {"RH_TO_RL", "SAME_W1"}
        candidates = sorted(
            (
                record for record in records
                if record["id"] != current["id"]
                and record["defined_at"] is not None
                and record["defined_at"] > bos_time
                and record["high_time"] is not None
                and record["low_time"] is not None
                and record["chronology"] in wanted
            ),
            key=lambda record: (record["defined_at"], record["id"]),
        )
        range2 = candidates[0] if candidates else None
        if range2 is None:
            payload["reason_codes"] = ["RANGE2_NOT_YET_MAPPED"]
            outputs.append(_output(node, "PENDING", payload))
            continue

        range2_node = range2["node"]
        range2_high = _number(range2_node.get("range_high"))
        range2_low = _number(range2_node.get("range_low"))
        if range2_high is None or range2_low is None or range2_high <= range2_low:
            payload["reason_codes"] = ["INVALID_RANGE2_PRICES"]
            outputs.append(_output(node, "NEEDS_REVIEW", payload))
            continue

        if direction == "BOS_UP":
            zero = high
            one = low
            opposite_type = "RL"
            opposite_price = range2_low
            opposite_time = range2["low_time"]
            continuation_type = "RH"
            continuation_price = range2_high
            continuation_time = range2["high_time"]
            depth_price = zero - opposite_price
            touched = opposite_price <= low
            exceeded = opposite_price < low
        else:
            zero = low
            one = high
            opposite_type = "RH"
            opposite_price = range2_high
            opposite_time = range2["high_time"]
            continuation_type = "RL"
            continuation_price = range2_low
            continuation_time = range2["low_time"]
            depth_price = opposite_price - zero
            touched = opposite_price >= high
            exceeded = opposite_price > high

        if opposite_time is None or continuation_time is None or range2["defined_at"] is None:
            payload["reason_codes"] = ["RANGE2_ANCHOR_TIME_MISSING"]
            outputs.append(_output(node, "NEEDS_REVIEW", payload))
            continue

        ratio = depth_price / (high - low)
        payload.update({
            "depth_status": "MEASURED",
            "fib_zero_price": zero,
            "fib_one_price": one,
            "range2_id": range2["id"],
            "range2_defined_at": _stamp(range2["defined_at"]),
            "range2_chronology": range2["chronology"],
            "range2_opposite_anchor_type": opposite_type,
            "range2_opposite_anchor_price": opposite_price,
            "range2_opposite_anchor_time": _stamp(opposite_time),
            "range2_continuation_anchor_type": continuation_type,
            "range2_continuation_anchor_price": continuation_price,
            "range2_continuation_anchor_time": _stamp(continuation_time),
            "reclaim_depth_price": depth_price,
            "reclaim_depth_ratio": round(ratio, 8),
            "reclaim_depth_percent": round(ratio * 100.0, 8),
            "weeks_bos_to_range2_definition": _week_distance(bos_time, range2["defined_at"]),
            "range2_formation_weeks": _week_distance(opposite_time, range2["defined_at"]),
            "old_opposite_external_touched": touched,
            "old_opposite_external_exceeded": exceeded,
        })
        outputs.append(_output(node, "COMPLETE", payload))

    return {"outputs": outputs}
