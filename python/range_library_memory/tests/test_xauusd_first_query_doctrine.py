from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from range_library_memory.xauusd_first_query_doctrine import (
    AnalysisStatus,
    ChildRelationship,
    Direction,
    DoctrineError,
    EntryCandidate,
    LocationZone,
    RangeState,
    StructureLayer,
    build_entry_candidates,
    build_first_query_doctrine_report,
    classify_child_relationship,
    classify_daily_failure,
    classify_location_zone,
    classify_touch,
    evaluate_outcome,
    first_wick_outside_parent_time,
    main,
    phase_advance_allowed,
)
from range_library_memory.master_map_comparison_adapter import adapt_master_map


def event(
    event_id: str,
    event_type: str,
    at: str,
    price: float,
    *,
    direction: str | None = None,
    source_timeframe: str = "D1",
    high: float | None = None,
    low: float | None = None,
) -> dict:
    payload = {
        "id": event_id,
        "node_type": "EVENT",
        "event_type": event_type,
        "event_time_utc": at,
        "price": price,
        "direction": direction,
        "source_timeframe": source_timeframe,
        "navigation_status": "TRUSTED",
        "statistics_status": "ELIGIBLE",
        "source_refs": [{"source_record_id": event_id}],
    }
    if high is not None:
        payload["high"] = high
    if low is not None:
        payload["low"] = low
    return payload


def range_node(
    range_id: str,
    layer: str,
    low: float,
    high: float,
    *,
    direction_of_break: str | None = None,
    events: list[dict] | None = None,
    children: list[dict] | None = None,
    navigation_status: str = "TRUSTED",
    statistics_status: str = "ELIGIBLE",
) -> dict:
    return {
        "id": range_id,
        "node_type": "RANGE",
        "structure_layer": layer,
        "source_timeframe": "W1" if layer == "WEEKLY" else "D1",
        "range_high": high,
        "range_low": low,
        "range_high_time": "2026-01-10T00:00:00Z",
        "range_low_time": "2026-01-01T00:00:00Z",
        "active_from_time": "2026-01-01T00:00:00Z",
        "status": "BROKEN" if direction_of_break else "ACTIVE",
        "direction_of_break": direction_of_break,
        "navigation_status": navigation_status,
        "statistics_status": statistics_status,
        "direct_parent_link_status": "VALID",
        "ancestor_review_status": "CLEAR",
        "source_refs": [{"source_record_id": range_id}],
        "events": events or [],
        "children": children or [],
    }


def master_map(*, parent_direction: str | None = "UP", daily_direction: str = "UP") -> dict:
    parent_event_type = f"BOS_{parent_direction}" if parent_direction in {"UP", "DOWN"} else "CUSTOM_EVENT"
    weekly_events = [
        event("e-weekly-direction", parent_event_type, "2026-01-05T00:00:00Z", 180, direction=parent_direction),
    ] if parent_direction else []
    daily_events = [
        event("e-choch-close", "CHOCH_CLOSE", "2026-01-11T00:00:00Z", 145, source_timeframe="M15"),
        event("e-choch-retest", "CHOCH_RETEST", "2026-01-12T00:00:00Z", 148, source_timeframe="M15"),
        event("e-freeze", f"BOS_{daily_direction}", "2026-01-13T00:00:00Z", 150, direction=daily_direction),
        event("e-future", "SWEEP_HIGH", "2026-01-14T00:00:00Z", 205, direction="UP"),
    ]
    daily = range_node("daily-a", "DAILY", 120, 180, events=daily_events)
    weekly = range_node(
        "weekly-a",
        "WEEKLY",
        100,
        200,
        direction_of_break=parent_direction,
        events=weekly_events,
        children=[daily],
    )
    root = {"id": "symbol:XAUUSD", "node_type": "SYMBOL", "children": [weekly]}
    return {
        "schema_version": "xauusd_master_map_v0.1",
        "built_at_utc": "2026-07-15T00:00:00Z",
        "symbol": "XAUUSD",
        "structural_content_hash": "structural-hash",
        "root": copy.deepcopy(root),
        "trusted_root": copy.deepcopy(root),
        "review_root": {"id": "review", "node_type": "SYMBOL", "children": []},
        "statistics": {
            "canonical_ranges_before_review_exclusion": 2,
            "canonical_events_before_review_exclusion": 4,
            "comparison_eligible_ranges": 2,
            "comparison_eligible_events": 4,
        },
    }


