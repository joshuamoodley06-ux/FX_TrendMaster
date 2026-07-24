from __future__ import annotations

from typing import Any

from range_library_memory.doctrine_drafts.daily.approved_ports import (
    run_daily_bos,
    run_daily_extreme_rejection_destination,
    run_daily_movement_classification,
    run_daily_profile_classification,
    run_daily_reclaim,
    run_daily_reclaim_depth,
)
from range_library_memory.doctrine_drafts.daily.catalog import DAILY_DRAFT_CATALOG
from range_library_memory.doctrine_drafts.daily.weekly_relative import (
    run_daily_child_trend_classification,
    run_daily_profile_streaks,
    run_first_daily_at_weekly_extreme_rejection,
    run_first_daily_external_to_internal,
    run_pdl_pdh_reversal_sweep,
)


class DraftContext:
    def __init__(
        self,
        weekly: list[dict[str, Any]],
        daily: list[dict[str, Any]],
        *,
        memory: dict[str, dict[str, Any]] | None = None,
        candles: dict[str, list[dict[str, Any]]] | None = None,
    ) -> None:
        self._weekly = weekly
        self._daily = daily
        self._memory = memory or {}
        self._candles = candles or {}
        self.case_ref = "CASE-DAILY-DRAFT"

    def selected_ranges(self, *, layer: str) -> list[dict[str, Any]]:
        return list(self._weekly if layer == "WEEKLY" else self._daily if layer == "DAILY" else [])

    def approved_memory(self, canonical_range_id: str) -> dict[str, Any]:
        return self._memory.get(canonical_range_id, {})

    def latest_candle_time(self, timeframe: str) -> str | None:
        rows = self._candles.get(timeframe, [])
        return str(rows[-1]["time"]) if rows else None

    def load_candles(self, *, timeframe: str, start_time: str, end_time: str) -> list[dict[str, Any]]:
        return [
            row for row in self._candles.get(timeframe, [])
            if start_time <= str(row["time"]) <= end_time
        ]


def candle(time: str, open_: float, high: float, low: float, close: float) -> dict[str, Any]:
    return {"time": time, "open": open_, "high": high, "low": low, "close": close}


def daily_range(
    range_id: str,
    high: float,
    low: float,
    high_time: str,
    low_time: str,
    *,
    status: str = "ACTIVE",
) -> dict[str, Any]:
    return {
        "id": range_id,
        "node_type": "RANGE",
        "structure_layer": "DAILY",
        "source_timeframe": "D1",
        "range_high": high,
        "range_low": low,
        "range_high_time": high_time,
        "range_low_time": low_time,
        "active_from_time": max(high_time, low_time),
        "inactive_from_time": None,
        "status": status,
        "direct_parent_link_status": "TRUSTED",
        "children": [],
    }


def weekly_range(
    range_id: str,
    children: list[dict[str, Any]],
    *,
    high: float = 120.0,
    low: float = 80.0,
    high_time: str = "2026-01-10T00:00:00Z",
    low_time: str = "2026-01-01T00:00:00Z",
) -> dict[str, Any]:
    return {
        "id": range_id,
        "node_type": "RANGE",
        "structure_layer": "WEEKLY",
        "source_timeframe": "W1",
        "range_high": high,
        "range_low": low,
        "range_high_time": high_time,
        "range_low_time": low_time,
        "active_from_time": max(high_time, low_time),
        "inactive_from_time": None,
        "status": "ACTIVE",
        "direct_parent_link_status": "TRUSTED",
        "children": children,
    }


def approved(payload: dict[str, Any], status: str = "COMPLETE") -> dict[str, Any]:
    return {"processing_status": status, "payload": payload}


def relationship(rows: list[dict[str, Any]], freeze: str = "2026-01-20T00:00:00Z") -> dict[str, Any]:
    return approved({
        "candidate_freeze_time": freeze,
        "future_daily_ranges_excluded": 0,
        "relationship_rows": rows,
    })


def relationship_row(
    range_id: str,
    sequence: int,
    direction: str,
    created: str,
    end: str | None = None,
) -> dict[str, Any]:
    return {
        "daily_range_id": range_id,
        "daily_sequence_number": sequence,
        "daily_direction": direction,
        "daily_start_time": created,
        "daily_created_time": created,
        "daily_end_time": end,
        "daily_status_at_freeze": "ACTIVE" if end is None else "BROKEN",
        "historically_available": True,
        "relationship_valid": True,
        "parent_link_valid": True,
    }


def payload_for(result: dict[str, Any], canonical_id: str) -> tuple[str, dict[str, Any]]:
    row = next(item for item in result["outputs"] if item["canonical_range_id"] == canonical_id)
    return row["processing_status"], row["payload"]


