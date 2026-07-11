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
    status: str | None
    inactive_from_time: str | None


def build_parent_child(
    db_path: str | Path,
    *,
    parent_layer: str,
    child_layer: str,
) -> dict[str, Any]:
    parent = parent_layer.upper()
    child = child_layer.upper()
    if parent != SUPPORTED_PARENT_LAYER or child != SUPPORTED_CHILD_LAYER:
        raise ValueError("Only WEEKLY parent to DAILY child pairing is supported in v0.1.")

    path = init_schema(db_path)
    created = 0
    skipped_existing = 0
    with connect(path) as connection:
        ranges = load_ranges(connection)
        parents = [row for row in ranges if row.layer == parent]
        children = [row for row in ranges if row.layer == child]
        for child_row in children:
            candidates = [
                parent_row
                for parent_row in parents
                if same_case_symbol(parent_row, child_row)
                and time_overlaps(parent_row, child_row)
                and price_overlaps(parent_row, child_row)
            ]
            relationship = classify_relationship(child_row, candidates)
            if relationship_exists(connection, relationship):
                skipped_existing += 1
                continue
            insert_relationship(connection, relationship)
            created += 1
        connection.commit()
    return {
        "relationship_type": RELATIONSHIP_TYPE,
        "parent_layer": parent,
        "child_layer": child,
        "children_seen": len(children),
        "relationships_created": created,
        "relationships_existing": skipped_existing,
    }


def summarize_parent_child(db_path: str | Path, *, case_ref: str | None = None) -> dict[str, Any]:
    path = require_existing_db(db_path)
    params: list[Any] = []
    where = ""
    if case_ref:
        where = "WHERE case_ref = ?"
        params.append(case_ref)
    with connect(path) as connection:
        rows = connection.execute(
            f"""
            SELECT relationship_type,
                   link_status,
                   review_status,
                   COUNT(*) AS count
            FROM parent_child_relationships
            {where}
            GROUP BY relationship_type, link_status, review_status
            ORDER BY relationship_type ASC, link_status ASC, review_status ASC
            """,
            tuple(params),
        ).fetchall()
    groups = [dict(row) for row in rows]
    return {
        "filters": {"case_ref": case_ref},
        "total": sum(int(row["count"]) for row in groups),
        "groups": groups,
    }


def format_build_summary(summary: dict[str, Any]) -> str:
    return "\n".join(f"{key}: {value}" for key, value in summary.items())


def format_parent_child_summary(summary: dict[str, Any], *, as_json: bool = False) -> str:
    if as_json:
        return deterministic_json(summary)
    if not summary["groups"]:
        return "No parent-child relationships found."
    keys = ("relationship_type", "link_status", "review_status", "count")
    lines = [" | ".join(keys)]
    for row in summary["groups"]:
        lines.append(" | ".join(str(row[key] if row[key] is not None else "") for key in keys))
    return "\n".join(lines)


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
        case_ref=text_value(payload, "case_ref"),
        symbol=str(row.get("symbol") or text_value(payload, "symbol") or "UNKNOWN").upper(),
        layer=str(layer).upper(),
        timeframe=row.get("timeframe") or text_value(payload, "timeframe", "source_timeframe", "chart_timeframe"),
        start_time=start,
        end_time=end,
        high=float(row["high"]) if row.get("high") is not None else numeric_value(payload, "high", "range_high_price", "range_high"),
        low=float(row["low"]) if row.get("low") is not None else numeric_value(payload, "low", "range_low_price", "range_low"),
        status=(text_value(payload, "status") or "ACTIVE").upper(),
        inactive_from_time=text_value(payload, "inactive_from_time"),
    )


def classify_relationship(child: RangeRow, candidates: list[RangeRow]) -> dict[str, Any]:
    now = utc_now()
    if not candidates:
        return relationship_payload(child, None, "ORPHAN", "low", "No valid Weekly parent found.", now)
    if len(candidates) > 1:
        return relationship_payload(child, candidates[0], "CONFLICT", "low", "Multiple possible Weekly parents found.", now)
    parent = candidates[0]
    link_status = "VALID"
    confidence = "high"
    notes = "One clear Weekly parent matched by case, symbol, time, and price."
    if lifecycle_ambiguous(parent, child):
        link_status = "NEEDS_REVIEW"
        confidence = "medium"
        notes = "Possible parent exists but lifecycle cutoff is uncertain."
    return relationship_payload(child, parent, link_status, confidence, notes, now)


