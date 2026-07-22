from __future__ import annotations

from range_library_memory.doctrine_packages import daily_mapping_coverage_audit


class FakeContext:
    def __init__(self, weekly: list[dict], daily: list[dict], memory: dict) -> None:
        self.weekly = weekly
        self.daily = daily
        self.memory = memory

    def selected_ranges(self, *, layer: str | None = None):
        if layer == "WEEKLY":
            return tuple(self.weekly)
        if layer == "DAILY":
            return tuple(self.daily)
        return ()

    def approved_memory(self, canonical_range_id: str):
        return self.memory.get(canonical_range_id, {})


def _entry(payload: dict, processing_status: str = "COMPLETE") -> dict:
    return {"processing_status": processing_status, "payload": payload}


def _daily(
    identity: str,
    *,
    start: str,
    created: str,
    end: str | None = None,
    status: str = "ACTIVE",
    link: str = "VALID",
) -> dict:
    return {
        "id": identity,
        "structure_layer": "DAILY",
        "range_low_time": start,
        "range_high_time": created,
        "active_from_time": created,
        "inactive_from_time": end,
        "status": status,
        "direction_of_break": None,
        "direct_parent_link_status": link,
        "children": [],
    }


def _weekly(identity: str, *, start: str, children: list[dict]) -> dict:
    return {
        "id": identity,
        "structure_layer": "WEEKLY",
        "range_low_time": start,
        "range_high_time": start,
        "active_from_time": start,
        "inactive_from_time": None,
        "status": "BROKEN",
        "children": children,
    }


def _run(weekly: dict, daily: list[dict], freeze: str) -> dict:
    memory = {
        weekly["id"]: {
            "weekly_structure": _entry({"bos_time": freeze}),
        },
    }
    return daily_mapping_coverage_audit.run(
        FakeContext([weekly], daily, memory)
    )["outputs"][0]


def test_pre_2025_weekly_freeze_is_not_mapped_not_no_structure() -> None:
    mapped_daily = _daily(
        "daily-2025",
        start="2025-01-01T00:00:00Z",
        created="2025-01-02T00:00:00Z",
    )
    weekly = _weekly(
        "weekly-2024",
        start="2023-12-01T00:00:00Z",
        children=[],
    )

    result = _run(weekly, [mapped_daily], "2024-06-01T00:00:00Z")

    assert result["processing_status"] == "COMPLETE"
    assert result["payload"]["coverage_status"] == "NOT_MAPPED"
    assert result["payload"]["daily_mapping_coverage_available"] is False
    assert result["payload"]["reason_codes"] == ["DAILY_NOT_MAPPED_AT_WEEKLY_FREEZE"]
    assert "NO_DAILY_STRUCTURE" not in str(result)


def test_contiguous_daily_children_cover_weekly_freeze_window() -> None:
    first = _daily(
        "daily-1",
        start="2025-01-01T00:00:00Z",
        created="2025-01-02T00:00:00Z",
        end="2025-02-01T00:00:00Z",
        status="BROKEN",
    )
    second = _daily(
        "daily-2",
        start="2025-02-01T00:00:00Z",
        created="2025-02-02T00:00:00Z",
    )
    weekly = _weekly(
        "weekly-1",
        start="2025-01-01T00:00:00Z",
        children=[first, second],
    )

    result = _run(weekly, [first, second], "2025-03-01T00:00:00Z")

    assert result["processing_status"] == "COMPLETE"
    assert result["payload"]["coverage_status"] == "COMPLETE"
    assert result["payload"]["daily_ranges_found"] == 2
    assert result["payload"]["earliest_daily_range"] == "daily-1"
    assert result["payload"]["latest_daily_range"] == "daily-2"
    assert result["payload"]["front_gap"] is None
    assert result["payload"]["middle_gaps"] == []
    assert result["payload"]["tail_gap"] is None


def test_front_or_tail_only_is_partial() -> None:
    child = _daily(
        "daily-1",
        start="2025-01-10T00:00:00Z",
        created="2025-01-11T00:00:00Z",
    )
    weekly = _weekly(
        "weekly-1",
        start="2025-01-01T00:00:00Z",
        children=[child],
    )

    result = _run(weekly, [child], "2025-02-01T00:00:00Z")

    assert result["payload"]["coverage_status"] == "PARTIAL"
    assert result["payload"]["front_gap"] == {
        "start_time": "2025-01-01T00:00:00Z",
        "end_time": "2025-01-10T00:00:00Z",
    }


def test_middle_gap_is_mapping_gap() -> None:
    first = _daily(
        "daily-1",
        start="2025-01-01T00:00:00Z",
        created="2025-01-02T00:00:00Z",
        end="2025-01-20T00:00:00Z",
        status="BROKEN",
    )
    second = _daily(
        "daily-2",
        start="2025-02-01T00:00:00Z",
        created="2025-02-02T00:00:00Z",
    )
    weekly = _weekly(
        "weekly-1",
        start="2025-01-01T00:00:00Z",
        children=[first, second],
    )

    result = _run(weekly, [first, second], "2025-03-01T00:00:00Z")

    assert result["payload"]["coverage_status"] == "MAPPING_GAP"
    assert result["payload"]["middle_gaps"] == [{
        "start_time": "2025-01-20T00:00:00Z",
        "end_time": "2025-02-01T00:00:00Z",
    }]


def test_future_daily_child_is_retained_but_excluded_at_freeze() -> None:
    current = _daily(
        "daily-current",
        start="2025-01-01T00:00:00Z",
        created="2025-01-02T00:00:00Z",
    )
    future = _daily(
        "daily-future",
        start="2025-03-01T00:00:00Z",
        created="2025-03-02T00:00:00Z",
    )
    weekly = _weekly(
        "weekly-1",
        start="2025-01-01T00:00:00Z",
        children=[future, current],
    )

    result = _run(weekly, [current, future], "2025-02-01T00:00:00Z")

    assert result["payload"]["daily_ranges_mapped_total"] == 2
    assert result["payload"]["daily_ranges_found"] == 1
    assert result["payload"]["future_daily_ranges_excluded"] == 1
    assert [child["daily_range_id"] for child in result["payload"]["daily_children"]] == [
        "daily-current",
        "daily-future",
    ]


def test_invalid_saved_parent_link_is_reported_not_repaired() -> None:
    child = _daily(
        "daily-bad-parent",
        start="2025-01-01T00:00:00Z",
        created="2025-01-02T00:00:00Z",
        link="INVALID",
    )
    weekly = _weekly(
        "weekly-1",
        start="2025-01-01T00:00:00Z",
        children=[child],
    )

    result = _run(weekly, [child], "2025-02-01T00:00:00Z")

    assert result["processing_status"] == "NEEDS_REVIEW"
    assert result["payload"]["coverage_status"] == "INVALID_PARENT_LINK"
    assert result["payload"]["invalid_parent_links"] == ["daily-bad-parent"]
    assert result["payload"]["daily_children"][0]["parent_range_id"] == "weekly-1"
    assert result["payload"]["daily_children"][0]["parent_link_valid"] is False
