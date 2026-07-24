"""Audit whether Daily mapping existed for each Weekly candidate story.

Completed Weekly stories freeze at their approved Weekly BOS. An open Weekly range
without a BOS is still analytically useful, so it freezes at the latest available
D1 candle, with W1 as a fallback, and is labelled IN_PROGRESS.

This package answers a coverage question only. It does not infer Daily trade
direction, rebuild parent links, or treat spaces and overlaps between structural
ranges as missing mapping.

Coverage is based on the mapped Daily history era:

NOT_MAPPED
    The Weekly freeze occurred before the first mapped Daily anchor.

PARTIAL
    The Weekly story began before Daily mapping started but ended after it
    started.

COMPLETE
    The full Weekly story occurred inside mapped Daily history and at least one
    valid linked Daily child existed by the freeze.

MAPPING_GAP
    Daily mapping already existed for the full Weekly story, but no valid linked
    Daily child existed by the freeze.

INVALID_PARENT_LINK
    Saved hierarchy evidence contains an invalid Daily parent link.

The canonical Master Map remains structural truth. Python reports bad links and
never repairs or replaces them.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Mapping

FXTM_DOCTRINE_CONTRACT = "fxtm_doctrine_package_v1"
SCRIPT_KEY = "daily_mapping_coverage_audit"
VERSION_LABEL = "3"
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


def _date(value: datetime | None) -> str:
    return value.date().isoformat() if value else "Pending"


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


def _output(
    node: Mapping[str, Any],
    status: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "canonical_range_id": str(node.get("id") or ""),
        "processing_status": status,
        "payload": payload,
    }


def _matches_case(node: Mapping[str, Any], case_ref: str) -> bool:
    if not case_ref:
        return True
    refs = node.get("source_refs")
    if not isinstance(refs, list):
        return True
    return any(
        isinstance(ref, Mapping) and str(ref.get("case_ref") or "") == case_ref
        for ref in refs
    )


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


def _mapping_start(node: Mapping[str, Any]) -> datetime | None:
    return _range_start(node) or _range_created(node)


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


def _latest_market_snapshot(context: Any) -> tuple[datetime | None, str | None]:
    reader = getattr(context, "latest_candle_time", None)
    if not callable(reader):
        return None, None

    for timeframe, basis in (
        ("D1", "LATEST_D1_CANDLE"),
        ("W1", "LATEST_W1_CANDLE"),
    ):
        try:
            latest = _time(reader(timeframe))
        except Exception:
            latest = None
        if latest is not None:
            return latest, basis
    return None, None


def _weekly_freeze(
    context: Any,
    node: Mapping[str, Any],
) -> tuple[datetime | None, str | None, str | None, str]:
    canonical_id = str(node.get("id") or "")
    structure, processing = _memory_entry(context, canonical_id, "weekly_structure")
    if structure is not None:
        bos_time = _time(structure.get("bos_time"))
        if processing == "NEEDS_REVIEW":
            return bos_time, "WEEKLY_BOS", "WEEKLY_STRUCTURE_NEEDS_REVIEW", "COMPLETED"
        if bos_time is not None and processing in {"", "COMPLETE"}:
            return bos_time, "WEEKLY_BOS", None, "COMPLETED"

    legacy_bos = _time(node.get("script1_bos_time"))
    if legacy_bos is not None:
        return legacy_bos, "WEEKLY_BOS", None, "COMPLETED"

    inactive = _time(node.get("inactive_from_time"))
    if inactive is not None:
        return inactive, "WEEKLY_INACTIVE_TIME", None, "COMPLETED"

    latest, basis = _latest_market_snapshot(context)
    if latest is not None:
        return latest, basis, None, "IN_PROGRESS"

    return (
        None,
        None,
        "ACTIVE_WEEKLY_SNAPSHOT_TIME_UNAVAILABLE",
        "IN_PROGRESS",
    )


def _base_payload(canonical_id: str) -> dict[str, Any]:
    # Primitive top-level values are intentionally trader-readable because the
    # Electron candidate card displays them directly. Technical evidence lives
    # inside audit_details instead of producing a database-shaped wall of text.
    return {
        "weekly_story": "Pending",
        "weekly_story_state": "Pending",
        "freeze_basis": "Pending",
        "candidate_freeze_time": None,
        "coverage_status": "PENDING",
        "daily_mapping_status": "Pending",
        "daily_ranges_found": 0,
        "first_daily_child": "Pending",
        "last_daily_child_at_freeze": "Pending",
        "future_daily_ranges_excluded": 0,
        "parent_link_summary": "Pending",
        "daily_children": [],
        "audit_details": {
            "weekly_candidate_id": canonical_id,
            "weekly_range_id": canonical_id,
            "candidate_freeze_basis": None,
            "daily_mapping_coverage_available": False,
            "daily_mapping_first_available_time": None,
            "daily_ranges_mapped_total": 0,
            "earliest_daily_range": None,
            "earliest_daily_range_time": None,
            "latest_daily_range": None,
            "latest_daily_range_time": None,
            "coverage_window_start": None,
            "coverage_window_end": None,
            "mapping_unavailable_window": None,
            "invalid_parent_links": [],
        },
        "reason_codes": [],
    }


def run(context: Any) -> dict[str, list[dict[str, Any]]]:
    weekly_nodes = [dict(node) for node in context.selected_ranges(layer="WEEKLY")]
    all_daily_nodes = [dict(node) for node in context.selected_ranges(layer="DAILY")]

    review_weekly_by_id: dict[str, dict[str, Any]] = {}
    review_reader = getattr(context, "review_ranges", None)
    if callable(review_reader):
        for review_node in review_reader(layer="WEEKLY"):
            review_row = dict(review_node)
            review_weekly_by_id[str(review_row.get("id") or "")] = review_row

    mapped_starts = sorted(
        start
        for node in all_daily_nodes
        if (start := _mapping_start(node)) is not None
    )
    first_daily_mapping = mapped_starts[0] if mapped_starts else None

    outputs: list[dict[str, Any]] = []
    for node in weekly_nodes:
        canonical_id = str(node.get("id") or "")
        payload = _base_payload(canonical_id)
        audit = payload["audit_details"]

        freeze, freeze_basis, freeze_error, story_state = _weekly_freeze(context, node)
        payload["candidate_freeze_time"] = _stamp(freeze)
        payload["weekly_story_state"] = story_state
        payload["freeze_basis"] = freeze_basis or "Pending"
        audit["candidate_freeze_basis"] = freeze_basis
        audit["daily_mapping_first_available_time"] = _stamp(first_daily_mapping)

        if freeze_error == "WEEKLY_STRUCTURE_NEEDS_REVIEW":
            payload["reason_codes"] = [freeze_error]
            outputs.append(_output(node, "NEEDS_REVIEW", payload))
            continue
        if freeze is None:
            payload["reason_codes"] = [
                freeze_error or "WEEKLY_CANDIDATE_FREEZE_TIME_UNAVAILABLE"
            ]
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

        story_suffix = " (IN PROGRESS)" if story_state == "IN_PROGRESS" else ""
        payload["weekly_story"] = (
            f"{_date(weekly_start)} -> {_date(freeze)}{story_suffix}"
        )
        audit["coverage_window_start"] = _stamp(weekly_start)
        audit["coverage_window_end"] = _stamp(freeze)

        mapping_available_at_freeze = (
            first_daily_mapping is not None and freeze >= first_daily_mapping
        )
        audit["daily_mapping_coverage_available"] = mapping_available_at_freeze
        payload["daily_mapping_status"] = (
            f"Available since {_date(first_daily_mapping)}"
            if mapping_available_at_freeze
            else "Not mapped at this Weekly freeze"
        )

        raw_children = node.get("children")
        case_ref = str(getattr(context, "case_ref", "") or "")
        direct_daily = [
            dict(child)
            for child in raw_children
            if isinstance(raw_children, list)
            and isinstance(child, Mapping)
            and str(child.get("structure_layer") or "").upper() == "DAILY"
            and _matches_case(child, case_ref)
        ] if isinstance(raw_children, list) else []

        # Review-root children are evidence only. They may expose a bad saved link,
        # but are never promoted into trusted hierarchy truth.
        review_parent = review_weekly_by_id.get(canonical_id) or {}
        review_children = review_parent.get("children")
        if isinstance(review_children, list):
            direct_daily.extend(
                dict(child)
                for child in review_children
                if isinstance(child, Mapping)
                and str(child.get("structure_layer") or "").upper() == "DAILY"
                and _matches_case(child, case_ref)
                and str(child.get("direct_parent_link_status") or "").upper()
                not in _VALID_PARENT_LINKS
            )

        deduplicated: dict[str, dict[str, Any]] = {}
        for child in direct_daily:
            child_id = str(child.get("id") or "")
            if not child_id:
                continue
            existing = deduplicated.get(child_id)
            child_valid = (
                str(child.get("direct_parent_link_status") or "").upper()
                in _VALID_PARENT_LINKS
            )
            existing_valid = existing is not None and (
                str(existing.get("direct_parent_link_status") or "").upper()
                in _VALID_PARENT_LINKS
            )
            if existing is None or (child_valid and not existing_valid):
                deduplicated[child_id] = child

        children = [
            _daily_child(canonical_id, child)
            for child in deduplicated.values()
        ]
        children.sort(key=lambda child: (
            child.get("daily_created_time") or "9999",
            child.get("daily_start_time") or "9999",
            child["daily_range_id"],
        ))
        payload["daily_children"] = children
        audit["daily_ranges_mapped_total"] = len(children)

        invalid_parent_links = [
            child["daily_range_id"]
            for child in children
            if not child["parent_link_valid"]
        ]
        audit["invalid_parent_links"] = invalid_parent_links
        payload["parent_link_summary"] = (
            f"INVALID: {len(invalid_parent_links)}"
            if invalid_parent_links
            else "Valid"
        )

        at_freeze = [
            child
            for child in children
            if child["parent_link_valid"]
            and (created := _time(child.get("daily_created_time"))) is not None
            and created <= freeze
        ]
        future = sum(
            (created := _time(child.get("daily_created_time"))) is not None
            and created > freeze
            for child in children
        )
        payload["daily_ranges_found"] = len(at_freeze)
        payload["future_daily_ranges_excluded"] = future

        if at_freeze:
            earliest = min(at_freeze, key=lambda child: (
                child.get("daily_created_time") or "9999",
                child["daily_range_id"],
            ))
            latest = max(at_freeze, key=lambda child: (
                child.get("daily_created_time") or "",
                child["daily_range_id"],
            ))
            audit.update({
                "earliest_daily_range": earliest["daily_range_id"],
                "earliest_daily_range_time": earliest.get("daily_created_time"),
                "latest_daily_range": latest["daily_range_id"],
                "latest_daily_range_time": latest.get("daily_created_time"),
            })
            payload["first_daily_child"] = _date(
                _time(earliest.get("daily_created_time"))
            )
            payload["last_daily_child_at_freeze"] = _date(
                _time(latest.get("daily_created_time"))
            )

        if invalid_parent_links:
            coverage_status = "INVALID_PARENT_LINK"
            processing_status = "NEEDS_REVIEW"
            reasons = ["ONE_OR_MORE_DAILY_PARENT_LINKS_INVALID"]
        elif first_daily_mapping is None or freeze < first_daily_mapping:
            coverage_status = "NOT_MAPPED"
            processing_status = "COMPLETE"
            reasons = ["DAILY_NOT_MAPPED_AT_WEEKLY_FREEZE"]
        elif weekly_start < first_daily_mapping:
            coverage_status = "PARTIAL"
            processing_status = "COMPLETE"
            audit["mapping_unavailable_window"] = {
                "start_time": _stamp(weekly_start),
                "end_time": _stamp(first_daily_mapping),
            }
            reasons = ["WEEKLY_STORY_BEGAN_BEFORE_DAILY_MAPPING"]
        elif not at_freeze:
            coverage_status = "MAPPING_GAP"
            processing_status = "COMPLETE"
            reasons = ["DAILY_MAPPING_AVAILABLE_BUT_NO_LINKED_DAILY_AT_FREEZE"]
        else:
            coverage_status = "COMPLETE"
            processing_status = "COMPLETE"
            reasons = [
                "IN_PROGRESS_WEEKLY_STORY_FULLY_INSIDE_DAILY_MAPPING_ERA"
                if story_state == "IN_PROGRESS"
                else "WEEKLY_STORY_FULLY_INSIDE_DAILY_MAPPING_ERA"
            ]

        payload["coverage_status"] = coverage_status
        payload["reason_codes"] = reasons
        outputs.append(_output(node, processing_status, payload))

    return {"outputs": outputs}
