"""Build a conservative, case-free XAUUSD Master Map from immutable raw evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

from .db import connect

VERSION = "xauusd_master_map_v0.1"
LAYERS = ("WEEKLY", "DAILY", "INTRADAY")
PARENT = {"DAILY": "WEEKLY", "INTRADAY": "DAILY"}
INCLUDED, NEEDS_REVIEW, VALID, ORPHAN = "INCLUDED", "NEEDS_REVIEW", "VALID", "ORPHAN"
NAV_TRUSTED, NAV_REVIEW, NAV_HIDDEN = "TRUSTED", "REVIEW", "HIDDEN"
STATS_ELIGIBLE, STATS_EXCLUDED = "ELIGIBLE", "EXCLUDED"
ANCESTOR_CLEAR = "CLEAR"
ANCESTOR_SELF_REVIEW = "SELF_NEEDS_REVIEW"
ANCESTOR_DIRECT_REVIEW = "DIRECT_PARENT_NEEDS_REVIEW"
ANCESTOR_UPSTREAM_REVIEW = "ANCESTOR_NEEDS_REVIEW"
ANCESTOR_SELF_AND_UPSTREAM = "SELF_AND_ANCESTOR_NEEDS_REVIEW"
ROOT_LINK = "ROOT"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS master_map_ranges (
 canonical_range_id TEXT PRIMARY KEY, build_id TEXT NOT NULL, symbol TEXT NOT NULL,
 structure_layer TEXT NOT NULL, source_timeframe TEXT, processing_status TEXT NOT NULL,
 excluded_from_statistics INTEGER NOT NULL, visible_in_hierarchy INTEGER NOT NULL,
 source_count INTEGER NOT NULL, canonical_payload_json TEXT NOT NULL,
 source_refs_json TEXT NOT NULL, built_at_utc TEXT NOT NULL,
 navigation_status TEXT NOT NULL DEFAULT 'HIDDEN',
 statistics_status TEXT NOT NULL DEFAULT 'EXCLUDED',
 ancestor_review_status TEXT NOT NULL DEFAULT 'CLEAR',
 direct_parent_link_status TEXT NOT NULL DEFAULT 'ROOT'
);
CREATE INDEX IF NOT EXISTS idx_master_ranges_scope
 ON master_map_ranges(symbol, structure_layer, processing_status);
CREATE TABLE IF NOT EXISTS master_map_events (
 canonical_event_id TEXT PRIMARY KEY, build_id TEXT NOT NULL, symbol TEXT NOT NULL,
 canonical_range_id TEXT, processing_status TEXT NOT NULL,
 excluded_from_statistics INTEGER NOT NULL, source_count INTEGER NOT NULL,
 canonical_payload_json TEXT NOT NULL, source_refs_json TEXT NOT NULL,
 built_at_utc TEXT NOT NULL,
 navigation_status TEXT NOT NULL DEFAULT 'HIDDEN',
 statistics_status TEXT NOT NULL DEFAULT 'EXCLUDED',
 ancestor_review_status TEXT NOT NULL DEFAULT 'CLEAR',
 direct_parent_link_status TEXT NOT NULL DEFAULT 'UNRESOLVED'
);
CREATE INDEX IF NOT EXISTS idx_master_events_scope
 ON master_map_events(symbol, canonical_range_id, processing_status);
CREATE TABLE IF NOT EXISTS master_map_relationships (
 child_canonical_range_id TEXT PRIMARY KEY, build_id TEXT NOT NULL, symbol TEXT NOT NULL,
 relationship_type TEXT NOT NULL, parent_canonical_range_id TEXT, link_source TEXT NOT NULL,
 link_status TEXT NOT NULL, link_confidence TEXT NOT NULL, reason_codes_json TEXT NOT NULL,
 notes TEXT NOT NULL, built_at_utc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_master_relationships_scope
 ON master_map_relationships(symbol, relationship_type, link_status);
CREATE TABLE IF NOT EXISTS master_map_review_items (
 review_key TEXT PRIMARY KEY, build_id TEXT NOT NULL, symbol TEXT NOT NULL,
 item_type TEXT NOT NULL, entity_kind TEXT NOT NULL, status TEXT NOT NULL,
 excluded_from_statistics INTEGER NOT NULL, review_json TEXT NOT NULL,
 built_at_utc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_master_reviews_scope
 ON master_map_review_items(symbol, status, item_type);
CREATE TABLE IF NOT EXISTS master_map_outputs (
 symbol TEXT PRIMARY KEY, build_id TEXT NOT NULL, schema_version TEXT NOT NULL,
 built_at_utc TEXT NOT NULL, structural_content_hash TEXT NOT NULL DEFAULT '',
 output_json TEXT NOT NULL
);
"""

MIGRATION_COLUMNS: dict[str, dict[str, str]] = {
    "master_map_ranges": {
        "navigation_status": "TEXT NOT NULL DEFAULT 'HIDDEN'",
        "statistics_status": "TEXT NOT NULL DEFAULT 'EXCLUDED'",
        "ancestor_review_status": "TEXT NOT NULL DEFAULT 'CLEAR'",
        "direct_parent_link_status": "TEXT NOT NULL DEFAULT 'ROOT'",
    },
    "master_map_events": {
        "navigation_status": "TEXT NOT NULL DEFAULT 'HIDDEN'",
        "statistics_status": "TEXT NOT NULL DEFAULT 'EXCLUDED'",
        "ancestor_review_status": "TEXT NOT NULL DEFAULT 'CLEAR'",
        "direct_parent_link_status": "TEXT NOT NULL DEFAULT 'UNRESOLVED'",
    },
    "master_map_outputs": {
        "structural_content_hash": "TEXT NOT NULL DEFAULT ''",
    },
}


@dataclass(frozen=True)
class RawRange:
    raw_id: int
    import_run_id: int | None
    case_ref: str | None
    source_id: str
    payload_hash: str
    raw_json: str
    symbol: str
    layer: str
    timeframe: str | None
    high: float | None
    low: float | None
    high_time: str | None
    low_time: str | None
    active_from: str | None
    inactive_from: str | None
    status: str
    break_direction: str | None
    explicit_parent_id: str | None
    imported_at: str | None
    import_started_at: str | None
    import_finished_at: str | None
    import_source_path: str | None
    source_created_at: str | None
    source_updated_at: str | None
    source_exported_at: str | None


@dataclass(frozen=True)
class RawEvent:
    raw_id: int
    raw_range_id: int | None
    case_ref: str | None
    source_id: str
    payload_hash: str
    raw_json: str
    event_type: str
    event_time: str | None
    price: float | None
    direction: str | None
    break_level: float | None
    range_source_id: str | None


@dataclass
class MasterRange:
    id: str
    key: tuple[Any, ...]
    sources: list[RawRange]
    processing_status: str = INCLUDED
    excluded: bool = False
    visible: bool = False
    reasons: set[str] = field(default_factory=set)
    navigation_status: str = NAV_HIDDEN
    statistics_status: str = STATS_EXCLUDED
    ancestor_review_status: str = ANCESTOR_CLEAR
    direct_parent_link_status: str = ROOT_LINK

    @property
    def row(self) -> RawRange:
        return self.sources[0]


