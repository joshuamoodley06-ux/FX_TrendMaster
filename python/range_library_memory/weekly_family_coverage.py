"""Read-only Weekly family D1 coverage analysis."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .db import connect
from .inspection import deterministic_json, require_existing_db
from .source_market_db import SourceCandle, SourceMarketDbError, load_candles, open_source_market_db

SCHEMA_VERSION = "weekly_family_coverage_v0.1"
RELATIONSHIP_TYPE = "weekly_daily"
WEEKLY_LAYER = "WEEKLY"
DAILY_LAYER = "DAILY"
D1_TIMEFRAME = "D1"
INACTIVE_STATUSES = {"BROKEN", "ABANDONED", "ARCHIVED"}


class WeeklyFamilyCoverageError(RuntimeError):
    """Raised when Weekly family coverage cannot be measured."""


@dataclass(frozen=True)
class RawRange:
    raw_id: int
    import_run_id: int
    source_record_id: str
    symbol: str
    layer: str
    timeframe: str | None
    status: str
    active_from_time: str | None
    inactive_from_time: str | None
    range_high_time: str | None
    range_low_time: str | None
    direction_of_break: str | None


@dataclass(frozen=True)
class ChildCoverage:
    range: RawRange
    link_source: str
    link_status: str
    link_confidence: str
    review_status: str
    effective_end_time: str


def analyze_weekly_family_coverage(
    db_path: str | Path,
    *,
    source_db: str | Path,
    weekly_source_id: str,
    as_of: str | None = None,
) -> dict[str, Any]:
    rlm_path = require_existing_db(db_path)
    weekly_id = str(weekly_source_id)
    as_of_time = normalize_required_time(as_of, field_name="as_of") if as_of else None

    try:
        with closing(open_source_market_db(source_db)) as source_connection, connect(rlm_path) as memory_connection:
            weekly = resolve_weekly(memory_connection, weekly_id)
            parent_end = lifecycle_end(weekly, as_of_time)
            parent_start = normalize_required_time(weekly.active_from_time, field_name="weekly.active_from_time")
            post_start = post_formation_start(weekly)

            parent_candles = load_source_candles(
                source_connection,
                symbol=weekly.symbol,
                start_time=parent_start,
                end_time=parent_end,
            )
            post_candles = load_source_candles(
                source_connection,
                symbol=weekly.symbol,
                start_time=post_start,
                end_time=parent_end,
            )

            children = load_children(memory_connection, weekly_source_id=weekly_id, parent_end=parent_end, as_of=as_of_time)
    except SourceMarketDbError as exc:
        raise WeeklyFamilyCoverageError(str(exc)) from exc

    parent_window = coverage_window(parent_start, parent_end, parent_candles, children)
    post_window = coverage_window(post_start, parent_end, post_candles, children)
    post_gaps = [{"candle_time": candle.time} for candle in post_candles if not covering_children(candle, children)]
    overlaps = [
        {"candle_time": candle.time, "child_source_ids": covering}
        for candle in post_candles
        if len(covering := covering_children(candle, children)) > 1
    ]
    children_output = [child_output(child) for child in children]

    return {
        "schema_version": SCHEMA_VERSION,
        "weekly_source_id": weekly_id,
        "symbol": weekly.symbol,
        "weekly_status": weekly.status,
        "weekly_direction_of_break": weekly.direction_of_break,
        "windows": {
            "parent_lifecycle": parent_window,
            "post_formation": post_window,
        },
        "children": children_output,
        "post_formation_gaps": post_gaps,
        "overlaps": overlaps,
        "counts": {
            "daily_children": len(children),
            "valid_children": count_status(children, "VALID"),
            "needs_review_children": count_status(children, "NEEDS_REVIEW"),
            "conflict_children": count_status(children, "CONFLICT"),
            "orphan_children": count_status(children, "ORPHAN"),
            "gap_candles": len(post_gaps),
            "overlap_candles": len(overlaps),
        },
    }


def format_weekly_family_coverage(report: dict[str, Any], *, as_json: bool = False) -> str:
    if as_json:
        return deterministic_json(report)
    post = report["windows"]["post_formation"]
    return "\n".join(
        [
            f"weekly_source_id: {report['weekly_source_id']}",
            f"symbol: {report['symbol']}",
            f"post_formation_coverage_status: {post['coverage_status']}",
            f"post_formation_d1_candle_count: {post['d1_candle_count']}",
            f"post_formation_covered_candle_count: {post['covered_candle_count']}",
            f"gap_candles: {report['counts']['gap_candles']}",
            f"overlap_candles: {report['counts']['overlap_candles']}",
        ]
    )


def resolve_weekly(connection: sqlite3.Connection, weekly_source_id: str) -> RawRange:
    row = connection.execute(
        "SELECT * FROM raw_ranges WHERE source_record_id = ? ORDER BY id DESC LIMIT 1",
        (weekly_source_id,),
    ).fetchone()
    if row is None:
        raise WeeklyFamilyCoverageError(f"Weekly source id cannot be resolved: {weekly_source_id}")
    weekly = raw_range_from_row(row)
    if weekly.layer != WEEKLY_LAYER:
        raise WeeklyFamilyCoverageError(f"Source id {weekly_source_id} is not a WEEKLY range.")
    return weekly


def load_children(
    connection: sqlite3.Connection,
    *,
    weekly_source_id: str,
    parent_end: str,
    as_of: str | None,
) -> list[ChildCoverage]:
    rows = connection.execute(
        """
        SELECT *
        FROM parent_child_relationships
        WHERE relationship_type = ?
          AND parent_range_id = ?
          AND child_layer = ?
        ORDER BY child_range_id ASC, id ASC
        """,
        (RELATIONSHIP_TYPE, weekly_source_id, DAILY_LAYER),
    ).fetchall()
    children: list[ChildCoverage] = []
    for relationship in rows:
        child = connection.execute(
            "SELECT * FROM raw_ranges WHERE source_record_id = ? ORDER BY id DESC LIMIT 1",
            (relationship["child_range_id"],),
        ).fetchone()
        if child is None:
            raise WeeklyFamilyCoverageError(
                f"Linked Daily child source id cannot be resolved: {relationship['child_range_id']}"
            )
        child_range = raw_range_from_row(child)
        end_time = child_end_time(child_range, parent_end=parent_end, as_of=as_of)
        children.append(
            ChildCoverage(
                range=child_range,
                link_source=str(relationship["link_source"]),
                link_status=str(relationship["link_status"]),
                link_confidence=str(relationship["link_confidence"]),
                review_status=str(relationship["review_status"]),
                effective_end_time=end_time,
            )
        )
    return sorted(children, key=lambda item: (item.range.active_from_time or "", item.range.source_record_id))


def raw_range_from_row(row: sqlite3.Row) -> RawRange:
    payload = parse_payload(row["raw_payload_json"])
    layer = text_value(payload, "structure_layer", "layer", "range_type") or row["range_type"] or ""
    return RawRange(
        raw_id=int(row["id"]),
        import_run_id=int(row["import_run_id"]),
        source_record_id=str(row["source_record_id"]),
        symbol=str(row["symbol"] or text_value(payload, "symbol") or "UNKNOWN").upper(),
        layer=str(layer).upper(),
        timeframe=row["timeframe"] or text_value(payload, "source_timeframe", "timeframe"),
        status=(text_value(payload, "status", "range_status") or "ACTIVE").upper(),
        active_from_time=text_value(payload, "active_from_time", "range_start_time"),
        inactive_from_time=text_value(payload, "inactive_from_time"),
        range_high_time=text_value(payload, "range_high_time", "rh_time"),
        range_low_time=text_value(payload, "range_low_time", "rl_time"),
        direction_of_break=text_value(payload, "direction_of_break"),
    )


def lifecycle_end(range_row: RawRange, as_of: str | None) -> str:
    if range_row.inactive_from_time:
        return normalize_required_time(range_row.inactive_from_time, field_name="inactive_from_time")
    if range_row.status in INACTIVE_STATUSES:
        raise WeeklyFamilyCoverageError("Inactive Weekly range is missing inactive_from_time.")
    if as_of is None:
        raise WeeklyFamilyCoverageError("Active Weekly range requires --as-of.")
    return as_of


def child_end_time(child: RawRange, *, parent_end: str, as_of: str | None) -> str:
    if child.inactive_from_time:
        return normalize_required_time(child.inactive_from_time, field_name="child.inactive_from_time")
    if child.status == "ACTIVE":
        cutoff = min_time(parent_end, as_of) if as_of else parent_end
        return cutoff
    if child.status in INACTIVE_STATUSES:
        raise WeeklyFamilyCoverageError(
            f"{child.status} Daily child is missing inactive_from_time: {child.source_record_id}"
        )
    raise WeeklyFamilyCoverageError(
        f"Unsupported Daily child status without inactive_from_time: {child.status} ({child.source_record_id})"
    )


def post_formation_start(weekly: RawRange) -> str:
    high = normalize_required_time(weekly.range_high_time, field_name="weekly.range_high_time")
    low = normalize_required_time(weekly.range_low_time, field_name="weekly.range_low_time")
    return max_time(high, low)


def load_source_candles(
    connection: sqlite3.Connection,
    *,
    symbol: str,
    start_time: str,
    end_time: str,
) -> list[SourceCandle]:
    try:
        return load_candles(connection, symbol=symbol, timeframe=D1_TIMEFRAME, start_time=start_time, end_time=end_time)
    except SourceMarketDbError as exc:
        raise WeeklyFamilyCoverageError(str(exc)) from exc


def coverage_window(
    start_time: str,
    end_time: str,
    candles: list[SourceCandle],
    children: list[ChildCoverage],
) -> dict[str, Any]:
    covered = sum(1 for candle in candles if covering_children(candle, children))
    total = len(candles)
    percent = round((covered / total) * 100, 6) if total else 0.0
    if covered == 0:
        status = "NONE"
    elif covered == total:
        status = "FULL"
    else:
        status = "PARTIAL"
    return {
        "start_time": start_time,
        "end_time": end_time,
        "d1_candle_count": total,
        "covered_candle_count": covered,
        "coverage_percent": percent,
        "coverage_status": status,
    }


def covering_children(candle: SourceCandle, children: list[ChildCoverage]) -> list[str]:
    covered = [
        child.range.source_record_id
        for child in children
        if child.range.active_from_time
        and normalize_time(child.range.active_from_time) <= normalize_time(candle.time) <= normalize_time(child.effective_end_time)
    ]
    return sorted(covered)


def child_output(child: ChildCoverage) -> dict[str, Any]:
    return {
        "child_source_id": child.range.source_record_id,
        "status": child.range.status,
        "active_from_time": child.range.active_from_time,
        "inactive_from_time": child.range.inactive_from_time,
        "direction_of_break": child.range.direction_of_break,
        "link_source": child.link_source,
        "link_status": child.link_status,
        "link_confidence": child.link_confidence,
        "review_status": child.review_status,
    }


def count_status(children: list[ChildCoverage], status: str) -> int:
    return sum(1 for child in children if child.link_status == status)


def parse_payload(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def text_value(payload: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if value is not None and str(value).strip() != "":
            return str(value)
    return None


def normalize_required_time(value: str | None, *, field_name: str) -> str:
    if not value:
        raise WeeklyFamilyCoverageError(f"Missing required time field: {field_name}")
    return format_time(normalize_time(value))


def normalize_time(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def format_time(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def max_time(first: str, second: str) -> str:
    return format_time(max(normalize_time(first), normalize_time(second)))


def min_time(first: str, second: str | None) -> str:
    if second is None:
        return first
    return format_time(min(normalize_time(first), normalize_time(second)))
