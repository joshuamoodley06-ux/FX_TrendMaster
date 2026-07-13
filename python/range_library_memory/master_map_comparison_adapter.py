"""Conservative adapter from the XAUUSD Master Map to comparison states.

The adapter reads only canonical Master Map output. It never mutates raw mapping
records or Master Map lifecycle/identity. It emits a state only from a trusted,
statistics-eligible range/event path and freezes every state at a factual chart
time. Fields not present in the Master Map contract remain explicit
``UNKNOWN``/``NOT_AVAILABLE`` and block comparison until supplied through a
separate, cited doctrine annotation.
"""
from __future__ import annotations

import argparse
import copy
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from .structural_comparison import (
    ALLOWED,
    CLOSE_TIER,
    MATCH_TIERS,
    MODEL_FAMILY_TIER,
    STATE_SCHEMA_VERSION,
    STRONG_TIER,
    canonical_time,
    compare_structural_state,
    parse_time,
    token,
)

MASTER_MAP_SCHEMA_VERSION = "xauusd_master_map_v0.1"
ADAPTER_SCHEMA_VERSION = "xauusd_master_map_comparison_adapter_v0.1"
REPORT_SCHEMA_VERSION = "xauusd_master_map_real_comparison_report_v0.1"
READY = "READY"
EXCLUDED = "EXCLUDED"
TRUSTED = "TRUSTED"
ELIGIBLE = "ELIGIBLE"
VALID = "VALID"
ROOT = "ROOT"
UNKNOWN = "UNKNOWN"
NOT_AVAILABLE = "NOT_AVAILABLE"

DOCTRINE_FIELDS = (
    "parent_direction",
    "parent_origin",
    "child_relationship",
)
OPTIONAL_DOCTRINE_FIELDS = (
    "reclaim_state",
    "retest_state",
    "ltf_confirmation_state",
)
SUPPORTED_FREEZE_EVENTS = {"BOS_UP", "BOS_DOWN"}


class MasterMapAdapterError(ValueError):
    """Unsafe or invalid Master Map adapter input."""


