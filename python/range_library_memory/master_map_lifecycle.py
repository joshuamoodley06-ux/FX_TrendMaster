"""Exact-boundary lifecycle resolution for XAUUSD Master Map v0.1."""
from __future__ import annotations

import argparse
import json
import uuid
from contextlib import closing
from pathlib import Path
from typing import Any

from .master_map_lifecycle_helpers import annotate_output, lifecycle_evidence_report, refine_break_time

C: Any = None
_BASE_BUILD_OUTPUT: Any = None
_BASE_RANGE_PAYLOAD: Any = None
_EFFECTIVE: dict[int, dict[str, Any]] = {}


def install(core: Any) -> None:
    global C, _BASE_BUILD_OUTPUT, _BASE_RANGE_PAYLOAD
    if getattr(core, "_exact_boundary_lifecycle_installed", False):
        return
    C = core
    _BASE_BUILD_OUTPUT = core.build_output
    _BASE_RANGE_PAYLOAD = core.range_payload
    core.range_key = range_key
    core.range_payload = range_payload
    core.parent_candidate = parent_candidate
    core.canonicalize_ranges = canonicalize_ranges
    core.build_master_map = build_master_map
    core._exact_boundary_lifecycle_installed = True


def build_master_map(
    db_path: str | Path, *, symbol: str = "XAUUSD",
    output_path: str | Path | None = None,
    built_at_utc: str | None = None, build_id: str | None = None,
    source_db: str | Path | None = None,
) -> dict[str, Any]:
    symbol = symbol.strip().upper()
    if symbol != "XAUUSD":
        raise ValueError("Master Map v0.1 is intentionally scoped to XAUUSD only.")
    db = Path(db_path)
    if not db.exists():
        raise FileNotFoundError(f"Range Library database does not exist: {db}")
    built_at = C.iso(built_at_utc or C.utc_now())
    run_id = build_id or str(uuid.uuid4())
    with closing(C.connect(db)) as con:
        C.require_raw_tables(con)
        C.ensure_master_map_schema(con)
        raw_ranges = C.load_ranges(con, symbol)
        raw_events = C.load_events(con, symbol, raw_ranges)
        ranges, source_map, raw_map, range_reviews = canonicalize_ranges(
            raw_ranges, raw_events, source_db=source_db
        )
        events, event_reviews = C.canonicalize_events(
            raw_events, source_map, raw_map, ranges
        )
        relationships, relationship_reviews = C.rebuild_relationships(ranges, source_map)
        C.apply_event_visibility(events, ranges)
        reviews = C.dedupe_reviews([
            *range_reviews, *event_reviews, *relationship_reviews
        ])
        lifecycle_report = lifecycle_evidence_report(C, ranges, reviews)
        output = _BASE_BUILD_OUTPUT(
            symbol, built_at, ranges, events, relationships, reviews,
            lifecycle_report, len(raw_ranges), len(raw_events),
        )
        annotate_output(C, output, ranges, lifecycle_report)
        output["build_id"] = run_id
        C.persist(
            con, symbol, run_id, built_at, ranges, events,
            relationships, reviews, output,
        )
        con.commit()
    if output_path is not None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def range_key(raw: Any) -> tuple[Any, ...]:
    """Only exact saved boundaries and anchor identity may collapse."""
    return (
        raw.symbol, raw.layer, raw.timeframe,
        C.num_key(raw.high), C.num_key(raw.low),
        raw.high_time, raw.low_time, raw.active_from,
    )


