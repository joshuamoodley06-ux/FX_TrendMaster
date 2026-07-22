"""Classify the approved Weekly range profile.

Profile rules:

* depth < 38.2%      -> S&R
* 38.2% <= depth <= 50% -> S&R>FP
* depth > 50%        -> S&D

A previous range that is ABANDONED and followed by a new BOS in the same
direction is classified S&R even when reclaim depth is not available. This is
the explicit continuation override supplied by the trader.
"""
from __future__ import annotations

from typing import Any, Mapping

FXTM_DOCTRINE_CONTRACT = "fxtm_doctrine_package_v1"
SCRIPT_KEY = "weekly_profile_classification"
VERSION_LABEL = "1"
ADAPTER_KEY = "doctrine_package_v1"
EXECUTION_ORDER = 50


_COMPLETE_DEPTH_STATES = {
    "NO_RETRACEMENT",
    "BOUNDARY_TOUCH",
    "RETRACED_INTO_RANGE",
    "TOUCHED_OLD_OPPOSITE",
    "EXCEEDED_OLD_OPPOSITE",
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


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def _output(node: Mapping[str, Any], status: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "canonical_range_id": str(node.get("id") or ""),
        "processing_status": status,
        "payload": payload,
    }


def _base_payload() -> dict[str, Any]:
    return {
        "profile_classification": None,
        "profile_badge": None,
        "classification_basis": None,
        "reclaim_depth_percent": None,
        "reclaim_status": None,
        "source_bos_direction": None,
        "next_bos_direction": None,
        "reason_codes": [],
    }


def _classify_depth(depth_percent: float) -> tuple[str, str]:
    # Four decimals matches the trader-facing audit and prevents microscopic
    # float noise from moving a case across an exact doctrine boundary.
    depth = round(depth_percent, 4)
    if depth < 38.2:
        return "S&R", "DEPTH_BELOW_38_2"
    if depth <= 50.0:
        return "S&R>FP", "DEPTH_38_2_TO_50"
    return "S&D", "DEPTH_ABOVE_50"


def run(context: Any) -> dict[str, list[dict[str, Any]]]:
    outputs: list[dict[str, Any]] = []

    for raw_node in context.selected_ranges(layer="WEEKLY"):
        node = dict(raw_node)
        canonical_id = str(node.get("id") or "")
        payload = _base_payload()

        reclaim, reclaim_processing = _memory_entry(
            context,
            canonical_id,
            "weekly_reclaim",
        )
        if reclaim is None:
            payload["reason_codes"] = ["APPROVED_WEEKLY_RECLAIM_MEMORY_MISSING"]
            outputs.append(_output(node, "PENDING", payload))
            continue

        reclaim_status = str(reclaim.get("reclaim_status") or "PENDING").upper()
        source_direction = str(reclaim.get("source_bos_direction") or "").upper()
        next_direction = str(reclaim.get("next_bos_direction") or "").upper()
        payload.update({
            "reclaim_status": reclaim_status,
            "source_bos_direction": source_direction or None,
            "next_bos_direction": next_direction or None,
        })

        if reclaim_processing == "NEEDS_REVIEW" or reclaim_status == "NEEDS_REVIEW":
            payload["reason_codes"] = ["WEEKLY_RECLAIM_NEEDS_REVIEW"]
            outputs.append(_output(node, "NEEDS_REVIEW", payload))
            continue

        same_direction_abandonment = (
            reclaim_status == "ABANDONED"
            and source_direction in {"BOS_UP", "BOS_DOWN"}
            and next_direction == source_direction
        )

        depth, depth_processing = _memory_entry(
            context,
            canonical_id,
            "weekly_reclaim_depth",
        )
        if depth is not None:
            depth_value = _number(depth.get("reclaim_depth_percent"))
            if depth_value is not None:
                payload["reclaim_depth_percent"] = round(depth_value, 4)

        if same_direction_abandonment:
            payload.update({
                "profile_classification": "S&R",
                "profile_badge": "S&R",
                "classification_basis": "ABND_SAME_DIRECTION_BOS",
                "reason_codes": ["ABANDONED_RANGE_FOLLOWED_BY_SAME_DIRECTION_BOS"],
            })
            outputs.append(_output(node, "COMPLETE", payload))
            continue

        if reclaim_status == "ABANDONED":
            payload["reason_codes"] = [
                "ABANDONED_RANGE_WITHOUT_SAME_DIRECTION_BOS_OVERRIDE"
            ]
            outputs.append(_output(node, "PENDING", payload))
            continue

        if depth is None:
            payload["reason_codes"] = ["APPROVED_WEEKLY_RECLAIM_DEPTH_MEMORY_MISSING"]
            outputs.append(_output(node, "PENDING", payload))
            continue

        depth_status = str(depth.get("depth_status") or "PENDING").upper()
        if depth_processing == "NEEDS_REVIEW" or depth_status == "NEEDS_REVIEW":
            payload["reason_codes"] = ["WEEKLY_RECLAIM_DEPTH_NEEDS_REVIEW"]
            outputs.append(_output(node, "NEEDS_REVIEW", payload))
            continue
        if depth_processing not in {"", "COMPLETE"} or depth_status not in _COMPLETE_DEPTH_STATES:
            payload["reason_codes"] = ["WEEKLY_RECLAIM_DEPTH_STILL_PENDING"]
            outputs.append(_output(node, "PENDING", payload))
            continue

        depth_percent = _number(depth.get("reclaim_depth_percent"))
        if depth_percent is None:
            payload["reason_codes"] = ["WEEKLY_RECLAIM_DEPTH_PERCENT_MISSING"]
            outputs.append(_output(node, "NEEDS_REVIEW", payload))
            continue

        profile, reason = _classify_depth(depth_percent)
        payload.update({
            "profile_classification": profile,
            "profile_badge": profile,
            "classification_basis": "RECLAIM_DEPTH",
            "reclaim_depth_percent": round(depth_percent, 4),
            "reason_codes": [reason],
        })
        outputs.append(_output(node, "COMPLETE", payload))

    return {"outputs": outputs}
