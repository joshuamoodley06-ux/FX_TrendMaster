"""First-query doctrine enrichment for canonical XAUUSD Master Map output.

This layer is intentionally descriptive. It reads canonical Master Map JSON,
builds immutable frozen research states, and emits a disposable report. It does
not mutate raw mapping rows, Master Map identity, lifecycle, or parent rules.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sqlite3
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping, Sequence

from .inspection import deterministic_json
from .master_map_comparison_adapter import adapt_master_map

REPORT_SCHEMA_VERSION = "xauusd_first_query_doctrine_report_v0.1"
STATE_SCHEMA_VERSION = "xauusd_first_query_state_v0.1"
MASTER_MAP_SCHEMA_VERSION = "xauusd_master_map_v0.1"
SUPPORTED_FREEZE_EVENTS = {"BOS_UP", "BOS_DOWN"}
TECHNICAL_EXCLUSION_REASONS = {
    "MISSING_PARENT_RANGE",
    "MISSING_PARENT_BOUNDS",
    "INVALID_PARENT_BOUNDS",
    "MISSING_FREEZE_PRICE",
    "MISSING_FREEZE_TIME",
}


class DoctrineError(ValueError):
    """Unsafe or invalid first-query doctrine input."""


class StructureLayer(StrEnum):
    MACRO = "MACRO"
    WEEKLY = "WEEKLY"
    DAILY = "DAILY"
    INTRADAY = "INTRADAY"
    MICRO = "MICRO"


class Direction(StrEnum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    UNCONFIRMED = "UNCONFIRMED"


class ChildRelationship(StrEnum):
    PRO_TREND = "PRO_TREND"
    COUNTER_TREND = "COUNTER_TREND"
    TRANSITION = "TRANSITION"


class RangeState(StrEnum):
    RANGE_DEVELOPING = "RANGE_DEVELOPING"
    ACTIVE = "ACTIVE"
    RETEST_IN_PROGRESS = "RETEST_IN_PROGRESS"
    HELD = "HELD"
    RANGE_FAILURE_DETECTED = "RANGE_FAILURE_DETECTED"
    RANGE_FAILURE_CONFIRMED = "RANGE_FAILURE_CONFIRMED"
    RECLASSIFIED_AS_SWEEP = "RECLASSIFIED_AS_SWEEP"


class AnalysisStatus(StrEnum):
    QUERY_READY = "QUERY_READY"
    VALID = "VALID"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    TRADING_RULE_NA = "TRADING_RULE_NA"
    UNKNOWN = "UNKNOWN"
    AMBIGUOUS_SAME_CANDLE = "AMBIGUOUS_SAME_CANDLE"
    EXCLUDED = "EXCLUDED"


class LocationZone(StrEnum):
    EXTREME_DISCOUNT = "EXTREME_DISCOUNT"
    DISCOUNT = "DISCOUNT"
    FAIR_PRICE = "FAIR_PRICE"
    PREMIUM = "PREMIUM"
    EXTREME_PREMIUM = "EXTREME_PREMIUM"


@dataclass(frozen=True)
class EntryCandidate:
    candidate_type: str
    entry_time: str | None
    entry_price: float | None
    source_timeframe: str | None
    status: str
    rejection_reason: str | None = None
    supporting_event_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class EntryRiskAssessment:
    candidate_type: str
    entry_price: float | None
    invalidation_price: float | None
    initial_risk: float | None
    three_r_price: float | None
    three_r_reached: bool | None
    three_r_reach_time: str | None
    maximum_favourable_excursion: float | None
    maximum_adverse_excursion: float | None
    maximum_favourable_r: float | None
    maximum_adverse_r: float | None
    status: str


@dataclass(frozen=True)
class EnrichedDoctrineState:
    schema_version: str
    candidate_state_id: str
    symbol: str
    freeze_at: str
    source_timeframe: str | None
    canonical_range_ids: tuple[str, ...]
    canonical_event_ids: tuple[str, ...]
    source_provenance: Mapping[str, Any]
    structural_content_hash: str
    parent_range_id: str | None
    parent_direction: str
    parent_direction_evidence: Mapping[str, Any]
    parent_origin: str
    parent_location_context: str
    parent_active_range_boundaries: Mapping[str, float | None]
    parent_external_objectives: Mapping[str, float | None]
    child_range_id: str
    child_direction: str
    child_relationship: str
    child_origin: str
    child_location_zone: str
    child_lifecycle_state: str
    reclaim_classification: str
    reclaim_evidence_event_ids: tuple[str, ...]
    profile_classification: str
    confidence: str
    status: str
    test_required_reasons: tuple[str, ...]
    choch_direction: str
    choch_timeframe: str | None
    choch_confirmation_type: str
    confirming_event_id: str | None
    confirming_candle_time: str | None
    confirming_price: float | None
    entry_candidates: tuple[EntryCandidate, ...]
    structural_invalidation_price: float | None
    structural_invalidation_time: str | None
    invalidation_source: str
    inducement_classification: str
    inducement_supporting_event_ids: tuple[str, ...]
    first_planned_target: float | None
    destination_zone: str
    external_objective: float | None
    first_objective_reach_time: str | None
    first_wick_outside_parent_time: str | None
    continuation_beyond_first_target: str
    entry_risk_assessments: tuple[EntryRiskAssessment, ...]
    first_planned_target_reached: bool | None
    target_reach_time: str | None
    stopped_before_target: bool | None
    invalidated: bool | None
    maximum_favourable_excursion: float | None
    maximum_adverse_excursion: float | None
    three_r_reached: bool | None
    breakeven_rule_activated: bool | None
    first_target_partial_applicable: bool | None
    continuation_outcome: str
    factual_outcome_status: str
    structure_query_ready: bool
    confirmation_query_ready: bool
    outcome_query_ready: bool
    overall_first_query_ready: bool
    blocker_reasons: tuple[str, ...] = field(default_factory=tuple)


def build_first_query_doctrine_report(
    master_map: Mapping[str, Any],
    *,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    source = validate_master_map(master_map)
    full_ranges, full_events, full_parent_by_child = flatten_root(master_map["root"])
    trusted_ranges, trusted_events, trusted_parent_by_child = flatten_root(master_map["trusted_root"])
    range_by_id = {str(item["id"]): item for item in trusted_ranges}
    full_range_by_id = {str(item["id"]): item for item in full_ranges}
    events_by_range = events_grouped_by_range(trusted_events)
    descendants_by_range = descendant_range_ids(trusted_ranges)
    adapted = adapt_master_map(master_map)

    states: list[EnrichedDoctrineState] = []
    for candidate in adapted["states"]:
        provenance = candidate["provenance"]
        freeze_event_id = str(provenance["freeze_event_id"])
        child_id = str(provenance["canonical_range_id"])
        child = range_by_id.get(child_id) or full_range_by_id.get(child_id)
        event = next((item for item in trusted_events if str(item.get("id")) == freeze_event_id), None)
        if child is None or event is None:
            continue
        parent_id = (
            str(provenance.get("parent_canonical_range_id") or "")
            or trusted_parent_by_child.get(child_id)
            or full_parent_by_child.get(child_id)
        )
        parent = range_by_id.get(parent_id or "") or full_range_by_id.get(parent_id or "")
        state = enrich_state(
            source=source,
            candidate_state_id=candidate["state"]["state_id"],
            event=event,
            child=child,
            parent=parent,
            range_events=events_by_range.get(child_id, []),
            lineage_events=lineage_events(
                candidate_range_id=child_id,
                descendants_by_range=descendants_by_range,
                events_by_range=events_by_range,
            ),
        )
        states.append(state)

    states.sort(key=lambda row: (parse_time(row.freeze_at), row.candidate_state_id))
    rows = [serialize_state(row) for row in states]
    status_counts = Counter(row["status"] for row in rows)
    blocker_counts = Counter(reason for row in rows for reason in row["blocker_reasons"])
    test_required_counts = Counter(reason for row in rows for reason in row["test_required_reasons"])
    factual_outcome_counts = Counter(row["factual_outcome_status"] for row in rows)

    stats = dict(master_map.get("statistics") or {})
    canonical_ranges = int(stats.get("canonical_ranges_before_review_exclusion") or len(full_ranges))
    canonical_events = int(stats.get("canonical_events_before_review_exclusion") or len(full_events))
    trusted_ranges_count = int(stats.get("comparison_eligible_ranges") or len(trusted_ranges))
    trusted_events_count = int(stats.get("comparison_eligible_events") or len(trusted_events))
    review_range_count = count_review_records(full_ranges)
    review_event_count = count_review_records(full_events)
    candidate_status_total = sum(
        status_counts[key] for key in (
            AnalysisStatus.QUERY_READY,
            AnalysisStatus.NEEDS_REVIEW,
            AnalysisStatus.LOW_CONFIDENCE,
            AnalysisStatus.UNKNOWN,
            AnalysisStatus.EXCLUDED,
        )
    )

    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at_utc": canonical_time(generated_at_utc) if generated_at_utc else utc_now(),
        "source_master_map": source,
        "contract": {
            "scope": "Weekly parent context -> Daily structure/location -> Intraday/M15 confirmation -> destination -> factual outcome",
            "source_root": "trusted_root",
            "mutation_policy": "read_only_disposable_report",
            "qualifying_pullback": "TEST_REQUIRED_NON_BLOCKING",
            "future_leakage_policy": "freeze fields use events at or before freeze_at; outcome fields may inspect later events only in outcome stage",
        },
        "summary": {
            "structural_content_hash": source["structural_content_hash"],
            "canonical_range_count": canonical_ranges,
            "canonical_event_count": canonical_events,
            "trusted_range_count": trusted_ranges_count,
            "trusted_event_count": trusted_events_count,
            "frozen_candidate_count": len(states),
            "enriched_candidate_count": len(states),
            "task_b_frozen_candidate_count": len(adapted["states"]),
            "candidate_query_ready_count": status_counts[AnalysisStatus.QUERY_READY],
            "candidate_needs_review_count": status_counts[AnalysisStatus.NEEDS_REVIEW],
            "candidate_low_confidence_count": status_counts[AnalysisStatus.LOW_CONFIDENCE],
            "candidate_unknown_count": status_counts[AnalysisStatus.UNKNOWN],
            "candidate_excluded_count": status_counts[AnalysisStatus.EXCLUDED],
            "candidate_status_total": candidate_status_total,
            "master_map_review_range_count": review_range_count,
            "master_map_review_event_count": review_event_count,
            "master_map_review_item_count": len(master_map.get("review_items") or []),
            "query_ready_count": status_counts[AnalysisStatus.QUERY_READY],
            "needs_review_count": status_counts[AnalysisStatus.NEEDS_REVIEW],
            "low_confidence_count": status_counts[AnalysisStatus.LOW_CONFIDENCE],
            "unknown_count": status_counts[AnalysisStatus.UNKNOWN],
            "excluded_count": status_counts[AnalysisStatus.EXCLUDED],
            "field_level_blockers_by_reason": dict(sorted(blocker_counts.items())),
            "classifications_by_parent_direction": count_field(rows, "parent_direction"),
            "classifications_by_child_relationship": count_field(rows, "child_relationship"),
            "classifications_by_location_zone": count_field(rows, "child_location_zone"),
            "reclaim_profile_totals": count_pairs(rows, "reclaim_classification", "profile_classification"),
            "choch_candidate_totals": count_entry(rows, "choch_confirmation_type"),
            "close_entry_candidate_totals": count_entry_type(rows, "CHOCH_CLOSE"),
            "retest_entry_candidate_totals": count_entry_type(rows, "CHOCH_RETEST"),
            "destination_totals": count_field(rows, "destination_zone"),
            "first_target_outcomes": count_field(rows, "factual_outcome_status"),
            "factual_outcome_totals": dict(sorted(factual_outcome_counts.items())),
            "continuation_outcomes": count_field(rows, "continuation_outcome"),
            "structure_query_ready_count": sum(1 for row in rows if row["structure_query_ready"]),
            "confirmation_query_ready_count": sum(1 for row in rows if row["confirmation_query_ready"]),
            "outcome_query_ready_count": sum(1 for row in rows if row["outcome_query_ready"]),
            "overall_first_query_ready_count": sum(1 for row in rows if row["overall_first_query_ready"]),
            "calculable_3r_state_count": sum(
                1 for row in rows
                if any(item["initial_risk"] is not None for item in row["entry_risk_assessments"])
            ),
            "calculable_mfe_mae_state_count": sum(
                1 for row in rows
                if row["maximum_favourable_excursion"] is not None
                or row["maximum_adverse_excursion"] is not None
            ),
            "test_required_field_totals": dict(sorted(test_required_counts.items())),
        },
        "states": rows,
        "anonymised_state_table": anonymised_table(rows),
    }
    report["determinism_hash"] = report_hash(report)
    return report


def enrich_state(
    *,
    source: Mapping[str, Any],
    candidate_state_id: str,
    event: Mapping[str, Any],
    child: Mapping[str, Any],
    parent: Mapping[str, Any] | None,
    range_events: Sequence[Mapping[str, Any]],
    lineage_events: Sequence[Mapping[str, Any]],
) -> EnrichedDoctrineState:
    freeze = canonical_time(event.get("event_time_utc"))
    freeze_dt = parse_time(freeze)
    frozen_events = sorted(
        [item for item in range_events if item.get("event_time_utc") and parse_time(item["event_time_utc"]) <= freeze_dt],
        key=lambda item: (parse_time(item["event_time_utc"]), str(item.get("id") or "")),
    )
    child_direction = direction_from_event(event)
    parent_direction, parent_evidence = parent_direction_at_freeze(parent, freeze)
    relationship = classify_child_relationship(parent_direction, child_direction)
    parent_low = finite(parent.get("range_low")) if parent else None
    parent_high = finite(parent.get("range_high")) if parent else None
    price = event_price(event)
    location_zone = classify_location_zone(price, parent_low, parent_high)
    range_state = classify_range_state(child, frozen_events)
    reclaim_events = tuple(str(item["id"]) for item in frozen_events if token(item.get("event_type")).startswith("RECLAIM_"))
    entry_candidates = tuple(build_entry_candidates(frozen_events))
    blockers = readiness_blockers(
        parent=parent,
        parent_low=parent_low,
        parent_high=parent_high,
        price=price,
        freeze=freeze,
        parent_direction=parent_direction,
        relationship=relationship,
    )
    review_reasons = trust_review_reasons(child, parent)
    test_required = (
        "QUALIFYING_PULLBACK",
        "RUNNER_MANAGEMENT",
    )
    first_target = planned_target(child_direction, parent_low, parent_high)
    invalidation = invalidation_price(child_direction, parent_low, parent_high)
    future = [
        item for item in lineage_events
        if item.get("event_time_utc")
        and parse_time(item["event_time_utc"]) > freeze_dt
        and event_within_lifecycle_horizon(item, child)
        and token(item.get("navigation_status")) != "REVIEW"
        and token(item.get("statistics_status")) != "EXCLUDED"
    ]
    outcome = evaluate_outcome(
        child_direction=child_direction,
        first_target=first_target,
        invalidation_price=invalidation,
        entry_candidates=entry_candidates,
        future_events=future,
    )
    status = readiness_status(blockers, review_reasons)
    confidence = "high" if status == AnalysisStatus.QUERY_READY else "medium" if status == AnalysisStatus.NEEDS_REVIEW else "low"
    return EnrichedDoctrineState(
        schema_version=STATE_SCHEMA_VERSION,
        candidate_state_id=candidate_state_id,
        symbol="XAUUSD",
        freeze_at=freeze,
        source_timeframe=child.get("source_timeframe"),
        canonical_range_ids=tuple(str(value) for value in (parent.get("id") if parent else None, child["id"]) if value),
        canonical_event_ids=tuple(str(item["id"]) for item in frozen_events),
        source_provenance={
            "child_source_refs": copy.deepcopy(child.get("source_refs") or []),
            "parent_source_refs": copy.deepcopy(parent.get("source_refs") if parent else []),
            "freeze_event_source_refs": copy.deepcopy(event.get("source_refs") or []),
        },
        structural_content_hash=source["structural_content_hash"],
        parent_range_id=str(parent["id"]) if parent else None,
        parent_direction=parent_direction,
        parent_origin="STRUCTURAL_RANGE" if parent else "UNKNOWN",
        parent_location_context=location_zone,
        parent_active_range_boundaries={"low": parent_low, "high": parent_high},
        parent_external_objectives={"bullish": parent_high, "bearish": parent_low},
        child_range_id=str(child["id"]),
        child_direction=child_direction,
        child_relationship=relationship,
        child_origin="STRUCTURAL_RANGE",
        child_location_zone=location_zone,
        child_lifecycle_state=range_state,
        reclaim_classification=classify_reclaim(frozen_events),
        reclaim_evidence_event_ids=reclaim_events,
        profile_classification=classify_profile(frozen_events),
        confidence=confidence,
        status=status,
        test_required_reasons=test_required,
        choch_direction=child_direction,
        choch_timeframe=choch_timeframe(frozen_events),
        choch_confirmation_type=choch_confirmation_type(frozen_events),
        confirming_event_id=str(event["id"]),
        confirming_candle_time=freeze,
        confirming_price=price,
        entry_candidates=entry_candidates,
        structural_invalidation_price=invalidation,
        structural_invalidation_time=None,
        invalidation_source="PARENT_BOUNDARY",
        inducement_classification="UNKNOWN",
        inducement_supporting_event_ids=(),
        first_planned_target=first_target,
        destination_zone=destination_zone(child_direction),
        external_objective=first_target,
        first_objective_reach_time=outcome["target_reach_time"],
        first_wick_outside_parent_time=outcome["first_wick_outside_parent_time"],
        continuation_beyond_first_target=outcome["continuation_outcome"],
        entry_risk_assessments=tuple(outcome["entry_risk_assessments"]),
        first_planned_target_reached=outcome["first_planned_target_reached"],
        target_reach_time=outcome["target_reach_time"],
        stopped_before_target=outcome["stopped_before_target"],
        invalidated=outcome["invalidated"],
        maximum_favourable_excursion=outcome["maximum_favourable_excursion"],
        maximum_adverse_excursion=outcome["maximum_adverse_excursion"],
        three_r_reached=outcome["three_r_reached"],
        breakeven_rule_activated=outcome["breakeven_rule_activated"],
        first_target_partial_applicable=outcome["first_target_partial_applicable"],
        continuation_outcome=outcome["continuation_outcome"],
        factual_outcome_status=outcome["factual_outcome_status"],
        structure_query_ready=not blockers and not review_reasons,
        confirmation_query_ready=choch_confirmation_type(frozen_events) != "UNKNOWN",
        outcome_query_ready=outcome["factual_outcome_status"] not in {"NOT_AVAILABLE", "UNKNOWN"},
        overall_first_query_ready=(
            not blockers
            and not review_reasons
            and choch_confirmation_type(frozen_events) != "UNKNOWN"
            and outcome["factual_outcome_status"] not in {"NOT_AVAILABLE", "UNKNOWN"}
        ),
        blocker_reasons=tuple([*review_reasons, *blockers]),
        parent_direction_evidence=parent_evidence,
    )


def validate_master_map(master_map: Mapping[str, Any]) -> dict[str, Any]:
    if master_map.get("schema_version") != MASTER_MAP_SCHEMA_VERSION:
        raise DoctrineError(f"Master Map schema must be {MASTER_MAP_SCHEMA_VERSION}")
    if token(master_map.get("symbol")) != "XAUUSD":
        raise DoctrineError("Master Map symbol must be XAUUSD")
    structural_hash = str(master_map.get("structural_content_hash") or "").strip()
    if not structural_hash:
        raise DoctrineError("Master Map structural_content_hash is required")
    for key in ("root", "trusted_root"):
        if not isinstance(master_map.get(key), Mapping):
            raise DoctrineError(f"Master Map {key} is required")
    return {
        "schema_version": MASTER_MAP_SCHEMA_VERSION,
        "symbol": "XAUUSD",
        "built_at_utc": master_map.get("built_at_utc"),
        "structural_content_hash": structural_hash,
    }


def flatten_root(root: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, str]]:
    ranges: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    parent_by_child: dict[str, str] = {}

    def visit(node: Mapping[str, Any], parent_id: str | None = None) -> None:
        if token(node.get("node_type")) == "RANGE":
            item = copy.deepcopy(dict(node))
            item["parent_canonical_range_id"] = parent_id
            ranges.append(item)
            node_id = str(node["id"])
            if parent_id:
                parent_by_child[node_id] = parent_id
            for event in node.get("events", []):
                event_item = copy.deepcopy(dict(event))
                event_item["canonical_range_id"] = node_id
                events.append(event_item)
            parent_id = node_id
        for child in node.get("children", []):
            visit(child, parent_id)
        for child in node.get("unlinked_review_children", []):
            visit(child, None)

    visit(root)
    return ranges, events, parent_by_child


def events_grouped_by_range(events: Sequence[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        grouped.setdefault(str(event.get("canonical_range_id") or ""), []).append(copy.deepcopy(dict(event)))
    return grouped


def descendant_range_ids(ranges: Sequence[Mapping[str, Any]]) -> dict[str, set[str]]:
    children_by_parent: dict[str, list[str]] = {}
    for item in ranges:
        parent_id = item.get("parent_canonical_range_id")
        if parent_id:
            children_by_parent.setdefault(str(parent_id), []).append(str(item["id"]))
    result: dict[str, set[str]] = {}
    for item in ranges:
        root_id = str(item["id"])
        seen: set[str] = set()
        stack = list(children_by_parent.get(root_id, []))
        while stack:
            child_id = stack.pop()
            if child_id in seen:
                continue
            seen.add(child_id)
            stack.extend(children_by_parent.get(child_id, []))
        result[root_id] = seen
    return result


def lineage_events(
    *,
    candidate_range_id: str,
    descendants_by_range: Mapping[str, set[str]],
    events_by_range: Mapping[str, Sequence[Mapping[str, Any]]],
) -> list[dict[str, Any]]:
    allowed_range_ids = {candidate_range_id, *descendants_by_range.get(candidate_range_id, set())}
    result: list[dict[str, Any]] = []
    for range_id in sorted(allowed_range_ids):
        result.extend(copy.deepcopy(dict(item)) for item in events_by_range.get(range_id, []))
    return result


def count_review_records(rows: Sequence[Mapping[str, Any]]) -> int:
    return sum(1 for row in rows if token(row.get("navigation_status")) == "REVIEW")


def event_within_lifecycle_horizon(event: Mapping[str, Any], child: Mapping[str, Any]) -> bool:
    inactive = child.get("inactive_from_time")
    if not inactive:
        return True
    return parse_time(event["event_time_utc"]) <= parse_time(inactive)


def parent_direction_at_freeze(parent: Mapping[str, Any] | None, freeze: str) -> tuple[str, dict[str, Any]]:
    if parent is None:
        return Direction.UNCONFIRMED, {"status": "NO_PARENT", "event_ids": [], "event_times": []}
    freeze_dt = parse_time(freeze)
    candidates = [
        item for item in parent.get("events", [])
        if token(item.get("event_type")) in SUPPORTED_FREEZE_EVENTS
        and item.get("event_time_utc")
        and parse_time(item["event_time_utc"]) <= freeze_dt
    ]
    candidates.sort(key=lambda item: (parse_time(item["event_time_utc"]), str(item.get("id") or "")))
    if not candidates:
        return Direction.UNCONFIRMED, {"status": "NO_PREFREEZE_PARENT_DIRECTION", "event_ids": [], "event_times": []}
    latest = candidates[-1]
    direction = direction_from_event(latest)
    return direction, {
        "status": "RESOLVED_FROM_PREFREEZE_PARENT_EVENT",
        "event_ids": [str(latest.get("id"))],
        "event_times": [canonical_time(latest.get("event_time_utc"))],
    }


def classify_child_relationship(parent_direction: str, child_direction: str) -> str:
    if parent_direction == Direction.UNCONFIRMED or child_direction == Direction.UNCONFIRMED:
        return ChildRelationship.TRANSITION
    return (
        ChildRelationship.PRO_TREND
        if parent_direction == child_direction
        else ChildRelationship.COUNTER_TREND
    )


def classify_location_zone(price: float | None, low: float | None, high: float | None) -> str:
    if price is None or low is None or high is None or high <= low:
        return "UNKNOWN"
    location = (price - low) / (high - low)
    if location <= 0.20:
        return LocationZone.EXTREME_DISCOUNT
    if location < 0.45:
        return LocationZone.DISCOUNT
    if location <= 0.55:
        return LocationZone.FAIR_PRICE
    if location < 0.80:
        return LocationZone.PREMIUM
    return LocationZone.EXTREME_PREMIUM


def classify_touch(price: float, boundary: float, tick_tolerance: float) -> bool:
    epsilon = max(abs(price), abs(boundary), 1.0) * 1e-12
    return abs(price - boundary) <= tick_tolerance + epsilon


def classify_range_state(child: Mapping[str, Any], frozen_events: Sequence[Mapping[str, Any]]) -> str:
    event_types = [token(item.get("event_type")) for item in frozen_events]
    if any(item.startswith("RANGE_FAILURE_CONFIRMED") for item in event_types):
        return RangeState.RANGE_FAILURE_CONFIRMED
    if any(item.startswith("RANGE_FAILURE") for item in event_types):
        return RangeState.RANGE_FAILURE_DETECTED
    if any(item == "RETEST_HELD" for item in event_types):
        return RangeState.HELD
    if any(item.startswith("RETEST_") for item in event_types):
        return RangeState.RETEST_IN_PROGRESS
    status = token(child.get("status"))
    return RangeState.ACTIVE if status in {"ACTIVE", "BROKEN"} else RangeState.RANGE_DEVELOPING


def classify_daily_failure(
    *,
    break_timeframe: str,
    break_kind: str,
    protected_swing_broken: bool,
    m15_support: bool | None = None,
) -> str:
    if token(break_timeframe) in {"H1", "H4"} and token(break_kind) == "WICK" and protected_swing_broken:
        return RangeState.RANGE_FAILURE_CONFIRMED
    if m15_support:
        return RangeState.RANGE_FAILURE_DETECTED
    return RangeState.RANGE_FAILURE_DETECTED if protected_swing_broken else RangeState.ACTIVE


def phase_advance_allowed(*, layer: str, break_kind: str) -> bool:
    return token(layer) in {"WEEKLY", "DAILY"} and token(break_kind) in {"WICK", "CLOSE"}


def build_entry_candidates(events: Sequence[Mapping[str, Any]]) -> list[EntryCandidate]:
    by_type = {token(item.get("event_type")): item for item in events}
    result: list[EntryCandidate] = []
    for event_type in ("CHOCH_CLOSE", "CHOCH_RETEST"):
        event = by_type.get(event_type)
        result.append(
            EntryCandidate(
                candidate_type=event_type,
                entry_time=canonical_time(event.get("event_time_utc")) if event and event.get("event_time_utc") else None,
                entry_price=event_price(event) if event else None,
                source_timeframe=event.get("source_timeframe") if event else None,
                status="VALID" if event else "UNKNOWN",
                rejection_reason=None if event else "MISSING_EVIDENCE",
                supporting_event_ids=(str(event["id"]),) if event else (),
            )
        )
    return result


def evaluate_outcome(
    *,
    child_direction: str,
    first_target: float | None,
    invalidation_price: float | None,
    entry_candidates: Sequence[EntryCandidate],
    future_events: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    reached_at = objective_reach_time(child_direction, first_target, future_events)
    reached = None if first_target is None else reached_at is not None
    continuation = "TEST_REQUIRED" if reached else "NOT_AVAILABLE"
    risk_assessments = tuple(
        assess_entry_risk(
            candidate,
            child_direction=child_direction,
            invalidation_price=invalidation_price,
            events=future_events,
        )
        for candidate in entry_candidates
    )
    calculable = [item for item in risk_assessments if item.initial_risk is not None]
    reached_3r = [item for item in calculable if item.three_r_reached is True]
    three_r_reached = True if reached_3r else None
    return {
        "first_planned_target_reached": reached,
        "target_reach_time": reached_at,
        "stopped_before_target": None,
        "invalidated": None,
        "maximum_favourable_excursion": None,
        "maximum_adverse_excursion": None,
        "entry_risk_assessments": risk_assessments,
        "three_r_reached": three_r_reached,
        "breakeven_rule_activated": True if three_r_reached is True else None,
        "first_target_partial_applicable": reached,
        "continuation_outcome": continuation,
        "factual_outcome_status": "FIRST_TARGET_REACHED" if reached else "NOT_AVAILABLE",
        "first_wick_outside_parent_time": reached_at,
    }


def assess_entry_risk(
    candidate: EntryCandidate,
    *,
    child_direction: str,
    invalidation_price: float | None,
    events: Sequence[Mapping[str, Any]],
) -> EntryRiskAssessment:
    entry_price = candidate.entry_price if candidate.status == "VALID" else None
    risk = initial_risk(child_direction, entry_price, invalidation_price)
    if risk is None:
        return EntryRiskAssessment(
            candidate_type=candidate.candidate_type,
            entry_price=entry_price,
            invalidation_price=invalidation_price,
            initial_risk=None,
            three_r_price=None,
            three_r_reached=None,
            three_r_reach_time=None,
            maximum_favourable_excursion=None,
            maximum_adverse_excursion=None,
            maximum_favourable_r=None,
            maximum_adverse_r=None,
            status="RISK_NOT_AVAILABLE",
        )
    three_r = entry_price + 3 * risk if child_direction == Direction.BULLISH else entry_price - 3 * risk
    reached_at = objective_reach_time(child_direction, three_r, events)
    return EntryRiskAssessment(
        candidate_type=candidate.candidate_type,
        entry_price=entry_price,
        invalidation_price=invalidation_price,
        initial_risk=risk,
        three_r_price=three_r,
        three_r_reached=True if reached_at else None,
        three_r_reach_time=reached_at,
        maximum_favourable_excursion=None,
        maximum_adverse_excursion=None,
        maximum_favourable_r=None,
        maximum_adverse_r=None,
        status="THREE_R_REACHED" if reached_at else "THREE_R_NOT_AVAILABLE",
    )


def initial_risk(child_direction: str, entry_price: float | None, invalidation_price: float | None) -> float | None:
    if entry_price is None or invalidation_price is None:
        return None
    risk = entry_price - invalidation_price if child_direction == Direction.BULLISH else invalidation_price - entry_price
    return risk if risk > 0 else None


def objective_reach_time(
    child_direction: str,
    objective: float | None,
    events: Sequence[Mapping[str, Any]],
) -> str | None:
    if objective is None:
        return None
    ordered = sorted(
        [item for item in events if item.get("event_time_utc")],
        key=lambda item: (parse_time(item["event_time_utc"]), str(item.get("id") or "")),
    )
    for event in ordered:
        price = objective_evidence_price(event, child_direction)
        if price is None:
            continue
        if child_direction == Direction.BULLISH and price >= objective:
            return canonical_time(event["event_time_utc"])
        if child_direction == Direction.BEARISH and price <= objective:
            return canonical_time(event["event_time_utc"])
    return None


def first_wick_outside_parent_time(
    child_direction: str,
    parent_low: float | None,
    parent_high: float | None,
    events: Sequence[Mapping[str, Any]],
) -> str | None:
    target = parent_high if child_direction == Direction.BULLISH else parent_low
    return objective_reach_time(child_direction, target, events)


def objective_evidence_price(event: Mapping[str, Any], child_direction: str) -> float | None:
    if child_direction == Direction.BULLISH:
        high = finite(event.get("high"))
        if high is not None:
            return high
        if token(event.get("event_type")) in {"SWEEP_HIGH", "OBJECTIVE_BREACH_UP", "BOUNDARY_BREACH_UP"}:
            return event_price(event)
        return None
    low = finite(event.get("low"))
    if low is not None:
        return low
    if token(event.get("event_type")) in {"SWEEP_LOW", "OBJECTIVE_BREACH_DOWN", "BOUNDARY_BREACH_DOWN"}:
        return event_price(event)
    return None


def readiness_blockers(
    *,
    parent: Mapping[str, Any] | None,
    parent_low: float | None,
    parent_high: float | None,
    price: float | None,
    freeze: str | None,
    parent_direction: str,
    relationship: str,
) -> list[str]:
    reasons: list[str] = []
    if parent is None:
        reasons.append("MISSING_PARENT_RANGE")
    if parent_low is None or parent_high is None:
        reasons.append("MISSING_PARENT_BOUNDS")
    elif parent_high <= parent_low:
        reasons.append("INVALID_PARENT_BOUNDS")
    if price is None:
        reasons.append("MISSING_FREEZE_PRICE")
    if not freeze:
        reasons.append("MISSING_FREEZE_TIME")
    if parent_direction == Direction.UNCONFIRMED:
        reasons.append("MISSING_PARENT_DIRECTION")
    if relationship == ChildRelationship.TRANSITION:
        reasons.append("TRANSITION_PARENT_CONTEXT")
    return reasons


def readiness_status(blockers: Sequence[str], review_reasons: Sequence[str]) -> str:
    if any(reason in TECHNICAL_EXCLUSION_REASONS for reason in blockers):
        return AnalysisStatus.EXCLUDED
    if review_reasons:
        return AnalysisStatus.NEEDS_REVIEW
    missing = [reason for reason in blockers if reason.startswith("MISSING_")]
    if missing:
        return AnalysisStatus.UNKNOWN
    return AnalysisStatus.QUERY_READY


def trust_review_reasons(child: Mapping[str, Any], parent: Mapping[str, Any] | None) -> list[str]:
    reasons: list[str] = []
    for prefix, node in (("CHILD", child), ("PARENT", parent)):
        if node is None:
            continue
        if token(node.get("navigation_status")) == "REVIEW":
            reasons.append(f"{prefix}_NEEDS_REVIEW")
        if token(node.get("statistics_status")) == "EXCLUDED":
            reasons.append(f"{prefix}_STATISTICS_EXCLUDED")
    return reasons


def direction_from_event(event: Mapping[str, Any]) -> str:
    event_type = token(event.get("event_type"))
    direction = token(event.get("direction"))
    if event_type.endswith("_UP") or direction == "UP":
        return Direction.BULLISH
    if event_type.endswith("_DOWN") or direction == "DOWN":
        return Direction.BEARISH
    return Direction.UNCONFIRMED


def direction_from_range(node: Mapping[str, Any] | None) -> str:
    if not node:
        return Direction.UNCONFIRMED
    direction = token(node.get("direction_of_break") or node.get("direction"))
    if direction in {"UP", "BULLISH"}:
        return Direction.BULLISH
    if direction in {"DOWN", "BEARISH"}:
        return Direction.BEARISH
    return Direction.UNCONFIRMED


def classify_reclaim(events: Sequence[Mapping[str, Any]]) -> str:
    matches = [token(item.get("event_type")) for item in events if token(item.get("event_type")).startswith("RECLAIM_")]
    return matches[-1] if matches else "NOT_REQUIRED_FOR_ACTIVE_LEG"


def classify_profile(events: Sequence[Mapping[str, Any]]) -> str:
    matches = [token(item.get("event_type")) for item in events if token(item.get("event_type")).startswith("PROFILE_")]
    return matches[-1] if matches else "UNKNOWN"


def choch_timeframe(events: Sequence[Mapping[str, Any]]) -> str | None:
    for item in events:
        if token(item.get("event_type")).startswith("CHOCH_"):
            return item.get("source_timeframe")
    return None


def choch_confirmation_type(events: Sequence[Mapping[str, Any]]) -> str:
    types = [token(item.get("event_type")) for item in events if token(item.get("event_type")).startswith("CHOCH_")]
    if {"CHOCH_CLOSE", "CHOCH_RETEST"}.issubset(set(types)):
        return "CHOCH_CLOSE_AND_RETEST"
    return types[-1] if types else "UNKNOWN"


def planned_target(child_direction: str, parent_low: float | None, parent_high: float | None) -> float | None:
    if child_direction == Direction.BULLISH:
        return parent_high
    if child_direction == Direction.BEARISH:
        return parent_low
    return None


def invalidation_price(child_direction: str, parent_low: float | None, parent_high: float | None) -> float | None:
    if child_direction == Direction.BULLISH:
        return parent_low
    if child_direction == Direction.BEARISH:
        return parent_high
    return None


def destination_zone(child_direction: str) -> str:
    if child_direction == Direction.BULLISH:
        return "PARENT_HIGH_EXTERNAL_OBJECTIVE"
    if child_direction == Direction.BEARISH:
        return "PARENT_LOW_EXTERNAL_OBJECTIVE"
    return "UNKNOWN"


def event_price(event: Mapping[str, Any] | None) -> float | None:
    if not event:
        return None
    for key in ("price", "break_level", "high", "low"):
        value = finite(event.get(key))
        if value is not None:
            return value
    return None


def finite(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if result != result or result in {float("inf"), float("-inf")}:
        return None
    return result


def serialize_state(state: EnrichedDoctrineState) -> dict[str, Any]:
    result = asdict(state)
    result["entry_candidates"] = [asdict(item) for item in state.entry_candidates]
    return result


def anonymised_table(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "candidate_state_id": row["candidate_state_id"],
            "weekly_direction": row["parent_direction"],
            "daily_relationship": row["child_relationship"],
            "daily_location": row["child_location_zone"],
            "reclaim_profile": f"{row['reclaim_classification']}|{row['profile_classification']}",
            "confirmation": row["choch_confirmation_type"],
            "entry_type": ",".join(
                item["candidate_type"] for item in row["entry_candidates"] if item["status"] == "VALID"
            ) or "NONE",
            "destination": row["destination_zone"],
            "outcome": row["factual_outcome_status"],
            "readiness_status": row["status"],
            "blocker_reasons": list(row["blocker_reasons"]),
        }
        for row in rows
    ]


def count_field(rows: Sequence[Mapping[str, Any]], field_name: str) -> dict[str, int]:
    return dict(sorted(Counter(str(row.get(field_name) or "UNKNOWN") for row in rows).items()))


def count_pairs(rows: Sequence[Mapping[str, Any]], left: str, right: str) -> dict[str, int]:
    return dict(sorted(Counter(f"{row.get(left) or 'UNKNOWN'}|{row.get(right) or 'UNKNOWN'}" for row in rows).items()))


def count_entry(rows: Sequence[Mapping[str, Any]], field_name: str) -> dict[str, int]:
    return count_field(rows, field_name)


def count_entry_type(rows: Sequence[Mapping[str, Any]], candidate_type: str) -> dict[str, int]:
    counts = Counter()
    for row in rows:
        for item in row["entry_candidates"]:
            if item["candidate_type"] == candidate_type:
                counts[item["status"]] += 1
    return dict(sorted(counts.items()))


def stable_state_id(event_id: str, freeze: str, structural_hash: str) -> str:
    digest = hashlib.sha256(f"{structural_hash}|{event_id}|{freeze}".encode("utf-8")).hexdigest()[:16]
    return f"fq:{digest}"


def report_hash(report: Mapping[str, Any]) -> str:
    stable = copy.deepcopy(dict(report))
    stable.pop("generated_at_utc", None)
    stable.pop("determinism_hash", None)
    return hashlib.sha256(deterministic_json(stable).encode("utf-8")).hexdigest()


def token(value: Any) -> str:
    return str(value or "").strip().upper().replace("-", "_").replace(" ", "_")


def parse_time(value: Any) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise DoctrineError("timestamp is required")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise DoctrineError(f"invalid ISO timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def canonical_time(value: Any) -> str:
    return parse_time(value).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_master_map_output_readonly(db_path: str | Path, *, symbol: str = "XAUUSD") -> dict[str, Any]:
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"Range Library database does not exist: {path}")
    uri = path.resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        row = connection.execute(
            "SELECT output_json FROM master_map_outputs WHERE symbol=?",
            (symbol.upper(),),
        ).fetchone()
    if row is None:
        raise LookupError(f"No Master Map output exists for {symbol.upper()}.")
    return json.loads(row[0])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build disposable XAUUSD first-query doctrine report")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--master-map", help="Master Map JSON output")
    source.add_argument("--range-library-db", help="Range Library DB containing master_map_outputs")
    parser.add_argument("--output", required=True, help="Disposable doctrine report path")
    parser.add_argument("--compact", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    master_map = (
        load_json(args.master_map)
        if args.master_map
        else load_master_map_output_readonly(args.range_library_db, symbol="XAUUSD")
    )
    report = build_first_query_doctrine_report(master_map)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=None if args.compact else 2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "output": str(output),
        "structural_content_hash": report["summary"]["structural_content_hash"],
        "frozen_candidate_count": report["summary"]["frozen_candidate_count"],
        "enriched_candidate_count": report["summary"]["enriched_candidate_count"],
        "query_ready_count": report["summary"]["query_ready_count"],
        "needs_review_count": report["summary"]["needs_review_count"],
        "excluded_count": report["summary"]["excluded_count"],
        "determinism_hash": report["determinism_hash"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