def test_catalog_contains_all_eleven_unregistered_daily_candidates() -> None:
    assert [item.script_key for item in DAILY_DRAFT_CATALOG] == [
        "daily_structure",
        "daily_reclaim",
        "daily_reclaim_depth",
        "daily_movement_classification",
        "daily_profile_classification",
        "daily_extreme_rejection_destination",
        "daily_child_trend_classification",
        "first_daily_external_to_internal",
        "first_daily_at_weekly_extreme_rejection",
        "daily_profile_streaks",
        "pdl_pdh_reversal_sweep",
    ]
    assert [item.planned_order for item in DAILY_DRAFT_CATALOG] == list(range(100, 201, 10))


def test_daily_bos_ignores_exact_touch_and_uses_first_strict_wick_break() -> None:
    d1 = daily_range("d1", 100, 90, "2026-01-02T00:00:00Z", "2026-01-01T00:00:00Z")
    weekly = weekly_range("w1", [d1])
    context = DraftContext([weekly], [d1], candles={"D1": [
        candle("2026-01-03T00:00:00Z", 95, 100, 94, 99),
        candle("2026-01-04T00:00:00Z", 99, 101, 96, 100),
    ]})

    status, payload = payload_for(run_daily_bos(context), "d1")

    assert status == "COMPLETE"
    assert payload["bos_direction"] == "BOS_UP"
    assert payload["bos_time"] == "2026-01-04T00:00:00Z"
    assert payload["days_to_bos"] == 2


def test_daily_reclaim_supports_same_bos_candle_reclaim() -> None:
    d1 = daily_range("d1", 100, 90, "2026-01-02T00:00:00Z", "2026-01-01T00:00:00Z")
    weekly = weekly_range("w1", [d1])
    memory = {"d1": {"daily_structure": approved({
        "range_defined_at": "2026-01-02T00:00:00Z",
        "bos_direction": "BOS_UP",
        "bos_time": "2026-01-04T00:00:00Z",
    })}}
    context = DraftContext([weekly], [d1], memory=memory, candles={"D1": [
        candle("2026-01-04T00:00:00Z", 99, 102, 96, 99),
    ]})

    status, payload = payload_for(run_daily_reclaim(context), "d1")

    assert status == "COMPLETE"
    assert payload["reclaim_status"] == "RECLAIMED"
    assert payload["same_candle_reclaim"] is True
    assert payload["days_to_reclaim"] == 0


def test_daily_reclaim_depth_cannot_borrow_range_two_from_another_weekly_parent() -> None:
    source = daily_range("source", 100, 80, "2026-01-02T00:00:00Z", "2026-01-01T00:00:00Z")
    valid_r2 = daily_range("valid-r2", 110, 90, "2026-01-07T00:00:00Z", "2026-01-05T00:00:00Z")
    wrong_parent = daily_range("wrong-parent", 108, 85, "2026-01-06T00:00:00Z", "2026-01-05T00:00:00Z")
    w1 = weekly_range("w1", [source, valid_r2])
    w2 = weekly_range("w2", [wrong_parent], high=140, low=110)
    memory = {"source": {
        "daily_structure": approved({
            "bos_direction": "BOS_UP",
            "bos_time": "2026-01-03T00:00:00Z",
        }),
        "daily_reclaim": approved({
            "reclaim_status": "RECLAIMED",
            "reclaim_time": "2026-01-04T00:00:00Z",
        }),
    }}
    context = DraftContext([w1, w2], [source, valid_r2, wrong_parent], memory=memory)

    status, payload = payload_for(run_daily_reclaim_depth(context), "source")

    assert status == "COMPLETE"
    assert payload["range2_id"] == "valid-r2"
    assert payload["range2_anchor_sequence"] == "OPPOSITE_THEN_CONTINUATION"
    assert payload["reclaim_depth_percent"] == 50.0


def test_daily_movement_classification_merges_consecutive_roles() -> None:
    source = daily_range("source", 100, 80, "2026-01-02T00:00:00Z", "2026-01-01T00:00:00Z")
    terminal = daily_range("terminal", 110, 90, "2026-01-06T00:00:00Z", "2026-01-05T00:00:00Z")
    weekly = weekly_range("w1", [source, terminal])
    memory = {
        "source": {"daily_structure": approved({
            "bos_direction": "BOS_UP",
            "bos_time": "2026-01-03T00:00:00Z",
        })},
        "terminal": {"daily_structure": approved({
            "bos_direction": "BOS_UP",
            "bos_time": "2026-01-07T00:00:00Z",
        })},
    }
    context = DraftContext([weekly], [source, terminal], memory=memory, candles={"D1": [
        candle("2026-01-04T00:00:00Z", 100, 101, 95, 96),
        candle("2026-01-05T00:00:00Z", 96, 102, 95, 101),
        candle("2026-01-06T00:00:00Z", 101, 105, 100, 104),
    ]})

    status, payload = payload_for(run_daily_movement_classification(context), "source")

    assert status == "COMPLETE"
    assert payload["movement_sequence"] == ["CT 1D", "PT 2D"]
    assert payload["movement_path"] == "CT 1D -> PT 2D -> BOS_UP"


