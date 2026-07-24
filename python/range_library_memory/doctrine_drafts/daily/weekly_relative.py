"""Weekly-relative Daily doctrine candidates.

The outputs are parent-scoped and consume trusted hierarchy plus approved memory.
No function repairs parent links or writes runtime state.
"""
from __future__ import annotations

from typing import Any, Mapping

from .shared import (
    EPSILON,
    anchor_chronology,
    candle_rows,
    historical_valid_relationships,
    inside_weekly,
    latest_time,
    memory_entry,
    node_id,
    node_index,
    number,
    output,
    range_direction_from_row,
    range_start_at,
    row_interval,
    selected_nodes,
    stamp,
    time_value,
    weekly_prices,
    weekly_zone,
    zone_levels,
)


def _weekly_direction(context: Any, node: Mapping[str, Any]) -> tuple[str, str, str | None]:
    canonical_id = node_id(node)
    structure, processing = memory_entry(context, canonical_id, "weekly_structure")
    if structure is not None:
        direction = str(structure.get("bos_direction") or "").upper()
        if processing == "NEEDS_REVIEW":
            return "UNRESOLVED", "WEEKLY_BOS", "WEEKLY_STRUCTURE_NEEDS_REVIEW"
        if processing in {"", "COMPLETE"} and direction in {"BOS_UP", "BOS_DOWN"}:
            return ("UP" if direction == "BOS_UP" else "DOWN"), "WEEKLY_BOS", None
    _, chronology_direction = anchor_chronology(node, "W1")
    if chronology_direction in {"UP", "DOWN"}:
        return chronology_direction, "WEEKLY_ANCHOR_CHRONOLOGY", None
    return "UNRESOLVED", "UNAVAILABLE", "WEEKLY_DIRECTION_UNRESOLVED"


def _trend_role(daily_direction: str, weekly_direction: str) -> str:
    if daily_direction not in {"UP", "DOWN"} or weekly_direction not in {"UP", "DOWN"}:
        return "UNRESOLVED"
    return "PROTREND" if daily_direction == weekly_direction else "COUNTERTREND"


def run_daily_child_trend_classification(context: Any) -> dict[str, list[dict[str, Any]]]:
    outputs: list[dict[str, Any]] = []
    for weekly in selected_nodes(context, "WEEKLY"):
        weekly_id = node_id(weekly)
        rows, relationship, relationship_processing = historical_valid_relationships(context, weekly_id)
        weekly_direction, direction_basis, direction_error = _weekly_direction(context, weekly)
        payload: dict[str, Any] = {
            "weekly_range_id": weekly_id,
            "weekly_direction": weekly_direction,
            "weekly_direction_basis": direction_basis,
            "daily_child_count": len(rows),
            "protrend_count": 0,
            "countertrend_count": 0,
            "unresolved_count": 0,
            "future_daily_ranges_excluded": int((relationship or {}).get("future_daily_ranges_excluded") or 0),
            "classifications": [],
            "reason_codes": [],
        }
        if relationship is None:
            payload["reason_codes"] = ["APPROVED_WEEKLY_DAILY_RELATIONSHIP_MEMORY_MISSING"]
            outputs.append(output(weekly, "PENDING", payload))
            continue
        if relationship_processing == "NEEDS_REVIEW":
            payload["reason_codes"] = ["WEEKLY_DAILY_RELATIONSHIP_NEEDS_REVIEW"]
            outputs.append(output(weekly, "NEEDS_REVIEW", payload))
            continue
        classifications: list[dict[str, Any]] = []
        for row in rows:
            daily_direction = range_direction_from_row(row)
            role = _trend_role(daily_direction, weekly_direction)
            classifications.append({
                "daily_range_id": str(row.get("daily_range_id") or ""),
                "daily_sequence_number": row.get("daily_sequence_number"),
                "daily_direction": daily_direction,
                "trend_role": role,
                "weekly_direction": weekly_direction,
                "classification_basis": direction_basis,
                "daily_status_at_freeze": row.get("daily_status_at_freeze"),
            })
        payload.update({
            "classifications": classifications,
            "protrend_count": sum(row["trend_role"] == "PROTREND" for row in classifications),
            "countertrend_count": sum(row["trend_role"] == "COUNTERTREND" for row in classifications),
            "unresolved_count": sum(row["trend_role"] == "UNRESOLVED" for row in classifications),
        })
        if direction_error:
            payload["reason_codes"] = [direction_error]
            outputs.append(output(weekly, "NEEDS_REVIEW", payload))
        elif not rows:
            payload["reason_codes"] = ["NO_HISTORICALLY_AVAILABLE_DAILY_CHILDREN"]
            outputs.append(output(weekly, "PENDING", payload))
        elif payload["unresolved_count"]:
            payload["reason_codes"] = ["ONE_OR_MORE_DAILY_DIRECTIONS_UNRESOLVED"]
            outputs.append(output(weekly, "NEEDS_REVIEW", payload))
        else:
            payload["reason_codes"] = ["WEEKLY_RELATIVE_DAILY_TREND_CLASSIFICATION_COMPLETE"]
            outputs.append(output(weekly, "COMPLETE", payload))
    return {"outputs": outputs}