def first_state(report: dict) -> dict:
    return report["states"][0]


def trusted_weekly(source: dict) -> dict:
    return source["trusted_root"]["children"][0]


def trusted_daily(source: dict) -> dict:
    return trusted_weekly(source)["children"][0]


def test_enum_validation() -> None:
    assert StructureLayer.WEEKLY == "WEEKLY"
    assert Direction.BULLISH == "BULLISH"
    assert ChildRelationship.PRO_TREND == "PRO_TREND"
    assert RangeState.ACTIVE == "ACTIVE"
    assert AnalysisStatus.QUERY_READY == "QUERY_READY"
    assert LocationZone.DISCOUNT == "DISCOUNT"


def test_direction_and_relationship_are_separate_fields() -> None:
    report = build_first_query_doctrine_report(master_map(parent_direction="DOWN", daily_direction="UP"))
    state = first_state(report)
    assert state["child_direction"] == "BULLISH"
    assert state["parent_direction"] == "BEARISH"
    assert state["child_relationship"] == "COUNTER_TREND"


def test_pro_trend_classification() -> None:
    assert classify_child_relationship("BULLISH", "BULLISH") == "PRO_TREND"


def test_counter_trend_classification() -> None:
    assert classify_child_relationship("BULLISH", "BEARISH") == "COUNTER_TREND"


def test_transition_classification() -> None:
    assert classify_child_relationship("UNCONFIRMED", "BULLISH") == "TRANSITION"


def test_location_zone_boundaries() -> None:
    assert classify_location_zone(100, 100, 200) == "EXTREME_DISCOUNT"
    assert classify_location_zone(130, 100, 200) == "DISCOUNT"
    assert classify_location_zone(150, 100, 200) == "FAIR_PRICE"
    assert classify_location_zone(170, 100, 200) == "PREMIUM"
    assert classify_location_zone(190, 100, 200) == "EXTREME_PREMIUM"


def test_active_leg_without_reclaim_is_query_ready() -> None:
    state = first_state(build_first_query_doctrine_report(master_map()))
    assert state["reclaim_classification"] == "NOT_REQUIRED_FOR_ACTIVE_LEG"
    assert state["status"] == "QUERY_READY"


def test_task_b_frozen_state_contract_is_preserved() -> None:
    source = master_map()
    task_b = adapt_master_map(source)
    report = build_first_query_doctrine_report(source)
    task_b_ids = [item["state"]["state_id"] for item in task_b["states"]]
    doctrine_ids = [item["candidate_state_id"] for item in report["states"]]
    assert report["summary"]["task_b_frozen_candidate_count"] == len(task_b_ids)
    assert report["summary"]["frozen_candidate_count"] == len(task_b_ids)
    assert sorted(doctrine_ids) == sorted(task_b_ids)
    assert len(doctrine_ids) == len(set(doctrine_ids))


def test_candidate_status_totals_sum_to_frozen_candidate_count() -> None:
    report = build_first_query_doctrine_report(master_map())
    summary = report["summary"]
    total = (
        summary["candidate_query_ready_count"]
        + summary["candidate_needs_review_count"]
        + summary["candidate_low_confidence_count"]
        + summary["candidate_unknown_count"]
        + summary["candidate_excluded_count"]
    )
    assert total == summary["frozen_candidate_count"]
    assert summary["candidate_status_total"] == summary["frozen_candidate_count"]
    assert "master_map_review_range_count" in summary
    assert "master_map_review_event_count" in summary
    assert "master_map_review_item_count" in summary


def test_missing_factual_outcome_blocks_outcome_readiness_only() -> None:
    source = master_map()
    trusted_daily(source)["events"][-1]["event_type"] = "BOS_UP"
    source["root"] = copy.deepcopy(source["trusted_root"])
    report = build_first_query_doctrine_report(source)
    state = first_state(report)
    summary = report["summary"]
    assert state["factual_outcome_status"] == "NOT_AVAILABLE"
    assert state["structure_query_ready"] is True
    assert state["confirmation_query_ready"] is True
    assert state["outcome_query_ready"] is False
    assert state["overall_first_query_ready"] is False
    assert summary["structure_query_ready_count"] == summary["frozen_candidate_count"]
    assert summary["confirmation_query_ready_count"] == summary["frozen_candidate_count"]
    assert summary["outcome_query_ready_count"] == 0
    assert summary["overall_first_query_ready_count"] == 0