@dataclass
class MasterEvent:
    id: str
    key: tuple[Any, ...]
    range_id: str | None
    sources: list[RawEvent]
    processing_status: str = INCLUDED
    excluded: bool = False
    reasons: set[str] = field(default_factory=set)
    navigation_status: str = NAV_HIDDEN
    statistics_status: str = STATS_EXCLUDED
    ancestor_review_status: str = ANCESTOR_CLEAR
    direct_parent_link_status: str = "UNRESOLVED"

    @property
    def row(self) -> RawEvent:
        return self.sources[0]


def build_master_map(
    db_path: str | Path,
    *,
    symbol: str = "XAUUSD",
    output_path: str | Path | None = None,
    built_at_utc: str | None = None,
    build_id: str | None = None,
) -> dict[str, Any]:
    """Rebuild one XAUUSD hierarchy without changing raw_ranges or raw_events."""
    symbol = symbol.strip().upper()
    if symbol != "XAUUSD":
        raise ValueError("Master Map v0.1 is intentionally scoped to XAUUSD only.")
    db = Path(db_path)
    if not db.exists():
        raise FileNotFoundError(f"Range Library database does not exist: {db}")
    built_at = iso(built_at_utc or utc_now())
    runtime_build_id = build_id or str(uuid.uuid4())

    with connect(db) as con:
        require_raw_tables(con)
        ensure_master_map_schema(con)
        raw_ranges = load_ranges(con, symbol)
        ranges, source_map, raw_map, range_reviews = canonicalize_ranges(raw_ranges)
        raw_events = load_events(con, symbol, raw_ranges)
        events, event_reviews = canonicalize_events(raw_events, source_map, raw_map, ranges)
        relationships, relationship_reviews = rebuild_relationships(ranges, source_map)
        apply_event_visibility(events, ranges)
        reviews = dedupe_reviews([*range_reviews, *event_reviews, *relationship_reviews])
        lifecycle_report = build_lifecycle_evidence_report(ranges, reviews)
        output = build_output(
            symbol, built_at, ranges, events, relationships, reviews, lifecycle_report,
            len(raw_ranges), len(raw_events),
        )
        output["build_id"] = runtime_build_id
        persist(
            con, symbol, runtime_build_id, built_at, ranges, events,
            relationships, reviews, output,
        )
        con.commit()

    if output_path is not None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def ensure_master_map_schema(con: sqlite3.Connection) -> None:
    con.executescript(SCHEMA_SQL)
    for table, columns in MIGRATION_COLUMNS.items():
        existing = {str(row["name"]) for row in con.execute(f"PRAGMA table_info({table})")}
        for name, definition in columns.items():
            if name not in existing:
                con.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def load_master_map_output(db_path: str | Path, *, symbol: str = "XAUUSD") -> dict[str, Any]:
    with connect(db_path) as con:
        ensure_master_map_schema(con)
        row = con.execute(
            "SELECT output_json FROM master_map_outputs WHERE symbol=?", (symbol.upper(),)
        ).fetchone()
    if row is None:
        raise LookupError(f"No Master Map output exists for {symbol.upper()}.")
    return json.loads(row["output_json"])


def require_raw_tables(con: sqlite3.Connection) -> None:
    names = {r["name"] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('raw_ranges','raw_events')"
    )}
    missing = {"raw_ranges", "raw_events"} - names
    if missing:
        raise RuntimeError(f"Range Library source tables missing: {', '.join(sorted(missing))}")


def load_ranges(con: sqlite3.Connection, symbol: str) -> list[RawRange]:
    rows = con.execute("""
      SELECT r.*,
             ir.source_path AS import_source_path,
             ir.started_at_utc AS import_started_at_utc,
             ir.finished_at_utc AS import_finished_at_utc
      FROM raw_ranges r
      LEFT JOIN import_runs ir ON ir.id=r.import_run_id
      JOIN (
        SELECT MAX(id) max_id FROM raw_ranges
        GROUP BY COALESCE(json_extract(raw_payload_json,'$.case_ref'),
                          json_extract(raw_payload_json,'$.raw_case_id'),
                          json_extract(raw_payload_json,'$.case_id'),''),
                 COALESCE(source_record_id,CAST(id AS TEXT))
      ) latest ON latest.max_id=r.id
      ORDER BY r.id
    """).fetchall()
    result = [parse_range(dict(row)) for row in rows]
    return [row for row in result if row.symbol == symbol and row.layer in LAYERS]


def load_events(con: sqlite3.Connection, symbol: str, ranges: list[RawRange]) -> list[RawEvent]:
    by_raw = {r.raw_id: r for r in ranges}
    by_identity = {(r.case_ref, r.source_id): r for r in ranges}
    rows = con.execute("""
      SELECT e.* FROM raw_events e
      JOIN (
        SELECT MAX(e2.id) max_id FROM raw_events e2
        LEFT JOIN raw_ranges r2 ON r2.id=e2.raw_range_id
        GROUP BY COALESCE(json_extract(e2.raw_payload_json,'$.case_ref'),
                          json_extract(e2.raw_payload_json,'$.raw_case_id'),
                          json_extract(e2.raw_payload_json,'$.case_id'),
                          json_extract(r2.raw_payload_json,'$.case_ref'),
                          json_extract(r2.raw_payload_json,'$.raw_case_id'),
                          json_extract(r2.raw_payload_json,'$.case_id'),''),
                 COALESCE(e2.source_record_id,CAST(e2.id AS TEXT))
      ) latest ON latest.max_id=e.id ORDER BY e.id
    """).fetchall()
    result: list[RawEvent] = []
    for sql_row in rows:
        linked = by_raw.get(int(sql_row["raw_range_id"])) if sql_row["raw_range_id"] is not None else None
        event = parse_event(dict(sql_row), linked)
        event_payload = payload(event.raw_json)
        payload_symbol = text(event_payload, "symbol")
        identity_link = by_identity.get((event.case_ref, event.range_source_id))
        resolved_symbol = (
            payload_symbol.upper() if payload_symbol else
            linked.symbol if linked else
            identity_link.symbol if identity_link else None
        )
        if resolved_symbol == symbol:
            result.append(event)
    return result