def canonicalize_ranges(
    raw: list[Any], raw_events: list[Any] | None = None, *,
    source_db: str | Path | None = None,
) -> tuple[list[Any], dict[tuple[str | None, str], str], dict[int, str], list[dict[str, Any]]]:
    groups: dict[tuple[Any, ...], list[Any]] = {}
    for row in raw:
        groups.setdefault(range_key(row), []).append(row)
    ranges = [
        C.MasterRange(C.cid("range", key), key, sorted(rows, key=C.raw_range_sort))
        for key, rows in groups.items()
    ]
    ranges.sort(key=C.master_range_sort)
    _EFFECTIVE.clear()
    lifecycle_reviews: list[dict[str, Any]] = []
    for item in ranges:
        review = resolve_lifecycle(item, raw_events or [], source_db)
        register_effective(item)
        if review is not None:
            lifecycle_reviews.append(review)

    conflicts: list[tuple[str, list[Any]]] = []
    by_source: dict[tuple[str, str, str], list[Any]] = {}
    for item in ranges:
        for row in item.sources:
            by_source.setdefault((row.symbol, row.layer, row.source_id), []).append(item)
    for items in by_source.values():
        items = C.unique_ranges(items)
        if len(items) > 1 and not C.clearly_distinct(items):
            conflicts.append(("DUPLICATED_SOURCE_ID_CONFLICT", items))
    by_anchor: dict[tuple[Any, ...], list[Any]] = {}
    for item in ranges:
        key = C.anchor_key(item.row)
        if key:
            by_anchor.setdefault(key, []).append(item)
    for items in by_anchor.values():
        for index, left in enumerate(items):
            for right in items[index + 1:]:
                if (
                    {row.case_ref for row in left.sources}
                    != {row.case_ref for row in right.sources}
                    and C.prices_overlap(left.row, right.row)
                ):
                    conflicts.append(("SAME_STRUCTURAL_ANCHORS_DIFFERENT_FACTS", [left, right]))

    reviews = C.dedupe_reviews([
        *lifecycle_reviews, *C.mark_range_conflicts(conflicts)
    ])
    source_map: dict[tuple[str | None, str], str] = {}
    raw_map: dict[int, str] = {}
    for item in ranges:
        for row in item.sources:
            source_map[(row.case_ref, row.source_id)] = item.id
            raw_map[row.raw_id] = item.id
    return ranges, source_map, raw_map, reviews


def resolve_lifecycle(item: Any, events: list[Any], source_db: str | Path | None) -> dict[str, Any] | None:
    sources = item.sources
    set_lifecycle(
        item, item.row.status, item.row.inactive_from, item.row.break_direction,
        (item.row.status,) if item.row.status else (), "SOURCE_SNAPSHOT",
        [snapshot(row, row.status) for row in sources], [],
    )
    if len(sources) == 1:
        return None

    linked = events_for_sources(sources, events)
    confirmed = sorted(
        [event for event in linked if confirms_break(item.row, event)],
        key=lambda event: (event.event_time or "", event.source_id, event.raw_id),
    )
    if confirmed:
        directions = {event_direction(event) for event in confirmed}
        directions.discard(None)
        if len(directions) != 1:
            return lifecycle_review(
                item, "CONFLICTING_CONFIRMED_BREAK_DIRECTIONS",
                "Exact-boundary snapshots have conflicting confirmed break directions.",
            )
        direction = next(iter(directions))
        first_time = min(event.event_time for event in confirmed if event.event_time)
        first = next(event for event in confirmed if event.event_time == first_time)
        refined = refine_break_time(C, source_db, item.row, first, direction)
        break_time = refined or first_time
        snapshots = []
        for raw in sources:
            own_events = [
                event for event in linked
                if event.raw_range_id == raw.raw_id
                or (event.case_ref == raw.case_ref and event.range_source_id == raw.source_id)
            ]
            has_break = any(confirms_break(raw, event) for event in own_events)
            state = "BROKEN" if has_break or raw.status in {"BROKEN", "ABANDONED", "ARCHIVED"} else "PENDING"
            snapshots.append(snapshot(raw, state))
        set_lifecycle(
            item, "BROKEN", break_time, direction, ("ACTIVE", "BROKEN"),
            "EVENT_AND_OHLC" if refined else "EVENT_EVIDENCE",
            snapshots, [event_ref(event) for event in confirmed],
        )
        return None

    statuses = {row.status for row in sources}
    if statuses <= {"ACTIVE", "FORMING", "PENDING"}:
        state = "ACTIVE" if "ACTIVE" in statuses else "PENDING"
        set_lifecycle(
            item, state, None, None, (state,), "EXACT_SNAPSHOT_CONSENSUS",
            [snapshot(row, row.status) for row in sources], [],
        )
        return None
    if statuses <= {"BROKEN", "ABANDONED", "ARCHIVED"}:
        times = {row.inactive_from for row in sources}
        directions = {row.break_direction for row in sources}
        if len(times) == 1 and len(directions) == 1:
            set_lifecycle(
                item, "BROKEN", next(iter(times)), next(iter(directions)),
                ("ACTIVE", "BROKEN"), "SAVED_LIFECYCLE_CONSENSUS",
                [snapshot(row, "BROKEN") for row in sources], [],
            )
            return None
    return lifecycle_review(
        item, "EXACT_BOUNDARY_LIFECYCLE_UNRESOLVED",
        "Exact-boundary snapshots disagree and no factual break evidence resolves them.",
    )


