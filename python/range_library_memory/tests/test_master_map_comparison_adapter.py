from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from range_library_memory.master_map_comparison_adapter import (
    ADAPTER_SCHEMA_VERSION,
    EXCLUDED,
    READY,
    MasterMapAdapterError,
    adapt_master_map,
    build_real_comparison_report,
    main,
    run_master_map_comparison,
)
from range_library_memory.structural_comparison import STRONG_TIER


def ref(raw_id: int, source_id: str) -> dict:
    return {
        "raw_id": raw_id,
        "case_ref": f"raw:case-{raw_id}",
        "source_record_id": source_id,
        "payload_sha256": f"sha-{raw_id}",
    }


def event(
    event_id: str,
    event_type: str,
    at: str,
    price: float,
    *,
    navigation_status: str = "TRUSTED",
    statistics_status: str = "ELIGIBLE",
    parent_status: str = "VALID",
) -> dict:
    return {
        "id": event_id,
        "node_type": "EVENT",
        "event_type": event_type,
        "event_time_utc": at,
        "price": price,
        "direction": "UP" if event_type.endswith("UP") else None,
        "break_level": price,
        "source_count": 1,
        "source_refs": [ref(abs(hash(event_id)) % 10000, event_id)],
        "navigation_status": navigation_status,
        "statistics_status": statistics_status,
        "ancestor_review_status": "CLEAR" if navigation_status == "TRUSTED" else "SELF_NEEDS_REVIEW",
        "direct_parent_link_status": parent_status,
    }


def range_node(
    range_id: str,
    layer: str,
    timeframe: str,
    low: float,
    high: float,
    active: str,
    *,
    events: list[dict] | None = None,
    children: list[dict] | None = None,
    navigation_status: str = "TRUSTED",
    statistics_status: str = "ELIGIBLE",
    parent_status: str = "VALID",
    direction: str | None = None,
    inactive: str | None = None,
) -> dict:
    return {
        "id": range_id,
        "node_type": "RANGE",
        "structure_layer": layer,
        "source_timeframe": timeframe,
        "range_high": high,
        "range_low": low,
        "range_high_time": active,
        "range_low_time": active,
        "active_from_time": active,
        "inactive_from_time": inactive,
        "status": "BROKEN" if inactive else "ACTIVE",
        "direction_of_break": direction,
        "source_count": 1,
        "source_refs": [ref(abs(hash(range_id)) % 10000, range_id)],
        "navigation_status": navigation_status,
        "statistics_status": statistics_status,
        "ancestor_review_status": "CLEAR" if navigation_status == "TRUSTED" else "DIRECT_PARENT_NEEDS_REVIEW",
        "direct_parent_link_status": parent_status,
        "events": events or [],
        "children": children or [],
    }


def master_map() -> dict:
    parent_bos = event("event-weekly-bos", "BOS_UP", "2024-01-01T00:00:00Z", 2100)
    future_reclaim = event("event-daily-a-future", "RECLAIM_WICK", "2024-01-04T00:00:00Z", 140)
    daily_a = range_node(
        "range-daily-a", "DAILY", "D1", 120, 180, "2024-01-01T00:00:00Z",
        events=[
            event("event-daily-a-bos", "BOS_UP", "2024-01-02T00:00:00Z", 150),
            future_reclaim,
        ],
    )
    daily_b = range_node(
        "range-daily-b", "DAILY", "D1", 220, 280, "2024-02-01T00:00:00Z",
        events=[event("event-daily-b-bos", "BOS_UP", "2024-02-02T00:00:00Z", 150)],
    )
    review_daily = range_node(
        "range-review", "DAILY", "D1", 130, 170, "2024-03-01T00:00:00Z",
        events=[event(
            "event-review", "BOS_UP", "2024-03-02T00:00:00Z", 150,
            navigation_status="REVIEW", statistics_status="EXCLUDED", parent_status="NEEDS_REVIEW",
        )],
        navigation_status="REVIEW", statistics_status="EXCLUDED", parent_status="NEEDS_REVIEW",
    )
    unresolved_daily = range_node(
        "range-unresolved", "DAILY", "D1", 130, 170, "2024-04-01T00:00:00Z",
        events=[event(
            "event-unresolved", "BOS_UP", "2024-04-02T00:00:00Z", 150,
            navigation_status="REVIEW", statistics_status="EXCLUDED", parent_status="NEEDS_REVIEW",
        )],
        navigation_status="REVIEW", statistics_status="EXCLUDED", parent_status="NEEDS_REVIEW",
    )
    weekly = range_node(
        "range-weekly", "WEEKLY", "W1", 100, 200, "2023-12-01T00:00:00Z",
        events=[parent_bos],
        children=[daily_a, daily_b, review_daily],
        parent_status="ROOT",
    )
    full_root = {
        "id": "symbol:XAUUSD",
        "node_type": "SYMBOL",
        "label": "XAUUSD",
        "children": [weekly],
        "unlinked_review_children": [unresolved_daily],
    }
    trusted_weekly = copy.deepcopy(weekly)
    trusted_weekly["children"] = [copy.deepcopy(daily_a), copy.deepcopy(daily_b)]
    trusted_root = {
        "id": "symbol:XAUUSD:trusted",
        "node_type": "SYMBOL",
        "label": "XAUUSD",
        "children": [trusted_weekly],
    }
    return {
        "schema_version": "xauusd_master_map_v0.1",
        "built_at_utc": "2026-07-13T18:00:00Z",
        "symbol": "XAUUSD",
        "structural_content_hash": "abc123structuralhash",
        "root": full_root,
        "trusted_root": trusted_root,
        "review_root": {"id": "symbol:XAUUSD:review", "node_type": "SYMBOL", "children": []},
        "statistics": {
            "canonical_ranges_before_review_exclusion": 5,
            "canonical_events_before_review_exclusion": 6,
            "comparison_eligible_ranges": 3,
            "comparison_eligible_events": 4,
        },
    }