def run_first_daily_external_to_internal(context: Any) -> dict[str, list[dict[str, Any]]]:
    daily_by_id = node_index(context, "DAILY")
    outputs: list[dict[str, Any]] = []
    for weekly in selected_nodes(context, "WEEKLY"):
        weekly_id = node_id(weekly)
        high, low = weekly_prices(weekly)
        rows, relationship, relationship_processing = historical_valid_relationships(context, weekly_id)
        payload: dict[str, Any] = {
            "weekly_range_id": weekly_id,
            "weekly_high": high,
            "weekly_low": low,
            "candidate_found": False,
            "daily_range_id": None,
            "daily_sequence_number": None,
            "daily_direction": None,
            "origin_price": None,
            "origin_zone": None,
            "origin_relation": None,
            "internal_finish_price": None,
            "internal_finish_zone": None,
            "classification": None,
            "candidates_scanned": 0,
            "reason_codes": [],
        }
        if relationship is None:
            payload["reason_codes"] = ["APPROVED_WEEKLY_DAILY_RELATIONSHIP_MEMORY_MISSING"]
            outputs.append(output(weekly, "PENDING", payload))
            continue
        if relationship_processing == "NEEDS_REVIEW":
            payload["reason_codes"] = ["WEEKLY_DAILY_RELATIONSHIP_NEEDS_REVIEW"]
            outputs.append(output(weekly, "NEEDS_REVIEW", payload))
            continue
        if high is None or low is None or high <= low:
            payload["reason_codes"] = ["INVALID_WEEKLY_RANGE_PRICES"]
            outputs.append(output(weekly, "NEEDS_REVIEW", payload))
            continue

        selected: dict[str, Any] | None = None
        ambiguous: dict[str, Any] | None = None
        for row in rows:
            payload["candidates_scanned"] += 1
            daily_id = str(row.get("daily_range_id") or "")
            daily = daily_by_id.get(daily_id)
            direction = range_direction_from_row(row)
            if daily is None or direction not in {"UP", "DOWN"}:
                continue
            daily_high = number(daily.get("range_high"))
            daily_low = number(daily.get("range_low"))
            if daily_high is None or daily_low is None or daily_high <= daily_low:
                continue
            spans_both = daily_low <= low + EPSILON and daily_high >= high - EPSILON
            if spans_both:
                ambiguous = {
                    "daily_range_id": daily_id,
                    "daily_sequence_number": row.get("daily_sequence_number"),
                    "reason": "DAILY_RANGE_SPANS_BOTH_WEEKLY_EXTERNALS",
                }
                break
            origin_price = daily_low if direction == "UP" else daily_high
            finish_price = daily_high if direction == "UP" else daily_low
            valid_origin = origin_price <= low + EPSILON if direction == "UP" else origin_price >= high - EPSILON
            if not valid_origin or not inside_weekly(finish_price, high, low):
                continue
            origin_relation = (
                "BEYOND_EXTERNAL"
                if (direction == "UP" and origin_price < low - EPSILON)
                or (direction == "DOWN" and origin_price > high + EPSILON)
                else "AT_EXTERNAL"
            )
            selected = {
                "daily_range_id": daily_id,
                "daily_sequence_number": row.get("daily_sequence_number"),
                "daily_direction": direction,
                "origin_price": origin_price,
                "origin_zone": weekly_zone(origin_price, high, low),
                "origin_relation": origin_relation,
                "internal_finish_price": finish_price,
                "internal_finish_zone": weekly_zone(finish_price, high, low),
                "classification": (
                    "EXTERNAL_LOW_TO_INTERNAL" if direction == "UP"
                    else "EXTERNAL_HIGH_TO_INTERNAL"
                ),
            }
            break

        if ambiguous:
            payload.update(ambiguous)
            payload["reason_codes"] = [ambiguous["reason"]]
            outputs.append(output(weekly, "NEEDS_REVIEW", payload))
        elif selected:
            payload.update(selected)
            payload["candidate_found"] = True
            payload["reason_codes"] = ["FIRST_DAILY_EXTERNAL_TO_INTERNAL_CLASSIFIED"]
            outputs.append(output(weekly, "COMPLETE", payload))
        else:
            payload["reason_codes"] = ["NO_DAILY_EXTERNAL_TO_INTERNAL_RANGE_FOUND"]
            outputs.append(output(weekly, "PENDING", payload))
    return {"outputs": outputs}