def test_approved_wick_break_phase_advance() -> None:
    assert phase_advance_allowed(layer="WEEKLY", break_kind="WICK")
    assert phase_advance_allowed(layer="DAILY", break_kind="WICK")


def test_h1_h4_protected_swing_daily_failure() -> None:
    assert classify_daily_failure(
        break_timeframe="H1",
        break_kind="WICK",
        protected_swing_broken=True,
    ) == "RANGE_FAILURE_CONFIRMED"


def test_parent_breaks_bullish_after_freeze_does_not_rewrite_parent_direction() -> None:
    source = master_map(parent_direction=None, daily_direction="UP")
    trusted_weekly(source)["events"].append(
        event("future-weekly-up", "BOS_UP", "2026-01-20T00:00:00Z", 205, direction="UP")
    )
    source["root"] = copy.deepcopy(source["trusted_root"])
    state = first_state(build_first_query_doctrine_report(source))
    assert state["parent_direction"] == "UNCONFIRMED"
    assert state["parent_direction_evidence"]["status"] == "NO_PREFREEZE_PARENT_DIRECTION"


def test_parent_breaks_bearish_before_freeze_sets_bearish_parent_direction() -> None:
    state = first_state(build_first_query_doctrine_report(master_map(parent_direction="DOWN", daily_direction="DOWN")))
    assert state["parent_direction"] == "BEARISH"
    assert state["parent_direction_evidence"]["event_ids"] == ["e-weekly-direction"]


def test_post_freeze_parent_events_do_not_change_classification_or_readiness() -> None:
    base = master_map(parent_direction=None, daily_direction="UP")
    changed = copy.deepcopy(base)
    trusted_weekly(changed)["events"].append(
        event("future-weekly-down", "BOS_DOWN", "2026-02-01T00:00:00Z", 90, direction="DOWN")
    )
    changed["root"] = copy.deepcopy(changed["trusted_root"])
    base_state = first_state(build_first_query_doctrine_report(base))
    changed_state = first_state(build_first_query_doctrine_report(changed))
    for key in ("parent_direction", "child_relationship", "status", "blocker_reasons"):
        assert changed_state[key] == base_state[key]
    assert classify_daily_failure(
        break_timeframe="H4",
        break_kind="WICK",
        protected_swing_broken=True,
    ) == "RANGE_FAILURE_CONFIRMED"


def test_m15_support_not_jointly_mandatory_for_daily_failure() -> None:
    assert classify_daily_failure(
        break_timeframe="H1",
        break_kind="WICK",
        protected_swing_broken=True,
        m15_support=False,
    ) == "RANGE_FAILURE_CONFIRMED"


def test_choch_close_candidate_generation() -> None:
    candidates = build_entry_candidates([event("close", "CHOCH_CLOSE", "2026-01-01T00:00:00Z", 150)])
    close = next(item for item in candidates if item.candidate_type == "CHOCH_CLOSE")
    assert close.status == "VALID"
    assert close.entry_price == 150


def test_choch_retest_candidate_generation() -> None:
    candidates = build_entry_candidates([event("retest", "CHOCH_RETEST", "2026-01-01T00:00:00Z", 151)])
    retest = next(item for item in candidates if item.candidate_type == "CHOCH_RETEST")
    assert retest.status == "VALID"
    assert retest.entry_price == 151


def test_both_entry_candidates_coexist() -> None:
    state = first_state(build_first_query_doctrine_report(master_map()))
    assert {
        item["candidate_type"] for item in state["entry_candidates"] if item["status"] == "VALID"
    } == {"CHOCH_CLOSE", "CHOCH_RETEST"}