def test_daily_profile_uses_approved_weekly_thresholds_and_abandonment_override() -> None:
    d1 = daily_range("d1", 100, 80, "2026-01-02T00:00:00Z", "2026-01-01T00:00:00Z")
    d2 = daily_range("d2", 110, 90, "2026-01-04T00:00:00Z", "2026-01-03T00:00:00Z")
    d3 = daily_range("d3", 120, 100, "2026-01-06T00:00:00Z", "2026-01-05T00:00:00Z")
    d4 = daily_range("d4", 130, 110, "2026-01-08T00:00:00Z", "2026-01-07T00:00:00Z")
    weekly = weekly_range("w1", [d1, d2, d3, d4])
    memory: dict[str, dict[str, Any]] = {}
    for range_id, depth in (("d1", 20.0), ("d2", 38.2), ("d3", 50.1)):
        memory[range_id] = {
            "daily_structure": approved({"bos_direction": "BOS_UP", "bos_time": "2026-01-10T00:00:00Z"}),
            "daily_reclaim": approved({"reclaim_status": "RECLAIMED", "next_bos_direction": "BOS_UP"}),
            "daily_reclaim_depth": approved({"reclaim_depth_percent": depth}),
        }
    memory["d4"] = {
        "daily_structure": approved({"bos_direction": "BOS_UP", "bos_time": "2026-01-10T00:00:00Z"}),
        "daily_reclaim": approved({"reclaim_status": "ABANDONED", "next_bos_direction": "BOS_UP"}),
    }
    context = DraftContext([weekly], [d1, d2, d3, d4], memory=memory)

    result = run_daily_profile_classification(context)

    assert payload_for(result, "d1")[1]["profile_classification"] == "S&R"
    assert payload_for(result, "d2")[1]["profile_classification"] == "S&R>FP"
    assert payload_for(result, "d3")[1]["profile_classification"] == "S&D"
    assert payload_for(result, "d4")[1]["classification_basis"] == "ABANDONED_SAME_DIRECTION_CONTINUATION_OVERRIDE"


def test_daily_extreme_rejection_tracks_destination_ladder() -> None:
    d1 = daily_range("d1", 100, 0, "2026-01-02T00:00:00Z", "2026-01-01T00:00:00Z")
    weekly = weekly_range("w1", [d1], high=150, low=-50)
    context = DraftContext([weekly], [d1], candles={"D1": [
        candle("2026-01-03T00:00:00Z", 25, 35, 20, 30),
        candle("2026-01-04T00:00:00Z", 30, 50, 28, 48),
        candle("2026-01-05T00:00:00Z", 48, 80, 45, 75),
        candle("2026-01-06T00:00:00Z", 75, 100, 70, 98),
    ]})

    status, payload = payload_for(run_daily_extreme_rejection_destination(context), "d1")

    assert status == "COMPLETE"
    assert payload["rejection_event_count"] >= 1
    assert payload["primary_event"]["origin_zone"] == "DISCOUNT_EXTREME"
    assert payload["primary_event"]["maximum_destination"] == "OPPOSITE_EXTERNAL"


def test_weekly_relative_trend_classifies_daily_children_protrend_and_countertrend() -> None:
    d1 = daily_range("d1", 100, 90, "2026-01-03T00:00:00Z", "2026-01-02T00:00:00Z")
    d2 = daily_range("d2", 105, 95, "2026-01-04T00:00:00Z", "2026-01-05T00:00:00Z")
    weekly = weekly_range("w1", [d1, d2])
    rows = [
        relationship_row("d1", 1, "UP", "2026-01-03T00:00:00Z"),
        relationship_row("d2", 2, "DOWN", "2026-01-05T00:00:00Z"),
    ]
    memory = {"w1": {
        "weekly_structure": approved({"bos_direction": "BOS_UP", "bos_time": "2026-01-20T00:00:00Z"}),
        "weekly_daily_relationship_builder": relationship(rows),
    }}
    context = DraftContext([weekly], [d1, d2], memory=memory)

    status, payload = payload_for(run_daily_child_trend_classification(context), "w1")

    assert status == "COMPLETE"
    assert [row["trend_role"] for row in payload["classifications"]] == ["PROTREND", "COUNTERTREND"]