def set_lifecycle(
    item: Any, status: str | None, inactive: str | None, direction: str | None,
    history: tuple[str, ...], source: str, snapshots: list[dict[str, Any]],
    supporting_events: list[dict[str, Any]],
) -> None:
    item.canonical_status = (status or "UNKNOWN").upper()
    item.canonical_inactive_from = inactive
    item.canonical_break_direction = direction
    item.lifecycle_history = history
    item.lifecycle_resolution_source = source
    item.snapshot_lifecycle = snapshots
    item.supporting_break_events = supporting_events


def register_effective(item: Any) -> None:
    for raw in item.sources:
        _EFFECTIVE[raw.raw_id] = {
            "status": item.canonical_status,
            "inactive_from_time": item.canonical_inactive_from,
            "direction_of_break": item.canonical_break_direction,
            "lifecycle_history": list(item.lifecycle_history),
            "lifecycle_resolution_source": item.lifecycle_resolution_source,
        }


def lifecycle_review(item: Any, reason: str, summary: str) -> dict[str, Any]:
    item.processing_status = C.NEEDS_REVIEW
    item.excluded = True
    item.statistics_status = C.STATS_EXCLUDED
    item.reasons.add(reason)
    return C.review(
        "RANGE_LIFECYCLE_CONFLICT", "RANGE", [item.id],
        [row.raw_id for row in item.sources],
        [row.case_ref for row in item.sources],
        [row.source_id for row in item.sources], [reason], summary,
    )


def snapshot(raw: Any, state: str | None) -> dict[str, Any]:
    return {
        "raw_id": raw.raw_id, "case_ref": raw.case_ref,
        "source_record_id": raw.source_id,
        "source_status": raw.status,
        "snapshot_status": (state or "UNKNOWN").upper(),
        "active_from_time": raw.active_from,
        "inactive_from_time": raw.inactive_from,
        "direction_of_break": raw.break_direction,
    }


def events_for_sources(sources: list[Any], events: list[Any]) -> list[Any]:
    raw_ids = {row.raw_id for row in sources}
    identities = {(row.case_ref, row.source_id) for row in sources}
    return [
        event for event in events
        if event.raw_range_id in raw_ids
        or (event.case_ref, event.range_source_id) in identities
    ]


def event_direction(event: Any) -> str | None:
    event_type = (event.event_type or "").upper()
    if event_type == "BOS_DOWN":
        return "DOWN"
    if event_type == "BOS_UP":
        return "UP"
    return (event.direction or "").upper() or None


def event_timeframe(event: Any) -> str | None:
    return C.upper(C.text(C.payload(event.raw_json), "source_timeframe", "timeframe", "chart_timeframe"))


def confirms_break(raw: Any, event: Any) -> bool:
    direction = event_direction(event)
    price = event.break_level if event.break_level is not None else event.price
    if event.event_time is None or price is None:
        return False
    if direction == "DOWN" and raw.low is not None:
        return price < raw.low
    if direction == "UP" and raw.high is not None:
        return price > raw.high
    return False


def event_ref(event: Any) -> dict[str, Any]:
    return {
        "raw_event_id": event.raw_id, "case_ref": event.case_ref,
        "source_record_id": event.source_id, "event_type": event.event_type,
        "event_time_utc": event.event_time, "source_timeframe": event_timeframe(event),
        "price": event.price, "break_level": event.break_level,
    }


def parent_candidate(parent: Any, child: Any) -> bool:
    p, c = parent.row, child.row
    if p.symbol != c.symbol or None in (p.high, p.low, c.high, c.low):
        return False
    p_low, p_high = sorted((p.low, p.high))
    c_low, c_high = sorted((c.low, c.high))
    if c_low > p_high or c_high < p_low:
        return False
    p_start, c_start = C.formation_time(p), C.formation_time(c)
    if p_start is None or c_start is None or c_start < p_start:
        return False
    status = getattr(parent, "canonical_status", p.status)
    inactive = getattr(parent, "canonical_inactive_from", p.inactive_from)
    if status in {"BROKEN", "ABANDONED", "ARCHIVED"}:
        cutoff = C.parse_time(inactive)
        if cutoff is None or c_start > cutoff:
            return False
    return True


def range_payload(raw: Any) -> dict[str, Any]:
    payload = _BASE_RANGE_PAYLOAD(raw)
    payload.update(_EFFECTIVE.get(raw.raw_id, {}))
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="range_library_memory.master_map")
    parser.add_argument("--db-path", type=Path, required=True)
    parser.add_argument("--symbol", default="XAUUSD", choices=("XAUUSD",))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-db", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = build_master_map(
        args.db_path, symbol=args.symbol, output_path=args.output,
        source_db=args.source_db,
    )
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
