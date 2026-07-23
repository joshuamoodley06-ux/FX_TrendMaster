from __future__ import annotations

from range_library_memory.doctrine_packages import daily_mapping_coverage_audit


class FakeContext:
    case_ref = "CASE"

    def __init__(self, weekly: dict, daily: list[dict], latest: dict[str, str | None]) -> None:
        self.weekly = weekly
        self.daily = daily
        self.latest = latest

    def selected_ranges(self, *, layer: str | None = None):
        if layer == "WEEKLY":
            return (self.weekly,)
        if layer == "DAILY":
            return tuple(self.daily)
        return ()

    def review_ranges(self, *, layer: str | None = None):
        return ()

    def approved_memory(self, canonical_range_id: str):
        assert canonical_range_id == self.weekly["id"]
        return {
            "weekly_structure": {
                "processing_status": "PENDING",
                "payload": {"bos_time": None},
            }
        }

    def latest_candle_time(self, timeframe: str):
        return self.latest.get(timeframe)


def _daily(identity: str, *, start: str, created: str) -> dict:
    return {
        "id": identity,
        "structure_layer": "DAILY",
        "range_low_time": start,
        "range_high_time": created,
        "active_from_time": created,
        "inactive_from_time": None,
        "status": "ACTIVE",
        "direction_of_break": None,
        "direct_parent_link_status": "VALID",
        "source_refs": [{"case_ref": "CASE", "source_record_id": identity}],
        "children": [],
    }


def _weekly(children: list[dict]) -> dict:
    return {
        "id": "weekly-active",
        "structure_layer": "WEEKLY",
        "range_low_time": "2026-04-12T00:00:00Z",
        "range_high_time": "2026-04-12T00:00:00Z",
        "active_from_time": "2026-04-12T00:00:00Z",
        "inactive_from_time": None,
        "status": "ACTIVE",
        "source_refs": [{"case_ref": "CASE", "source_record_id": "weekly-active"}],
        "children": children,
    }


def test_active_weekly_without_bos_uses_latest_d1_snapshot() -> None:
    first = _daily(
        "daily-1",
        start="2026-04-14T00:00:00Z",
        created="2026-04-15T00:00:00Z",
    )
    second = _daily(
        "daily-2",
        start="2026-06-01T00:00:00Z",
        created="2026-06-02T00:00:00Z",
    )
    future = _daily(
        "daily-future",
        start="2026-08-01T00:00:00Z",
        created="2026-08-02T00:00:00Z",
    )
    weekly = _weekly([future, second, first])
    context = FakeContext(
        weekly,
        [first, second, future],
        {"D1": "2026-07-22T00:00:00Z", "W1": "2026-07-19T00:00:00Z"},
    )

    result = daily_mapping_coverage_audit.run(context)["outputs"][0]
    payload = result["payload"]

    assert result["processing_status"] == "COMPLETE"
    assert payload["weekly_story_state"] == "IN_PROGRESS"
    assert payload["freeze_basis"] == "LATEST_D1_CANDLE"
    assert payload["candidate_freeze_time"] == "2026-07-22T00:00:00Z"
    assert payload["weekly_story"] == "2026-04-12 -> 2026-07-22 (IN PROGRESS)"
    assert payload["coverage_status"] == "COMPLETE"
    assert payload["daily_ranges_found"] == 2
    assert payload["first_daily_child"] == "2026-04-15"
    assert payload["last_daily_child_at_freeze"] == "2026-06-02"
    assert payload["future_daily_ranges_excluded"] == 1
    assert payload["reason_codes"] == [
        "IN_PROGRESS_WEEKLY_STORY_FULLY_INSIDE_DAILY_MAPPING_ERA"
    ]
    assert [child["daily_range_id"] for child in payload["daily_children"]] == [
        "daily-1",
        "daily-2",
        "daily-future",
    ]


def test_active_weekly_falls_back_to_latest_w1_when_d1_is_unavailable() -> None:
    child = _daily(
        "daily-1",
        start="2026-04-14T00:00:00Z",
        created="2026-04-15T00:00:00Z",
    )
    weekly = _weekly([child])
    context = FakeContext(
        weekly,
        [child],
        {"D1": None, "W1": "2026-07-19T00:00:00Z"},
    )

    result = daily_mapping_coverage_audit.run(context)["outputs"][0]

    assert result["processing_status"] == "COMPLETE"
    assert result["payload"]["weekly_story_state"] == "IN_PROGRESS"
    assert result["payload"]["freeze_basis"] == "LATEST_W1_CANDLE"
    assert result["payload"]["candidate_freeze_time"] == "2026-07-19T00:00:00Z"
