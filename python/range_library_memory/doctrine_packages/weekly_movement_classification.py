"""Classify the two structural movements that create the next Weekly range.

This package consumes approved Weekly Reclaim Depth memory. It does not detect
new anchors, rebuild ranges, or recalculate Fib depth.

For BOS Up:

    Countertrend: old W1 RH -> W2 RL (DOWN)
    Protrend:     W2 RL -> W2 RH (UP)

For BOS Down:

    Countertrend: old W1 RL -> W2 RH (UP)
    Protrend:     W2 RH -> W2 RL (DOWN)

Reclaim is the countertrend timeline boundary. The mapped Range 2 anchor order
states whether countertrend or protrend occurred first in time.
"""
from __future__ import annotations

from typing import Any, Mapping

FXTM_DOCTRINE_CONTRACT = "fxtm_doctrine_package_v1"
SCRIPT_KEY = "weekly_movement_classification"
VERSION_LABEL = "1"
ADAPTER_KEY = "doctrine_package_v1"
EXECUTION_ORDER = 40


_COMPLETE_DEPTH_STATES = {
    "NO_RETRACEMENT",
    "BOUNDARY_TOUCH",
    "RETRACED_INTO_RANGE",
    "TOUCHED_OLD_OPPOSITE",
    "EXCEEDED_OLD_OPPOSITE",
}


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


def _integer(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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
        "movement_status": "PENDING",
        "movement_sequence": None,
        "source_range1_id": None,
        "range2_id": None,
        "source_bos_direction": None,
        "countertrend_classification": None,
        "countertrend_direction": None,
        "countertrend_distance": None,
        "countertrend_depth_percent": None,
        "countertrend_weeks": None,
        "protrend_classification": None,
        "protrend_direction": None,
        "protrend_distance": None,
        "protrend_weeks": None,
        "range2_anchor_sequence": None,
        "reason_codes": [],
    }


def _movement_sequence(anchor_sequence: str) -> str:
    if anchor_sequence == "OPPOSITE_THEN_CONTINUATION":
        return "COUNTERTREND_THEN_PROTREND"
    if anchor_sequence == "CONTINUATION_THEN_OPPOSITE":
        return "PROTREND_THEN_COUNTERTREND"
    if anchor_sequence == "SAME_W1":
        return "SAME_W1_MOVEMENTS"
    return "UNKNOWN"


def _countertrend_classification(depth_status: str) -> str:
    if depth_status == "NO_RETRACEMENT":
        return "NO_RANGE1_RETRACEMENT"
    if depth_status == "BOUNDARY_TOUCH":
        return "BOUNDARY_TOUCH"
    return "COUNTERTREND_RETRACEMENT"


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
            payload["movement_status"] = "NEEDS_REVIEW"
            payload["reason_codes"] = ["WEEKLY_RECLAIM_DEPTH_NEEDS_REVIEW"]
            outputs.append(_output(node, "NEEDS_REVIEW", payload))
            continue
        if depth_processing not in {"", "COMPLETE"}:
            payload["reason_codes"] = ["WEEKLY_RECLAIM_DEPTH_NOT_COMPLETE"]
            outputs.append(_output(node, "PENDING", payload))
            continue

        depth_status = str(depth.get("depth_status") or "").upper()
        direction = str(depth.get("source_bos_direction") or "").upper()
        anchor_sequence = str(depth.get("range2_anchor_sequence") or "").upper()
        range2_id = str(depth.get("range2_id") or "").strip()
        opposite_price = _number(depth.get("range2_opposite_anchor_price"))
        continuation_price = _number(depth.get("range2_continuation_anchor_price"))
        countertrend_distance = _number(depth.get("reclaim_depth_price"))
        countertrend_percent = _number(depth.get("reclaim_depth_percent"))
        countertrend_weeks = _integer(depth.get("weeks_reclaim_to_depth_anchor"))
        protrend_weeks = _integer(depth.get("range2_formation_weeks"))

        payload.update({
            "range2_id": range2_id or None,
            "source_bos_direction": direction or None,
            "range2_anchor_sequence": anchor_sequence or None,
        })

        if depth_status not in _COMPLETE_DEPTH_STATES:
            payload["reason_codes"] = ["WEEKLY_RECLAIM_DEPTH_STILL_PENDING"]
            outputs.append(_output(node, "PENDING", payload))
            continue
        if direction not in {"BOS_UP", "BOS_DOWN"}:
            payload["movement_status"] = "NEEDS_REVIEW"
            payload["reason_codes"] = ["SOURCE_BOS_DIRECTION_INVALID"]
            outputs.append(_output(node, "NEEDS_REVIEW", payload))
            continue
        if anchor_sequence not in {
            "OPPOSITE_THEN_CONTINUATION",
            "CONTINUATION_THEN_OPPOSITE",
            "SAME_W1",
        }:
            payload["movement_status"] = "NEEDS_REVIEW"
            payload["reason_codes"] = ["RANGE2_ANCHOR_SEQUENCE_INVALID"]
            outputs.append(_output(node, "NEEDS_REVIEW", payload))
            continue
        if (
            not range2_id
            or opposite_price is None
            or continuation_price is None
            or countertrend_distance is None
            or countertrend_percent is None
            or countertrend_weeks is None
            or protrend_weeks is None
        ):
            payload["movement_status"] = "NEEDS_REVIEW"
            payload["reason_codes"] = ["WEEKLY_MOVEMENT_INPUTS_INCOMPLETE"]
            outputs.append(_output(node, "NEEDS_REVIEW", payload))
            continue

        protrend_distance = abs(continuation_price - opposite_price)
        if direction == "BOS_UP":
            countertrend_direction = "DOWN"
            protrend_direction = "UP"
        else:
            countertrend_direction = "UP"
            protrend_direction = "DOWN"

        payload.update({
            "movement_status": "CLASSIFIED",
            "movement_sequence": _movement_sequence(anchor_sequence),
            "countertrend_classification": _countertrend_classification(depth_status),
            "countertrend_direction": countertrend_direction,
            "countertrend_distance": round(max(0.0, countertrend_distance), 8),
            "countertrend_depth_percent": round(max(0.0, countertrend_percent), 8),
            "countertrend_weeks": max(0, countertrend_weeks),
            "protrend_classification": "PROTREND_CONTINUATION",
            "protrend_direction": protrend_direction,
            "protrend_distance": round(protrend_distance, 8),
            "protrend_weeks": max(0, protrend_weeks),
            "reason_codes": (
                ["BOTH_MOVEMENTS_WITHIN_SAME_W1_SEQUENCE_UNORDERED"]
                if anchor_sequence == "SAME_W1"
                else []
            ),
        })
        outputs.append(_output(node, "COMPLETE", payload))

    return {"outputs": outputs}