def test_outside_hierarchy_becomes_needs_review_not_excluded() -> None:
    source = master_map()
    source["trusted_root"]["children"][0]["navigation_status"] = "REVIEW"
    source["trusted_root"]["children"][0]["children"][0]["navigation_status"] = "REVIEW"
    state = first_state(build_first_query_doctrine_report(source))
    assert state["status"] == "NEEDS_REVIEW"
    assert "EXCLUDED" not in state["status"]


def test_exact_tick_tolerance_limited_to_touch() -> None:
    assert classify_touch(100.0001, 100.0, 0.0001)
    assert not classify_touch(100.0002, 100.0, 0.0001)
    assert classify_child_relationship("BULLISH", "BEARISH") == "COUNTER_TREND"


def test_first_wick_outside_parent_marks_external_objective() -> None:
    reached = first_wick_outside_parent_time(
        "BULLISH",
        100,
        200,
        [
            event("inside", "BOS_UP", "2026-01-01T00:00:00Z", 199),
            event("outside", "SWEEP_HIGH", "2026-01-02T00:00:00Z", 201),
        ],
    )
    assert reached == "2026-01-02T00:00:00Z"


def test_future_sibling_daily_event_cannot_satisfy_candidate_target() -> None:
    source = master_map()
    trusted_daily(source)["events"] = [
        item for item in trusted_daily(source)["events"] if item["id"] != "e-future"
    ]
    sibling = range_node(
        "daily-b",
        "DAILY",
        130,
        170,
        events=[event("sibling-target", "SWEEP_HIGH", "2026-01-14T00:00:00Z", 205, direction="UP")],
    )
    trusted_weekly(source)["children"].append(sibling)
    source["root"] = copy.deepcopy(source["trusted_root"])
    state = first_state(build_first_query_doctrine_report(source))
    assert state["first_planned_target_reached"] is False
    assert state["target_reach_time"] is None


def test_unrelated_later_weekly_event_cannot_satisfy_candidate_outcome() -> None:
    source = master_map()
    trusted_daily(source)["events"] = [
        item for item in trusted_daily(source)["events"] if item["id"] != "e-future"
    ]
    trusted_weekly(source)["events"].append(
        event("weekly-target", "SWEEP_HIGH", "2026-01-14T00:00:00Z", 205, direction="UP")
    )
    source["root"] = copy.deepcopy(source["trusted_root"])
    state = first_state(build_first_query_doctrine_report(source))
    assert state["first_planned_target_reached"] is False
    assert state["target_reach_time"] is None


def test_inlineage_target_event_can_satisfy_target() -> None:
    state = first_state(build_first_query_doctrine_report(master_map()))
    assert state["first_planned_target_reached"] is True
    assert state["target_reach_time"] == "2026-01-14T00:00:00Z"


def test_post_invalidation_target_event_does_not_convert_failure_to_success() -> None:
    source = master_map()
    trusted_daily(source)["inactive_from_time"] = "2026-01-13T12:00:00Z"
    source["root"] = copy.deepcopy(source["trusted_root"])
    state = first_state(build_first_query_doctrine_report(source))
    assert state["first_planned_target_reached"] is False
    assert state["target_reach_time"] is None


def test_external_objective_does_not_create_new_active_leg() -> None:
    state = first_state(build_first_query_doctrine_report(master_map()))
    assert state["first_wick_outside_parent_time"] == "2026-01-14T00:00:00Z"
    assert state["child_lifecycle_state"] == "ACTIVE"


def test_first_planned_target_defines_success() -> None:
    outcome = evaluate_outcome(
        child_direction="BULLISH",
        first_target=200,
        invalidation_price=100,
        entry_candidates=[],
        future_events=[event("target", "SWEEP_HIGH", "2026-01-02T00:00:00Z", 201)],
    )
    assert outcome["first_planned_target_reached"] is True
    assert outcome["factual_outcome_status"] == "FIRST_TARGET_REACHED"


def test_continuation_tracked_separately() -> None:
    state = first_state(build_first_query_doctrine_report(master_map()))
    assert state["factual_outcome_status"] == "FIRST_TARGET_REACHED"
    assert state["continuation_outcome"] == "TEST_REQUIRED"


def test_three_r_breakeven_baseline() -> None:
    state = first_state(build_first_query_doctrine_report(master_map()))
    assert state["three_r_reached"] is None
    assert state["breakeven_rule_activated"] is None
    assert state["first_target_partial_applicable"] is True