def run_first_daily_at_weekly_extreme_rejection(context: Any) -> dict[str, list[dict[str, Any]]]:
    outputs: list[dict[str, Any]] = []
    for weekly in selected_nodes(context, "WEEKLY"):
        weekly_id = node_id(weekly)
        rows, relationship, relationship_processing = historical_valid_relationships(context, weekly_id)
        extreme, extreme_processing = memory_entry(context, weekly_id, "weekly_extreme_rejection_destination")
        weekly_direction, direction_basis, _ = _weekly_direction(context, weekly)
        payload: dict[str, Any] = {
            "weekly_range_id": weekly_id,
            "weekly_direction": weekly_direction,
            "weekly_direction_basis": direction_basis,
            "weekly_rejection_event_count": 0,
            "matched_event_count": 0,
            "unmatched_event_count": 0,
            "primary_match": None,
            "matches": [],
            "reason_codes": [],
        }
        if relationship is None or extreme is None:
            payload["reason_codes"] = ["APPROVED_RELATIONSHIP_OR_WEEKLY_REJECTION_MEMORY_MISSING"]
            outputs.append(output(weekly, "PENDING", payload))
            continue
        if "NEEDS_REVIEW" in {relationship_processing, extreme_processing}:
            payload["reason_codes"] = ["RELATIONSHIP_OR_WEEKLY_REJECTION_NEEDS_REVIEW"]
            outputs.append(output(weekly, "NEEDS_REVIEW", payload))
            continue
        raw_events = extreme.get("rejection_events")
        events = [dict(event) for event in raw_events if isinstance(event, Mapping)] if isinstance(raw_events, list) else []
        events.sort(key=lambda event: (str(event.get("rejection_time") or "9999"), str(event.get("origin_zone") or "")))
        payload["weekly_rejection_event_count"] = len(events)
        if not events:
            payload["reason_codes"] = ["NO_WEEKLY_EXTREME_REJECTION_TO_CLASSIFY"]
            outputs.append(output(weekly, "COMPLETE", payload))
            continue
        freeze = time_value((relationship or {}).get("candidate_freeze_time"))
        matches: list[dict[str, Any]] = []
        ambiguous = False
        unmatched = 0
        for event in events:
            event_time = time_value(event.get("rejection_time"))
            if event_time is None:
                ambiguous = True
                continue
            owners: list[dict[str, Any]] = []
            for index, row in enumerate(rows):
                next_row = rows[index + 1] if index + 1 < len(rows) else None
                start, end = row_interval(row, next_row, freeze)
                if start is None:
                    continue
                if event_time >= start and (end is None or event_time <= end):
                    owners.append(row)
            if len(owners) > 1:
                ambiguous = True
                matches.append({
                    "rejection_time": event.get("rejection_time"),
                    "origin_zone": event.get("origin_zone"),
                    "ownership_status": "NEEDS_REVIEW",
                    "candidate_daily_range_ids": [str(row.get("daily_range_id") or "") for row in owners],
                    "reason": "MULTIPLE_DAILY_CHILDREN_OWN_REJECTION_DATE",
                })
                continue
            if not owners:
                unmatched += 1
                continue
            owner = owners[0]
            daily_direction = range_direction_from_row(owner)
            matches.append({
                "rejection_time": event.get("rejection_time"),
                "origin_zone": event.get("origin_zone"),
                "maximum_destination": event.get("maximum_destination"),
                "journey_status": event.get("journey_status"),
                "daily_range_id": str(owner.get("daily_range_id") or ""),
                "daily_sequence_number": owner.get("daily_sequence_number"),
                "daily_direction": daily_direction,
                "weekly_relative_role": _trend_role(daily_direction, weekly_direction),
                "ownership_status": "MATCHED_ACTIVE_ON_REJECTION_DATE",
            })
        payload.update({
            "matched_event_count": sum(match.get("ownership_status") == "MATCHED_ACTIVE_ON_REJECTION_DATE" for match in matches),
            "unmatched_event_count": unmatched,
            "matches": matches,
            "primary_match": next((match for match in matches if match.get("ownership_status") == "MATCHED_ACTIVE_ON_REJECTION_DATE"), matches[0] if matches else None),
        })
        if ambiguous:
            payload["reason_codes"] = ["WEEKLY_REJECTION_DAILY_OWNERSHIP_AMBIGUOUS"]
            outputs.append(output(weekly, "NEEDS_REVIEW", payload))
        elif unmatched:
            payload["reason_codes"] = ["ONE_OR_MORE_WEEKLY_REJECTIONS_HAVE_NO_DAILY_CHILD_MATCH"]
            outputs.append(output(weekly, "PENDING", payload))
        else:
            payload["reason_codes"] = ["WEEKLY_EXTREME_REJECTIONS_MATCHED_TO_DAILY_CHILDREN"]
            outputs.append(output(weekly, "COMPLETE", payload))
    return {"outputs": outputs}