def parse_range(row: dict[str, Any]) -> RawRange:
    p = payload(row["raw_payload_json"])
    high = number(p, "range_high_price", "range_high", "high", "rh")
    low = number(p, "range_low_price", "range_low", "low", "rl")
    return RawRange(
        raw_id=int(row["id"]),
        import_run_id=int(row["import_run_id"]) if row.get("import_run_id") is not None else None,
        case_ref=text(p, "case_ref", "raw_case_id", "case_id"),
        source_id=str(row.get("source_record_id") or text(p, "range_id", "id") or row["id"]),
        payload_hash=str(row["payload_sha256"]),
        raw_json=str(row["raw_payload_json"]),
        symbol=str(row.get("symbol") or text(p, "symbol") or "UNKNOWN").upper(),
        layer=str(text(p, "structure_layer", "layer", "range_type", "type") or row.get("range_type") or "").upper(),
        timeframe=upper(row.get("timeframe") or text(p, "source_timeframe", "timeframe", "chart_timeframe")),
        high=high if high is not None else float(row["high"]) if row.get("high") is not None else None,
        low=low if low is not None else float(row["low"]) if row.get("low") is not None else None,
        high_time=maybe_iso(text(p, "range_high_time", "rh_time", "high_time")),
        low_time=maybe_iso(text(p, "range_low_time", "rl_time", "low_time")),
        active_from=maybe_iso(text(p, "active_from_time", "range_start_time", "start_time_utc", "start_time") or row.get("start_time_utc")),
        inactive_from=maybe_iso(text(p, "inactive_from_time")),
        status=str(text(p, "status", "range_status") or "UNKNOWN").upper(),
        break_direction=upper(text(p, "direction_of_break", "break_direction")),
        explicit_parent_id=text(p, "parent_range_id", "parent_id", "parent_source_record_id"),
        imported_at=maybe_iso(row.get("created_at_utc")),
        import_started_at=maybe_iso(row.get("import_started_at_utc")),
        import_finished_at=maybe_iso(row.get("import_finished_at_utc")),
        import_source_path=text_value(row.get("import_source_path")),
        source_created_at=maybe_iso(text(p, "created_at_utc", "created_at")),
        source_updated_at=maybe_iso(text(p, "updated_at_utc", "updated_at")),
        source_exported_at=maybe_iso(text(p, "source_exported_at", "exported_at", "generated_at_utc")),
    )


def parse_event(row: dict[str, Any], linked: RawRange | None) -> RawEvent:
    p = payload(row["raw_payload_json"])
    case_ref = text(p, "case_ref", "raw_case_id", "case_id") or (linked.case_ref if linked else None)
    range_id = text(p, "range_source_record_id", "raw_range_source_record_id", "active_range_id", "range_id")
    range_id = range_id or (linked.source_id if linked else None)
    event_price = number(p, "price", "event_price")
    return RawEvent(
        raw_id=int(row["id"]),
        raw_range_id=int(row["raw_range_id"]) if row.get("raw_range_id") is not None else None,
        case_ref=case_ref,
        source_id=str(row.get("source_record_id") or text(p, "event_id", "id") or row["id"]),
        payload_hash=str(row["payload_sha256"]),
        raw_json=str(row["raw_payload_json"]),
        event_type=str(row.get("event_type") or text(p, "event_type", "type", "legacy_event_type") or "UNKNOWN").upper(),
        event_time=maybe_iso(text(p, "event_time_utc", "event_time", "time", "timestamp", "candle_time") or row.get("event_time_utc")),
        price=event_price if event_price is not None else float(row["price"]) if row.get("price") is not None else None,
        direction=upper(text(p, "direction", "break_direction")),
        break_level=number(p, "break_level_price", "break_level", "boundary_price"),
        range_source_id=range_id,
    )


def canonicalize_ranges(raw: list[RawRange]) -> tuple[list[MasterRange], dict[tuple[str | None, str], str], dict[int, str], list[dict[str, Any]]]:
    groups: dict[tuple[Any, ...], list[RawRange]] = {}
    for row in raw:
        groups.setdefault(range_key(row), []).append(row)
    ranges = [MasterRange(cid("range", key), key, sorted(rows, key=raw_range_sort)) for key, rows in groups.items()]
    ranges.sort(key=master_range_sort)
    conflicts: list[tuple[str, list[MasterRange]]] = []

    by_source: dict[tuple[str, str, str], list[MasterRange]] = {}
    for item in ranges:
        for row in item.sources:
            by_source.setdefault((row.symbol, row.layer, row.source_id), []).append(item)
    for items in by_source.values():
        items = unique_ranges(items)
        if len(items) > 1 and not clearly_distinct(items):
            conflicts.append(("DUPLICATED_SOURCE_ID_CONFLICT", items))

    by_anchor: dict[tuple[Any, ...], list[MasterRange]] = {}
    for item in ranges:
        key = anchor_key(item.row)
        if key:
            by_anchor.setdefault(key, []).append(item)
    for items in by_anchor.values():
        for left_i, left in enumerate(items):
            for right in items[left_i + 1:]:
                if set(r.case_ref for r in left.sources) != set(r.case_ref for r in right.sources) and prices_overlap(left.row, right.row):
                    conflicts.append(("SAME_STRUCTURAL_ANCHORS_DIFFERENT_FACTS", [left, right]))

    reviews = mark_range_conflicts(conflicts)
    source_map: dict[tuple[str | None, str], str] = {}
    raw_map: dict[int, str] = {}
    for item in ranges:
        for row in item.sources:
            source_map[(row.case_ref, row.source_id)] = item.id
            raw_map[row.raw_id] = item.id
    return ranges, source_map, raw_map, reviews


def mark_range_conflicts(conflicts: list[tuple[str, list[MasterRange]]]) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, ...], tuple[set[str], list[MasterRange]]] = {}
    for reason, items in conflicts:
        ids = tuple(sorted({item.id for item in items}))
        reasons, current = buckets.setdefault(ids, (set(), unique_ranges(items)))
        reasons.add(reason)
        current[:] = unique_ranges([*current, *items])
    reviews = []
    for ids, (reasons, items) in sorted(buckets.items()):
        for item in items:
            item.processing_status = NEEDS_REVIEW
            item.excluded = True
            item.statistics_status = STATS_EXCLUDED
            item.reasons.update(reasons)
        reviews.append(review(
            "RANGE_DUPLICATE_CONFLICT", "RANGE", list(ids),
            [r.raw_id for i in items for r in i.sources],
            [r.case_ref for i in items for r in i.sources],
            [r.source_id for i in items for r in i.sources], sorted(reasons),
            "Potential duplicate ranges disagree on factual structure; all candidates remain reviewed and excluded from statistics.",
        ))
    return reviews