def adapt_master_map(
    master_map: Mapping[str, Any],
    *,
    doctrine_annotations: Mapping[str, Mapping[str, Any]] | None = None,
    outcomes: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Adapt trusted Master Map BOS snapshots into frozen comparison candidates."""
    source = _validate_master_map(master_map)
    annotations = doctrine_annotations or {}
    outcome_map = outcomes or {}

    full_ranges, full_events = _flatten_root(master_map["root"])
    trusted_ranges, trusted_events = _flatten_root(master_map["trusted_root"])
    full_range_by_id = {item["id"]: item for item in full_ranges}
    trusted_range_by_id = {item["id"]: item for item in trusted_ranges}

    parent_by_child: dict[str, str] = {}
    for parent in full_ranges:
        for child in parent.get("children", []):
            parent_by_child[str(child.get("id"))] = str(parent["id"])

    trusted_range_ids = {str(item["id"]) for item in trusted_ranges}
    trusted_event_ids = {str(event["id"]) for event in trusted_events}
    exclusions: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []

    for range_node in full_ranges:
        if str(range_node.get("id") or "") in trusted_range_ids:
            continue
        reasons = _trust_exclusion_reasons(range_node, entity_kind="RANGE")
        if not reasons:
            reasons = ["NOT_PRESENT_IN_TRUSTED_ROOT"]
        exclusions.append(_exclusion("RANGE", range_node, range_node, reasons))

    for event in full_events:
        event_id = str(event.get("id") or "")
        range_id = str(event.get("canonical_range_id") or "")
        if not range_id:
            range_id = _find_event_owner(full_ranges, event_id) or ""
        range_node = full_range_by_id.get(range_id)
        reasons = _trust_exclusion_reasons(event, entity_kind="EVENT")
        if event_id not in trusted_event_ids:
            if not reasons:
                reasons.append("NOT_PRESENT_IN_TRUSTED_ROOT")
            exclusions.append(_exclusion("EVENT", event, range_node, reasons))
            continue
        if token(event.get("event_type")) not in SUPPORTED_FREEZE_EVENTS:
            exclusions.append(_exclusion(
                "EVENT", event, range_node, ["UNSUPPORTED_FREEZE_EVENT_TYPE"]
            ))
            continue
        if range_node is None:
            exclusions.append(_exclusion("EVENT", event, None, ["MISSING_CANONICAL_RANGE"]))
            continue

        parent_id = parent_by_child.get(range_id)
        parent = trusted_range_by_id.get(parent_id or "")
        range_reasons = _trust_exclusion_reasons(range_node, entity_kind="RANGE")
        if range_reasons:
            exclusions.append(_exclusion("EVENT", event, range_node, range_reasons))
            continue
        if not parent_id:
            exclusions.append(_exclusion("EVENT", event, range_node, ["ROOT_RANGE_HAS_NO_PARENT"]))
            continue
        if parent is None:
            exclusions.append(_exclusion(
                "EVENT", event, range_node, ["UNRESOLVED_PARENT_RELATIONSHIP"]
            ))
            continue
        if token(range_node.get("direct_parent_link_status")) != VALID:
            exclusions.append(_exclusion(
                "EVENT", event, range_node, ["UNRESOLVED_PARENT_RELATIONSHIP"]
            ))
            continue

        candidates.append(_build_candidate(
            source=source,
            event=event,
            range_node=range_node,
            parent=parent,
            all_range_events=_events_for_range(trusted_ranges, range_id),
            annotation=annotations.get(event_id) or annotations.get(range_id),
            outcome=outcome_map.get(event_id) or outcome_map.get(range_id),
        ))

    candidates.sort(key=lambda row: (
        parse_time(row["state"]["as_of_time"]), row["state"]["state_id"]
    ))
    exclusions.sort(key=lambda row: (
        row.get("entity_kind", ""), row.get("canonical_id", ""),
        tuple(row.get("reason_codes", [])),
    ))

    reason_counts = Counter(
        reason for item in exclusions for reason in item.get("reason_codes", [])
    )
    for item in candidates:
        if item["comparison_status"] == EXCLUDED:
            for reason in item["exclusion_reasons"]:
                reason_counts[reason] += 1

    ready = [item for item in candidates if item["comparison_status"] == READY]
    blocked = [item for item in candidates if item["comparison_status"] == EXCLUDED]
    stats = dict(master_map.get("statistics") or {})
    canonical_range_count = _non_negative_int(
        stats.get("canonical_ranges_before_review_exclusion")
    )
    canonical_event_count = _non_negative_int(
        stats.get("canonical_events_before_review_exclusion")
    )
    unmaterialized_ranges = max(0, canonical_range_count - len(full_ranges))
    unmaterialized_events = max(0, canonical_event_count - len(full_events))
    if unmaterialized_ranges:
        exclusions.append(_aggregate_exclusion(
            "RANGE", unmaterialized_ranges, "MASTER_MAP_RECORD_NOT_MATERIALIZED_IN_ROOT"
        ))
        reason_counts["MASTER_MAP_RECORD_NOT_MATERIALIZED_IN_ROOT"] += unmaterialized_ranges
    if unmaterialized_events:
        exclusions.append(_aggregate_exclusion(
            "EVENT", unmaterialized_events, "MASTER_MAP_RECORD_NOT_MATERIALIZED_IN_ROOT"
        ))
        reason_counts["MASTER_MAP_RECORD_NOT_MATERIALIZED_IN_ROOT"] += unmaterialized_events
    exclusions.sort(key=lambda row: (
        row.get("entity_kind", ""), row.get("canonical_id") or "",
        tuple(row.get("reason_codes", [])),
    ))
    excluded_record_count = sum(int(item.get("record_count", 1)) for item in exclusions)

    return {
        "schema_version": ADAPTER_SCHEMA_VERSION,
        "state_schema_version": STATE_SCHEMA_VERSION,
        "source_master_map": source,
        "contract": {
            "source_root": "trusted_root",
            "statistics_gate": {
                "navigation_status": TRUSTED,
                "statistics_status": ELIGIBLE,
                "direct_parent_link_status": VALID,
            },
            "freeze_rule": "one state per trusted BOS event, including only direct range events at or before that event time",
            "outcome_rule": "outcomes are separate optional factual inputs and never qualify or score a match",
            "missing_field_rule": "UNKNOWN/NOT_AVAILABLE is preserved and blocks scoring",
        },
        "filtering": {
            "canonical_ranges_reported_by_master_map": canonical_range_count,
            "canonical_events_reported_by_master_map": canonical_event_count,
            "range_records_materialized_from_root": len(full_ranges),
            "event_records_materialized_from_root": len(full_events),
            "range_records_not_materialized_from_root": unmaterialized_ranges,
            "event_records_not_materialized_from_root": unmaterialized_events,
            "records_considered": canonical_range_count + canonical_event_count,
            "trusted_range_records_used": len(trusted_ranges),
            "trusted_event_records_used": len(trusted_events),
            "comparison_candidates_built": len(candidates),
            "comparison_ready_states": len(ready),
            "comparison_blocked_states": len(blocked),
            "excluded_records": excluded_record_count,
            "exclusion_entries": len(exclusions),
            "excluded_by_reason": dict(sorted(reason_counts.items())),
        },
        "states": candidates,
        "record_exclusions": exclusions,
        "doctrine_fields_still_required": [
            {
                "field": "parent_direction",
                "status": NOT_AVAILABLE,
                "reason": "Master Map lifecycle direction is not automatically the parent-direction state intended by the comparison contract.",
            },
            {
                "field": "parent_origin",
                "status": NOT_AVAILABLE,
                "reason": "Master Map v0.1 carries factual ranges/events but no approved parent-origin vocabulary.",
            },
            {
                "field": "child_relationship",
                "status": NOT_AVAILABLE,
                "reason": "PROTREND/COUNTERTREND/TRANSITION assignment is strategy doctrine, not a Master Map identity fact.",
            },
            {
                "field": "reclaim_state",
                "status": NOT_AVAILABLE,
                "reason": "Master Map events do not guarantee wick/close reclaim semantics required by the comparison contract.",
            },
            {
                "field": "retest_state",
                "status": NOT_AVAILABLE,
                "reason": "HELD/FAILED retest definitions remain unapproved doctrine.",
            },
            {
                "field": "ltf_confirmation_state",
                "status": NOT_AVAILABLE,
                "reason": "Lower-timeframe confirmation rules remain unapproved doctrine.",
            },
            {
                "field": "outcome",
                "status": NOT_AVAILABLE,
                "reason": "Continuation/failure/alternative destination rules are not part of Master Map v0.1.",
            },
        ],
    }


def build_real_comparison_report(
    adapted: Mapping[str, Any],
    *,
    target_state_id: str | None = None,
    requested_tiers: Sequence[str] = MATCH_TIERS,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    """Build a disposable report from comparison-ready adapted states only."""
    ready = [
        copy.deepcopy(item) for item in adapted.get("states", [])
        if item.get("comparison_status") == READY
    ]
    ready.sort(key=lambda row: (
        parse_time(row["state"]["as_of_time"]), row["state"]["state_id"]
    ))
    target = None
    if target_state_id:
        target = next((item for item in ready if item["state"]["state_id"] == target_state_id), None)
        if target is None:
            raise MasterMapAdapterError(
                f"target state is not comparison-ready or does not exist: {target_state_id}"
            )
    elif ready:
        target = ready[-1]

    empty_tier = {
        "sample_size": 0,
        "frequency": {
            key: {"count": 0, "percent": 0.0}
            for key in ("ALTERNATIVE", "CONTINUATION", "FAILURE", "NOT_AVAILABLE")
        },
        "next_structural_destination": {},
        "time_to_destination": {},
        "linked_historical_examples": [],
    }
    if target is None:
        comparison = {
            "schema_version": "xauusd_comparison_report_v0.1",
            "query": None,
            "filtering": {
                "historical_records_seen": 0,
                "trusted_records_used": 0,
                "excluded_needs_review": 0,
                "excluded_excluded": 0,
                "excluded_untrusted": 0,
            },
            "tiers": {
                STRONG_TIER: copy.deepcopy(empty_tier),
                CLOSE_TIER: copy.deepcopy(empty_tier),
                MODEL_FAMILY_TIER: copy.deepcopy(empty_tier),
            },
            "overall": copy.deepcopy(empty_tier),
            "status": "NO_COMPARISON_READY_STATES",
        }
    else:
        freeze = parse_time(target["state"]["as_of_time"])
        historical = []
        for item in ready:
            state = item["state"]
            if state["state_id"] == target["state"]["state_id"]:
                continue
            if parse_time(state["as_of_time"]) >= freeze:
                continue
            historical.append({
                "example_id": state["state_id"],
                "snapshot": state,
                "outcome": item["outcome"],
                "source_refs": item["provenance"]["source_refs"],
                "example_ref": {
                    "example_id": state["state_id"],
                    "canonical_range_id": item["provenance"]["canonical_range_id"],
                    "parent_canonical_range_id": item["provenance"]["parent_canonical_range_id"],
                    "canonical_event_ids": item["provenance"]["canonical_event_ids"],
                    "source_refs": item["provenance"]["source_refs"],
                    "source_timeframe": item["provenance"]["source_timeframe"],
                    "chart_times": item["provenance"]["chart_times"],
                    "snapshot_as_of": state["as_of_time"],
                    "structural_content_hash": item["provenance"]["structural_content_hash"],
                    "link": f"master-map://XAUUSD/{item['provenance']['canonical_range_id']}?event={item['provenance']['freeze_event_id']}",
                },
            })
        comparison = compare_structural_state(
            target["state"], historical, requested_tiers=requested_tiers
        )
        comparison["status"] = "COMPLETE"

    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at_utc": canonical_time(generated_at_utc) if generated_at_utc else _utc_now(),
        "source_master_map": copy.deepcopy(adapted["source_master_map"]),
        "adapter_contract": copy.deepcopy(adapted["contract"]),
        "records": copy.deepcopy(adapted["filtering"]),
        "target_state_id": target["state"]["state_id"] if target else None,
        "comparison": comparison,
        "record_exclusions": copy.deepcopy(adapted.get("record_exclusions", [])),
        "blocked_states": [
            copy.deepcopy(item) for item in adapted.get("states", [])
            if item.get("comparison_status") == EXCLUDED
        ],
        "doctrine_fields_still_required": copy.deepcopy(
            adapted.get("doctrine_fields_still_required", [])
        ),
    }


def run_master_map_comparison(
    master_map: Mapping[str, Any],
    *,
    doctrine_annotations: Mapping[str, Mapping[str, Any]] | None = None,
    outcomes: Mapping[str, Mapping[str, Any]] | None = None,
    target_state_id: str | None = None,
    requested_tiers: Sequence[str] = MATCH_TIERS,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    adapted = adapt_master_map(
        master_map,
        doctrine_annotations=doctrine_annotations,
        outcomes=outcomes,
    )
    return build_real_comparison_report(
        adapted,
        target_state_id=target_state_id,
        requested_tiers=requested_tiers,
        generated_at_utc=generated_at_utc,
    )


def _build_candidate(
    *,
    source: Mapping[str, Any],
    event: Mapping[str, Any],
    range_node: Mapping[str, Any],
    parent: Mapping[str, Any],
    all_range_events: Sequence[Mapping[str, Any]],
    annotation: Mapping[str, Any] | None,
    outcome: Mapping[str, Any] | None,
) -> dict[str, Any]:
    freeze = canonical_time(event.get("event_time_utc"))
    freeze_dt = parse_time(freeze)
    frozen_events = [
        item for item in all_range_events
        if item.get("event_time_utc") and parse_time(item["event_time_utc"]) <= freeze_dt
    ]
    frozen_events.sort(key=lambda item: (
        parse_time(item["event_time_utc"]), str(item.get("id") or "")
    ))
    state_id = f"{event['id']}@{freeze}"
    state = {
        "schema_version": STATE_SCHEMA_VERSION,
        "state_id": state_id,
        "symbol": "XAUUSD",
        "as_of_time": freeze,
        "trust_status": TRUSTED,
        "review_status": "CLEAR",
        "resolution_status": "RESOLVED",
        "parent_link_status": VALID,
        "parent_direction": NOT_AVAILABLE,
        "parent_origin": NOT_AVAILABLE,
        "parent_range": {
            "low": parent.get("range_low"),
            "high": parent.get("range_high"),
        },
        "current_price": _event_price(event),
        "child_relationship": NOT_AVAILABLE,
        "bos_state": "UP" if token(event.get("event_type")) == "BOS_UP" else "DOWN",
        "reclaim_state": _event_state(
            frozen_events, "RECLAIM_", {
                "RECLAIM_PENDING": "PENDING",
                "RECLAIM_WICK": "WICK",
                "RECLAIM_CLOSE": "CLOSE",
                "RECLAIM_WICK_AND_CLOSE": "WICK_AND_CLOSE",
            }
        ),
        "retest_state": _event_state(
            frozen_events, "RETEST_", {
                "RETEST_PENDING": "PENDING",
                "RETEST_TOUCHED": "TOUCHED",
                "RETEST_HELD": "HELD",
                "RETEST_FAILED": "FAILED",
            }
        ),
        "ltf_confirmation_state": _event_state(
            frozen_events, "LTF_", {
                "LTF_PENDING": "PENDING",
                "LTF_CONFIRMED_UP": "CONFIRMED_UP",
                "LTF_CONFIRMED_DOWN": "CONFIRMED_DOWN",
                "LTF_FAILED": "FAILED",
            }
        ),
        "event_sequence": [token(item.get("event_type")) for item in frozen_events],
    }
    annotation_provenance = None
    if annotation is not None:
        state, annotation_provenance = _apply_annotation(state, annotation)

    missing = _readiness_reasons(state)
    provenance = {
        "master_map_schema_version": source["schema_version"],
        "structural_content_hash": source["structural_content_hash"],
        "canonical_range_id": str(range_node["id"]),
        "parent_canonical_range_id": str(parent["id"]),
        "freeze_event_id": str(event["id"]),
        "canonical_event_ids": [str(item["id"]) for item in frozen_events],
        "source_timeframe": range_node.get("source_timeframe"),
        "structure_layer": range_node.get("structure_layer"),
        "chart_times": {
            "frozen_state_time": freeze,
            "range_high_time": range_node.get("range_high_time"),
            "range_low_time": range_node.get("range_low_time"),
            "active_from_time": range_node.get("active_from_time"),
            "inactive_from_time": range_node.get("inactive_from_time"),
            "event_times": [item.get("event_time_utc") for item in frozen_events],
        },
        "parent_relationship": {
            "status": range_node.get("direct_parent_link_status"),
            "parent_canonical_range_id": str(parent["id"]),
        },
        "source_refs": {
            "range": copy.deepcopy(range_node.get("source_refs") or []),
            "parent_range": copy.deepcopy(parent.get("source_refs") or []),
            "events": [
                {
                    "canonical_event_id": str(item["id"]),
                    "source_refs": copy.deepcopy(item.get("source_refs") or []),
                }
                for item in frozen_events
            ],
        },
        "doctrine_annotation": annotation_provenance,
    }
    return {
        "comparison_status": READY if not missing else EXCLUDED,
        "exclusion_reasons": missing,
        "state": state,
        "outcome": _normalize_adapter_outcome(outcome, freeze_at=freeze),
        "provenance": provenance,
    }


def _validate_master_map(master_map: Mapping[str, Any]) -> dict[str, Any]:
    if master_map.get("schema_version") != MASTER_MAP_SCHEMA_VERSION:
        raise MasterMapAdapterError(
            f"Master Map schema must be {MASTER_MAP_SCHEMA_VERSION}"
        )
    if token(master_map.get("symbol")) != "XAUUSD":
        raise MasterMapAdapterError("Master Map symbol must be XAUUSD")
    structural_hash = str(master_map.get("structural_content_hash") or "").strip()
    if not structural_hash:
        raise MasterMapAdapterError("Master Map structural_content_hash is required")
    for key in ("root", "trusted_root"):
        if not isinstance(master_map.get(key), Mapping):
            raise MasterMapAdapterError(f"Master Map {key} is required")
    return {
        "schema_version": MASTER_MAP_SCHEMA_VERSION,
        "symbol": "XAUUSD",
        "built_at_utc": master_map.get("built_at_utc"),
        "structural_content_hash": structural_hash,
    }


def _flatten_root(root: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ranges: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []

    def visit(node: Mapping[str, Any], parent_id: str | None = None) -> None:
        if token(node.get("node_type")) == "RANGE":
            item = copy.deepcopy(dict(node))
            item["parent_canonical_range_id"] = parent_id
            item["children"] = [copy.deepcopy(dict(child)) for child in node.get("children", [])]
            ranges.append(item)
            for event in node.get("events", []):
                event_item = copy.deepcopy(dict(event))
                event_item["canonical_range_id"] = str(node["id"])
                events.append(event_item)
            parent_id = str(node["id"])
        for child in node.get("children", []):
            visit(child, parent_id)
        for child in node.get("unlinked_review_children", []):
            visit(child, None)

    visit(root)
    return ranges, events


def _events_for_range(ranges: Sequence[Mapping[str, Any]], range_id: str) -> list[dict[str, Any]]:
    node = next((item for item in ranges if str(item.get("id")) == range_id), None)
    return [copy.deepcopy(dict(item)) for item in (node or {}).get("events", [])]


def _find_event_owner(ranges: Sequence[Mapping[str, Any]], event_id: str) -> str | None:
    for item in ranges:
        if any(str(event.get("id")) == event_id for event in item.get("events", [])):
            return str(item["id"])
    return None


def _trust_exclusion_reasons(node: Mapping[str, Any], *, entity_kind: str) -> list[str]:
    reasons: list[str] = []
    nav = token(node.get("navigation_status"))
    stats = token(node.get("statistics_status"))
    parent = token(node.get("direct_parent_link_status"))
    if nav == "REVIEW":
        reasons.append("REVIEW")
    elif nav not in {TRUSTED, ""}:
        reasons.append(nav or "UNKNOWN_NAVIGATION_STATUS")
    if stats == EXCLUDED:
        reasons.append("STATISTICS_EXCLUDED")
    elif stats not in {ELIGIBLE, ""}:
        reasons.append(stats or "UNKNOWN_STATISTICS_STATUS")
    if entity_kind == "RANGE" and parent not in {VALID, ROOT, ""}:
        reasons.append("UNRESOLVED_PARENT_RELATIONSHIP")
    if "NEEDS_REVIEW" in {
        token(node.get("ancestor_review_status")),
        token(node.get("direct_parent_link_status")),
    } or "NEEDS_REVIEW" in token(node.get("ancestor_review_status")):
        reasons.append("NEEDS_REVIEW")
    return list(dict.fromkeys(reasons))


def _exclusion(
    entity_kind: str,
    entity: Mapping[str, Any],
    range_node: Mapping[str, Any] | None,
    reasons: Sequence[str],
) -> dict[str, Any]:
    return {
        "entity_kind": entity_kind,
        "canonical_id": str(entity.get("id") or ""),
        "canonical_range_id": str(range_node.get("id")) if range_node else None,
        "source_timeframe": range_node.get("source_timeframe") if range_node else None,
        "chart_time": entity.get("event_time_utc") if entity_kind == "EVENT" else None,
        "source_refs": copy.deepcopy(entity.get("source_refs") or []),
        "reason_codes": sorted(set(reasons)),
    }


def _event_price(event: Mapping[str, Any]) -> float | None:
    for key in ("price", "break_level"):
        value = event.get(key)
        if value is None:
            continue
        try:
            result = float(value)
        except (TypeError, ValueError):
            continue
        if result == result and result not in {float("inf"), float("-inf")}:
            return result
    return None


def _event_state(
    events: Sequence[Mapping[str, Any]],
    prefix: str,
    mapping: Mapping[str, str],
) -> str:
    matching = [
        token(item.get("event_type")) for item in events
        if token(item.get("event_type")).startswith(prefix)
    ]
    if not matching:
        return NOT_AVAILABLE
    return mapping.get(matching[-1], NOT_AVAILABLE)


def _apply_annotation(
    state: Mapping[str, Any], annotation: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    reference = str(annotation.get("annotation_ref") or "").strip()
    if not reference:
        raise MasterMapAdapterError("doctrine annotation requires annotation_ref")
    result = copy.deepcopy(dict(state))
    allowed_fields = set(DOCTRINE_FIELDS) | set(OPTIONAL_DOCTRINE_FIELDS)
    for key in annotation:
        if key in {"annotation_ref", "notes"}:
            continue
        if key not in allowed_fields:
            raise MasterMapAdapterError(f"unsupported doctrine annotation field: {key}")
        value = token(annotation[key])
        if key == "parent_origin":
            if not value or value in {UNKNOWN, NOT_AVAILABLE}:
                raise MasterMapAdapterError("parent_origin annotation must be explicit")
        else:
            allowed = ALLOWED.get(key)
            if allowed is not None and value not in allowed:
                raise MasterMapAdapterError(
                    f"{key} annotation must be one of {sorted(allowed)}"
                )
        result[key] = value
    return result, {
        "annotation_ref": reference,
        "fields": sorted(key for key in annotation if key in allowed_fields),
        "notes": annotation.get("notes"),
    }


def _readiness_reasons(state: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    current_price = _finite_number(state.get("current_price"))
    if current_price is None:
        reasons.append("MISSING_CURRENT_PRICE")
    parent = state.get("parent_range") or {}
    low = _finite_number(parent.get("low"))
    high = _finite_number(parent.get("high"))
    if low is None or high is None:
        reasons.append("MISSING_PARENT_RANGE_BOUNDS")
    elif high <= low:
        reasons.append("INVALID_PARENT_RANGE_BOUNDS")
    for field in ("parent_direction", "parent_origin", "child_relationship"):
        if token(state.get(field)) in {"", UNKNOWN, NOT_AVAILABLE}:
            reasons.append(f"MISSING_{field.upper()}")
    for field in ("reclaim_state", "retest_state", "ltf_confirmation_state"):
        if token(state.get(field)) in {"", UNKNOWN, NOT_AVAILABLE}:
            reasons.append(f"MISSING_{field.upper()}")
    return reasons


def _normalize_adapter_outcome(
    raw: Mapping[str, Any] | None, *, freeze_at: str
) -> dict[str, Any]:
    if raw is None:
        return {
            "path": NOT_AVAILABLE,
            "destination": NOT_AVAILABLE,
            "reached_at": None,
            "time_to_destination": None,
            "source_refs": [],
        }
    path = token(raw.get("path"))
    if path not in {"CONTINUATION", "FAILURE", "ALTERNATIVE"}:
        raise MasterMapAdapterError(
            "factual outcome path must be CONTINUATION, FAILURE, or ALTERNATIVE"
        )
    destination = token(raw.get("destination"))
    if not destination:
        raise MasterMapAdapterError("factual outcome destination is required")
    reached = canonical_time(raw.get("reached_at")) if raw.get("reached_at") else None
    if reached and parse_time(reached) < parse_time(freeze_at):
        raise MasterMapAdapterError("factual outcome occurs before frozen state")
    time_value = copy.deepcopy(raw.get("time_to_destination"))
    if time_value is not None:
        try:
            bars = int(time_value.get("bars"))
        except (AttributeError, TypeError, ValueError) as exc:
            raise MasterMapAdapterError(
                "time_to_destination requires non-negative bars and timeframe"
            ) from exc
        timeframe = token(time_value.get("timeframe"))
        if bars < 0 or not timeframe:
            raise MasterMapAdapterError(
                "time_to_destination requires non-negative bars and timeframe"
            )
        time_value = {"bars": bars, "timeframe": timeframe}
    return {
        "path": path,
        "destination": destination,
        "reached_at": reached,
        "time_to_destination": time_value,
        "source_refs": copy.deepcopy(raw.get("source_refs") or []),
    }


def _aggregate_exclusion(entity_kind: str, count: int, reason: str) -> dict[str, Any]:
    return {
        "entity_kind": entity_kind,
        "canonical_id": None,
        "canonical_range_id": None,
        "source_timeframe": None,
        "chart_time": None,
        "source_refs": [],
        "record_count": count,
        "reason_codes": [reason],
    }


def _non_negative_int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _finite_number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if result != result or result in {float("inf"), float("-inf")}:
        return None
    return result


def _load_json(path: str | Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Adapt a real XAUUSD Master Map into frozen comparison states"
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--master-map", help="Master Map JSON output")
    source.add_argument("--range-library-db", help="Range Library DB containing master_map_outputs")
    parser.add_argument("--doctrine-annotations")
    parser.add_argument("--outcomes")
    parser.add_argument("--target-state-id")
    parser.add_argument("--tiers", nargs="+", default=list(MATCH_TIERS), choices=list(MATCH_TIERS))
    parser.add_argument("--output", required=True)
    parser.add_argument("--compact", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.master_map:
        master_map = _load_json(args.master_map)
    else:
        from .master_map import load_master_map_output
        master_map = load_master_map_output(args.range_library_db, symbol="XAUUSD")
    assert master_map is not None
    report = run_master_map_comparison(
        master_map,
        doctrine_annotations=_load_json(args.doctrine_annotations),
        outcomes=_load_json(args.outcomes),
        target_state_id=args.target_state_id,
        requested_tiers=args.tiers,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=None if args.compact else 2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "output": str(output),
        "records": report["records"],
        "target_state_id": report["target_state_id"],
        "comparison_status": report["comparison"]["status"],
        "strong_matches": report["comparison"]["tiers"][STRONG_TIER]["sample_size"],
        "close_matches": report["comparison"]["tiers"][CLOSE_TIER]["sample_size"],
        "broader_family_matches": report["comparison"]["tiers"][MODEL_FAMILY_TIER]["sample_size"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
