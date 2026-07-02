from __future__ import annotations

from tools.mapping_quality_audit.audit_mapping_export import audit_export


def export_doc(ranges, events=None, formal_bos_events=None):
    return {
        "active_case_ref": "raw:test",
        "symbol": "XAUUSD",
        "saved_structural_ranges": {"ranges": ranges},
        "saved_structural_events": {"events": events or []},
        "formal_bos_events": formal_bos_events or [],
    }


def range_row(
    range_id,
    layer,
    parent_range_id="",
    start="2026-02-24T00:00:00Z",
    end="2026-03-03T00:00:00Z",
    status="ACTIVE",
    parent_link_status="OK",
    active_from_time="2026-02-24T00:00:00Z",
    inactive_from_time="",
):
    return {
        "range_id": str(range_id),
        "structure_layer": layer,
        "parent_range_id": str(parent_range_id) if parent_range_id else "",
        "status": status,
        "parent_link_status": parent_link_status,
        "range_high_price": "5418.89",
        "range_low_price": "5093.52",
        "range_high_time": start,
        "range_low_time": end,
        "range_start_time": start,
        "range_end_time": end,
        "active_from_time": active_from_time,
        "inactive_from_time": inactive_from_time,
    }


def clean_chain():
    return [
        range_row("W1", "WEEKLY"),
        range_row("D1", "DAILY", "W1"),
        range_row("I1", "INTRADAY", "D1"),
    ]


def test_clean_weekly_daily_intraday_chain_is_research_ready():
    report, _, _ = audit_export(export_doc(clean_chain()))

    assert report["research_readiness_status"] == "RESEARCH_READY"
    assert report["range_counts_by_layer"] == {"WEEKLY": 1, "DAILY": 1, "INTRADAY": 1}


def test_duplicate_range_group_is_detected():
    duplicate = range_row("I2", "INTRADAY", "D1")
    report, _, _ = audit_export(export_doc([*clean_chain(), duplicate]))

    assert report["research_readiness_status"] == "AUDIT_READY"
    assert report["duplicate_range_groups"][0]["ids"] == ["I1", "I2"]


def test_needs_review_range_blocks_research_readiness():
    rows = clean_chain()
    rows[2]["parent_link_status"] = "NEEDS_REVIEW"

    report, _, _ = audit_export(export_doc(rows))

    assert report["research_readiness_status"] == "AUDIT_READY"
    assert report["ranges_needing_review"][0]["range_id"] == "I1"


def test_inactive_before_active_is_lifecycle_issue():
    rows = clean_chain()
    rows[1]["active_from_time"] = "2026-03-03T00:00:00Z"
    rows[1]["inactive_from_time"] = "2026-03-02T23:59:59Z"

    report, _, _ = audit_export(export_doc(rows))

    assert report["research_readiness_status"] == "AUDIT_READY"
    assert report["lifecycle_issues"][0]["issue_code"] == "LIFECYCLE_INVERSION"


def test_bos_event_missing_active_range_id_is_detected():
    events = [{"event_id": "E1", "structure_layer": "DAILY", "event_type": "BOS_UP"}]

    report, _, _ = audit_export(export_doc(clean_chain(), events))

    assert report["research_readiness_status"] == "AUDIT_READY"
    assert report["bos_linkage_issues"][0]["issue_code"] == "BOS_MISSING_ACTIVE_RANGE_ID"


def test_micro_event_without_micro_range_is_warned():
    events = [{"event_id": "E1", "structure_layer": "MICRO", "event_type": "CUSTOM_EVENT"}]

    report, _, _ = audit_export(export_doc(clean_chain(), events))

    assert report["research_readiness_status"] == "RESEARCH_READY"
    assert report["micro_event_without_micro_range_warning"] is True


def test_focused_chain_ignores_duplicate_outside_subtree():
    outside_a = range_row("X1", "DAILY", "OTHER_PARENT", start="2026-01-01T00:00:00Z", end="2026-01-02T00:00:00Z")
    outside_b = range_row("X2", "DAILY", "OTHER_PARENT", start="2026-01-01T00:00:00Z", end="2026-01-02T00:00:00Z")

    report, _, _ = audit_export(export_doc([*clean_chain(), outside_a, outside_b]), focus_root_range_id="W1")

    assert report["duplicate_range_groups"][0]["ids"] == ["X1", "X2"]
    assert report["research_readiness_status"] == "RESEARCH_READY"
    assert report["out_of_focus_ranges_count"] == 2


def test_focused_chain_fails_when_duplicate_is_inside_subtree():
    duplicate = range_row("I2", "INTRADAY", "D1")

    report, _, _ = audit_export(export_doc([*clean_chain(), duplicate]), focus_root_range_id="W1")

    assert report["research_readiness_status"] == "AUDIT_READY"
    assert report["scope_quality"]["applicable_duplicate_range_groups"][0]["ids"] == ["I1", "I2"]


def test_focused_chain_events_include_active_or_direct_range_links():
    events = [
        {"event_id": "E1", "structure_layer": "INTRADAY", "event_type": "CUSTOM_EVENT", "active_range_id": "I1"},
        {"event_id": "E2", "structure_layer": "DAILY", "event_type": "CUSTOM_EVENT", "range_id": "D1"},
        {"event_id": "E3", "structure_layer": "DAILY", "event_type": "CUSTOM_EVENT", "range_id": "OUT"},
    ]

    report, _, _ = audit_export(export_doc(clean_chain(), events), focus_root_range_id="W1")

    assert report["focus_chain_event_ids"] == ["E1", "E2"]