def canonicalize_events(
    raw: list[RawEvent],
    source_map: dict[tuple[str | None, str], str],
    raw_map: dict[int, str],
    ranges: list[MasterRange],
) -> tuple[list[MasterEvent], list[dict[str, Any]]]:
    range_status = {r.id: r.processing_status for r in ranges}
    resolved: list[tuple[RawEvent, str | None, str | None]] = []
    for row in raw:
        range_id = source_map.get((row.case_ref, row.range_source_id)) if row.range_source_id else None
        range_id = range_id or (raw_map.get(row.raw_range_id) if row.raw_range_id is not None else None)
        reason = "EVENT_RANGE_UNRESOLVED" if range_id is None else "EVENT_RANGE_NEEDS_REVIEW" if range_status.get(range_id) != INCLUDED else None
        resolved.append((row, range_id, reason))

    groups: dict[tuple[Any, ...], list[tuple[RawEvent, str | None, str | None]]] = {}
    for row, range_id, reason in resolved:
        groups.setdefault(event_key(row, range_id), []).append((row, range_id, reason))
    events: list[MasterEvent] = []
    reviews: list[dict[str, Any]] = []
    for key, group in groups.items():
        item = MasterEvent(cid("event", key), key, group[0][1], sorted([g[0] for g in group], key=raw_event_sort))
        reasons = sorted({g[2] for g in group if g[2]})
        if reasons:
            item.processing_status = NEEDS_REVIEW
            item.excluded = True
            item.statistics_status = STATS_EXCLUDED
            item.reasons.update(reasons)
            reviews.append(review(
                "EVENT_RANGE_UNCERTAIN", "EVENT", [item.id],
                [r.raw_id for r in item.sources], [r.case_ref for r in item.sources],
                [r.source_id for r in item.sources], reasons,
                "Event could not be attached to one comparison-eligible canonical range.",
            ))
        events.append(item)
    events.sort(key=master_event_sort)

    conflicts: list[tuple[str, list[MasterEvent]]] = []
    by_source: dict[str, list[MasterEvent]] = {}
    by_signature: dict[tuple[Any, ...], list[MasterEvent]] = {}
    for item in events:
        for row in item.sources:
            by_source.setdefault(row.source_id, []).append(item)
        if item.row.event_time:
            by_signature.setdefault((item.range_id, item.row.event_type, item.row.event_time), []).append(item)
    for items in by_source.values():
        items = unique_events(items)
        times = {item.row.event_time for item in items}
        if len(items) > 1 and (None in times or len(times) < len(items)):
            conflicts.append(("DUPLICATED_EVENT_ID_CONFLICT", items))
    for items in by_signature.values():
        items = unique_events(items)
        if len(items) > 1:
            conflicts.append(("SAME_EVENT_TIME_DIFFERENT_FACTS", items))
    reviews.extend(mark_event_conflicts(conflicts))
    return events, dedupe_reviews(reviews)


def mark_event_conflicts(conflicts: list[tuple[str, list[MasterEvent]]]) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, ...], tuple[set[str], list[MasterEvent]]] = {}
    for reason, items in conflicts:
        ids = tuple(sorted({item.id for item in items}))
        reasons, current = buckets.setdefault(ids, (set(), unique_events(items)))
        reasons.add(reason)
        current[:] = unique_events([*current, *items])
    reviews = []
    for ids, (reasons, items) in sorted(buckets.items()):
        for item in items:
            item.processing_status = NEEDS_REVIEW
            item.excluded = True
            item.statistics_status = STATS_EXCLUDED
            item.reasons.update(reasons)
        reviews.append(review(
            "EVENT_DUPLICATE_CONFLICT", "EVENT", list(ids),
            [r.raw_id for i in items for r in i.sources],
            [r.case_ref for i in items for r in i.sources],
            [r.source_id for i in items for r in i.sources], sorted(reasons),
            "Potential duplicate events disagree on factual evidence; all candidates remain reviewed and excluded from statistics.",
        ))
    return reviews


