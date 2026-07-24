from __future__ import annotations

from typing import Any

from range_library_memory.doctrine_drafts.daily.weekly_relative import (
    run_daily_child_trend_classification,
    run_pdl_pdh_reversal_sweep,
)


class Context:
    def __init__(
        self,
        weekly: dict[str, Any],
        daily: list[dict[str, Any]],
        memory: dict[str, dict[str, Any]],
        candles: list[dict[str, Any]],
    ) -> None:
        self.weekly = weekly
        self.daily = daily
        self.memory = memory
        self.candles = candles

    def selected_ranges(self, *, layer: str) -> list[dict[str, Any]]:
        return [self.weekly] if layer == "WEEKLY" else self.daily if layer == "DAILY" else []

    def approved_memory(self, canonical_range_id: str) -> dict[str, Any]:
        return self.memory.get(canonical_range_id, {})

    def latest_candle_time(self, timeframe: str) -> str | None:
        return self.candles[-1]["time"] if self.candles else None

    def load_candles(self, *, timeframe: str, start_time: str, end_time: str) -> list[dict[str, Any]]:
        return [row for row in self.candles if start_time <= row["time"] <= end_time]


def approved(payload: dict[str, Any], status: str = "COMPLETE") -> dict[str, Any]:
    return {"processing_status": status, "payload": payload}


def payload(result: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    row = result["outputs"][0]
    return row["processing_status"], row["payload"]


def test_active_weekly_without_bos_uses_anchor_chronology_for_child_trend() -> None:
    daily = {
        "id": "d1",
        "structure_layer": "DAILY",
        "direct_parent_link_status": "TRUSTED",
        "range_high": 100.0,
        "range_low": 90.0,
        "range_high_time": "2026-01-12T00:00:00Z",
        "range_low_time": "2026-01-11T00:00:00Z",
        "children": [],
    }
    weekly = {
        "id": "w-active",
        "structure_layer": "WEEKLY",
        "range_high": 120.0,
        "range_low": 80.0,
        "range_high_time": "2026-01-10T00:00:00Z",
        "range_low_time": "2026-01-01T00:00:00Z",
        "inactive_from_time": None,
        "children": [daily],
    }
    relationship = {
        "candidate_freeze_time": "2026-01-20T00:00:00Z",
        "future_daily_ranges_excluded": 0,
        "relationship_rows": [{
            "daily_range_id": "d1",
            "daily_sequence_number": 1,
            "daily_direction": "UP",
            "daily_created_time": "2026-01-12T00:00:00Z",
            "daily_start_time": "2026-01-11T00:00:00Z",
            "daily_end_time": None,
            "daily_status_at_freeze": "ACTIVE",
            "historically_available": True,
            "relationship_valid": True,
        }],
    }
    context = Context(
        weekly,
        [daily],
        {"w-active": {
            "weekly_structure": approved({
                "bos_direction": None,
                "bos_time": None,
                "reason_codes": ["WEEKLY_BOS_NOT_FOUND"],
            }, "PENDING"),
            "weekly_daily_relationship_builder": approved(relationship),
        }},
        [],
    )

    status, result = payload(run_daily_child_trend_classification(context))

    assert status == "COMPLETE"
    assert result["weekly_direction"] == "UP"
    assert result["weekly_direction_basis"] == "WEEKLY_ANCHOR_CHRONOLOGY"
    assert result["classifications"][0]["trend_role"] == "PROTREND"


def test_active_weekly_snapshot_can_scan_pdl_sweep_without_weekly_bos() -> None:
    weekly = {
        "id": "w-active",
        "structure_layer": "WEEKLY",
        "range_high": 120.0,
        "range_low": 80.0,
        "range_high_time": "2026-01-01T00:00:00Z",
        "range_low_time": "2026-01-01T00:00:00Z",
        "inactive_from_time": None,
        "children": [],
    }
    relationship = approved({
        "candidate_freeze_time": "2026-01-02T00:00:00Z",
        "relationship_rows": [],
        "future_daily_ranges_excluded": 0,
    })
    candles = [
        {"time": "2026-01-01T00:00:00Z", "open": 95.0, "high": 100.0, "low": 85.0, "close": 95.0},
        {"time": "2026-01-02T00:00:00Z", "open": 95.0, "high": 101.0, "low": 84.0, "close": 90.0},
    ]
    context = Context(
        weekly,
        [],
        {"w-active": {"weekly_daily_relationship_builder": relationship}},
        candles,
    )

    status, result = payload(run_pdl_pdh_reversal_sweep(context))

    assert status == "COMPLETE"
    assert result["pdl_sweep_count"] == 1
    assert result["primary_event"]["event_type"] == "PDL_REVERSAL_SWEEP"