def run_daily_profile_streaks(context: Any) -> dict[str, list[dict[str, Any]]]:
    outputs: list[dict[str, Any]] = []
    for weekly in selected_nodes(context, "WEEKLY"):
        weekly_id = node_id(weekly)
        rows, relationship, relationship_processing = historical_valid_relationships(context, weekly_id)
        payload: dict[str, Any] = {
            "weekly_range_id": weekly_id,
            "daily_child_count": len(rows),
            "profiled_daily_count": 0,
            "missing_profile_count": 0,
            "review_profile_count": 0,
            "streak_count": 0,
            "maximum_streak_profile": None,
            "maximum_streak_length": 0,
            "current_streak_profile": None,
            "current_streak_length": 0,
            "streaks": [],
            "daily_profiles": [],
            "reason_codes": [],
        }
        if relationship is None:
            payload["reason_codes"] = ["APPROVED_WEEKLY_DAILY_RELATIONSHIP_MEMORY_MISSING"]
            outputs.append(output(weekly, "PENDING", payload))
            continue
        if relationship_processing == "NEEDS_REVIEW":
            payload["reason_codes"] = ["WEEKLY_DAILY_RELATIONSHIP_NEEDS_REVIEW"]
            outputs.append(output(weekly, "NEEDS_REVIEW", payload))
            continue

        streaks: list[dict[str, Any]] = []
        daily_profiles: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None
        missing = 0
        review = 0
        for row in rows:
            daily_id = str(row.get("daily_range_id") or "")
            profile_memory, processing = memory_entry(context, daily_id, "daily_profile_classification")
            profile = str((profile_memory or {}).get("profile_classification") or "").upper()
            valid_profile = profile in {"S&R", "S&R>FP", "S&D"} and processing in {"", "COMPLETE"}
            daily_profiles.append({
                "daily_range_id": daily_id,
                "daily_sequence_number": row.get("daily_sequence_number"),
                "profile": profile or None,
                "processing_status": processing,
            })
            if processing == "NEEDS_REVIEW":
                review += 1
            elif not valid_profile:
                missing += 1
            if not valid_profile:
                current = None
                continue
            sequence = int(row.get("daily_sequence_number") or 0)
            if current and current["profile"] == profile and current["end_sequence"] + 1 == sequence:
                current["end_sequence"] = sequence
                current["end_daily_range_id"] = daily_id
                current["length"] += 1
            else:
                current = {
                    "streak_number": len(streaks) + 1,
                    "profile": profile,
                    "start_sequence": sequence,
                    "end_sequence": sequence,
                    "start_daily_range_id": daily_id,
                    "end_daily_range_id": daily_id,
                    "length": 1,
                }
                streaks.append(current)
        maximum = max(streaks, key=lambda streak: (streak["length"], -streak["start_sequence"])) if streaks else None
        current_streak = streaks[-1] if streaks and daily_profiles and daily_profiles[-1].get("profile") == streaks[-1]["profile"] else None
        payload.update({
            "profiled_daily_count": len(rows) - missing - review,
            "missing_profile_count": missing,
            "review_profile_count": review,
            "streak_count": len(streaks),
            "maximum_streak_profile": maximum.get("profile") if maximum else None,
            "maximum_streak_length": maximum.get("length", 0) if maximum else 0,
            "current_streak_profile": current_streak.get("profile") if current_streak else None,
            "current_streak_length": current_streak.get("length", 0) if current_streak else 0,
            "streaks": streaks,
            "daily_profiles": daily_profiles,
        })
        if review:
            payload["reason_codes"] = ["ONE_OR_MORE_DAILY_PROFILES_NEED_REVIEW"]
            outputs.append(output(weekly, "NEEDS_REVIEW", payload))
        elif missing:
            payload["reason_codes"] = ["ONE_OR_MORE_DAILY_PROFILES_NOT_AVAILABLE"]
            outputs.append(output(weekly, "PENDING", payload))
        elif not rows:
            payload["reason_codes"] = ["NO_HISTORICALLY_AVAILABLE_DAILY_CHILDREN"]
            outputs.append(output(weekly, "PENDING", payload))
        else:
            payload["reason_codes"] = ["DAILY_PROFILE_STREAKS_COMPLETE"]
            outputs.append(output(weekly, "COMPLETE", payload))
    return {"outputs": outputs}


