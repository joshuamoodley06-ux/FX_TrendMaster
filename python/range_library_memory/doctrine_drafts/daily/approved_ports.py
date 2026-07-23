"""Draft Daily ports of the six approved Weekly doctrine packages.

These functions are intentionally unregistered. They preserve the approved rule
shape while using D1 candles and requiring a trusted Weekly parent for every Daily
range included in analytics.
"""
from __future__ import annotations

from typing import Any, Mapping

from .shared import (
    EPSILON,
    anchor_chronology,
    candle_body_direction,
    candle_rows,
    latest_time,
    memory_entry,
    next_completed_structure,
    node_id,
    number,
    output,
    range_anchor_times,
    range_defined_at,
    same_parent_candidates,
    selected_nodes,
    stamp,
    time_value,
    weekly_parent_map,
    zone_levels,
)


def _parent_guard(
    node: Mapping[str, Any],
    parents: Mapping[str, str],
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    canonical_id = node_id(node)
    parent_id = parents.get(canonical_id)
    payload["weekly_parent_id"] = parent_id
    if parent_id:
        return None
    payload["reason_codes"] = ["TRUSTED_WEEKLY_PARENT_UNAVAILABLE"]
    return output(node, "NEEDS_REVIEW", payload)


def run_daily_bos(context: Any) -> dict[str, list[dict[str, Any]]]:
    outputs: list[dict[str, Any]] = []
    latest = latest_time(context, "D1")
    parents = weekly_parent_map(context)

    for node in selected_nodes(context, "DAILY"):
        high = number(node.get("range_high"))
        low = number(node.get("range_low"))
        high_time, low_time = range_anchor_times(node)
        chronology, expected_direction = anchor_chronology(node, "D1")
        defined_at = range_defined_at(node)
        payload: dict[str, Any] = {
            "weekly_parent_id": None,
            "chronology": chronology,
            "range_defined_at": stamp(defined_at),
            "expected_bos_direction": (
                f"BOS_{expected_direction}" if expected_direction in {"UP", "DOWN"} else None
            ),
            "bos_direction": None,
            "bos_time": None,
            "bos_price": None,
            "candles_scanned": 0,
            "days_to_bos": None,
            "reason_codes": [],
        }
        guarded = _parent_guard(node, parents, payload)
        if guarded:
            outputs.append(guarded)
            continue
        if high is None or low is None or high <= low:
            payload["reason_codes"] = ["INVALID_RANGE_PRICES"]
            outputs.append(output(node, "NEEDS_REVIEW", payload))
            continue
        if high_time is None or low_time is None or defined_at is None:
            payload["reason_codes"] = ["MISSING_OR_INVALID_ANCHOR_TIME"]
            outputs.append(output(node, "NEEDS_REVIEW", payload))
            continue
        if latest is None or latest <= defined_at:
            payload["reason_codes"] = ["NO_D1_CANDLES_AFTER_RANGE_DEFINED"]
            outputs.append(output(node, "PENDING", payload))
            continue

        completed = False
        for candle in candle_rows(context, "D1", defined_at, latest, exclude_start=True):
            candle_high = number(candle.get("high"))
            candle_low = number(candle.get("low"))
            if candle_high is None or candle_low is None:
                payload["reason_codes"] = ["INVALID_D1_OHLC"]
                outputs.append(output(node, "NEEDS_REVIEW", payload))
                completed = True
                break
            payload["candles_scanned"] += 1
            broke_up = candle_high > high + EPSILON
            broke_down = candle_low < low - EPSILON
            if not broke_up and not broke_down:
                continue
            if broke_up and broke_down:
                payload.update({
                    "bos_time": candle.get("time"),
                    "reason_codes": ["BOTH_BOUNDARIES_BREACHED_SAME_D1"],
                })
                outputs.append(output(node, "NEEDS_REVIEW", payload))
                completed = True
                break
            payload.update({
                "bos_direction": "BOS_UP" if broke_up else "BOS_DOWN",
                "bos_time": candle.get("time"),
                "bos_price": candle_high if broke_up else candle_low,
                "days_to_bos": payload["candles_scanned"],
                "reason_codes": ["FIRST_LATER_D1_WICK_BREAK"],
            })
            outputs.append(output(node, "COMPLETE", payload))
            completed = True
            break
        if not completed:
            payload["reason_codes"] = ["DAILY_BOS_NOT_FOUND"]
            outputs.append(output(node, "PENDING", payload))
    return {"outputs": outputs}


def _reclaim_base() -> dict[str, Any]:
    return {
        "weekly_parent_id": None,
        "reclaim_status": "PENDING",
        "reclaim_abbreviation": "PEND",
        "source_bos_direction": None,
        "source_bos_time": None,
        "source_bos_processing_status": None,
        "bos_candle_close": None,
        "same_candle_reclaim": False,
        "reclaim_boundary": None,
        "reclaim_time": None,
        "reclaim_wick_price": None,
        "next_bos_range_id": None,
        "next_bos_direction": None,
        "next_bos_time": None,
        "abandoned_before_reclaim": False,
        "candles_scanned": 0,
        "days_to_reclaim": None,
        "days_to_abandonment": None,
        "days_from_abandonment_to_reclaim": None,
        "reason_codes": [],
    }


def _touches_boundary(candle: Mapping[str, Any], direction: str, boundary: float) -> bool:
    low = number(candle.get("low"))
    high = number(candle.get("high"))
    if low is None or high is None:
        return False
    return low <= boundary + EPSILON if direction == "BOS_UP" else high >= boundary - EPSILON


def _same_candle_reclaim(candle: Mapping[str, Any], direction: str, boundary: float) -> bool:
    high = number(candle.get("high"))
    low = number(candle.get("low"))
    close = number(candle.get("close"))
    if high is None or low is None or close is None:
        return False
    if direction == "BOS_UP":
        return high > boundary + EPSILON and close <= boundary + EPSILON
    return low < boundary - EPSILON and close >= boundary - EPSILON


def run_daily_reclaim(context: Any) -> dict[str, list[dict[str, Any]]]:
    nodes = selected_nodes(context, "DAILY")
    parents = weekly_parent_map(context)
    latest = latest_time(context, "D1")
    records: list[dict[str, Any]] = []
    for node in nodes:
        canonical_id = node_id(node)
        structure, structure_status = memory_entry(context, canonical_id, "daily_structure")
        records.append({
            "node": node,
            "id": canonical_id,
            "parent": parents.get(canonical_id),
            "structure": structure,
            "status": structure_status,
            "defined_at": time_value((structure or {}).get("range_defined_at")),
            "bos_time": time_value((structure or {}).get("bos_time")),
            "bos_direction": str((structure or {}).get("bos_direction") or "").upper(),
        })

    outputs: list[dict[str, Any]] = []
    for current in records:
        node = current["node"]
        payload = _reclaim_base()
        guarded = _parent_guard(node, parents, payload)
        if guarded:
            outputs.append(guarded)
            continue
        structure = current["structure"]
        structure_status = current["status"]
        payload["source_bos_processing_status"] = structure_status
        if structure is None:
            payload["reason_codes"] = ["APPROVED_DAILY_BOS_MEMORY_MISSING"]
            outputs.append(output(node, "PENDING", payload))
            continue
        if structure_status == "PENDING":
            payload["reason_codes"] = ["DAILY_BOS_STILL_PENDING"]
            outputs.append(output(node, "PENDING", payload))
            continue
        if structure_status == "NEEDS_REVIEW":
            payload["reason_codes"] = ["DAILY_BOS_NEEDS_REVIEW"]
            outputs.append(output(node, "NEEDS_REVIEW", payload))
            continue
        direction = current["bos_direction"]
        bos_time = current["bos_time"]
        defined_at = current["defined_at"]
        high = number(node.get("range_high"))
        low = number(node.get("range_low"))
        if structure_status not in {"", "COMPLETE"} or direction not in {"BOS_UP", "BOS_DOWN"} or bos_time is None or defined_at is None:
            payload["reason_codes"] = ["APPROVED_DAILY_BOS_MEMORY_INCOMPLETE"]
            outputs.append(output(node, "NEEDS_REVIEW", payload))
            continue
        if high is None or low is None or high <= low:
            payload["reason_codes"] = ["INVALID_RANGE_PRICES"]
            outputs.append(output(node, "NEEDS_REVIEW", payload))
            continue
        boundary = high if direction == "BOS_UP" else low
        payload.update({
            "source_bos_direction": direction,
            "source_bos_time": stamp(bos_time),
            "reclaim_boundary": boundary,
        })

        later_bos = sorted(
            (
                record for record in records
                if record["id"] != current["id"]
                and record["parent"] == current["parent"]
                and record["status"] in {"", "COMPLETE"}
                and record["bos_time"] is not None
                and record["bos_time"] > bos_time
                and record["bos_direction"] in {"BOS_UP", "BOS_DOWN"}
            ),
            key=lambda record: (record["bos_time"], record["id"]),
        )
        next_bos = later_bos[0] if later_bos else None
        next_bos_time = next_bos["bos_time"] if next_bos else None
        if next_bos:
            payload.update({
                "next_bos_range_id": next_bos["id"],
                "next_bos_direction": next_bos["bos_direction"],
                "next_bos_time": stamp(next_bos_time),
            })
        if latest is None or latest < bos_time:
            payload["reason_codes"] = ["NO_D1_CANDLES_FROM_BOS"]
            outputs.append(output(node, "PENDING", payload))
            continue
        candles = candle_rows(context, "D1", bos_time, latest)
        bos_candle = next((row for row in candles if time_value(row.get("time")) == bos_time), None)
        if bos_candle is None:
            payload["reason_codes"] = ["BOS_CANDLE_NOT_AVAILABLE_FOR_RECLAIM_CHECK"]
            outputs.append(output(node, "NEEDS_REVIEW", payload))
            continue
        payload["bos_candle_close"] = number(bos_candle.get("close"))
        if _same_candle_reclaim(bos_candle, direction, boundary):
            payload.update({
                "reclaim_status": "RECLAIMED",
                "reclaim_abbreviation": "RECL",
                "same_candle_reclaim": True,
                "reclaim_time": bos_candle.get("time"),
                "reclaim_wick_price": number(bos_candle.get("low" if direction == "BOS_UP" else "high")),
                "days_to_reclaim": 0,
                "reason_codes": ["BOS_CANDLE_CLOSED_BACK_THROUGH_BOUNDARY"],
            })
            outputs.append(output(node, "COMPLETE", payload))
            continue

        later = [row for row in candles if (time_value(row.get("time")) or bos_time) > bos_time]
        reclaim: dict[str, Any] | None = None
        reclaim_index: int | None = None
        for index, candle in enumerate(later, start=1):
            payload["candles_scanned"] = index
            if _touches_boundary(candle, direction, boundary):
                reclaim = candle
                reclaim_index = index
                break
        if reclaim is not None and reclaim_index is not None:
            reclaim_time = time_value(reclaim.get("time"))
            if reclaim_time is None:
                payload["reason_codes"] = ["RECLAIM_CANDLE_TIME_INVALID"]
                outputs.append(output(node, "NEEDS_REVIEW", payload))
                continue
            if next_bos_time is not None and reclaim_time == next_bos_time:
                payload.update({
                    "reclaim_status": "NEEDS_REVIEW",
                    "reclaim_abbreviation": "REVIEW",
                    "reclaim_time": reclaim.get("time"),
                    "reclaim_wick_price": number(reclaim.get("low" if direction == "BOS_UP" else "high")),
                    "days_to_reclaim": reclaim_index,
                    "reason_codes": ["RECLAIM_AND_NEW_BOS_SAME_D1_ORDER_UNKNOWN"],
                })
                outputs.append(output(node, "NEEDS_REVIEW", payload))
                continue
            abandoned_first = next_bos_time is not None and next_bos_time < reclaim_time
            days_to_abandonment = None
            days_after_abandonment = None
            if abandoned_first and next_bos_time is not None:
                days_to_abandonment = sum(
                    1 for candle in later
                    if (time_value(candle.get("time")) or latest) <= next_bos_time
                )
                days_after_abandonment = sum(
                    1 for candle in later
                    if next_bos_time < (time_value(candle.get("time")) or bos_time) <= reclaim_time
                )
            payload.update({
                "reclaim_status": "ABANDONED_THEN_RECLAIMED" if abandoned_first else "RECLAIMED",
                "reclaim_abbreviation": "ABND→RECL" if abandoned_first else "RECL",
                "abandoned_before_reclaim": abandoned_first,
                "reclaim_time": reclaim.get("time"),
                "reclaim_wick_price": number(reclaim.get("low" if direction == "BOS_UP" else "high")),
                "days_to_reclaim": reclaim_index,
                "days_to_abandonment": days_to_abandonment,
                "days_from_abandonment_to_reclaim": days_after_abandonment,
                "reason_codes": [
                    "DAILY_RANGE_ABANDONED_THEN_RECLAIMED" if abandoned_first
                    else "DAILY_RANGE_RECLAIMED"
                ],
            })
            outputs.append(output(node, "COMPLETE", payload))
            continue
        if next_bos_time is not None:
            payload.update({
                "reclaim_status": "ABANDONED",
                "reclaim_abbreviation": "ABND",
                "abandoned_before_reclaim": True,
                "days_to_abandonment": sum(
                    1 for candle in later
                    if (time_value(candle.get("time")) or latest) <= next_bos_time
                ),
                "reason_codes": ["NEW_DAILY_BOS_BEFORE_RECLAIM"],
            })
            outputs.append(output(node, "COMPLETE", payload))
            continue
        payload["reason_codes"] = ["DAILY_RECLAIM_NOT_FOUND"]
        outputs.append(output(node, "PENDING", payload))
    return {"outputs": outputs}


def _depth_base() -> dict[str, Any]:
    return {
        "weekly_parent_id": None,
        "depth_status": "PENDING",
        "source_bos_direction": None,
        "source_bos_time": None,
        "source_reclaim_status": None,
        "source_reclaim_time": None,
        "range1_id": None,
        "range1_high": None,
        "range1_low": None,
        "range1_size": None,
        "fib_zero_price": None,
        "fib_one_price": None,
        "range2_id": None,
        "range2_completed_at": None,
        "range2_anchor_sequence": None,
        "range2_opposite_anchor_type": None,
        "range2_opposite_anchor_price": None,
        "range2_opposite_anchor_time": None,
        "range2_continuation_anchor_type": None,
        "range2_continuation_anchor_price": None,
        "range2_continuation_anchor_time": None,
        "reclaim_depth_price": None,
        "reclaim_depth_ratio": None,
        "reclaim_depth_percent": None,
        "raw_reclaim_depth_ratio": None,
        "raw_reclaim_depth_percent": None,
        "boundary_position": None,
        "days_bos_to_depth_anchor": None,
        "days_reclaim_to_depth_anchor": None,
        "days_bos_to_range2_completion": None,
        "days_reclaim_to_range2_completion": None,
        "reason_codes": [],
    }


def run_daily_reclaim_depth(context: Any) -> dict[str, list[dict[str, Any]]]:
    parents = weekly_parent_map(context)
    all_daily = selected_nodes(context, "DAILY")
    outputs: list[dict[str, Any]] = []
    for node in all_daily:
        canonical_id = node_id(node)
        payload = _depth_base()
        guarded = _parent_guard(node, parents, payload)
        if guarded:
            outputs.append(guarded)
            continue
        structure, structure_status = memory_entry(context, canonical_id, "daily_structure")
        reclaim, reclaim_processing = memory_entry(context, canonical_id, "daily_reclaim")
        if structure is None or reclaim is None:
            payload["reason_codes"] = ["APPROVED_DAILY_STRUCTURE_OR_RECLAIM_MEMORY_MISSING"]
            outputs.append(output(node, "PENDING", payload))
            continue
        if structure_status == "NEEDS_REVIEW" or reclaim_processing == "NEEDS_REVIEW":
            payload["reason_codes"] = ["DAILY_STRUCTURE_OR_RECLAIM_NEEDS_REVIEW"]
            outputs.append(output(node, "NEEDS_REVIEW", payload))
            continue
        direction = str(structure.get("bos_direction") or "").upper()
        bos_time = time_value(structure.get("bos_time"))
        reclaim_status = str(reclaim.get("reclaim_status") or "").upper()
        reclaim_time = time_value(reclaim.get("reclaim_time"))
        high = number(node.get("range_high"))
        low = number(node.get("range_low"))
        payload.update({
            "source_bos_direction": direction or None,
            "source_bos_time": stamp(bos_time),
            "source_reclaim_status": reclaim_status or None,
            "source_reclaim_time": stamp(reclaim_time),
            "range1_id": canonical_id,
            "range1_high": high,
            "range1_low": low,
        })
        if structure_status not in {"", "COMPLETE"} or direction not in {"BOS_UP", "BOS_DOWN"} or bos_time is None:
            payload["reason_codes"] = ["APPROVED_DAILY_BOS_MEMORY_INCOMPLETE"]
            outputs.append(output(node, "PENDING", payload))
            continue
        if reclaim_status not in {"RECLAIMED", "ABANDONED_THEN_RECLAIMED"} or reclaim_time is None:
            payload["reason_codes"] = ["DAILY_RECLAIM_NOT_COMPLETE"]
            outputs.append(output(node, "PENDING", payload))
            continue
        if high is None or low is None or high <= low:
            payload["reason_codes"] = ["INVALID_RANGE_PRICES"]
            outputs.append(output(node, "NEEDS_REVIEW", payload))
            continue
        size = high - low
        payload.update({
            "range1_size": size,
            "fib_zero_price": high if direction == "BOS_UP" else low,
            "fib_one_price": low if direction == "BOS_UP" else high,
        })

        candidates: list[tuple[Any, str, dict[str, Any], Any, Any]] = []
        for candidate in same_parent_candidates(context, canonical_id, all_daily):
            candidate_id = node_id(candidate)
            if not candidate_id or candidate_id == canonical_id:
                continue
            candidate_high = number(candidate.get("range_high"))
            candidate_low = number(candidate.get("range_low"))
            high_time, low_time = range_anchor_times(candidate)
            completed_at = range_defined_at(candidate)
            if candidate_high is None or candidate_low is None or high_time is None or low_time is None or completed_at is None:
                continue
            opposite_time = low_time if direction == "BOS_UP" else high_time
            if opposite_time < reclaim_time or completed_at < opposite_time:
                continue
            candidates.append((completed_at, candidate_id, candidate, high_time, low_time))
        candidates.sort(key=lambda item: (item[0], item[1]))
        if not candidates:
            payload["reason_codes"] = ["NEXT_MAPPED_DAILY_RANGE_NOT_AVAILABLE"]
            outputs.append(output(node, "PENDING", payload))
            continue
        completed_at, range2_id, range2, high_time, low_time = candidates[0]
        range2_high = number(range2.get("range_high"))
        range2_low = number(range2.get("range_low"))
        if range2_high is None or range2_low is None:
            payload["reason_codes"] = ["RANGE2_PRICES_INVALID"]
            outputs.append(output(node, "NEEDS_REVIEW", payload))
            continue
        opposite_type = "RL" if direction == "BOS_UP" else "RH"
        continuation_type = "RH" if direction == "BOS_UP" else "RL"
        opposite_price = range2_low if direction == "BOS_UP" else range2_high
        continuation_price = range2_high if direction == "BOS_UP" else range2_low
        opposite_time = low_time if direction == "BOS_UP" else high_time
        continuation_time = high_time if direction == "BOS_UP" else low_time
        if opposite_time == continuation_time:
            anchor_sequence = "SAME_D1"
        elif opposite_time < continuation_time:
            anchor_sequence = "OPPOSITE_THEN_CONTINUATION"
        else:
            anchor_sequence = "CONTINUATION_THEN_OPPOSITE"
        raw_ratio = (
            (high - opposite_price) / size
            if direction == "BOS_UP"
            else (opposite_price - low) / size
        )
        trading_ratio = max(0.0, raw_ratio)
        boundary_position = (
            "NO_RETRACEMENT" if raw_ratio < 0
            else "INSIDE_RANGE" if raw_ratio <= 1 + EPSILON
            else "BEYOND_OLD_OPPOSITE_EXTERNAL"
        )
        payload.update({
            "depth_status": "COMPLETE",
            "range2_id": range2_id,
            "range2_completed_at": stamp(completed_at),
            "range2_anchor_sequence": anchor_sequence,
            "range2_opposite_anchor_type": opposite_type,
            "range2_opposite_anchor_price": opposite_price,
            "range2_opposite_anchor_time": stamp(opposite_time),
            "range2_continuation_anchor_type": continuation_type,
            "range2_continuation_anchor_price": continuation_price,
            "range2_continuation_anchor_time": stamp(continuation_time),
            "reclaim_depth_price": opposite_price,
            "reclaim_depth_ratio": trading_ratio,
            "reclaim_depth_percent": trading_ratio * 100.0,
            "raw_reclaim_depth_ratio": raw_ratio,
            "raw_reclaim_depth_percent": raw_ratio * 100.0,
            "boundary_position": boundary_position,
            "days_bos_to_depth_anchor": max(0, (opposite_time - bos_time).days),
            "days_reclaim_to_depth_anchor": max(0, (opposite_time - reclaim_time).days),
            "days_bos_to_range2_completion": max(0, (completed_at - bos_time).days),
            "days_reclaim_to_range2_completion": max(0, (completed_at - reclaim_time).days),
            "reason_codes": [
                "DAILY_NO_RETRACEMENT" if raw_ratio < 0 else "MAPPED_DAILY_RECLAIM_DEPTH_COMPLETE"
            ],
        })
        outputs.append(output(node, "COMPLETE", payload))
    return {"outputs": outputs}


def run_daily_movement_classification(context: Any) -> dict[str, list[dict[str, Any]]]:
    parents = weekly_parent_map(context)
    outputs: list[dict[str, Any]] = []
    for node in selected_nodes(context, "DAILY"):
        canonical_id = node_id(node)
        payload: dict[str, Any] = {
            "weekly_parent_id": None,
            "source_bos_direction": None,
            "source_bos_time": None,
            "next_bos_range_id": None,
            "next_bos_direction": None,
            "next_bos_time": None,
            "movement_path": None,
            "movement_sequence": [],
            "movement_legs": [],
            "protrend_leg_count": 0,
            "countertrend_leg_count": 0,
            "protrend_days": 0,
            "countertrend_days": 0,
            "candles_classified": 0,
            "depth_enrichment_status": "OPTIONAL_NOT_AVAILABLE",
            "reason_codes": [],
        }
        guarded = _parent_guard(node, parents, payload)
        if guarded:
            outputs.append(guarded)
            continue
        structure, processing = memory_entry(context, canonical_id, "daily_structure")
        if structure is None:
            payload["reason_codes"] = ["APPROVED_DAILY_BOS_MEMORY_MISSING"]
            outputs.append(output(node, "PENDING", payload))
            continue
        if processing == "NEEDS_REVIEW":
            payload["reason_codes"] = ["DAILY_BOS_NEEDS_REVIEW"]
            outputs.append(output(node, "NEEDS_REVIEW", payload))
            continue
        direction = str(structure.get("bos_direction") or "").upper()
        bos_time = time_value(structure.get("bos_time"))
        payload.update({"source_bos_direction": direction or None, "source_bos_time": stamp(bos_time)})
        if processing not in {"", "COMPLETE"} or direction not in {"BOS_UP", "BOS_DOWN"} or bos_time is None:
            payload["reason_codes"] = ["DAILY_BOS_STILL_PENDING"]
            outputs.append(output(node, "PENDING", payload))
            continue
        next_node, next_structure = next_completed_structure(context, canonical_id, bos_time)
        if next_node is None or next_structure is None:
            payload["reason_codes"] = ["NEXT_APPROVED_DAILY_BOS_NOT_AVAILABLE"]
            outputs.append(output(node, "PENDING", payload))
            continue
        next_time = time_value(next_structure.get("bos_time"))
        next_direction = str(next_structure.get("bos_direction") or "").upper()
        if next_time is None or next_time <= bos_time:
            payload["reason_codes"] = ["NEXT_DAILY_BOS_TIME_INVALID"]
            outputs.append(output(node, "NEEDS_REVIEW", payload))
            continue
        payload.update({
            "next_bos_range_id": node_id(next_node),
            "next_bos_direction": next_direction,
            "next_bos_time": stamp(next_time),
        })
        depth, depth_processing = memory_entry(context, canonical_id, "daily_reclaim_depth")
        if depth is not None:
            payload["depth_enrichment_status"] = depth_processing or "AVAILABLE"
        candles = candle_rows(context, "D1", bos_time, next_time, exclude_start=True, exclude_end=True)
        legs: list[dict[str, Any]] = []
        for candle in candles:
            candle_direction = candle_body_direction(candle)
            if candle_direction in {"DOJI", "INVALID"}:
                payload.update({
                    "candles_classified": len(candles),
                    "reason_codes": ["DOJI_OR_INVALID_D1_OHLC_IN_MOVEMENT"],
                })
                outputs.append(output(node, "NEEDS_REVIEW", payload))
                break
            role = (
                "PROTREND"
                if (direction == "BOS_UP" and candle_direction == "UP")
                or (direction == "BOS_DOWN" and candle_direction == "DOWN")
                else "COUNTERTREND"
            )
            candle_time = str(candle.get("time") or "")
            if legs and legs[-1]["role"] == role:
                legs[-1]["days"] += 1
                legs[-1]["end_time"] = candle_time
            else:
                legs.append({
                    "leg_number": len(legs) + 1,
                    "role": role,
                    "direction": candle_direction,
                    "days": 1,
                    "start_time": candle_time,
                    "end_time": candle_time,
                })
        else:
            sequence = [f"{'PT' if leg['role'] == 'PROTREND' else 'CT'} {leg['days']}D" for leg in legs]
            payload.update({
                "movement_path": " -> ".join(sequence + [next_direction or "BOS_PENDING"]),
                "movement_sequence": sequence,
                "movement_legs": legs,
                "protrend_leg_count": sum(leg["role"] == "PROTREND" for leg in legs),
                "countertrend_leg_count": sum(leg["role"] == "COUNTERTREND" for leg in legs),
                "protrend_days": sum(leg["days"] for leg in legs if leg["role"] == "PROTREND"),
                "countertrend_days": sum(leg["days"] for leg in legs if leg["role"] == "COUNTERTREND"),
                "candles_classified": len(candles),
                "reason_codes": ["DAILY_MOVEMENT_CHAPTER_COMPLETE"],
            })
            outputs.append(output(node, "COMPLETE", payload))
    return {"outputs": outputs}


def run_daily_profile_classification(context: Any) -> dict[str, list[dict[str, Any]]]:
    parents = weekly_parent_map(context)
    outputs: list[dict[str, Any]] = []
    for node in selected_nodes(context, "DAILY"):
        canonical_id = node_id(node)
        payload: dict[str, Any] = {
            "weekly_parent_id": None,
            "profile_classification": None,
            "profile_badge": None,
            "classification_basis": None,
            "reclaim_depth_percent": None,
            "reclaim_status": None,
            "source_bos_direction": None,
            "next_bos_direction": None,
            "reason_codes": [],
        }
        guarded = _parent_guard(node, parents, payload)
        if guarded:
            outputs.append(guarded)
            continue
        structure, structure_processing = memory_entry(context, canonical_id, "daily_structure")
        reclaim, reclaim_processing = memory_entry(context, canonical_id, "daily_reclaim")
        depth, depth_processing = memory_entry(context, canonical_id, "daily_reclaim_depth")
        if structure is None or reclaim is None:
            payload["reason_codes"] = ["APPROVED_DAILY_STRUCTURE_OR_RECLAIM_MEMORY_MISSING"]
            outputs.append(output(node, "PENDING", payload))
            continue
        if "NEEDS_REVIEW" in {structure_processing, reclaim_processing, depth_processing}:
            payload["reason_codes"] = ["DAILY_PROFILE_DEPENDENCY_NEEDS_REVIEW"]
            outputs.append(output(node, "NEEDS_REVIEW", payload))
            continue
        source_direction = str(structure.get("bos_direction") or "").upper()
        reclaim_status = str(reclaim.get("reclaim_status") or "").upper()
        next_direction = str(reclaim.get("next_bos_direction") or "").upper()
        payload.update({
            "source_bos_direction": source_direction or None,
            "reclaim_status": reclaim_status or None,
            "next_bos_direction": next_direction or None,
        })
        if reclaim_status == "ABANDONED" and source_direction in {"BOS_UP", "BOS_DOWN"} and next_direction == source_direction:
            profile = "S&R"
            payload.update({
                "profile_classification": profile,
                "profile_badge": f"◆ {profile}",
                "classification_basis": "ABANDONED_SAME_DIRECTION_CONTINUATION_OVERRIDE",
                "reason_codes": ["DAILY_ABANDONED_CONTINUATION_PROFILE_OVERRIDE"],
            })
            outputs.append(output(node, "COMPLETE", payload))
            continue
        if reclaim_status == "ABANDONED" and next_direction and next_direction != source_direction:
            payload["reason_codes"] = ["ABANDONED_DAILY_FOLLOWED_BY_OPPOSITE_BOS"]
            outputs.append(output(node, "PENDING", payload))
            continue
        depth_percent = number((depth or {}).get("reclaim_depth_percent"))
        payload["reclaim_depth_percent"] = depth_percent
        if depth is None or depth_processing not in {"", "COMPLETE"} or depth_percent is None:
            payload["reason_codes"] = ["COMPLETED_DAILY_RECLAIM_DEPTH_NOT_AVAILABLE"]
            outputs.append(output(node, "PENDING", payload))
            continue
        if depth_percent < 38.2 - EPSILON:
            profile = "S&R"
        elif depth_percent <= 50.0 + EPSILON:
            profile = "S&R>FP"
        else:
            profile = "S&D"
        payload.update({
            "profile_classification": profile,
            "profile_badge": f"◆ {profile}",
            "classification_basis": "DAILY_RECLAIM_DEPTH",
            "reason_codes": ["DAILY_PROFILE_CLASSIFIED_FROM_DEPTH"],
        })
        outputs.append(output(node, "COMPLETE", payload))
    return {"outputs": outputs}


def _destination_rank(name: str) -> int:
    return {
        "NO_FOLLOW_THROUGH": 0,
        "FAIR_PRICE": 1,
        "OPPOSITE_EXTREME": 2,
        "OPPOSITE_EXTERNAL": 3,
    }.get(name, 0)


def _daily_rejection_event(
    candles: list[dict[str, Any]],
    index: int,
    origin: str,
    high: float,
    low: float,
    levels: Mapping[str, float],
) -> dict[str, Any]:
    rejection = candles[index]
    rejection_time = time_value(rejection.get("time"))
    close = number(rejection.get("close"))
    origin_discount = origin == "DISCOUNT"
    fair = levels["fair_price"]
    opposite_extreme = levels["premium_floor"] if origin_discount else levels["discount_ceiling"]
    opposite_external = high if origin_discount else low
    origin_external = low if origin_discount else high
    event: dict[str, Any] = {
        "origin_zone": "DISCOUNT_EXTREME" if origin_discount else "PREMIUM_EXTREME",
        "rejection_time": rejection.get("time"),
        "rejection_price": number(rejection.get("low" if origin_discount else "high")),
        "rejection_close": close,
        "journey_status": "PENDING",
        "maximum_destination": "NO_FOLLOW_THROUGH",
        "fair_price_reached": False,
        "fair_price_time": None,
        "days_to_fair_price": None,
        "opposite_extreme_reached": False,
        "opposite_extreme_time": None,
        "days_to_opposite_extreme": None,
        "opposite_external_reached": False,
        "opposite_external_time": None,
        "days_to_opposite_external": None,
        "terminal_reason": None,
        "terminal_time": None,
        "reason_codes": [],
    }

    def close_reaches(price: float) -> bool:
        return bool(close is not None and (close >= price - EPSILON if origin_discount else close <= price + EPSILON))

    if close_reaches(fair):
        event.update({"fair_price_reached": True, "fair_price_time": rejection.get("time"), "days_to_fair_price": 0, "maximum_destination": "FAIR_PRICE"})
    if close_reaches(opposite_extreme):
        event.update({"opposite_extreme_reached": True, "opposite_extreme_time": rejection.get("time"), "days_to_opposite_extreme": 0, "maximum_destination": "OPPOSITE_EXTREME"})
    if close_reaches(opposite_external):
        event.update({
            "opposite_external_reached": True,
            "opposite_external_time": rejection.get("time"),
            "days_to_opposite_external": 0,
            "maximum_destination": "OPPOSITE_EXTERNAL",
            "journey_status": "COMPLETE",
            "terminal_reason": "OPPOSITE_EXTERNAL_REACHED",
            "terminal_time": rejection.get("time"),
        })
        return event

    for later in candles[index + 1:]:
        later_time = time_value(later.get("time"))
        later_high = number(later.get("high"))
        later_low = number(later.get("low"))
        if later_time is None or later_high is None or later_low is None:
            event.update({"journey_status": "NEEDS_REVIEW", "reason_codes": ["INVALID_D1_OHLC_IN_REJECTION_JOURNEY"]})
            return event
        origin_broken = later_low < origin_external - EPSILON if origin_discount else later_high > origin_external + EPSILON
        fair_new = not event["fair_price_reached"] and (later_high >= fair - EPSILON if origin_discount else later_low <= fair + EPSILON)
        extreme_new = not event["opposite_extreme_reached"] and (later_high >= opposite_extreme - EPSILON if origin_discount else later_low <= opposite_extreme + EPSILON)
        external_new = not event["opposite_external_reached"] and (later_high >= opposite_external - EPSILON if origin_discount else later_low <= opposite_external + EPSILON)
        if origin_broken and (fair_new or extreme_new or external_new):
            event.update({
                "journey_status": "NEEDS_REVIEW",
                "terminal_reason": "BOTH_DIRECTIONS_TOUCHED_SAME_D1",
                "terminal_time": later.get("time"),
                "reason_codes": ["BOTH_DIRECTIONS_TOUCHED_SAME_D1"],
            })
            return event
        days = max(0, (later_time - rejection_time).days) if rejection_time else None
        if fair_new:
            event.update({"fair_price_reached": True, "fair_price_time": later.get("time"), "days_to_fair_price": days, "maximum_destination": "FAIR_PRICE"})
        if extreme_new:
            event.update({"opposite_extreme_reached": True, "opposite_extreme_time": later.get("time"), "days_to_opposite_extreme": days, "maximum_destination": "OPPOSITE_EXTREME"})
        if external_new:
            event.update({
                "opposite_external_reached": True,
                "opposite_external_time": later.get("time"),
                "days_to_opposite_external": days,
                "maximum_destination": "OPPOSITE_EXTERNAL",
                "journey_status": "COMPLETE",
                "terminal_reason": "OPPOSITE_EXTERNAL_REACHED",
                "terminal_time": later.get("time"),
            })
            return event
        if origin_broken:
            event.update({
                "journey_status": "COMPLETE",
                "terminal_reason": "ORIGIN_EXTERNAL_BROKEN",
                "terminal_time": later.get("time"),
                "reason_codes": ["REJECTION_FAILED_BEFORE_OPPOSITE_EXTERNAL"],
            })
            return event
    event["reason_codes"] = ["D1_DATA_ENDED_WITH_REJECTION_JOURNEY_OPEN"]
    return event


def run_daily_extreme_rejection_destination(context: Any) -> dict[str, list[dict[str, Any]]]:
    parents = weekly_parent_map(context)
    latest = latest_time(context, "D1")
    outputs: list[dict[str, Any]] = []
    for node in selected_nodes(context, "DAILY"):
        payload: dict[str, Any] = {
            "weekly_parent_id": None,
            "range_high": number(node.get("range_high")),
            "range_low": number(node.get("range_low")),
            "rejection_event_count": 0,
            "completed_event_count": 0,
            "pending_event_count": 0,
            "review_event_count": 0,
            "primary_event": None,
            "rejection_events": [],
            "reason_codes": [],
        }
        guarded = _parent_guard(node, parents, payload)
        if guarded:
            outputs.append(guarded)
            continue
        high = payload["range_high"]
        low = payload["range_low"]
        defined_at = range_defined_at(node)
        if high is None or low is None or high <= low:
            payload["reason_codes"] = ["INVALID_RANGE_PRICES"]
            outputs.append(output(node, "NEEDS_REVIEW", payload))
            continue
        if defined_at is None:
            payload["reason_codes"] = ["MISSING_OR_INVALID_ANCHOR_TIME"]
            outputs.append(output(node, "NEEDS_REVIEW", payload))
            continue
        if latest is None or latest < defined_at:
            payload["reason_codes"] = ["NO_D1_CANDLES_FOR_EXTREME_REJECTION"]
            outputs.append(output(node, "PENDING", payload))
            continue
        levels = zone_levels(high, low)
        candles = candle_rows(context, "D1", defined_at, latest)
        events: list[dict[str, Any]] = []
        ambiguous = False
        for index, candle in enumerate(candles):
            candle_high = number(candle.get("high"))
            candle_low = number(candle.get("low"))
            close = number(candle.get("close"))
            if candle_high is None or candle_low is None or close is None:
                ambiguous = True
                continue
            discount = candle_low <= levels["discount_ceiling"] + EPSILON and close > levels["discount_ceiling"] + EPSILON
            premium = candle_high >= levels["premium_floor"] - EPSILON and close < levels["premium_floor"] - EPSILON
            if discount and premium:
                events.append({
                    "origin_zone": "BOTH_EXTREMES",
                    "rejection_time": candle.get("time"),
                    "journey_status": "NEEDS_REVIEW",
                    "maximum_destination": "NO_FOLLOW_THROUGH",
                    "reason_codes": ["BOTH_EXTREMES_REJECTED_SAME_D1"],
                })
                ambiguous = True
                continue
            if discount:
                events.append(_daily_rejection_event(candles, index, "DISCOUNT", high, low, levels))
            elif premium:
                events.append(_daily_rejection_event(candles, index, "PREMIUM", high, low, levels))
        payload.update({
            "rejection_event_count": len(events),
            "completed_event_count": sum(event.get("journey_status") == "COMPLETE" for event in events),
            "pending_event_count": sum(event.get("journey_status") == "PENDING" for event in events),
            "review_event_count": sum(event.get("journey_status") == "NEEDS_REVIEW" for event in events),
            "rejection_events": events,
        })
        if events:
            completed = [event for event in events if event.get("journey_status") == "COMPLETE"]
            payload["primary_event"] = (completed or events)[0]
        if ambiguous or any(event.get("journey_status") == "NEEDS_REVIEW" for event in events):
            payload["reason_codes"] = ["ONE_OR_MORE_DAILY_REJECTION_EVENTS_NEED_REVIEW"]
            outputs.append(output(node, "NEEDS_REVIEW", payload))
        elif any(event.get("journey_status") == "PENDING" for event in events):
            payload["reason_codes"] = ["ONE_OR_MORE_DAILY_REJECTION_JOURNEYS_OPEN"]
            outputs.append(output(node, "PENDING", payload))
        else:
            payload["reason_codes"] = [
                "DAILY_EXTREME_REJECTION_EVENTS_COMPLETE" if events
                else "NO_DAILY_EXTREME_REJECTION_FOUND"
            ]
            outputs.append(output(node, "COMPLETE", payload))
    return {"outputs": outputs}
