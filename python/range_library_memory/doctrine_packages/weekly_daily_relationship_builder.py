"""Build the factual Weekly-to-Daily relationship table at the Weekly freeze.

The package consumes approved Daily Mapping Coverage Audit memory. It does not
search for substitute parents or re-parent Daily ranges. Future Daily ranges stay
visible as NOT_YET_CREATED rows so historical candidates cannot borrow structure
from later candles.

Daily direction in this package is anchor chronology only. It is not yet the
Weekly-relative PRO_TREND / COUNTER_TREND classification.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Mapping

FXTM_DOCTRINE_CONTRACT = "fxtm_doctrine_package_v1"
SCRIPT_KEY = "weekly_daily_relationship_builder"
VERSION_LABEL = "1"
ADAPTER_KEY = "doctrine_package_v1"
EXECUTION_ORDER = 80


def _time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _memory_entry(
    context: Any,
    canonical_range_id: str,
    key: str,
) -> tuple[dict[str, Any] | None, str]:
    memory = context.approved_memory(canonical_range_id)
    if not isinstance(memory, Mapping):
        return None, "MISSING"
    entry = memory.get(key)
    if not isinstance(entry, Mapping):
        return None, "MISSING"
    payload = entry.get("payload")
    if not isinstance(payload, Mapping):
        return None, "MISSING"
    return dict(payload), str(entry.get("processing_status") or "").upper()


def _output(node: Mapping[str, Any], status: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "canonical_range_id": str(node.get("id") or ""),
        "processing_status": status,
        "payload": payload,
    }


def _daily_direction(child: Mapping[str, Any]) -> str:
    high_time = _time(child.get("range_high_time"))
    low_time = _time(child.get("range_low_time"))
    if high_time is None or low_time is None or high_time == low_time:
        return "UNRESOLVED"
    return "UP" if low_time < high_time else "DOWN"


def _status_at_freeze(child: Mapping[str, Any], freeze: datetime) -> str:
    created = _time(child.get("daily_created_time"))
    if created is None or created > freeze:
        return "NOT_YET_CREATED"

    raw_status = str(child.get("daily_status") or "ACTIVE").upper()
    inactive = _time(child.get("daily_end_time"))
    if inactive is not None and inactive <= freeze:
        return "ABANDONED" if raw_status == "ABANDONED" else "BROKEN"
    if raw_status in {"FORMING", "RETESTING", "ABANDONED"}:
        return raw_status
    return "ACTIVE"


def _base_payload(canonical_id: str) -> dict[str, Any]:
    return {
        "weekly_candidate_id": canonical_id,
        "weekly_range_id": canonical_id,
        "candidate_freeze_time": None,
        "coverage_status": None,
        "daily_relationship_count": 0,
        "daily_ranges_at_freeze": 0,
        "future_daily_ranges_excluded": 0,
        "valid_relationship_count": 0,
        "invalid_relationship_count": 0,
        "active_daily_range_id": None,
        "previous_daily_range_id": None,
        "daily_sequence_summary": None,
        "relationship_rows": [],
        "reason_codes": [],
    }


def run(context: Any) -> dict[str, list[dict[str, Any]]]:
    outputs: list[dict[str, Any]] = []
    for raw_node in context.selected_ranges(layer="WEEKLY"):
        node = dict(raw_node)
        canonical_id = str(node.get("id") or "")
        payload = _base_payload(canonical_id)

        coverage, coverage_processing = _memory_entry(
            context,
            canonical_id,
            "daily_mapping_coverage_audit",
        )
        if coverage is None:
            payload["reason_codes"] = ["APPROVED_DAILY_MAPPING_COVERAGE_MEMORY_MISSING"]
            outputs.append(_output(node, "PENDING", payload))
            continue

        freeze = _time(coverage.get("candidate_freeze_time"))
        coverage_status = str(coverage.get("coverage_status") or "PENDING").upper()
        payload["candidate_freeze_time"] = coverage.get("candidate_freeze_time")
        payload["coverage_status"] = coverage_status

        if coverage_processing == "NEEDS_REVIEW" or coverage_status == "INVALID_PARENT_LINK":
            payload["reason_codes"] = ["DAILY_MAPPING_COVERAGE_NEEDS_REVIEW"]
            outputs.append(_output(node, "NEEDS_REVIEW", payload))
            continue
        if freeze is None:
            payload["reason_codes"] = ["WEEKLY_CANDIDATE_FREEZE_TIME_UNAVAILABLE"]
            outputs.append(_output(node, "PENDING", payload))
            continue

        raw_children = coverage.get("daily_children")
        children = [dict(child) for child in raw_children if isinstance(child, Mapping)] \
            if isinstance(raw_children, list) else []
        children.sort(key=lambda child: (
            child.get("daily_created_time") or "9999",
            child.get("daily_start_time") or "9999",
            str(child.get("daily_range_id") or ""),
        ))

        rows: list[dict[str, Any]] = []
        for index, child in enumerate(children, start=1):
            daily_id = str(child.get("daily_range_id") or "")
            created = _time(child.get("daily_created_time"))
            start = _time(child.get("daily_start_time"))
            end = _time(child.get("daily_end_time"))
            state = _status_at_freeze(child, freeze)
            parent_range_id = str(child.get("parent_range_id") or "").strip() or None
            parent_link_valid = (
                child.get("parent_link_valid") is True
                and parent_range_id == canonical_id
            )
            timing_valid = (
                bool(daily_id)
                and created is not None
                and (start is None or start <= created)
                and (end is None or end >= created)
            )
            historically_available = state != "NOT_YET_CREATED"
            relationship_valid = parent_link_valid and timing_valid and historically_available
            rows.append({
                "weekly_candidate_id": canonical_id,
                "weekly_range_id": canonical_id,
                "daily_range_id": daily_id,
                "daily_sequence_number": index,
                "daily_start_time": child.get("daily_start_time"),
                "daily_created_time": child.get("daily_created_time"),
                "daily_end_time": child.get("daily_end_time"),
                "daily_direction": _daily_direction(child),
                "daily_status_at_freeze": state,
                "parent_range_id": parent_range_id,
                "parent_link_status": child.get("parent_link_status"),
                "parent_link_valid": parent_link_valid,
                "historically_available": historically_available,
                "relationship_valid": relationship_valid,
            })

        at_freeze = [row for row in rows if row["historically_available"]]
        active = [
            row for row in at_freeze
            if row["daily_status_at_freeze"] in {"FORMING", "ACTIVE", "RETESTING"}
            and row["relationship_valid"]
        ]
        active_row = active[-1] if active else None
        prior_rows = [
            row for row in at_freeze
            if active_row is None or row["daily_sequence_number"] < active_row["daily_sequence_number"]
        ]
        previous_row = prior_rows[-1] if prior_rows else None

        payload.update({
            "daily_relationship_count": len(rows),
            "daily_ranges_at_freeze": len(at_freeze),
            "future_daily_ranges_excluded": sum(
                row["daily_status_at_freeze"] == "NOT_YET_CREATED" for row in rows
            ),
            "valid_relationship_count": sum(row["relationship_valid"] for row in rows),
            "invalid_relationship_count": sum(
                not row["relationship_valid"] and row["historically_available"] for row in rows
            ),
            "active_daily_range_id": active_row["daily_range_id"] if active_row else None,
            "previous_daily_range_id": previous_row["daily_range_id"] if previous_row else None,
            "daily_sequence_summary": " -> ".join(
                f"{row['daily_sequence_number']}:{row['daily_range_id']} {row['daily_status_at_freeze']}"
                for row in rows
            ) or "NO_LINKED_DAILY_RANGES",
            "relationship_rows": rows,
        })

        invalid_historical = [
            row["daily_range_id"] for row in rows
            if row["historically_available"] and not row["relationship_valid"]
        ]
        if invalid_historical:
            payload["reason_codes"] = ["ONE_OR_MORE_WEEKLY_DAILY_RELATIONSHIPS_INVALID"]
            outputs.append(_output(node, "NEEDS_REVIEW", payload))
            continue

        if coverage_status == "NOT_MAPPED":
            payload["reason_codes"] = ["DAILY_NOT_MAPPED_AT_WEEKLY_FREEZE"]
        elif coverage_status == "MAPPING_GAP":
            payload["reason_codes"] = ["WEEKLY_DAILY_RELATIONSHIP_HAS_MAPPING_GAP"]
        elif coverage_status == "PARTIAL":
            payload["reason_codes"] = ["WEEKLY_DAILY_RELATIONSHIP_PARTIAL"]
        else:
            payload["reason_codes"] = ["WEEKLY_DAILY_RELATIONSHIP_TABLE_COMPLETE"]
        outputs.append(_output(node, "COMPLETE", payload))

    return {"outputs": outputs}
