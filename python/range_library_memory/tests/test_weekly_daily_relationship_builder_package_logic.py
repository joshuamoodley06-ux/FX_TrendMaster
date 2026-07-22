from __future__ import annotations

from range_library_memory.doctrine_packages import weekly_daily_relationship_builder


class FakeContext:
    def __init__(self, memory: dict) -> None:
        self.memory = memory

    def selected_ranges(self, *, layer: str | None = None):
        assert layer == "WEEKLY"
        return ({"id": "weekly-1"},)

    def approved_memory(self, canonical_range_id: str):
        assert canonical_range_id == "weekly-1"
        return self.memory


def _entry(payload: dict, processing_status: str = "COMPLETE") -> dict:
    return {"processing_status": processing_status, "payload": payload}


def _child(
    identity: str,
    *,
    start: str,
    created: str,
    end: str | None = None,
    status: str = "ACTIVE",
    link_valid: bool = True,
    low_time: str | None = None,
    high_time: str | None = None,
) -> dict:
    return {
        "daily_range_id": identity,
        "parent_range_id": "weekly-1",
        "parent_link_status": "VALID" if link_valid else "INVALID",
        "parent_link_valid": link_valid,
        "daily_start_time": start,
        "daily_created_time": created,
        "daily_end_time": end,
        "daily_status": status,
        "direction_of_break": None,
        "range_low_time": low_time or start,
        "range_high_time": high_time or created,
    }


def _run(payload: dict, processing_status: str = "COMPLETE") -> dict:
    memory = {
        "daily_mapping_coverage_audit": _entry(payload, processing_status),
    }
    return weekly_daily_relationship_builder.run(FakeContext(memory))["outputs"][0]


def test_orders_daily_children_and_excludes_future_structure() -> None:
    payload = {
        "candidate_freeze_time": "2025-03-01T00:00:00Z",
        "coverage_status": "COMPLETE",
        "daily_children": [
            _child(
                "daily-future",
                start="2025-04-01T00:00:00Z",
                created="2025-04-02T00:00:00Z",
            ),
            _child(
                "daily-active",
                start="2025-02-01T00:00:00Z",
                created="2025-02-02T00:00:00Z",
            ),
            _child(
                "daily-broken",
                start="2025-01-01T00:00:00Z",
                created="2025-01-02T00:00:00Z",
                end="2025-01-25T00:00:00Z",
                status="BROKEN",
            ),
        ],
    }

    result = _run(payload)
    rows = result["payload"]["relationship_rows"]

    assert result["processing_status"] == "COMPLETE"
    assert [row["daily_range_id"] for row in rows] == [
        "daily-broken",
        "daily-active",
        "daily-future",
    ]
    assert [row["daily_sequence_number"] for row in rows] == [1, 2, 3]
    assert [row["daily_status_at_freeze"] for row in rows] == [
        "BROKEN",
        "ACTIVE",
        "NOT_YET_CREATED",
    ]
    assert rows[2]["historically_available"] is False
    assert rows[2]["relationship_valid"] is False
    assert result["payload"]["future_daily_ranges_excluded"] == 1
    assert result["payload"]["active_daily_range_id"] == "daily-active"
    assert result["payload"]["previous_daily_range_id"] == "daily-broken"


def test_anchor_chronology_supplies_factual_daily_direction() -> None:
    payload = {
        "candidate_freeze_time": "2025-03-01T00:00:00Z",
        "coverage_status": "COMPLETE",
        "daily_children": [
            _child(
                "daily-up",
                start="2025-01-01T00:00:00Z",
                created="2025-01-02T00:00:00Z",
                low_time="2025-01-01T00:00:00Z",
                high_time="2025-01-02T00:00:00Z",
            ),
            _child(
                "daily-down",
                start="2025-02-01T00:00:00Z",
                created="2025-02-02T00:00:00Z",
                low_time="2025-02-02T00:00:00Z",
                high_time="2025-02-01T00:00:00Z",
            ),
        ],
    }

    rows = _run(payload)["payload"]["relationship_rows"]

    assert rows[0]["daily_direction"] == "UP"
    assert rows[1]["daily_direction"] == "DOWN"


def test_abandoned_state_is_preserved_at_freeze() -> None:
    payload = {
        "candidate_freeze_time": "2025-03-01T00:00:00Z",
        "coverage_status": "COMPLETE",
        "daily_children": [
            _child(
                "daily-abandoned",
                start="2025-01-01T00:00:00Z",
                created="2025-01-02T00:00:00Z",
                end="2025-02-01T00:00:00Z",
                status="ABANDONED",
            ),
        ],
    }

    row = _run(payload)["payload"]["relationship_rows"][0]

    assert row["daily_status_at_freeze"] == "ABANDONED"
    assert row["relationship_valid"] is True


def test_not_mapped_coverage_produces_valid_empty_relationship_table() -> None:
    result = _run({
        "candidate_freeze_time": "2024-06-01T00:00:00Z",
        "coverage_status": "NOT_MAPPED",
        "daily_children": [],
    })

    assert result["processing_status"] == "COMPLETE"
    assert result["payload"]["relationship_rows"] == []
    assert result["payload"]["daily_sequence_summary"] == "NO_LINKED_DAILY_RANGES"
    assert result["payload"]["reason_codes"] == ["DAILY_NOT_MAPPED_AT_WEEKLY_FREEZE"]


def test_invalid_historical_relationship_requires_review() -> None:
    result = _run({
        "candidate_freeze_time": "2025-03-01T00:00:00Z",
        "coverage_status": "COMPLETE",
        "daily_children": [
            _child(
                "daily-invalid",
                start="2025-01-01T00:00:00Z",
                created="2025-01-02T00:00:00Z",
                link_valid=False,
            ),
        ],
    })

    assert result["processing_status"] == "NEEDS_REVIEW"
    assert result["payload"]["invalid_relationship_count"] == 1
    assert result["payload"]["relationship_rows"][0]["parent_link_valid"] is False
    assert result["payload"]["reason_codes"] == [
        "ONE_OR_MORE_WEEKLY_DAILY_RELATIONSHIPS_INVALID"
    ]


def test_missing_approved_coverage_memory_stays_pending() -> None:
    result = weekly_daily_relationship_builder.run(FakeContext({}))["outputs"][0]

    assert result["processing_status"] == "PENDING"
    assert result["payload"]["reason_codes"] == [
        "APPROVED_DAILY_MAPPING_COVERAGE_MEMORY_MISSING"
    ]