def relationship_payload(
    child: RangeRow,
    parent: RangeRow | None,
    link_status: str,
    confidence: str,
    notes: str,
    timestamp: str,
) -> dict[str, Any]:
    return {
        "import_run_id": child.import_run_id,
        "case_ref": child.case_ref,
        "symbol": child.symbol,
        "parent_range_id": parent.source_record_id if parent else None,
        "parent_layer": parent.layer if parent else SUPPORTED_PARENT_LAYER,
        "parent_timeframe": parent.timeframe if parent else None,
        "parent_start_time": parent.start_time if parent else None,
        "parent_end_time": parent.inactive_from_time if parent and parent.inactive_from_time else None,
        "parent_high": parent.high if parent else None,
        "parent_low": parent.low if parent else None,
        "parent_status": parent.status if parent else None,
        "child_range_id": child.source_record_id,
        "child_layer": child.layer,
        "child_timeframe": child.timeframe,
        "child_start_time": child.start_time,
        "child_end_time": child.end_time,
        "child_high": child.high,
        "child_low": child.low,
        "child_status": child.status,
        "relationship_type": RELATIONSHIP_TYPE,
        "link_confidence": confidence,
        "link_status": link_status,
        "review_status": "open",
        "child_position_in_parent": child_position(parent, child),
        "child_boundary_interaction": boundary_interaction(parent, child),
        "child_lifecycle_relationship": lifecycle_relationship(parent, child),
        "notes": notes,
        "created_at": timestamp,
        "updated_at": timestamp,
    }


def same_case_symbol(parent: RangeRow, child: RangeRow) -> bool:
    return parent.case_ref == child.case_ref and parent.symbol == child.symbol


def time_overlaps(parent: RangeRow, child: RangeRow) -> bool:
    if parent.start_time is None or child.start_time is None:
        return False
    parent_start = parse_time(parent.start_time)
    child_start = parse_time(child.start_time)
    child_end = parse_time(child.end_time) or child_start
    parent_cutoff = lifecycle_cutoff(parent)
    if parent_start is None or child_start is None or child_end is None:
        return False
    if parent_cutoff is None:
        return child_end >= parent_start
    return child_start <= parent_cutoff and child_end >= parent_start


def price_overlaps(parent: RangeRow, child: RangeRow) -> bool:
    if None in (parent.high, parent.low, child.high, child.low):
        return False
    parent_low = min(parent.low, parent.high)
    parent_high = max(parent.low, parent.high)
    child_low = min(child.low, child.high)
    child_high = max(child.low, child.high)
    return child_low <= parent_high and child_high >= parent_low


def lifecycle_cutoff(parent: RangeRow) -> datetime | None:
    if parent.status == "ACTIVE":
        return None
    if parent.status in {"BROKEN", "ABANDONED", "ARCHIVED"} and parent.inactive_from_time:
        return parse_time(parent.inactive_from_time)
    return None


def lifecycle_ambiguous(parent: RangeRow, child: RangeRow) -> bool:
    return parent.status in {"BROKEN", "ABANDONED", "ARCHIVED"} and not parent.inactive_from_time


def child_position(parent: RangeRow | None, child: RangeRow) -> str | None:
    if parent is None or None in (parent.high, parent.low, child.high, child.low):
        return None
    parent_low = min(parent.low, parent.high)
    parent_high = max(parent.low, parent.high)
    span = parent_high - parent_low
    if span <= 0:
        return None
    midpoint = (min(child.low, child.high) + max(child.low, child.high)) / 2
    lower_third = parent_low + span / 3
    upper_third = parent_low + (span * 2 / 3)
    if midpoint < lower_third:
        return "inside_discount"
    if midpoint <= upper_third:
        return "inside_fair_price"
    return "inside_premium"


def boundary_interaction(parent: RangeRow | None, child: RangeRow) -> str | None:
    if parent is None or None in (parent.high, parent.low, child.high, child.low):
        return None
    parent_low = min(parent.low, parent.high)
    parent_high = max(parent.low, parent.high)
    child_low = min(child.low, child.high)
    child_high = max(child.low, child.high)
    if child_low < parent_low or child_high > parent_high:
        return "overlaps_boundary"
    if child_low == parent_low or child_high == parent_high:
        return "touches_boundary"
    return "inside_boundary"


def lifecycle_relationship(parent: RangeRow | None, child: RangeRow) -> str | None:
    if parent is None:
        return "no_parent"
    if lifecycle_ambiguous(parent, child):
        return "uncertain_parent_cutoff"
    return "overlaps_parent_lifecycle"


def relationship_exists(connection, relationship: dict[str, Any]) -> bool:
    row = connection.execute(
        """
        SELECT id
        FROM parent_child_relationships
        WHERE relationship_type = ?
          AND COALESCE(case_ref, '') = COALESCE(?, '')
          AND COALESCE(parent_range_id, '') = COALESCE(?, '')
          AND child_range_id = ?
        LIMIT 1
        """,
        (
            relationship["relationship_type"],
            relationship["case_ref"],
            relationship["parent_range_id"],
            relationship["child_range_id"],
        ),
    ).fetchone()
    return row is not None


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