def test_first_target_reached_below_three_r_does_not_set_three_r() -> None:
    outcome = evaluate_outcome(
        child_direction="BULLISH",
        first_target=120,
        invalidation_price=90,
        entry_candidates=[
            EntryCandidate("CHOCH_CLOSE", "2026-01-01T00:00:00Z", 100, "M15", "VALID")
        ],
        future_events=[event("target", "SWEEP_HIGH", "2026-01-02T00:00:00Z", 121)],
    )
    assert outcome["first_planned_target_reached"] is True
    assert outcome["first_target_partial_applicable"] is True
    assert outcome["three_r_reached"] is None
    assert outcome["breakeven_rule_activated"] is None


def test_three_r_reached_activates_breakeven() -> None:
    outcome = evaluate_outcome(
        child_direction="BULLISH",
        first_target=120,
        invalidation_price=90,
        entry_candidates=[
            EntryCandidate("CHOCH_CLOSE", "2026-01-01T00:00:00Z", 100, "M15", "VALID")
        ],
        future_events=[event("three-r", "SWEEP_HIGH", "2026-01-02T00:00:00Z", 130)],
    )
    assert outcome["three_r_reached"] is True
    assert outcome["breakeven_rule_activated"] is True


def test_bullish_and_bearish_three_r_calculations_are_correct() -> None:
    bullish = evaluate_outcome(
        child_direction="BULLISH",
        first_target=120,
        invalidation_price=90,
        entry_candidates=[
            EntryCandidate("CHOCH_CLOSE", "2026-01-01T00:00:00Z", 100, "M15", "VALID")
        ],
        future_events=[event("three-r-up", "SWEEP_HIGH", "2026-01-02T00:00:00Z", 130)],
    )
    bearish = evaluate_outcome(
        child_direction="BEARISH",
        first_target=80,
        invalidation_price=110,
        entry_candidates=[
            EntryCandidate("CHOCH_CLOSE", "2026-01-01T00:00:00Z", 100, "M15", "VALID")
        ],
        future_events=[event("three-r-down", "SWEEP_LOW", "2026-01-02T00:00:00Z", 70)],
    )
    assert bullish["entry_risk_assessments"][0].three_r_price == 130
    assert bearish["entry_risk_assessments"][0].three_r_price == 70
    assert bullish["three_r_reached"] is True
    assert bearish["three_r_reached"] is True


def test_choch_close_and_retest_can_have_different_r_outcomes() -> None:
    outcome = evaluate_outcome(
        child_direction="BULLISH",
        first_target=120,
        invalidation_price=90,
        entry_candidates=[
            EntryCandidate("CHOCH_CLOSE", "2026-01-01T00:00:00Z", 100, "M15", "VALID"),
            EntryCandidate("CHOCH_RETEST", "2026-01-01T01:00:00Z", 105, "M15", "VALID"),
        ],
        future_events=[event("three-r-close-only", "SWEEP_HIGH", "2026-01-02T00:00:00Z", 130)],
    )
    close, retest = outcome["entry_risk_assessments"]
    assert close.three_r_price == 130
    assert close.three_r_reached is True
    assert retest.three_r_price == 150
    assert retest.three_r_reached is None


def test_arbitrary_bos_or_choch_event_price_cannot_prove_wick_outside_parent() -> None:
    assert first_wick_outside_parent_time(
        "BULLISH",
        100,
        200,
        [
            event("bos", "BOS_UP", "2026-01-02T00:00:00Z", 250),
            event("choch", "CHOCH_CLOSE", "2026-01-03T00:00:00Z", 260),
        ],
    ) is None


def test_approved_ohlc_or_breach_evidence_can_prove_objective_reach() -> None:
    candle = first_wick_outside_parent_time(
        "BULLISH",
        100,
        200,
        [event("candle", "CANDLE_OHLC", "2026-01-02T00:00:00Z", 0, high=201)],
    )
    breach = first_wick_outside_parent_time(
        "BEARISH",
        100,
        200,
        [event("breach", "BOUNDARY_BREACH_DOWN", "2026-01-03T00:00:00Z", 99)],
    )
    assert candle == "2026-01-02T00:00:00Z"
    assert breach == "2026-01-03T00:00:00Z"