def rebuild_relationships(
    ranges: list[MasterRange], source_map: dict[tuple[str | None, str], str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_id = {r.id: r for r in ranges}
    relationships: list[dict[str, Any]] = []
    reviews: list[dict[str, Any]] = []

    for weekly in (r for r in ranges if r.row.layer == "WEEKLY"):
        weekly.direct_parent_link_status = ROOT_LINK
        if navigable_range(weekly):
            weekly.visible = True
            if weekly.processing_status == INCLUDED:
                weekly.navigation_status = NAV_TRUSTED
                weekly.statistics_status = STATS_ELIGIBLE
                weekly.ancestor_review_status = ANCESTOR_CLEAR
                weekly.excluded = False
            else:
                weekly.navigation_status = NAV_REVIEW
                weekly.statistics_status = STATS_EXCLUDED
                weekly.ancestor_review_status = ANCESTOR_SELF_REVIEW
                weekly.excluded = True

    for child_layer in ("DAILY", "INTRADAY"):
        parent_layer = PARENT[child_layer]
        parents = [r for r in ranges if r.row.layer == parent_layer]
        for child in [r for r in ranges if r.row.layer == child_layer]:
            parent_id: str | None = None
            source, status, confidence, reasons = "inferred", VALID, "medium", []
            notes = "One factual parent candidate matched time and price."
            explicit, unresolved = explicit_parent_candidates(child, source_map)

            if child.processing_status != INCLUDED:
                status, confidence, reasons = NEEDS_REVIEW, "none", ["CHILD_RANGE_NEEDS_REVIEW"]
                notes = "Child range identity is unresolved; a unique explicit parent may still be used for review navigation."
                if not unresolved and len(explicit) == 1:
                    source, parent_id = "explicit_review", next(iter(explicit))
                elif unresolved:
                    reasons.append("EXPLICIT_PARENT_UNRESOLVED")
                elif len(explicit) > 1:
                    reasons.append("EXPLICIT_PARENT_CONFLICT")
            elif unresolved or len(explicit) > 1:
                status, confidence = NEEDS_REVIEW, "low"
                reasons = ["EXPLICIT_PARENT_UNRESOLVED" if unresolved else "EXPLICIT_PARENT_CONFLICT"]
                notes = "Source evidence does not resolve to one canonical explicit parent."
            elif explicit:
                source, parent_id, confidence = "explicit", next(iter(explicit)), "high"
                parent = by_id.get(parent_id)
                if not parent or parent.row.layer != parent_layer or not parent_candidate(parent, child):
                    status, confidence, reasons = NEEDS_REVIEW, "low", ["EXPLICIT_PARENT_FACTS_DISAGREE"]
                    notes = "Explicit parent failed layer, time, or price checks; retained only as a review-navigation link."
                elif parent.processing_status != INCLUDED:
                    status, confidence, reasons = VALID, "high", []
                    notes = "Explicit factual parent is reviewed; the direct link remains valid while the chain is excluded from statistics."
                else:
                    notes = "All explicit source references resolve to one factual canonical parent."
            else:
                candidates = [p for p in parents if p.processing_status == INCLUDED and parent_candidate(p, child)]
                if not candidates:
                    status, confidence, reasons = ORPHAN, "low", ["NO_FACTUAL_PARENT_CANDIDATE"]
                    notes = "No canonical parent matched factual time and price evidence."
                elif len(candidates) > 1:
                    status, confidence, reasons = NEEDS_REVIEW, "low", ["MULTIPLE_FACTUAL_PARENT_CANDIDATES"]
                    notes = "More than one parent remains plausible; v0.1 does not guess."
                else:
                    parent_id = candidates[0].id

            child.direct_parent_link_status = status
            relationship = {
                "relationship_type": f"{parent_layer.lower()}_{child_layer.lower()}",
                "parent_canonical_range_id": parent_id,
                "child_canonical_range_id": child.id,
                "link_source": source,
                "link_status": status,
                "link_confidence": confidence,
                "reason_codes": sorted(set(reasons)),
                "notes": notes,
            }
            relationships.append(relationship)

            parent = by_id.get(parent_id) if parent_id else None
            configure_child_navigation(child, parent, status)
            if child.statistics_status == STATS_EXCLUDED and child.processing_status == INCLUDED:
                reviews.append(review(
                    "ORPHAN_RANGE" if status == ORPHAN else "PARENT_RELATIONSHIP_REVIEW",
                    "RELATIONSHIP", [child.id] + ([parent_id] if parent_id else []),
                    [r.raw_id for r in child.sources], [r.case_ref for r in child.sources],
                    [r.source_id for r in child.sources], reasons or [status], notes,
                ))

    relationships.sort(key=lambda r: (r["relationship_type"], r["child_canonical_range_id"]))
    return relationships, reviews


def explicit_parent_candidates(
    child: MasterRange, source_map: dict[tuple[str | None, str], str]
) -> tuple[set[str], bool]:
    explicit: set[str] = set()
    unresolved = False
    for raw in child.sources:
        if raw.explicit_parent_id:
            found = source_map.get((raw.case_ref, raw.explicit_parent_id))
            unresolved = unresolved or found is None
            if found:
                explicit.add(found)
    return explicit, unresolved


def configure_child_navigation(child: MasterRange, parent: MasterRange | None, link_status: str) -> None:
    child.statistics_status = STATS_EXCLUDED
    child.excluded = True
    child.visible = False
    child.navigation_status = NAV_HIDDEN
    child.ancestor_review_status = ANCESTOR_CLEAR
    if not navigable_range(child):
        return

    if parent is None:
        # Factual child evidence may remain navigable as an unlinked review branch.
        # No parent is guessed, and identity-conflicted children stay hidden.
        if child.processing_status == INCLUDED and link_status in {ORPHAN, NEEDS_REVIEW}:
            child.visible = True
            child.navigation_status = NAV_REVIEW
            child.ancestor_review_status = ANCESTOR_DIRECT_REVIEW
        return
    if parent.navigation_status == NAV_HIDDEN:
        return

    child.visible = True
    self_review = child.processing_status != INCLUDED
    direct_review = link_status != VALID
    upstream_review = parent.statistics_status != STATS_ELIGIBLE
    if not self_review and not direct_review and not upstream_review:
        child.navigation_status = NAV_TRUSTED
        child.statistics_status = STATS_ELIGIBLE
        child.ancestor_review_status = ANCESTOR_CLEAR
        child.excluded = False
        return

    child.navigation_status = NAV_REVIEW
    if self_review and upstream_review:
        child.ancestor_review_status = ANCESTOR_SELF_AND_UPSTREAM
    elif self_review:
        child.ancestor_review_status = ANCESTOR_SELF_REVIEW
    elif direct_review:
        child.ancestor_review_status = ANCESTOR_DIRECT_REVIEW
    else:
        child.ancestor_review_status = ANCESTOR_UPSTREAM_REVIEW


def apply_event_visibility(events: list[MasterEvent], ranges: list[MasterRange]) -> None:
    by_id = {r.id: r for r in ranges}
    for event in events:
        parent = by_id.get(event.range_id) if event.range_id else None
        if parent is None or parent.navigation_status == NAV_HIDDEN:
            continue
        if event.processing_status == INCLUDED and parent.statistics_status == STATS_ELIGIBLE:
            event.navigation_status = NAV_TRUSTED
            event.statistics_status = STATS_ELIGIBLE
            event.ancestor_review_status = ANCESTOR_CLEAR
            event.direct_parent_link_status = VALID
            event.excluded = False
        elif event.range_id is not None:
            event.navigation_status = NAV_REVIEW
            event.statistics_status = STATS_EXCLUDED
            event.direct_parent_link_status = parent.direct_parent_link_status
            event.ancestor_review_status = (
                ANCESTOR_SELF_REVIEW if event.processing_status != INCLUDED
                else ANCESTOR_UPSTREAM_REVIEW
            )
            event.excluded = True


def parent_candidate(parent: MasterRange, child: MasterRange) -> bool:
    p, c = parent.row, child.row
    if p.symbol != c.symbol or None in (p.high, p.low, c.high, c.low):
        return False
    p_low, p_high = sorted((p.low, p.high))
    c_low, c_high = sorted((c.low, c.high))
    if c_low > p_high or c_high < p_low:
        return False
    p_start, c_start = formation_time(p), formation_time(c)
    if p_start is None or c_start is None or c_start < p_start:
        return False
    if p.status in {"BROKEN", "ABANDONED", "ARCHIVED"}:
        cutoff = parse_time(p.inactive_from)
        if cutoff is None or c_start > cutoff:
            return False
    return True


def navigable_range(item: MasterRange) -> bool:
    row = item.row
    return row.layer in LAYERS and row.high is not None and row.low is not None and formation_time(row) is not None


def build_output(
    symbol: str,
    built_at: str,
    ranges: list[MasterRange],
    events: list[MasterEvent],
    relationships: list[dict[str, Any]],
    reviews: list[dict[str, Any]],
    lifecycle_report: list[dict[str, Any]],
    raw_range_count: int,
    raw_event_count: int,
) -> dict[str, Any]:
    by_id = {r.id: r for r in ranges}
    child_ids: dict[str, list[str]] = {}
    unlinked_review_ids: list[str] = []
    for rel in relationships:
        child = by_id[rel["child_canonical_range_id"]]
        parent_id = rel["parent_canonical_range_id"]
        if child.navigation_status != NAV_HIDDEN and parent_id:
            child_ids.setdefault(parent_id, []).append(child.id)
        elif child.navigation_status == NAV_REVIEW and parent_id is None:
            unlinked_review_ids.append(child.id)

    events_by_range: dict[str, list[MasterEvent]] = {}
    for event in events:
        if event.navigation_status != NAV_HIDDEN and event.range_id in by_id:
            events_by_range.setdefault(str(event.range_id), []).append(event)

    def event_node(event: MasterEvent) -> dict[str, Any]:
        p = event.row
        return {
            "id": event.id,
            "node_type": "EVENT",
            "event_type": p.event_type,
            "event_time_utc": p.event_time,
            "price": p.price,
            "direction": p.direction,
            "break_level": p.break_level,
            "source_count": len(event.sources),
            "source_refs": refs(event.sources),
            "navigation_status": event.navigation_status,
            "statistics_status": event.statistics_status,
            "ancestor_review_status": event.ancestor_review_status,
            "direct_parent_link_status": event.direct_parent_link_status,
        }

    def range_node(range_id: str, *, child_filter: str = "all") -> dict[str, Any]:
        item, p = by_id[range_id], by_id[range_id].row
        children = []
        for child_id in sorted(child_ids.get(range_id, []), key=lambda value: master_range_sort(by_id[value])):
            child = by_id[child_id]
            if child_filter == "trusted" and child.statistics_status != STATS_ELIGIBLE:
                continue
            children.append(range_node(child_id, child_filter=child_filter))
        event_nodes = []
        for event in sorted(events_by_range.get(item.id, []), key=master_event_sort):
            if child_filter == "trusted" and event.statistics_status != STATS_ELIGIBLE:
                continue
            event_nodes.append(event_node(event))
        return {
            "id": item.id,
            "node_type": "RANGE",
            "structure_layer": p.layer,
            "source_timeframe": p.timeframe,
            "range_high": p.high,
            "range_low": p.low,
            "range_high_time": p.high_time,
            "range_low_time": p.low_time,
            "active_from_time": p.active_from,
            "inactive_from_time": p.inactive_from,
            "status": p.status,
            "direction_of_break": p.break_direction,
            "source_count": len(item.sources),
            "source_refs": refs(item.sources),
            "navigation_status": item.navigation_status,
            "statistics_status": item.statistics_status,
            "ancestor_review_status": item.ancestor_review_status,
            "direct_parent_link_status": item.direct_parent_link_status,
            "events": event_nodes,
            "children": children,
        }

    nav_weeklies = sorted(
        [r for r in ranges if r.row.layer == "WEEKLY" and r.navigation_status != NAV_HIDDEN],
        key=master_range_sort,
    )
    trusted_weeklies = [r for r in nav_weeklies if r.statistics_status == STATS_ELIGIBLE]
    full_children = [range_node(r.id) for r in nav_weeklies]
    trusted_children = [range_node(r.id, child_filter="trusted") for r in trusted_weeklies]
    full_root = {
        "id": f"symbol:{symbol}", "node_type": "SYMBOL", "label": symbol,
        "children": full_children,
        "unlinked_review_children": [range_node(rid) for rid in sorted(unlinked_review_ids, key=lambda value: master_range_sort(by_id[value]))],
    }
    trusted_root = {
        "id": f"symbol:{symbol}:trusted", "node_type": "SYMBOL", "label": symbol,
        "children": trusted_children,
    }
    review_root = build_review_root(symbol, full_root)

    trusted_counts = {layer: sum(1 for r in ranges if r.row.layer == layer and r.statistics_status == STATS_ELIGIBLE) for layer in LAYERS}
    nav_counts = {layer: sum(1 for r in ranges if r.row.layer == layer and r.navigation_status != NAV_HIDDEN) for layer in LAYERS}
    review_counts = {layer: sum(1 for r in ranges if r.row.layer == layer and r.navigation_status == NAV_REVIEW) for layer in LAYERS}
    eligible_events = sum(1 for e in events if e.statistics_status == STATS_ELIGIBLE)
    review_events = sum(1 for e in events if e.navigation_status == NAV_REVIEW)
    hidden_ranges = sum(1 for r in ranges if r.navigation_status == NAV_HIDDEN)
    hidden_events = sum(1 for e in events if e.navigation_status == NAV_HIDDEN)

    statistics = {
        "raw_range_sources": raw_range_count,
        "raw_event_sources": raw_event_count,
        "canonical_ranges_before_review_exclusion": len(ranges),
        "canonical_events_before_review_exclusion": len(events),
        "exact_range_duplicates_collapsed": max(0, raw_range_count - len(ranges)),
        "exact_event_duplicates_collapsed": max(0, raw_event_count - len(events)),
        "comparison_eligible_ranges": sum(trusted_counts.values()),
        "comparison_eligible_events": eligible_events,
        "visible_ranges_by_layer": trusted_counts,
        "trusted_visible_ranges_by_layer": trusted_counts,
        "navigation_visible_ranges_by_layer": nav_counts,
        "review_visible_ranges_by_layer": review_counts,
        "review_visible_events": review_events,
        "hidden_range_records": hidden_ranges,
        "hidden_event_records": hidden_events,
        "needs_review_items": len(reviews),
        "excluded_range_records": sum(1 for r in ranges if r.statistics_status == STATS_EXCLUDED),
        "excluded_event_records": sum(1 for e in events if e.statistics_status == STATS_EXCLUDED),
    }
    stable_content = {
        "schema_version": VERSION,
        "symbol": symbol,
        "root": strip_volatile_for_hash(full_root),
        "trusted_root": strip_volatile_for_hash(trusted_root),
        "review_root": strip_volatile_for_hash(review_root),
        "statistics": statistics,
        "review_items": strip_volatile_for_hash(reviews),
        "lifecycle_evidence_report": strip_volatile_for_hash(lifecycle_report),
    }
    content_hash = hashlib.sha256(dump(stable_content).encode()).hexdigest()
    return {
        "schema_version": VERSION,
        "built_at_utc": built_at,
        "symbol": symbol,
        "structural_content_hash": content_hash,
        "root": full_root,
        "trusted_root": trusted_root,
        "review_root": review_root,
        "statistics": statistics,
        "review_items": reviews,
        "lifecycle_evidence_report": lifecycle_report,
    }


def build_review_root(symbol: str, full_root: dict[str, Any]) -> dict[str, Any]:
    def filter_node(node: dict[str, Any]) -> dict[str, Any] | None:
        children = [filtered for child in node.get("children", []) if (filtered := filter_node(child)) is not None]
        events = [event for event in node.get("events", []) if event.get("navigation_status") == NAV_REVIEW]
        own_review = node.get("navigation_status") == NAV_REVIEW
        if not own_review and not children and not events:
            return None
        result = dict(node)
        result["children"] = children
        result["events"] = events
        result["review_context_only"] = not own_review
        return result

    children = [filtered for child in full_root.get("children", []) if (filtered := filter_node(child)) is not None]
    return {
        "id": f"symbol:{symbol}:review",
        "node_type": "SYMBOL",
        "label": symbol,
        "children": children,
        "unlinked_review_children": full_root.get("unlinked_review_children", []),
    }


def build_lifecycle_evidence_report(
    ranges: list[MasterRange], reviews: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    by_id = {item.id: item for item in ranges}
    report: list[dict[str, Any]] = []
    for review_item in reviews:
        if review_item.get("item_type") != "RANGE_DUPLICATE_CONFLICT":
            continue
        canonical_ids = review_item.get("canonical_ids", [])
        items = [by_id[item_id] for item_id in canonical_ids if item_id in by_id]
        if not items:
            continue
        candidates = []
        for item in items:
            for raw in item.sources:
                p = payload(raw.raw_json)
                candidates.append({
                    "canonical_range_id": item.id,
                    "case_ref": raw.case_ref,
                    "source_record_id": raw.source_id,
                    "raw_id": raw.raw_id,
                    "import_run_id": raw.import_run_id,
                    "import_order": raw.raw_id,
                    "import_source_path": raw.import_source_path,
                    "import_started_at_utc": raw.import_started_at,
                    "import_finished_at_utc": raw.import_finished_at,
                    "imported_at_utc": raw.imported_at,
                    "source_created_at_utc": raw.source_created_at,
                    "source_updated_at_utc": raw.source_updated_at,
                    "source_exported_at_utc": raw.source_exported_at,
                    "status": raw.status,
                    "active_from_time": raw.active_from,
                    "inactive_from_time": raw.inactive_from,
                    "direction_of_break": raw.break_direction,
                    "broken_by_event_id": text(p, "broken_by_event_id"),
                    "old_range_id": text(p, "old_range_id"),
                    "new_range_id": text(p, "new_range_id"),
                    "range_high": raw.high,
                    "range_low": raw.low,
                    "range_high_time": raw.high_time,
                    "range_low_time": raw.low_time,
                })
        candidates.sort(key=lambda row: (
            row.get("source_updated_at_utc") or row.get("source_created_at_utc") or "",
            row.get("import_order") or 0,
            row.get("case_ref") or "",
            source_id_sort(str(row.get("source_record_id") or "")),
        ))
        chronology = assess_lifecycle_chronology(candidates)
        anchor = items[0].row
        report.append({
            "conflict_group_id": cid("lifecycle", tuple(sorted(canonical_ids))),
            "canonical_ids": sorted(canonical_ids),
            "reason_codes": sorted(review_item.get("reason_codes", [])),
            "anchor": {
                "symbol": anchor.symbol,
                "structure_layer": anchor.layer,
                "source_timeframe": anchor.timeframe,
                "range_high_time": anchor.high_time,
                "range_low_time": anchor.low_time,
                "range_high": anchor.high,
                "range_low": anchor.low,
            },
            "candidates": candidates,
            "chronology_assessment": chronology,
            "automatic_reconciliation": "NOT_APPLIED",
        })
    return sorted(report, key=lambda item: item["conflict_group_id"])


def assess_lifecycle_chronology(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    observations: list[tuple[datetime, str, dict[str, Any]]] = []
    for candidate in candidates:
        observed = candidate.get("source_updated_at_utc") or candidate.get("source_created_at_utc") or candidate.get("source_exported_at_utc")
        parsed = parse_time(observed)
        if parsed is not None:
            observations.append((parsed, str(candidate.get("status") or "UNKNOWN").upper(), candidate))
    observations.sort(key=lambda item: item[0])
    statuses = [status for _, status, _ in observations]
    if len(observations) < 2:
        return {
            "status": "INSUFFICIENT_CHRONOLOGY",
            "status_sequence": statuses,
            "recommendation": "Keep all lifecycle variants in NEEDS_REVIEW until reliable observation chronology is available.",
        }
    active_positions = [index for index, status in enumerate(statuses) if status in {"ACTIVE", "FORMING"}]
    closed_positions = [index for index, status in enumerate(statuses) if status in {"BROKEN", "ABANDONED", "ARCHIVED"}]
    if active_positions and closed_positions and max(active_positions) < min(closed_positions):
        closed_rows = [row for _, status, row in observations if status in {"BROKEN", "ABANDONED", "ARCHIVED"}]
        lifecycle_complete = all(row.get("inactive_from_time") for row in closed_rows)
        if lifecycle_complete:
            return {
                "status": "CHRONOLOGICAL_TRANSITION_CANDIDATE",
                "status_sequence": statuses,
                "recommendation": "A monotonic active-to-inactive sequence is present. Review chart evidence before adding an explicit lifecycle reconciliation rule; do not auto-merge yet.",
            }
    if active_positions and closed_positions:
        return {
            "status": "CONTRADICTORY_LIFECYCLE_OBSERVATIONS",
            "status_sequence": statuses,
            "recommendation": "Observed statuses are not monotonic. Keep every variant reviewed and require manual chart confirmation.",
        }
    return {
        "status": "NON_TRANSITIONAL_FACT_DIFFERENCE",
        "status_sequence": statuses,
        "recommendation": "The conflict is not a supported active-to-inactive lifecycle sequence. Keep reviewed.",
    }


def persist(
    con: sqlite3.Connection,
    symbol: str,
    build_id: str,
    built_at: str,
    ranges: list[MasterRange],
    events: list[MasterEvent],
    relationships: list[dict[str, Any]],
    reviews: list[dict[str, Any]],
    output: dict[str, Any],
) -> None:
    for table in (
        "master_map_relationships", "master_map_review_items", "master_map_events",
        "master_map_ranges", "master_map_outputs",
    ):
        con.execute(f"DELETE FROM {table} WHERE symbol=?", (symbol,))
    for item in ranges:
        con.execute("""
            INSERT INTO master_map_ranges (
              canonical_range_id,build_id,symbol,structure_layer,source_timeframe,
              processing_status,excluded_from_statistics,visible_in_hierarchy,
              source_count,canonical_payload_json,source_refs_json,built_at_utc,
              navigation_status,statistics_status,ancestor_review_status,direct_parent_link_status
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            item.id, build_id, symbol, item.row.layer, item.row.timeframe,
            item.processing_status, int(item.statistics_status == STATS_EXCLUDED),
            int(item.navigation_status != NAV_HIDDEN), len(item.sources),
            dump(range_payload(item.row)), dump(refs(item.sources)), built_at,
            item.navigation_status, item.statistics_status,
            item.ancestor_review_status, item.direct_parent_link_status,
        ))
    for item in events:
        con.execute("""
            INSERT INTO master_map_events (
              canonical_event_id,build_id,symbol,canonical_range_id,processing_status,
              excluded_from_statistics,source_count,canonical_payload_json,source_refs_json,
              built_at_utc,navigation_status,statistics_status,ancestor_review_status,
              direct_parent_link_status
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            item.id, build_id, symbol, item.range_id, item.processing_status,
            int(item.statistics_status == STATS_EXCLUDED), len(item.sources),
            dump(event_payload(item.row, item.range_id)), dump(refs(item.sources)), built_at,
            item.navigation_status, item.statistics_status,
            item.ancestor_review_status, item.direct_parent_link_status,
        ))
    for rel in relationships:
        con.execute("""
            INSERT INTO master_map_relationships (
              child_canonical_range_id,build_id,symbol,relationship_type,
              parent_canonical_range_id,link_source,link_status,link_confidence,
              reason_codes_json,notes,built_at_utc
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (
            rel["child_canonical_range_id"], build_id, symbol, rel["relationship_type"],
            rel["parent_canonical_range_id"], rel["link_source"], rel["link_status"],
            rel["link_confidence"], dump(rel["reason_codes"]), rel["notes"], built_at,
        ))
    for item in reviews:
        con.execute("""
            INSERT INTO master_map_review_items (
              review_key,build_id,symbol,item_type,entity_kind,status,
              excluded_from_statistics,review_json,built_at_utc
            ) VALUES (?,?,?,?,?,?,?,?,?)
        """, (
            item["review_key"], build_id, symbol, item["item_type"], item["entity_kind"],
            NEEDS_REVIEW, 1, dump(item), built_at,
        ))
    con.execute("""
        INSERT INTO master_map_outputs (
          symbol,build_id,schema_version,built_at_utc,structural_content_hash,output_json
        ) VALUES (?,?,?,?,?,?)
    """, (
        symbol, build_id, VERSION, built_at, output["structural_content_hash"], dump(output),
    ))


def range_key(r: RawRange) -> tuple[Any, ...]:
    return (
        r.symbol, r.layer, r.timeframe, num_key(r.high), num_key(r.low),
        r.high_time, r.low_time, r.active_from, r.inactive_from, r.status,
        r.break_direction,
    )


def anchor_key(r: RawRange) -> tuple[Any, ...] | None:
    times = (r.high_time, r.low_time, r.active_from)
    return (r.symbol, r.layer, r.timeframe, *times) if sum(v is not None for v in times) >= 2 else None


def event_key(e: RawEvent, range_id: str | None) -> tuple[Any, ...]:
    return (range_id, e.event_type, e.event_time, num_key(e.price), e.direction, num_key(e.break_level))


def range_payload(r: RawRange) -> dict[str, Any]:
    return {
        "symbol": r.symbol,
        "structure_layer": r.layer,
        "source_timeframe": r.timeframe,
        "range_high": r.high,
        "range_low": r.low,
        "range_high_time": r.high_time,
        "range_low_time": r.low_time,
        "active_from_time": r.active_from,
        "inactive_from_time": r.inactive_from,
        "status": r.status,
        "direction_of_break": r.break_direction,
    }


def event_payload(e: RawEvent, range_id: str | None) -> dict[str, Any]:
    return {
        "canonical_range_id": range_id,
        "event_type": e.event_type,
        "event_time_utc": e.event_time,
        "price": e.price,
        "direction": e.direction,
        "break_level": e.break_level,
    }


def review(
    item_type: str,
    entity_kind: str,
    canonical_ids: list[str],
    raw_ids: list[int],
    case_refs: list[str | None],
    source_ids: list[str],
    reasons: list[str],
    summary: str,
) -> dict[str, Any]:
    canonical_ids = sorted(set(canonical_ids))
    raw_ids = sorted(set(raw_ids))
    return {
        "review_key": cid("review", (item_type, entity_kind, *canonical_ids, *raw_ids)),
        "item_type": item_type,
        "entity_kind": entity_kind,
        "status": NEEDS_REVIEW,
        "excluded_from_statistics": True,
        "canonical_ids": canonical_ids,
        "raw_ids": raw_ids,
        "case_refs": sorted({c for c in case_refs if c is not None}),
        "source_record_ids": sorted(set(source_ids), key=source_id_sort),
        "reason_codes": sorted(set(reasons)),
        "summary": summary,
    }


def dedupe_reviews(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    for item in items:
        current = by_key.get(item["review_key"])
        if current is None:
            by_key[item["review_key"]] = item
        else:
            current["reason_codes"] = sorted(set(current["reason_codes"] + item["reason_codes"]))
    return sorted(by_key.values(), key=lambda item: item["review_key"])


def refs(rows: Iterable[RawRange | RawEvent]) -> list[dict[str, Any]]:
    return [
        {
            "raw_id": r.raw_id,
            "case_ref": r.case_ref,
            "source_record_id": r.source_id,
            "payload_sha256": r.payload_hash,
        }
        for r in sorted(rows, key=lambda r: (r.case_ref or "", source_id_sort(r.source_id), r.raw_id))
    ]


def strip_volatile_for_hash(value: Any) -> Any:
    volatile = {
        "build_id", "built_at_utc", "raw_id", "raw_ids", "review_key",
        "import_run_id", "import_order", "import_source_path",
        "import_started_at_utc", "import_finished_at_utc", "imported_at_utc",
        "payload_sha256", "source_refs",
    }
    if isinstance(value, dict):
        return {
            key: strip_volatile_for_hash(item)
            for key, item in sorted(value.items()) if key not in volatile
        }
    if isinstance(value, list):
        return [strip_volatile_for_hash(item) for item in value]
    return value


def clearly_distinct(items: list[MasterRange]) -> bool:
    return all(not windows_overlap(left.row, right.row) for i, left in enumerate(items) for right in items[i + 1:])


def windows_overlap(left: RawRange, right: RawRange) -> bool:
    a, b = time_window(left), time_window(right)
    return True if a is None or b is None else a[0] <= b[1] and b[0] <= a[1]


def time_window(r: RawRange) -> tuple[datetime, datetime] | None:
    values = [parse_time(v) for v in (r.high_time, r.low_time, r.active_from, r.inactive_from) if v]
    values = [v for v in values if v is not None]
    return (min(values), max(values)) if values else None


def prices_overlap(left: RawRange, right: RawRange) -> bool:
    if None in (left.high, left.low, right.high, right.low):
        return True
    l_low, l_high = sorted((left.low, left.high))
    r_low, r_high = sorted((right.low, right.high))
    return l_low <= r_high and r_low <= l_high


def formation_time(r: RawRange) -> datetime | None:
    active = parse_time(r.active_from)
    anchors = [v for v in (parse_time(r.high_time), parse_time(r.low_time)) if v]
    return active or (max(anchors) if anchors else None)


def unique_ranges(items: list[MasterRange]) -> list[MasterRange]:
    return list({item.id: item for item in items}.values())


def unique_events(items: list[MasterEvent]) -> list[MasterEvent]:
    return list({item.id: item for item in items}.values())


def cid(kind: str, key: tuple[Any, ...]) -> str:
    return f"mm:{kind}:{hashlib.sha256(dump(list(key)).encode()).hexdigest()[:20]}"


def master_range_sort(item: MasterRange) -> tuple[Any, ...]:
    r = item.row
    return (LAYERS.index(r.layer), r.active_from or r.high_time or r.low_time or "", num_key(r.low) or "", item.id)


def master_event_sort(item: MasterEvent) -> tuple[Any, ...]:
    return (item.row.event_time or "", item.row.event_type, item.id)


def raw_range_sort(r: RawRange) -> tuple[Any, ...]:
    return (r.case_ref or "", source_id_sort(r.source_id), r.raw_id)


def raw_event_sort(r: RawEvent) -> tuple[Any, ...]:
    return (r.case_ref or "", source_id_sort(r.source_id), r.raw_id)


def source_id_sort(value: str) -> tuple[int, int | str]:
    return (0, int(value)) if value.isdigit() else (1, value)


def payload(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def text(p: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = p.get(key)
        if value is not None and str(value).strip():
            return str(value)
    nested = p.get("raw_payload_json")
    if isinstance(nested, str):
        nested = payload(nested)
    return text(nested, *keys) if isinstance(nested, dict) else None


def text_value(value: Any) -> str | None:
    if value is None or not str(value).strip():
        return None
    return str(value)


def number(p: dict[str, Any], *keys: str) -> float | None:
    value = text(p, *keys)
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


def upper(value: Any) -> str | None:
    return str(value).upper() if value is not None and str(value).strip() else None


def num_key(value: float | None) -> str | None:
    return format(float(value), ".12g") if value is not None else None


def maybe_iso(value: Any) -> str | None:
    if value is None or not str(value).strip():
        return None
    try:
        return iso(str(value))
    except ValueError:
        return str(value)


def iso(value: str) -> str:
    parsed = parse_time(value)
    if parsed is None:
        raise ValueError(f"Invalid ISO timestamp: {value}")
    return parsed.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return (parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed).astimezone(UTC)


def dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="range_library_memory.master_map")
    parser.add_argument("--db-path", type=Path, required=True)
    parser.add_argument("--symbol", default="XAUUSD", choices=("XAUUSD",))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = build_master_map(args.db_path, symbol=args.symbol, output_path=args.output)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        stats = result["statistics"]
        print(f"symbol: {result['symbol']}")
        print(f"comparison_eligible_ranges: {stats['comparison_eligible_ranges']}")
        print(f"comparison_eligible_events: {stats['comparison_eligible_events']}")
        print(f"navigation_visible_ranges_by_layer: {stats['navigation_visible_ranges_by_layer']}")
        print(f"needs_review_items: {stats['needs_review_items']}")
        print(f"structural_content_hash: {result['structural_content_hash']}")
        print(f"output: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
