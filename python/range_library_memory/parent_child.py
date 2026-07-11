"""Derived WEEKLY to DAILY parent-child pairing for raw range memory."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .db import connect
from .inspection import deterministic_json, require_existing_db
from .schema import init_schema

RELATIONSHIP_TYPE = "weekly_daily"
SUPPORTED_PARENT_LAYER = "WEEKLY"
SUPPORTED_CHILD_LAYER = "DAILY"

VALID = "VALID"
ORPHAN = "ORPHAN"
CONFLICT = "CONFLICT"
NEEDS_REVIEW = "NEEDS_REVIEW"


@dataclass(frozen=True)
class RangeRow:
    raw_id: int
    import_run_id: int
    source_record_id: str
    case_ref: str | None
    symbol: str
    layer: str
    timeframe: str | None
    start_time: str | None
    end_time: str | None
    high: float | None
    low: float | None
    status: str
    inactive_from_time: str | None
    explicit_parent_id: str | None


def build_parent_child(
    db_path: str | Path,
    *,
    parent_layer: str,
    child_layer: str,
    case_ref: str | None = None,
) -> dict[str, Any]:
    parent = parent_layer.upper()
    child = child_layer.upper()
    if parent != SUPPORTED_PARENT_LAYER or child != SUPPORTED_CHILD_LAYER:
        raise ValueError("Only WEEKLY parent to DAILY child pairing is supported in v0.1.")

    path = init_schema(db_path)
    now = utc_now()
    with connect(path) as connection:
        clear_scope(connection, case_ref=case_ref)
        ranges = load_ranges(connection)
        parents = [row for row in ranges if row.layer == parent and case_matches(row, case_ref)]
        children = [row for row in ranges if row.layer == child and case_matches(row, case_ref)]
        for child_row in children:
            relationship = classify_relationship(child_row, parents, now)
            insert_relationship(connection, relationship)
        connection.commit()
    return {
        "relationship_type": RELATIONSHIP_TYPE,
        "parent_layer": parent,
        "child_layer": child,
        "case_ref": case_ref,
        "children_seen": len(children),
        "relationships_created": len(children),
    }


def summarize_parent_child(db_path: str | Path, *, case_ref: str | None = None) -> dict[str, Any]:
    path = require_existing_db(db_path)
    where, params = scope_where(case_ref)
    with connect(path) as connection:
        by_case_rows = connection.execute(
            f"""
            SELECT case_ref,
                   relationship_type,
                   COUNT(*) AS total,
                   SUM(CASE WHEN link_status = 'VALID' THEN 1 ELSE 0 END) AS valid,
                   SUM(CASE WHEN link_status = 'ORPHAN' THEN 1 ELSE 0 END) AS orphan,
                   SUM(CASE WHEN link_status = 'CONFLICT' THEN 1 ELSE 0 END) AS conflict,
                   SUM(CASE WHEN link_status = 'NEEDS_REVIEW' THEN 1 ELSE 0 END) AS needs_review
            FROM parent_child_relationships
            {where}
            GROUP BY case_ref, relationship_type
            ORDER BY COALESCE(case_ref, ''), relationship_type
            """,
            tuple(params),
        ).fetchall()
        grouped = {
            "child_position_in_parent": grouped_count(connection, "child_position_in_parent", where, params),
            "child_boundary_interaction": grouped_count(connection, "child_boundary_interaction", where, params),
            "child_lifecycle_relationship": grouped_count(connection, "child_lifecycle_relationship", where, params),
            "link_source": grouped_count(connection, "link_source", where, params),
        }

    by_case = [dict(row) for row in by_case_rows]
    return {
        "filters": {"case_ref": case_ref},
        "totals": {
            "relationships": sum(int(row["total"] or 0) for row in by_case),
            "valid": sum(int(row["valid"] or 0) for row in by_case),
            "orphan": sum(int(row["orphan"] or 0) for row in by_case),
            "conflict": sum(int(row["conflict"] or 0) for row in by_case),
            "needs_review": sum(int(row["needs_review"] or 0) for row in by_case),
        },
        "by_case": by_case,
        "groups": grouped,
    }


def grouped_count(connection, field: str, where: str, params: list[Any]) -> list[dict[str, Any]]:
    rows = connection.execute(
        f"""
        SELECT {field} AS value, COUNT(*) AS count
        FROM parent_child_relationships
        {where}
        GROUP BY {field}
        ORDER BY {field} ASC
        """,
        tuple(params),
    ).fetchall()
    return [dict(row) for row in rows]


def format_build_summary(summary: dict[str, Any]) -> str:
    return "\n".join(f"{key}: {value if value is not None else ''}" for key, value in summary.items())


def format_parent_child_summary(summary: dict[str, Any], *, as_json: bool = False) -> str:
    if as_json:
        return deterministic_json(summary)
    if not summary["by_case"]:
        return "No parent-child relationships found."
    lines = [
        "case_ref | relationship_type | total | valid | orphan | conflict | needs_review",
    ]
    for row in summary["by_case"]:
        lines.append(
            " | ".join(
                str(row[key] if row[key] is not None else "")
                for key in ("case_ref", "relationship_type", "total", "valid", "orphan", "conflict", "needs_review")
            )
        )
    for title, rows in (
        ("child_position_in_parent", summary["groups"]["child_position_in_parent"]),
        ("child_boundary_interaction", summary["groups"]["child_boundary_interaction"]),
        ("child_lifecycle_relationship", summary["groups"]["child_lifecycle_relationship"]),
        ("link_source", summary["groups"]["link_source"]),
    ):
        lines.extend(["", title])
        if rows:
            for row in rows:
                lines.append(f"{row['value']} | {row['count']}")
        else:
            lines.append("none")
    return "\n".join(lines)


def clear_scope(connection, *, case_ref: str | None) -> None:
    if case_ref:
        connection.execute(
            "DELETE FROM parent_child_relationships WHERE relationship_type = ? AND case_ref = ?",
            (RELATIONSHIP_TYPE, case_ref),
        )
        return
    connection.execute(
        "DELETE FROM parent_child_relationships WHERE relationship_type = ?",
        (RELATIONSHIP_TYPE,),
    )


def scope_where(case_ref: str | None) -> tuple[str, list[Any]]:
    if case_ref:
        return "WHERE case_ref = ?", [case_ref]
    return "", []


def load_ranges(connection) -> list[RangeRow]:
    rows = connection.execute("SELECT * FROM raw_ranges ORDER BY id ASC").fetchall()
    return [range_from_row(dict(row)) for row in rows]


def range_from_row(row: dict[str, Any]) -> RangeRow:
    payload = parse_payload(row["raw_payload_json"])
    layer = text_value(payload, "structure_layer", "layer", "range_type", "type") or row.get("range_type") or ""
    start = text_value(payload, "active_from_time", "range_start_time", "start_time_utc", "start_time", "start") or row.get("start_time_utc")
    end = text_value(payload, "range_end_time", "end_time_utc", "end_time", "end") or row.get("end_time_utc")
    return RangeRow(
        raw_id=int(row["id"]),
        import_run_id=int(row["import_run_id"]),
        source_record_id=str(row.get("source_record_id") or row["id"]),
        case_ref=text_value(payload, "case_ref", "raw_case_id", "case_id"),
        symbol=str(row.get("symbol") or text_value(payload, "symbol") or "UNKNOWN").upper(),
        layer=str(layer).upper(),
        timeframe=row.get("timeframe") or text_value(payload, "timeframe", "source_timeframe", "chart_timeframe"),
        start_time=start,
        end_time=end,
        high=float(row["high"]) if row.get("high") is not None else numeric_value(payload, "high", "range_high_price", "range_high", "rh"),
        low=float(row["low"]) if row.get("low") is not None else numeric_value(payload, "low", "range_low_price", "range_low", "rl"),
        status=(text_value(payload, "status", "range_status") or "ACTIVE").upper(),
        inactive_from_time=text_value(payload, "inactive_from_time"),
        explicit_parent_id=text_value(payload, "parent_range_id", "parent_id", "parent_source_record_id"),
    )


def classify_relationship(child: RangeRow, parents: list[RangeRow], timestamp: str) -> dict[str, Any]:
    inferred = valid_inferred_parents(child, parents)
    explicit_parent = explicit_parent_for(child, parents)
    explicit_id = child.explicit_parent_id

    if explicit_id:
        if explicit_parent is None:
            return relationship_payload(
                child,
                None,
                link_source="explicit",
                link_status=NEEDS_REVIEW,
                confidence="low",
                notes=f"Explicit parent reference could not be resolved: {explicit_id}",
                timestamp=timestamp,
            )
        explicit_ok = is_valid_parent_candidate(explicit_parent, child)
        inferred_disagrees = bool(inferred) and explicit_parent.raw_id not in {row.raw_id for row in inferred}
        status = VALID
        confidence = "high"
        notes = "Explicit parent reference validated."
        if inferred_disagrees:
            status = NEEDS_REVIEW
            confidence = "medium"
            notes = "Explicit parent and inferred parent candidates disagree."
        elif not explicit_ok:
            status = NEEDS_REVIEW
            confidence = "medium"
            notes = "Explicit parent reference exists but lifecycle or price relationship is not sensible."
        elif lifecycle_ambiguous(explicit_parent):
            status = NEEDS_REVIEW
            confidence = "medium"
            notes = "Explicit parent lifecycle cutoff is uncertain."
        return relationship_payload(
            child,
            explicit_parent,
            link_source="explicit",
            link_status=status,
            confidence=confidence,
            notes=notes,
            timestamp=timestamp,
        )

    if not inferred:
        return relationship_payload(
            child,
            None,
            link_source="inferred",
            link_status=ORPHAN,
            confidence="low",
            notes="No explicit parent and no valid inferred Weekly parent found.",
            timestamp=timestamp,
        )
    if len(inferred) > 1:
        return relationship_payload(
            child,
            inferred[0],
            link_source="inferred",
            link_status=CONFLICT,
            confidence="low",
            notes="Multiple equally plausible inferred Weekly parents found.",
            timestamp=timestamp,
        )
    parent = inferred[0]
    if lifecycle_ambiguous(parent):
        return relationship_payload(
            child,
            parent,
            link_source="inferred",
            link_status=NEEDS_REVIEW,
            confidence="medium",
            notes="Inferred parent exists but lifecycle cutoff is uncertain.",
            timestamp=timestamp,
        )
    return relationship_payload(
        child,
        parent,
        link_source="inferred",
        link_status=VALID,
        confidence="medium",
        notes="One inferred Weekly parent matched by case, symbol, time, and price.",
        timestamp=timestamp,
    )


def relationship_payload(
    child: RangeRow,
    parent: RangeRow | None,
    *,
    link_source: str,
    link_status: str,
    confidence: str,
    notes: str,
    timestamp: str,
) -> dict[str, Any]:
    return {
        "import_run_id": child.import_run_id,
        "case_ref": child.case_ref,
        "symbol": child.symbol,
        "relationship_type": RELATIONSHIP_TYPE,
        "parent_range_id": parent.source_record_id if parent else child.explicit_parent_id,
        "child_range_id": child.source_record_id,
        "parent_layer": parent.layer if parent else SUPPORTED_PARENT_LAYER,
        "child_layer": child.layer,
        "parent_timeframe": parent.timeframe if parent else None,
        "child_timeframe": child.timeframe,
        "link_source": link_source,
        "link_status": link_status,
        "link_confidence": confidence,
        "review_status": "open",
        "child_position_in_parent": child_position(parent, child),
        "child_boundary_interaction": boundary_interaction(parent, child),
        "child_lifecycle_relationship": lifecycle_relationship(parent, child),
        "notes": notes,
        "created_at_utc": timestamp,
        "updated_at_utc": timestamp,
    }


def valid_inferred_parents(child: RangeRow, parents: list[RangeRow]) -> list[RangeRow]:
    return [parent for parent in parents if is_valid_parent_candidate(parent, child)]


def is_valid_parent_candidate(parent: RangeRow, child: RangeRow) -> bool:
    return same_case_symbol(parent, child) and time_overlaps(parent, child) and price_overlaps(parent, child)


def explicit_parent_for(child: RangeRow, parents: list[RangeRow]) -> RangeRow | None:
    if not child.explicit_parent_id:
        return None
    explicit_id = child.explicit_parent_id
    matches = [parent for parent in parents if parent.source_record_id == explicit_id]
    return matches[0] if matches else None


def same_case_symbol(parent: RangeRow, child: RangeRow) -> bool:
    return parent.case_ref == child.case_ref and parent.symbol == child.symbol


def time_overlaps(parent: RangeRow, child: RangeRow) -> bool:
    if parent.start_time is None or child.start_time is None:
        return False
    parent_start = parse_time(parent.start_time)
    child_start = parse_time(child.start_time)
    child_end = parse_time(child.end_time) or child_start
    cutoff = lifecycle_cutoff(parent)
    if parent_start is None or child_start is None or child_end is None:
        return False
    if cutoff is None:
        return child_end >= parent_start
    return child_start <= cutoff and child_end >= parent_start


def price_overlaps(parent: RangeRow, child: RangeRow) -> bool:
    if None in (parent.high, parent.low, child.high, child.low):
        return False
    parent_low, parent_high = normalized_bounds(parent.low, parent.high)
    child_low, child_high = normalized_bounds(child.low, child.high)
    return child_low <= parent_high and child_high >= parent_low


def lifecycle_cutoff(parent: RangeRow) -> datetime | None:
    if parent.status == "ACTIVE":
        return None
    if parent.status in {"BROKEN", "ABANDONED", "ARCHIVED"} and parent.inactive_from_time:
        return parse_time(parent.inactive_from_time)
    return None


def lifecycle_ambiguous(parent: RangeRow) -> bool:
    return parent.status in {"BROKEN", "ABANDONED", "ARCHIVED"} and not parent.inactive_from_time


def child_position(parent: RangeRow | None, child: RangeRow) -> str:
    if parent is None or None in (parent.high, parent.low, child.high, child.low):
        return "needs_review"
    parent_low, parent_high = normalized_bounds(parent.low, parent.high)
    child_low, child_high = normalized_bounds(child.low, child.high)
    span = parent_high - parent_low
    if span <= 0:
        return "needs_review"
    if child_high < parent_low or child_low > parent_high:
        return "outside_parent"
    lower_third = parent_low + span / 3
    upper_third = parent_low + (span * 2 / 3)
    touched_zones = set()
    if child_low < lower_third:
        touched_zones.add("discount")
    if child_low <= upper_third and child_high >= lower_third:
        touched_zones.add("fair")
    if child_high > upper_third:
        touched_zones.add("premium")
    if len(touched_zones) > 1:
        return "spans_zones"
    if touched_zones == {"discount"}:
        return "inside_discount"
    if touched_zones == {"fair"}:
        return "inside_fair_price"
    if touched_zones == {"premium"}:
        return "inside_premium"
    return "needs_review"


def boundary_interaction(parent: RangeRow | None, child: RangeRow) -> str:
    if parent is None or None in (parent.high, parent.low, child.high, child.low):
        return "needs_review"
    parent_low, parent_high = normalized_bounds(parent.low, parent.high)
    child_low, child_high = normalized_bounds(child.low, child.high)
    if child_high < parent_low or child_low > parent_high:
        return "outside_parent"
    breached_low = child_low < parent_low
    breached_high = child_high > parent_high
    if breached_low and breached_high:
        return "breached_both_sides"
    if breached_high:
        return "breached_parent_high"
    if breached_low:
        return "breached_parent_low"
    return "inside_parent"


def lifecycle_relationship(parent: RangeRow | None, child: RangeRow) -> str:
    if parent is None or parent.start_time is None or child.start_time is None:
        return "needs_review"
    parent_start = parse_time(parent.start_time)
    child_start = parse_time(child.start_time)
    child_end = parse_time(child.end_time) or child_start
    if parent_start is None or child_start is None or child_end is None:
        return "needs_review"
    if lifecycle_ambiguous(parent):
        return "needs_review"
    cutoff = lifecycle_cutoff(parent)
    if child_end < parent_start:
        return "formed_before_parent"
    if cutoff is not None and child_start > cutoff:
        return "formed_after_parent_inactive"
    if child_start >= parent_start and (cutoff is None or child_start <= cutoff):
        return "formed_during_active_parent"
    if child_start <= parent_start and (cutoff is None or child_end >= parent_start):
        return "overlaps_parent_lifecycle"
    return "needs_review"


def normalized_bounds(first: float, second: float) -> tuple[float, float]:
    return (min(first, second), max(first, second))


def case_matches(row: RangeRow, case_ref: str | None) -> bool:
    return case_ref is None or row.case_ref == case_ref


def insert_relationship(connection, relationship: dict[str, Any]) -> None:
    keys = tuple(relationship)
    placeholders = ", ".join("?" for _ in keys)
    connection.execute(
        f"INSERT INTO parent_child_relationships ({', '.join(keys)}) VALUES ({placeholders})",
        tuple(relationship[key] for key in keys),
    )


def parse_payload(value: str) -> dict[str, Any]:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def text_value(payload: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if value is not None and str(value).strip() != "":
            return str(value)
    return None


def numeric_value(payload: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