def annotations() -> dict:
    shared = {
        "annotation_ref": "doctrine-fixture-v1",
        "parent_direction": "UP",
        "parent_origin": "DEMAND",
        "child_relationship": "PROTREND",
        "reclaim_state": "NONE",
        "retest_state": "NONE",
        "ltf_confirmation_state": "NONE",
    }
    return {
        "event-daily-a-bos": copy.deepcopy(shared),
        "event-daily-b-bos": copy.deepcopy(shared),
    }


def test_adapter_uses_only_trusted_statistics_eligible_master_map_records() -> None:
    adapted = adapt_master_map(master_map())
    filtering = adapted["filtering"]
    assert adapted["schema_version"] == ADAPTER_SCHEMA_VERSION
    assert filtering["trusted_range_records_used"] == 3
    assert filtering["trusted_event_records_used"] == 4
    assert all(item["state"]["trust_status"] == "TRUSTED" for item in adapted["states"])
    reasons = {reason for item in adapted["record_exclusions"] for reason in item["reason_codes"]}
    assert "REVIEW" in reasons
    assert "STATISTICS_EXCLUDED" in reasons
    assert "NEEDS_REVIEW" in reasons


def test_missing_doctrine_fields_are_explicit_and_block_scoring() -> None:
    adapted = adapt_master_map(master_map())
    candidate = next(item for item in adapted["states"] if item["provenance"]["freeze_event_id"] == "event-daily-a-bos")
    assert candidate["comparison_status"] == EXCLUDED
    assert candidate["state"]["parent_direction"] == "NOT_AVAILABLE"
    assert candidate["state"]["parent_origin"] == "NOT_AVAILABLE"
    assert candidate["state"]["child_relationship"] == "NOT_AVAILABLE"
    assert "MISSING_PARENT_DIRECTION" in candidate["exclusion_reasons"]
    assert "MISSING_PARENT_ORIGIN" in candidate["exclusion_reasons"]
    assert "MISSING_CHILD_RELATIONSHIP" in candidate["exclusion_reasons"]
    report = build_real_comparison_report(adapted, generated_at_utc="2026-07-13T20:00:00Z")
    assert report["comparison"]["status"] == "NO_COMPARISON_READY_STATES"
    assert report["comparison"]["overall"]["sample_size"] == 0


def test_no_future_events_leak_into_frozen_state() -> None:
    adapted = adapt_master_map(master_map(), doctrine_annotations=annotations())
    candidate = next(item for item in adapted["states"] if item["provenance"]["freeze_event_id"] == "event-daily-a-bos")
    assert candidate["comparison_status"] == READY
    assert candidate["state"]["as_of_time"] == "2024-01-02T00:00:00Z"
    assert candidate["state"]["event_sequence"] == ["BOS_UP"]
    assert candidate["provenance"]["canonical_event_ids"] == ["event-daily-a-bos"]
    assert "event-daily-a-future" not in candidate["provenance"]["canonical_event_ids"]


def test_structural_hash_canonical_ids_source_refs_and_chart_times_are_preserved() -> None:
    adapted = adapt_master_map(master_map(), doctrine_annotations=annotations())
    candidate = next(item for item in adapted["states"] if item["provenance"]["freeze_event_id"] == "event-daily-a-bos")
    provenance = candidate["provenance"]
    assert provenance["structural_content_hash"] == "abc123structuralhash"
    assert provenance["canonical_range_id"] == "range-daily-a"
    assert provenance["parent_canonical_range_id"] == "range-weekly"
    assert provenance["source_timeframe"] == "D1"
    assert provenance["chart_times"]["frozen_state_time"] == "2024-01-02T00:00:00Z"
    assert provenance["source_refs"]["range"][0]["source_record_id"] == "range-daily-a"
    assert provenance["source_refs"]["events"][0]["canonical_event_id"] == "event-daily-a-bos"


