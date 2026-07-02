#!/usr/bin/env python
"""Read-only quality auditor for FXTM mapping export JSON files."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


EXPECTED_CHILD_BY_PARENT = {
    "MACRO": "WEEKLY",
    "WEEKLY": "DAILY",
    "DAILY": "INTRADAY",
    "INTRADAY": "MICRO",
}

BROKEN_STATUSES = {"BROKEN", "ABANDONED", "ARCHIVED"}
BOS_TYPES = {"BOS_UP", "BOS_DOWN", "BREAK_UP", "BREAK_DOWN"}


def _as_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, dict)]


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _id(value: Any) -> str:
    return _as_str(value)


def _upper(value: Any) -> str:
    return _as_str(value).upper()


def _is_blank(value: Any) -> bool:
    return value is None or _as_str(value) == ""


def _time_ms(value: Any) -> int | None:
    raw = _as_str(value)
    if not raw:
        return None
    if raw.isdigit():
        return int(raw)
    normalized = raw.replace(" ", "T")
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _range_id(row: dict[str, Any]) -> str:
    return _id(row.get("range_id") or row.get("id"))


def _event_row_id(row: dict[str, Any]) -> str:
    return _id(row.get("event_id") or row.get("id"))


def _range_signature(row: dict[str, Any]) -> tuple[str, ...]:
    return (
        _upper(row.get("structure_layer") or row.get("layer")),
        _id(row.get("parent_range_id")),
        _as_str(row.get("range_high_price") if row.get("range_high_price") is not None else row.get("range_high")),
        _as_str(row.get("range_low_price") if row.get("range_low_price") is not None else row.get("range_low")),
        _as_str(row.get("range_start_time")),
        _as_str(row.get("range_end_time")),
    )


def _event_signature(row: dict[str, Any]) -> tuple[str, ...]:
    return (
        _upper(row.get("structure_layer") or row.get("layer")),
        _upper(row.get("event_type") or row.get("type") or row.get("role")),
        _as_str(row.get("event_time") or row.get("time") or row.get("candle_time")),
        _as_str(row.get("event_price") if row.get("event_price") is not None else row.get("price")),
        _id(row.get("parent_range_id")),
        _id(row.get("active_range_id")),
    )


def _event_type(row: dict[str, Any]) -> str:
    return _upper(row.get("event_type") or row.get("type") or row.get("role"))


def _is_bos_event(row: dict[str, Any]) -> bool:
    event_type = _event_type(row)
    return event_type in BOS_TYPES or "BOS" in event_type


def load_export(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        return None, str(exc)
    if not isinstance(data, dict):
        return None, "export root must be a JSON object"
    return data, None


def extract_export_rows(data: dict[str, Any]) -> tuple[list[dict[str, Any]] | None, list[dict[str, Any]] | None, list[dict[str, Any]]]:
    ranges_container = data.get("saved_structural_ranges")
    events_container = data.get("saved_structural_events")
    if not isinstance(ranges_container, dict) or not isinstance(ranges_container.get("ranges"), list):
        return None, None, []
    if not isinstance(events_container, dict) or not isinstance(events_container.get("events"), list):
        return None, None, []
    ranges = _as_list(ranges_container.get("ranges"))
    events = _as_list(events_container.get("events"))
    formal_bos = _as_list(data.get("formal_bos_events"))
    return ranges, events, formal_bos


def build_child_lookup(ranges: Iterable[dict[str, Any]]) -> dict[str, list[str]]:
    children: dict[str, list[str]] = defaultdict(list)
    for row in ranges:
        parent_id = _id(row.get("parent_range_id"))
        rid = _range_id(row)
        if parent_id and rid:
            children[parent_id].append(rid)
    return dict(children)


def build_focus_range_ids(
    ranges: list[dict[str, Any]],
    focus_root_range_id: str | None = None,
    focus_parent_range_id: str | None = None,
) -> set[str]:
    selected = {_id(focus_root_range_id), _id(focus_parent_range_id)} - {""}
    if not selected:
        return set()
    child_lookup = build_child_lookup(ranges)
    focus_ids: set[str] = set()
    stack = list(selected)
    while stack:
        rid = stack.pop()
        if not rid or rid in focus_ids:
            continue
        focus_ids.add(rid)
        stack.extend(child_lookup.get(rid, []))
    return focus_ids


def _duplicate_groups(rows: list[dict[str, Any]], signature_fn: Any, id_fn: Any, group_type: str) -> list[dict[str, Any]]:
    groups: dict[tuple[str, ...], list[str]] = defaultdict(list)
    for row in rows:
        groups[signature_fn(row)].append(id_fn(row))
    result = []
    for signature, ids in groups.items():
        clean_ids = [rid for rid in ids if rid]
        if len(clean_ids) > 1:
            result.append({"type": group_type, "signature": list(signature), "ids": clean_ids})
    return result


def _case_summary(data: dict[str, Any], ranges: list[dict[str, Any]], events: list[dict[str, Any]], formal_bos: list[dict[str, Any]]) -> dict[str, Any]:
    current_case_container = data.get("current_case_container")
    current_case_symbol = current_case_container.get("symbol") if isinstance(current_case_container, dict) else None
    return {
        "active_case_ref": data.get("active_case_ref"),
        "current_case_container": current_case_container,
        "symbol": data.get("symbol") or current_case_symbol,
        "range_count": len(ranges),
        "event_count": len(events),
        "formal_bos_event_count": len(formal_bos),
    }


def _range_issue_map(
    ranges: list[dict[str, Any]],
    range_lookup: dict[str, dict[str, Any]],
) -> tuple[dict[str, list[str]], list[dict[str, Any]], list[dict[str, Any]]]:
    issue_map: dict[str, list[str]] = defaultdict(list)
    parent_child_summary: list[dict[str, Any]] = []
    lifecycle_issues: list[dict[str, Any]] = []

    for row in ranges:
        rid = _range_id(row)
        layer = _upper(row.get("structure_layer") or row.get("layer"))
        parent_id = _id(row.get("parent_range_id"))

        if _upper(row.get("parent_link_status")) == "NEEDS_REVIEW":
            issue_map[rid].append("PARENT_LINK_NEEDS_REVIEW")

        if parent_id:
            parent = range_lookup.get(parent_id)
            if not parent:
                issue_map[rid].append("MISSING_PARENT")
                parent_child_summary.append({
                    "range_id": rid,
                    "parent_range_id": parent_id,
                    "issue_code": "MISSING_PARENT",
                })
            else:
                parent_layer = _upper(parent.get("structure_layer") or parent.get("layer"))
                expected = EXPECTED_CHILD_BY_PARENT.get(parent_layer)
                if expected and expected != layer:
                    issue_map[rid].append("CHILD_LAYER_MISMATCH")
                    parent_child_summary.append({
                        "range_id": rid,
                        "parent_range_id": parent_id,
                        "parent_layer": parent_layer,
                        "child_layer": layer,
                        "expected_child_layer": expected,
                        "issue_code": "CHILD_LAYER_MISMATCH",
                    })

        missing_anchor = []
        for field in ("range_high_price", "range_low_price", "range_high_time", "range_low_time"):
            if _is_blank(row.get(field)):
                missing_anchor.append(field)
        if missing_anchor:
            issue_map[rid].append("MISSING_RH_RL_ANCHOR")

        active_ms = _time_ms(row.get("active_from_time") or row.get("range_start_time"))
        inactive_ms = _time_ms(row.get("inactive_from_time"))
        if active_ms is not None and inactive_ms is not None and inactive_ms < active_ms:
            issue_map[rid].append("LIFECYCLE_INVERSION")
            lifecycle_issues.append({
                "range_id": rid,
                "issue_code": "LIFECYCLE_INVERSION",
                "active_from_time": row.get("active_from_time"),
                "inactive_from_time": row.get("inactive_from_time"),
            })

        status = _upper(row.get("status"))
        if status in BROKEN_STATUSES and _is_blank(row.get("broken_by_event_id")):
            issue_map[rid].append("BROKEN_MISSING_BROKEN_BY_EVENT_ID")
            lifecycle_issues.append({
                "range_id": rid,
                "issue_code": "BROKEN_MISSING_BROKEN_BY_EVENT_ID",
            })
        if status in BROKEN_STATUSES and _is_blank(row.get("inactive_from_time")):
            issue_map[rid].append("BROKEN_MISSING_INACTIVE_FROM_TIME")
            lifecycle_issues.append({
                "range_id": rid,
                "issue_code": "BROKEN_MISSING_INACTIVE_FROM_TIME",
            })

    return dict(issue_map), parent_child_summary, lifecycle_issues


def _event_issue_map(
    events: list[dict[str, Any]],
    range_lookup: dict[str, dict[str, Any]],
) -> tuple[dict[str, list[str]], list[dict[str, Any]]]:
    issue_map: dict[str, list[str]] = defaultdict(list)
    bos_linkage_issues: list[dict[str, Any]] = []
    for row in events:
        eid = _event_row_id(row)
        active_range_id = _id(row.get("active_range_id"))
        if not _is_bos_event(row):
            continue
        if not active_range_id:
            issue_map[eid].append("BOS_MISSING_ACTIVE_RANGE_ID")
            bos_linkage_issues.append({
                "event_id": row.get("event_id"),
                "id": row.get("id"),
                "issue_code": "BOS_MISSING_ACTIVE_RANGE_ID",
            })
        elif active_range_id not in range_lookup:
            issue_map[eid].append("BOS_INVALID_ACTIVE_RANGE_ID")
            bos_linkage_issues.append({
                "event_id": row.get("event_id"),
                "id": row.get("id"),
                "active_range_id": active_range_id,
                "issue_code": "BOS_INVALID_ACTIVE_RANGE_ID",
            })
    return dict(issue_map), bos_linkage_issues


def _scope_report(
    ranges: list[dict[str, Any]],
    events: list[dict[str, Any]],
    range_lookup: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    range_issue_map, parent_child_summary, lifecycle_issues = _range_issue_map(ranges, range_lookup)
    event_issue_map, bos_linkage_issues = _event_issue_map(events, range_lookup)
    duplicate_range_groups = _duplicate_groups(ranges, _range_signature, _range_id, "range")
    duplicate_event_groups = _duplicate_groups(events, _event_signature, _event_row_id, "event")
    ranges_needing_review = [
        {
            "range_id": _range_id(row),
            "parent_link_status": row.get("parent_link_status"),
            "structure_layer": row.get("structure_layer") or row.get("layer"),
        }
        for row in ranges
        if _upper(row.get("parent_link_status")) == "NEEDS_REVIEW"
    ]
    return {
        "range_issue_map": range_issue_map,
        "event_issue_map": event_issue_map,
        "parent_child_summary": parent_child_summary,
        "ranges_needing_review": ranges_needing_review,
        "duplicate_range_groups": duplicate_range_groups,
        "duplicate_event_groups": duplicate_event_groups,
        "lifecycle_issues": lifecycle_issues,
        "bos_linkage_issues": bos_linkage_issues,
    }


def _research_ready(scope: dict[str, Any]) -> bool:
    disqualifying_range_codes = {
        "MISSING_PARENT",
        "PARENT_LINK_NEEDS_REVIEW",
        "LIFECYCLE_INVERSION",
        "BROKEN_MISSING_BROKEN_BY_EVENT_ID",
        "BROKEN_MISSING_INACTIVE_FROM_TIME",
    }
    disqualifying_event_codes = {
        "BOS_MISSING_ACTIVE_RANGE_ID",
        "BOS_INVALID_ACTIVE_RANGE_ID",
    }
    if scope["duplicate_range_groups"]:
        return False
    for codes in scope["range_issue_map"].values():
        if disqualifying_range_codes.intersection(codes):
            return False
    for codes in scope["event_issue_map"].values():
        if disqualifying_event_codes.intersection(codes):
            return False
    return True


def audit_export(
    data: dict[str, Any],
    focus_root_range_id: str | None = None,
    focus_parent_range_id: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    extracted_ranges, extracted_events, formal_bos = extract_export_rows(data)
    if extracted_ranges is None or extracted_events is None:
        report = {
            "case_summary": {},
            "case_hygiene_status": "EXPORT_INVALID",
            "range_counts_by_layer": {},
            "range_counts_by_status": {},
            "parent_child_summary": [],
            "ranges_needing_review": [],
            "duplicate_range_groups": [],
            "duplicate_event_groups": [],
            "lifecycle_issues": [],
            "bos_linkage_issues": [],
            "micro_event_without_micro_range_warning": False,
            "focus_chain_summary": {},
            "focus_chain_range_ids": [],
            "focus_chain_event_ids": [],
            "out_of_focus_ranges_count": 0,
            "research_readiness_status": "EXPORT_INVALID",
            "warnings": ["required range/event containers are missing or unusable"],
        }
        return report, [], []

    ranges = extracted_ranges
    events = extracted_events
    combined_events = events + formal_bos
    range_lookup = {_range_id(row): row for row in ranges if _range_id(row)}
    child_lookup = build_child_lookup(ranges)
    whole_scope = _scope_report(ranges, combined_events, range_lookup)
    focus_ids = build_focus_range_ids(ranges, focus_root_range_id, focus_parent_range_id)
    has_focus = bool(_id(focus_root_range_id) or _id(focus_parent_range_id))
    focus_events = [
        event for event in combined_events
        if _id(event.get("active_range_id")) in focus_ids or _id(event.get("range_id")) in focus_ids
    ]
    focus_ranges = [row for row in ranges if _range_id(row) in focus_ids]
    focus_scope = _scope_report(focus_ranges, focus_events, range_lookup) if has_focus else whole_scope
    applicable_scope = focus_scope if has_focus else whole_scope

    micro_range_count = sum(1 for row in ranges if _upper(row.get("structure_layer") or row.get("layer")) == "MICRO")
    micro_event_count = sum(1 for row in combined_events if _upper(row.get("structure_layer") or row.get("layer")) == "MICRO")
    micro_warning = micro_event_count > 0 and micro_range_count == 0
    whole_ready = _research_ready(whole_scope)
    research_ready = _research_ready(applicable_scope)
    issue_count = (
        len(whole_scope["ranges_needing_review"])
        + len(whole_scope["duplicate_range_groups"])
        + len(whole_scope["duplicate_event_groups"])
        + len(whole_scope["lifecycle_issues"])
        + len(whole_scope["bos_linkage_issues"])
        + len(whole_scope["parent_child_summary"])
    )
    case_hygiene_status = "CLEAN" if issue_count == 0 else "POLLUTED_BY_SMOKE_TESTING"
    report = {
        "case_summary": _case_summary(data, ranges, events, formal_bos),
        "case_hygiene_status": case_hygiene_status,
        "range_counts_by_layer": dict(Counter(_upper(row.get("structure_layer") or row.get("layer")) or "UNKNOWN" for row in ranges)),
        "range_counts_by_status": dict(Counter(_upper(row.get("status")) or "UNKNOWN" for row in ranges)),
        "parent_child_summary": whole_scope["parent_child_summary"],
        "ranges_needing_review": whole_scope["ranges_needing_review"],
        "duplicate_range_groups": whole_scope["duplicate_range_groups"],
        "duplicate_event_groups": whole_scope["duplicate_event_groups"],
        "lifecycle_issues": whole_scope["lifecycle_issues"],
        "bos_linkage_issues": whole_scope["bos_linkage_issues"],
        "micro_event_without_micro_range_warning": micro_warning,
        "focus_chain_summary": {
            "enabled": has_focus,
            "focus_root_range_id": _id(focus_root_range_id) or None,
            "focus_parent_range_id": _id(focus_parent_range_id) or None,
            "focus_range_count": len(focus_ranges) if has_focus else 0,
            "focus_event_count": len(focus_events) if has_focus else 0,
            "research_readiness_scope": "FOCUSED_CHAIN" if has_focus else "WHOLE_CASE",
        },
        "focus_chain_range_ids": sorted(focus_ids, key=str),
        "focus_chain_event_ids": sorted([_event_row_id(row) for row in focus_events if _event_row_id(row)], key=str),
        "out_of_focus_ranges_count": max(0, len(ranges) - len(focus_ranges)) if has_focus else 0,
        "research_readiness_status": "RESEARCH_READY" if research_ready else "AUDIT_READY",
        "warnings": ["MICRO events exist but MICRO range count is zero"] if micro_warning else [],
        "scope_quality": {
            "whole_case_research_ready": whole_ready,
            "applicable_duplicate_range_groups": applicable_scope["duplicate_range_groups"],
            "applicable_duplicate_event_groups": applicable_scope["duplicate_event_groups"],
            "applicable_ranges_needing_review": applicable_scope["ranges_needing_review"],
            "applicable_lifecycle_issues": applicable_scope["lifecycle_issues"],
            "applicable_bos_linkage_issues": applicable_scope["bos_linkage_issues"],
        },
        "_range_issue_map": whole_scope["range_issue_map"],
        "_event_issue_map": whole_scope["event_issue_map"],
    }
    return report, ranges, combined_events


def _range_csv_rows(ranges: list[dict[str, Any]], issue_map: dict[str, list[str]]) -> list[dict[str, Any]]:
    return [
        {
            "range_id": _range_id(row),
            "structure_layer": row.get("structure_layer") or row.get("layer"),
            "status": row.get("status"),
            "parent_range_id": row.get("parent_range_id"),
            "parent_link_status": row.get("parent_link_status"),
            "range_start_time": row.get("range_start_time"),
            "range_end_time": row.get("range_end_time"),
            "active_from_time": row.get("active_from_time"),
            "inactive_from_time": row.get("inactive_from_time"),
            "issue_codes": "|".join(issue_map.get(_range_id(row), [])),
        }
        for row in ranges
    ]


def _event_csv_rows(events: list[dict[str, Any]], issue_map: dict[str, list[str]]) -> list[dict[str, Any]]:
    return [
        {
            "event_id": row.get("event_id"),
            "id": row.get("id"),
            "event_type": row.get("event_type") or row.get("type") or row.get("role"),
            "structure_layer": row.get("structure_layer") or row.get("layer"),
            "event_time": row.get("event_time") or row.get("time") or row.get("candle_time"),
            "event_price": row.get("event_price") if row.get("event_price") is not None else row.get("price"),
            "active_range_id": row.get("active_range_id"),
            "range_id": row.get("range_id"),
            "parent_range_id": row.get("parent_range_id"),
            "issue_codes": "|".join(issue_map.get(_event_row_id(row), [])),
        }
        for row in events
    ]


def write_outputs(report: dict[str, Any], ranges: list[dict[str, Any]], events: list[dict[str, Any]], out_dir: Path) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    public_report = dict(report)
    range_issue_map = public_report.pop("_range_issue_map", {})
    event_issue_map = public_report.pop("_event_issue_map", {})
    json_path = out_dir / "mapping_quality_report.json"
    range_csv_path = out_dir / "range_quality_report.csv"
    event_csv_path = out_dir / "event_quality_report.csv"
    json_path.write_text(json.dumps(public_report, indent=2, sort_keys=True), encoding="utf-8")

    range_rows = _range_csv_rows(ranges, range_issue_map)
    with range_csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "range_id", "structure_layer", "status", "parent_range_id", "parent_link_status",
            "range_start_time", "range_end_time", "active_from_time", "inactive_from_time", "issue_codes",
        ])
        writer.writeheader()
        writer.writerows(range_rows)

    event_rows = _event_csv_rows(events, event_issue_map)
    with event_csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "event_id", "id", "event_type", "structure_layer", "event_time", "event_price",
            "active_range_id", "range_id", "parent_range_id", "issue_codes",
        ])
        writer.writeheader()
        writer.writerows(event_rows)
    return {
        "json_report": str(json_path),
        "range_csv": str(range_csv_path),
        "event_csv": str(event_csv_path),
    }


def run_cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit FXTM mapping export quality.")
    parser.add_argument("--export", required=True, dest="export_path")
    parser.add_argument("--out", required=True, dest="out_dir")
    parser.add_argument("--focus-root-range-id", default=None)
    parser.add_argument("--focus-parent-range-id", default=None)
    args = parser.parse_args(argv)

    data, error = load_export(Path(args.export_path))
    if data is None:
        report = {
            "case_summary": {},
            "case_hygiene_status": "EXPORT_INVALID",
            "research_readiness_status": "EXPORT_INVALID",
            "warnings": [error or "export could not be loaded"],
        }
        paths = write_outputs(report, [], [], Path(args.out_dir))
        print(json.dumps({"status": "EXPORT_INVALID", "outputs": paths}, indent=2))
        return 2

    report, ranges, events = audit_export(
        data,
        focus_root_range_id=args.focus_root_range_id,
        focus_parent_range_id=args.focus_parent_range_id,
    )
    status = report.get("research_readiness_status", "EXPORT_INVALID")
    paths = write_outputs(report, ranges, events, Path(args.out_dir))
    print(json.dumps({"status": status, "outputs": paths}, indent=2))
    return 0 if status in {"RESEARCH_READY", "AUDIT_READY"} else 2


if __name__ == "__main__":
    raise SystemExit(run_cli())