def _sweep_location(level: float, high: float, low: float, sweep_type: str) -> str | None:
    levels = zone_levels(high, low)
    if sweep_type == "PDL":
        if level < low - EPSILON:
            return "EXTERNAL_LOW"
        if level <= levels["discount_ceiling"] + EPSILON:
            return "DISCOUNT_EXTREME"
        return None
    if level > high + EPSILON:
        return "EXTERNAL_HIGH"
    if level >= levels["premium_floor"] - EPSILON:
        return "PREMIUM_EXTREME"
    return None


def run_pdl_pdh_reversal_sweep(context: Any) -> dict[str, list[dict[str, Any]]]:
    outputs: list[dict[str, Any]] = []
    for weekly in selected_nodes(context, "WEEKLY"):
        weekly_id = node_id(weekly)
        high, low = weekly_prices(weekly)
        _, relationship, relationship_processing = historical_valid_relationships(context, weekly_id)
        payload: dict[str, Any] = {
            "weekly_range_id": weekly_id,
            "weekly_high": high,
            "weekly_low": low,
            "candidate_freeze_time": (relationship or {}).get("candidate_freeze_time"),
            "pdl_sweep_count": 0,
            "pdh_sweep_count": 0,
            "dual_sweep_review_count": 0,
            "primary_event": None,
            "sweep_events": [],
            "reason_codes": [],
        }
        if relationship is None:
            payload["reason_codes"] = ["APPROVED_WEEKLY_DAILY_RELATIONSHIP_MEMORY_MISSING"]
            outputs.append(output(weekly, "PENDING", payload))
            continue
        if relationship_processing == "NEEDS_REVIEW":
            payload["reason_codes"] = ["WEEKLY_DAILY_RELATIONSHIP_NEEDS_REVIEW"]
            outputs.append(output(weekly, "NEEDS_REVIEW", payload))
            continue
        if high is None or low is None or high <= low:
            payload["reason_codes"] = ["INVALID_WEEKLY_RANGE_PRICES"]
            outputs.append(output(weekly, "NEEDS_REVIEW", payload))
            continue
        start = range_start_at(weekly)
        freeze = time_value(relationship.get("candidate_freeze_time")) or latest_time(context, "D1")
        if start is None or freeze is None or freeze <= start:
            payload["reason_codes"] = ["WEEKLY_D1_SWEEP_WINDOW_UNAVAILABLE"]
            outputs.append(output(weekly, "PENDING", payload))
            continue
        candles = candle_rows(context, "D1", start, freeze)
        events: list[dict[str, Any]] = []
        invalid_ohlc = False
        for index in range(1, len(candles)):
            previous = candles[index - 1]
            current = candles[index]
            pdl = number(previous.get("low"))
            pdh = number(previous.get("high"))
            current_low = number(current.get("low"))
            current_high = number(current.get("high"))
            current_close = number(current.get("close"))
            if None in {pdl, pdh, current_low, current_high, current_close}:
                invalid_ohlc = True
                break
            assert pdl is not None and pdh is not None and current_low is not None and current_high is not None and current_close is not None
            pdl_location = _sweep_location(pdl, high, low, "PDL")
            pdh_location = _sweep_location(pdh, high, low, "PDH")
            swept_pdl = pdl_location is not None and current_low < pdl - EPSILON and current_close > pdl + EPSILON
            swept_pdh = pdh_location is not None and current_high > pdh + EPSILON and current_close < pdh - EPSILON
            if swept_pdl and swept_pdh:
                events.append({
                    "event_type": "PDL_AND_PDH_SWEEP_SAME_D1",
                    "previous_day_time": previous.get("time"),
                    "sweep_day_time": current.get("time"),
                    "pdl": pdl,
                    "pdh": pdh,
                    "current_low": current_low,
                    "current_high": current_high,
                    "current_close": current_close,
                    "pdl_location": pdl_location,
                    "pdh_location": pdh_location,
                    "reversal_direction": "ORDER_UNKNOWN",
                    "processing_status": "NEEDS_REVIEW",
                    "reason_codes": ["PDL_AND_PDH_SWEPT_SAME_D1_ORDER_UNKNOWN"],
                })
                continue
            if swept_pdl:
                events.append({
                    "event_type": "PDL_REVERSAL_SWEEP",
                    "previous_day_time": previous.get("time"),
                    "sweep_day_time": current.get("time"),
                    "swept_level": pdl,
                    "sweep_extreme": current_low,
                    "close_back_through": current_close,
                    "weekly_location": pdl_location,
                    "reversal_direction": "UP",
                    "processing_status": "COMPLETE",
                    "reason_codes": ["PDL_SWEPT_AND_D1_CLOSED_BACK_ABOVE"],
                })
            elif swept_pdh:
                events.append({
                    "event_type": "PDH_REVERSAL_SWEEP",
                    "previous_day_time": previous.get("time"),
                    "sweep_day_time": current.get("time"),
                    "swept_level": pdh,
                    "sweep_extreme": current_high,
                    "close_back_through": current_close,
                    "weekly_location": pdh_location,
                    "reversal_direction": "DOWN",
                    "processing_status": "COMPLETE",
                    "reason_codes": ["PDH_SWEPT_AND_D1_CLOSED_BACK_BELOW"],
                })
        payload.update({
            "pdl_sweep_count": sum(event.get("event_type") == "PDL_REVERSAL_SWEEP" for event in events),
            "pdh_sweep_count": sum(event.get("event_type") == "PDH_REVERSAL_SWEEP" for event in events),
            "dual_sweep_review_count": sum(event.get("processing_status") == "NEEDS_REVIEW" for event in events),
            "sweep_events": events,
            "primary_event": next((event for event in events if event.get("processing_status") == "COMPLETE"), events[0] if events else None),
        })
        if invalid_ohlc:
            payload["reason_codes"] = ["INVALID_D1_OHLC_IN_PDL_PDH_WINDOW"]
            outputs.append(output(weekly, "NEEDS_REVIEW", payload))
        elif payload["dual_sweep_review_count"]:
            payload["reason_codes"] = ["ONE_OR_MORE_D1_CANDLES_SWEPT_BOTH_PREVIOUS_DAY_EXTREMES"]
            outputs.append(output(weekly, "NEEDS_REVIEW", payload))
        else:
            payload["reason_codes"] = [
                "PDL_PDH_REVERSAL_SWEEP_SCAN_COMPLETE" if events
                else "NO_QUALIFYING_PDL_PDH_REVERSAL_SWEEP"
            ]
            outputs.append(output(weekly, "COMPLETE", payload))
    return {"outputs": outputs}