def test_mfe_mae_remain_unavailable_without_sufficient_path_evidence() -> None:
    outcome = evaluate_outcome(
        child_direction="BULLISH",
        first_target=120,
        invalidation_price=90,
        entry_candidates=[
            EntryCandidate("CHOCH_CLOSE", "2026-01-01T00:00:00Z", 100, "M15", "VALID")
        ],
        future_events=[event("target", "SWEEP_HIGH", "2026-01-02T00:00:00Z", 130)],
    )
    risk = outcome["entry_risk_assessments"][0]
    assert outcome["maximum_favourable_excursion"] is None
    assert outcome["maximum_adverse_excursion"] is None
    assert risk.maximum_favourable_excursion is None
    assert risk.maximum_adverse_excursion is None


def test_qualifying_pullback_remains_test_required() -> None:
    state = first_state(build_first_query_doctrine_report(master_map()))
    assert "QUALIFYING_PULLBACK" in state["test_required_reasons"]


def test_qualifying_pullback_does_not_block_query_ready() -> None:
    state = first_state(build_first_query_doctrine_report(master_map()))
    assert "QUALIFYING_PULLBACK" in state["test_required_reasons"]
    assert state["status"] == "QUERY_READY"


def test_future_event_leakage_prevention() -> None:
    state = first_state(build_first_query_doctrine_report(master_map()))
    assert "e-future" not in state["canonical_event_ids"]
    assert state["target_reach_time"] == "2026-01-14T00:00:00Z"


def test_deterministic_repeated_runs_ignore_timestamp() -> None:
    first = build_first_query_doctrine_report(master_map(), generated_at_utc="2026-07-15T00:00:00Z")
    second = build_first_query_doctrine_report(master_map(), generated_at_utc="2026-07-16T00:00:00Z")
    assert first["determinism_hash"] == second["determinism_hash"]
    assert first["states"] == second["states"]


def test_known_master_map_canonical_regression_fields_are_preserved() -> None:
    source = master_map(parent_direction="DOWN", daily_direction="DOWN")
    weekly = source["root"]["children"][0]
    trusted_weekly = source["trusted_root"]["children"][0]
    for node in (weekly, trusted_weekly):
        node["id"] = "mm:range:82f4324c5cf54c71b8b9"
        node["range_high"] = 5598.08
        node["range_low"] = 4274.60
        node["range_high_time"] = "2026-01-25T00:00:00Z"
        node["range_low_time"] = "2025-12-28T00:00:00Z"
        node["status"] = "BROKEN"
        node["direction_of_break"] = "DOWN"
        node["inactive_from_time"] = "2026-03-23T00:00:00Z"
        node["source_refs"] = [
            {"source_record_id": "418"},
            {"source_record_id": "431", "lifecycle_status": "PENDING"},
            {"source_record_id": "453", "lifecycle_status": "PENDING"},
            {"source_record_id": "455"},
        ]
    state = first_state(build_first_query_doctrine_report(source))
    assert state["parent_range_id"] == "mm:range:82f4324c5cf54c71b8b9"
    assert state["parent_active_range_boundaries"] == {"low": 4274.6, "high": 5598.08}
    assert {ref["source_record_id"] for ref in state["source_provenance"]["parent_source_refs"]} == {
        "418",
        "431",
        "453",
        "455",
    }


def test_wrong_master_map_schema_is_rejected() -> None:
    source = master_map()
    source["schema_version"] = "wrong"
    with pytest.raises(DoctrineError, match="schema"):
        build_first_query_doctrine_report(source)


def test_cli_writes_disposable_report(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "master-map.json"
    output = tmp_path / "doctrine-report.json"
    source.write_text(json.dumps(master_map()), encoding="utf-8")
    assert main(["--master-map", str(source), "--output", str(output), "--compact"]) == 0
    summary = json.loads(capsys.readouterr().out)
    report = json.loads(output.read_text(encoding="utf-8"))
    assert summary["query_ready_count"] == 1
    assert report["schema_version"] == "xauusd_first_query_doctrine_report_v0.1"