def test_first_daily_external_to_internal_uses_ordered_valid_children() -> None:
    d1 = daily_range("d1", 100, 75, "2026-01-04T00:00:00Z", "2026-01-02T00:00:00Z")
    d2 = daily_range("d2", 110, 85, "2026-01-06T00:00:00Z", "2026-01-05T00:00:00Z")
    weekly = weekly_range("w1", [d1, d2], high=120, low=80)
    rows = [
        relationship_row("d1", 1, "UP", "2026-01-04T00:00:00Z"),
        relationship_row("d2", 2, "UP", "2026-01-06T00:00:00Z"),
    ]
    context = DraftContext([weekly], [d1, d2], memory={"w1": {
        "weekly_daily_relationship_builder": relationship(rows),
    }})

    status, payload = payload_for(run_first_daily_external_to_internal(context), "w1")

    assert status == "COMPLETE"
    assert payload["daily_range_id"] == "d1"
    assert payload["classification"] == "EXTERNAL_LOW_TO_INTERNAL"
    assert payload["origin_relation"] == "BEYOND_EXTERNAL"


def test_weekly_rejection_is_matched_to_daily_child_active_on_rejection_date() -> None:
    d1 = daily_range("d1", 100, 75, "2026-01-03T00:00:00Z", "2026-01-02T00:00:00Z")
    d2 = daily_range("d2", 110, 90, "2026-01-07T00:00:00Z", "2026-01-06T00:00:00Z")
    weekly = weekly_range("w1", [d1, d2])
    rows = [
        relationship_row("d1", 1, "UP", "2026-01-03T00:00:00Z", "2026-01-06T00:00:00Z"),
        relationship_row("d2", 2, "UP", "2026-01-07T00:00:00Z"),
    ]
    memory = {"w1": {
        "weekly_structure": approved({"bos_direction": "BOS_UP", "bos_time": "2026-01-20T00:00:00Z"}),
        "weekly_daily_relationship_builder": relationship(rows),
        "weekly_extreme_rejection_destination": approved({"rejection_events": [{
            "origin_zone": "DISCOUNT_EXTREME",
            "rejection_time": "2026-01-05T00:00:00Z",
            "maximum_destination": "FAIR_PRICE",
            "journey_status": "COMPLETE",
        }]}),
    }}
    context = DraftContext([weekly], [d1, d2], memory=memory)

    status, payload = payload_for(run_first_daily_at_weekly_extreme_rejection(context), "w1")

    assert status == "COMPLETE"
    assert payload["primary_match"]["daily_range_id"] == "d1"
    assert payload["primary_match"]["ownership_status"] == "MATCHED_ACTIVE_ON_REJECTION_DATE"


def test_daily_profile_streaks_count_consecutive_same_profile_children() -> None:
    children = [
        daily_range(f"d{index}", 100 + index, 90 + index, f"2026-01-0{index + 2}T00:00:00Z", f"2026-01-0{index + 1}T00:00:00Z")
        for index in range(1, 4)
    ]
    weekly = weekly_range("w1", children)
    rows = [relationship_row(f"d{index}", index, "UP", f"2026-01-0{index + 2}T00:00:00Z") for index in range(1, 4)]
    memory = {"w1": {"weekly_daily_relationship_builder": relationship(rows)}}
    memory.update({
        "d1": {"daily_profile_classification": approved({"profile_classification": "S&R"})},
        "d2": {"daily_profile_classification": approved({"profile_classification": "S&R"})},
        "d3": {"daily_profile_classification": approved({"profile_classification": "S&D"})},
    })
    context = DraftContext([weekly], children, memory=memory)

    status, payload = payload_for(run_daily_profile_streaks(context), "w1")

    assert status == "COMPLETE"
    assert payload["maximum_streak_profile"] == "S&R"
    assert payload["maximum_streak_length"] == 2
    assert payload["current_streak_profile"] == "S&D"
    assert payload["current_streak_length"] == 1


def test_pdl_and_pdh_reversal_sweeps_require_close_back_through_in_correct_weekly_zone() -> None:
    weekly = weekly_range("w1", [], high=120, low=80, high_time="2026-01-01T00:00:00Z", low_time="2026-01-01T00:00:00Z")
    memory = {"w1": {"weekly_daily_relationship_builder": relationship([], "2026-01-04T00:00:00Z")}}
    context = DraftContext([weekly], [], memory=memory, candles={"D1": [
        candle("2026-01-01T00:00:00Z", 95, 100, 85, 95),
        candle("2026-01-02T00:00:00Z", 95, 105, 84, 90),
        candle("2026-01-03T00:00:00Z", 100, 115, 95, 110),
        candle("2026-01-04T00:00:00Z", 110, 116, 100, 114),
    ]})

    status, payload = payload_for(run_pdl_pdh_reversal_sweep(context), "w1")

    assert status == "COMPLETE"
    assert payload["pdl_sweep_count"] == 1
    assert payload["pdh_sweep_count"] == 1
    assert [event["event_type"] for event in payload["sweep_events"]] == [
        "PDL_REVERSAL_SWEEP",
        "PDH_REVERSAL_SWEEP",
    ]