def test_ready_states_compare_and_link_real_canonical_contract_fields() -> None:
    report = run_master_map_comparison(
        master_map(),
        doctrine_annotations=annotations(),
        target_state_id="event-daily-b-bos@2024-02-02T00:00:00Z",
        generated_at_utc="2026-07-13T20:00:00Z",
    )
    assert report["comparison"]["status"] == "COMPLETE"
    assert report["comparison"]["tiers"][STRONG_TIER]["sample_size"] == 1
    linked = report["comparison"]["tiers"][STRONG_TIER]["linked_historical_examples"][0]
    ref_data = linked["historical_example"]
    assert ref_data["canonical_range_id"] == "range-daily-a"
    assert ref_data["parent_canonical_range_id"] == "range-weekly"
    assert ref_data["canonical_event_ids"] == ["event-daily-a-bos"]
    assert ref_data["structural_content_hash"] == "abc123structuralhash"
    assert linked["outcome"]["path"] == "NOT_AVAILABLE"


def test_outcome_data_is_separate_and_does_not_change_matching() -> None:
    target = "event-daily-b-bos@2024-02-02T00:00:00Z"
    base = run_master_map_comparison(
        master_map(), doctrine_annotations=annotations(), target_state_id=target
    )
    with_outcome = run_master_map_comparison(
        master_map(),
        doctrine_annotations=annotations(),
        outcomes={
            "event-daily-a-bos": {
                "path": "FAILURE",
                "destination": "PARENT_LOW",
                "reached_at": "2024-01-10T00:00:00Z",
                "time_to_destination": {"bars": 8, "timeframe": "D1"},
                "source_refs": ["factual-outcome-fixture"],
            }
        },
        target_state_id=target,
    )
    first = base["comparison"]["tiers"][STRONG_TIER]["linked_historical_examples"][0]
    second = with_outcome["comparison"]["tiers"][STRONG_TIER]["linked_historical_examples"][0]
    assert first["tier"] == second["tier"]
    assert first["score"] == second["score"]
    assert first["match_evidence"] == second["match_evidence"]
    assert first["outcome"]["path"] == "NOT_AVAILABLE"
    assert second["outcome"]["path"] == "FAILURE"


def test_annotation_requires_a_source_reference() -> None:
    bad = annotations()
    bad["event-daily-a-bos"].pop("annotation_ref")
    with pytest.raises(MasterMapAdapterError, match="annotation_ref"):
        adapt_master_map(master_map(), doctrine_annotations=bad)


def test_cli_writes_disposable_report(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "master-map.json"
    doctrine = tmp_path / "doctrine.json"
    output = tmp_path / "report.json"
    source.write_text(json.dumps(master_map()), encoding="utf-8")
    doctrine.write_text(json.dumps(annotations()), encoding="utf-8")
    assert main([
        "--master-map", str(source),
        "--doctrine-annotations", str(doctrine),
        "--target-state-id", "event-daily-b-bos@2024-02-02T00:00:00Z",
        "--output", str(output),
        "--compact",
    ]) == 0
    summary = json.loads(capsys.readouterr().out)
    report = json.loads(output.read_text(encoding="utf-8"))
    assert summary["strong_matches"] == 1
    assert report["schema_version"] == "xauusd_master_map_real_comparison_report_v0.1"


def test_wrong_master_map_schema_or_missing_hash_is_rejected() -> None:
    wrong = master_map()
    wrong["schema_version"] = "other"
    with pytest.raises(MasterMapAdapterError, match="schema"):
        adapt_master_map(wrong)
    missing_hash = master_map()
    missing_hash["structural_content_hash"] = ""
    with pytest.raises(MasterMapAdapterError, match="structural_content_hash"):
        adapt_master_map(missing_hash)


def test_report_accounts_for_master_map_records_not_materialized_in_root() -> None:
    source = master_map()
    source["statistics"]["canonical_events_before_review_exclusion"] = 9
    adapted = adapt_master_map(source)
    filtering = adapted["filtering"]
    assert filtering["event_records_not_materialized_from_root"] == 3
    aggregate = next(
        item for item in adapted["record_exclusions"]
        if item.get("record_count") == 3
    )
    assert aggregate["entity_kind"] == "EVENT"
    assert aggregate["reason_codes"] == ["MASTER_MAP_RECORD_NOT_MATERIALIZED_IN_ROOT"]


def test_factual_outcome_cannot_precede_frozen_state() -> None:
    with pytest.raises(MasterMapAdapterError, match="before frozen state"):
        adapt_master_map(
            master_map(),
            doctrine_annotations=annotations(),
            outcomes={
                "event-daily-a-bos": {
                    "path": "FAILURE",
                    "destination": "PARENT_LOW",
                    "reached_at": "2024-01-01T00:00:00Z",
                }
            },
        )


def test_invalid_parent_bounds_exclude_state_instead_of_reaching_scoring() -> None:
    source = master_map()
    weekly = source["root"]["children"][0]
    trusted_weekly = source["trusted_root"]["children"][0]
    weekly["range_low"] = weekly["range_high"]
    trusted_weekly["range_low"] = trusted_weekly["range_high"]
    adapted = adapt_master_map(source, doctrine_annotations=annotations())
    candidate = next(
        item for item in adapted["states"]
        if item["provenance"]["freeze_event_id"] == "event-daily-a-bos"
    )
    assert candidate["comparison_status"] == EXCLUDED
    assert "INVALID_PARENT_RANGE_BOUNDS" in candidate["exclusion_reasons"]
