"""Audit mapped Daily coverage inside each approved Weekly candidate freeze.

This package distinguishes missing mapping work from a genuine absence of Daily
structure. Weekly history before the first mapped Daily range is classified
NOT_MAPPED, never NO_DAILY_STRUCTURE.

The canonical Master Map hierarchy is structural truth. Direct Daily children are
read from the Weekly node exactly as stored; bad parent-link evidence is reported
and never repaired or re-parented by Python.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Mapping

FXTM_DOCTRINE_CONTRACT = "fxtm_doctrine_package_v1"
SCRIPT_KEY = "daily_mapping_coverage_audit"
VERSION_LABEL = "1"
ADAPTER_KEY = "doctrine_package_v1"
EXECUTION_ORDER = 70

_VALID_PARENT_LINKS = {"VALID", "TRUSTED"}


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


def _stamp(value: datetime | None) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value else None


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


def _range_start(node: Mapping[str, Any]) -> datetime | None:
    high_time = _time(node.get("range_high_time"))
    low_time = _time(node.get("range_low_time"))
    times = [value for value in (high_time, low_time) if value is not None]
    return min(times) if times else None


def _range_created(node: Mapping[str, Any]) -> datetime | None:
    active = _time(node.get("active_from_time"))
    if active is not None:
        return active
    high_time = _time(node.get("range_high_time"))
    low_time = _time(node.get("range_low_time"))
    if high_time is None or low_time is None:
        return None
    return max(high_time, low_time)


def _daily_child(parent_id: str, node: Mapping[str, Any]) -> dict[str, Any]:
    link_status = str(node.get("direct_parent_link_status") or "MISSING").upper()
    start = _range_start(node)
    created = _range_created(node)
    inactive = _time(node.get("inactive_from_time"))
    return {
        "daily_range_id": str(node.get("id") or ""),
        "parent_range_id": parent_id,
        "parent_link_status": link_status,
        "parent_link_valid": link_status in _VALID_PARENT_LINKS,
        "daily_start_time": _stamp(start),
        "daily_created_time": _stamp(created),
        "daily_end_time": _stamp(inactive),
        "daily_status": str(node.get("status") or "PENDING").upper(),
        "direction_of_break": str(node.get("direction_of_break") or "").upper() or None,
        "range_high_time": _stamp(_time(node.get("range_high_time"))),
        "range_low_time": _stamp(_time(node.get("range_low_time"))),
    }


def _base_payload(canonical_id: str) -> dict[str, Any]:
    return {
        "weekly_candidate_id": canonical_id,
        "weekly_range_id": canonical_id,
        "candidate_freeze_time": None,
        "candidate_freeze_basis": None,
        "daily_mapping_coverage_available": False,
        "daily_mapping_first_available_time": None,
        "daily_ranges_found": 0,
        "daily_ranges_mapped_total": 0,
        "future_daily_ranges_excluded": 0,
        "earliest_daily_range": None,
        "earliest_daily_range_time": None,
        "latest_daily_range": None,
        "latest_daily_range_time": None,
        "coverage_window_start": None,
        "coverage_window_end": None,
        "coverage_status": None,
        "front_gap": None,
        "middle_gaps": [],
        "tail_gap": None,
        "overlap_count": 0,
        "invalid_parent_links": [],
        "daily_children": [],
        "reason_codes": [],
    }


def _weekly_freeze(context: Any, node: Mapping[str, Any]) -> tuple[datetime | None, str | None, str | None]:
    canonical_id = str(node.get("id") or "")
    structure, processing = _memory_entry(context, canonical_id, "weekly_structure")
    if structure is not None:
        bos_time = _time(structure.get("bos_time"))
        if processing == "NEEDS_REVIEW":
            return bos_time, "WEEKLY_BOS", "WEEKLY_STRUCTURE_NEEDS_REVIEW"
        if bos_time is not None and processing in {"", "COMPLETE"}:
            return bos_time, "WEEKLY_BOS", None
    legacy_bos = _time(node.get("script1_bos_time"))
    if legacy_bos is not None:
        return legacy_bos, "WEEKLY_BOS", None
    inactive = _time(node.get("inactive_from_time"))
    if inactive is not None:
        return inactive, "WEEKLY_INACTIVE_TIME", None
    return None, None, "WEEKLY_CANDIDATE_FREEZE_TIME_UNAVAILABLE"


def _coverage_gaps(
    *,
    window_start: datetime,
    window_end: datetime,
    children: list[dict[str, Any]],
) -> tuple[dict[str, str] | None, list[dict[str, str]], dict[str, str] | None, int]:
    intervals: list[tuple[datetime, datetime]] = []
    for child in children:
        if not child["parent_link_valid"]:
            continue
        created = _time(child.get("daily_created_time"))
        if created is None or created > window_end:
            continue
        start = _time(child.get("daily_start_time")) or created
        end = _time(child.get("daily_end_time")) or window_end
        start = max(window_start, start)
        end = min(window_end, end)
        if end < start:
            continue
        intervals.append((start, end))
    intervals.sort(key=lambda item: (item[0], item[1]))

    if not intervals:
        return None, [], None, 0

    cursor = window_start
    front: dict[str, str] | None = None
    middle: list[dict[str, str]] = []
    overlap_count = 0
    for index, (start, end) in enumerate(intervals):
        if start > cursor:
            gap = {"start_time": _stamp(cursor), "end_time": _stamp(start)}
            if index == 0:
                front = gap
            else:
                middle.append(gap)
        elif start < cursor:
            overlap_count += 1
        if end > cursor:
            cursor = end

    tail = None
    if cursor < window_end:
        tail = {"start_time": _stamp(cursor), "end_time": _stamp(window_end)}
    return front, middle, tail, overlap_count


def run(context: Any) -> dict[str, list[dict[str, Any]]]:
    weekly_nodes = [dict(node) for node in context.selected_ranges(layer="WEEKLY")]
    all_daily_nodes = [dict(node) for node in context.selected_ranges(layer="DAILY")]
    all_daily_created = sorted(
        created for node in all_daily_nodes
        if (created := _range_created(node)) is not None
    )
    first_daily_mapping = all_daily_created[0] if all_daily_created else None

    outputs: list[dict[str, Any]] = []
    for node in weekly_nodes:
        canonical_id = str(node.get("id") or "")
        payload = _base_payload(canonical_id)
        freeze, freeze_basis, freeze_error = _weekly_freeze(context, node)
        payload["candidate_freeze_time"] = _stamp(freeze)
        payload["candidate_freeze_basis"] = freeze_basis
        payload["daily_mapping_first_available_time"] = _stamp(first_daily_mapping)

        if freeze_error == "WEEKLY_STRUCTURE_NEEDS_REVIEW":
            payload["reason_codes"] = [freeze_error]
            outputs.append(_output(node, "NEEDS_REVIEW", payload))
            continue
        if freeze is None:
            payload["reason_codes"] = [freeze_error or "WEEKLY_CANDIDATE_FREEZE_TIME_UNAVAILABLE"]
            outputs.append(_output(node, "PENDING", payload))
            continue

        weekly_start = _range_created(node)
        if weekly_start is None:
            payload["reason_codes"] = ["WEEKLY_RANGE_START_UNAVAILABLE"]
            outputs.append(_output(node, "NEEDS_REVIEW", payload))
            continue
        if weekly_start > freeze:
            payload["reason_codes"] = ["WEEKLY_RANGE_START_AFTER_FREEZE"]
            outputs.append(_output(node, "NEEDS_REVIEW", payload))
            continue

        payload["coverage_window_start"] = _stamp(weekly_start)
        payload["coverage_window_end"] = _stamp(freeze)
        payload["daily_mapping_coverage_available"] = (
            first_daily_mapping is not None and freeze >= first_daily_mapping
        )

        raw_children = node.get("children")
        direct_daily = [
            dict(child) for child in raw_children
            if isinstance(raw_children, list)
            and isinstance(child, Mapping)
            and str(child.get("structure_layer") or "").upper() == "DAILY"
        ] if isinstance(raw_children, list) else []
        children = [_daily_child(canonical_id, child) for child in direct_daily]
        children.sort(key=lambda child: (
            child.get("daily_created_time") or "9999",
            child.get("daily_start_time") or "9999",
            child["daily_range_id"],
        ))
        payload["daily_children"] = children
        payload["daily_ranges_mapped_total"] = len(children)
        payload["invalid_parent_links"] = [
            child["daily_range_id"] for child in children if not child["parent_link_valid"]
        ]

        at_freeze = [
            child for child in children
            if (created := _time(child.get("daily_created_time"))) is not None
            and created <= freeze
        ]
        future = len(children) - len(at_freeze)
        payload["daily_ranges_found"] = len(at_freeze)
        payload["future_daily_ranges_excluded"] = future
        if at_freeze:
            earliest = min(at_freeze, key=lambda child: (
                child.get("daily_created_time") or "9999", child["daily_range_id"]
            ))
            latest = max(at_freeze, key=lambda child: (
                child.get("daily_created_time") or "", child["daily_range_id"]
            ))
            payload.update({
                "earliest_daily_range": earliest["daily_range_id"],
                "earliest_daily_range_time": earliest.get("daily_created_time"),
                "latest_daily_range": latest["daily_range_id"],
                "latest_daily_range_time": latest.get("daily_created_time"),
            })

        front, middle, tail, overlap_count = _coverage_gaps(
            window_start=weekly_start,
            window_end=freeze,
            children=children,
        )
        payload["front_gap"] = front
        payload["middle_gaps"] = middle
        payload["tail_gap"] = tail
        payload["overlap_count"] = overlap_count

        if payload["invalid_parent_links"]:
            coverage_status = "INVALID_PARENT_LINK"
            processing_status = "NEEDS_REVIEW"
            reasons = ["ONE_OR_MORE_DAILY_PARENT_LINKS_INVALID"]
        elif not payload["daily_mapping_coverage_available"]:
            coverage_status = "NOT_MAPPED"
            processing_status = "COMPLETE"
            reasons = ["DAILY_NOT_MAPPED_AT_WEEKLY_FREEZE"]
        elif not at_freeze:
            coverage_status = "MAPPING_GAP"
            processing_status = "COMPLETE"
            reasons = ["DAILY_MAPPING_AVAILABLE_BUT_NO_LINKED_DAILY_AT_FREEZE"]
        elif middle:
            coverage_status = "MAPPING_GAP"
            processing_status = "COMPLETE"
            reasons = ["MIDDLE_DAILY_MAPPING_GAP_DETECTED"]
        elif front or tail:
            coverage_status = "PARTIAL"
            processing_status = "COMPLETE"
            reasons = ["DAILY_MAPPING_PARTIAL_AT_FREEZE"]
        else:
            coverage_status = "COMPLETE"
            processing_status = "COMPLETE"
            reasons = ["DAILY_MAPPING_COVERAGE_COMPLETE_AT_FREEZE"]

        payload["coverage_status"] = coverage_status
        payload["reason_codes"] = reasons
        outputs.append(_output(node, processing_status, payload))

    return {"outputs": outputs}
