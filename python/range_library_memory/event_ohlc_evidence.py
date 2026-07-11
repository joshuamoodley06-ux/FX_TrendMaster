"""Mapped BOS event evidence against source OHLC candles."""

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
from .schema import init_schema
from .source_market_db import SourceCandle, SourceMarketDbError, latest_candle_time, load_candles, open_source_market_db

SUPPORTED_EVENTS = {"BOS_UP", "BOS_DOWN"}
INACTIVE_STATUSES = {"BROKEN", "ABANDONED", "ARCHIVED"}


class EventOhlcEvidenceError(RuntimeError):
    """Raised when event evidence cannot be built safely."""


@dataclass(frozen=True)
class RawRange:
    raw_id: int
    import_run_id: int
    source_record_id: str
    case_ref: str | None
    symbol: str
    structure_layer: str
    source_timeframe: str
    status: str | None
    active_from_time: str | None
    inactive_from_time: str | None
    range_high_price: float | None
    range_low_price: float | None
    range_high_time: str | None
    range_low_time: str | None
    broken_by_event_id: str | None
    new_range_id: str | None
    old_range_id: str | None
    created_by_event_id: str | None


@dataclass(frozen=True)
class RawEvent:
    raw_id: int
    import_run_id: int
    source_record_id: str
    raw_range_id: int | None
    event_type: str
    direction: str
    event_time: str | None
    event_price: float | None
    break_level_price: float | None
    candle_time: str | None
    active_range_id: str | None
    range_id: str | None
    new_range_id: str | None
    old_range_id: str | None
    case_ref: str | None
    structure_layer: str | None
    source_timeframe: str | None


def build_event_ohlc_evidence(
    db_path: str | Path,
    *,
    source_db: str | Path,
    case_ref: str | None = None,
    symbol: str | None = None,
    layer: str | None = None,
    range_source_id: str | None = None,
    event_source_id: str | None = None,
    as_of: str | None = None,
) -> dict[str, Any]:
    path = init_schema(db_path)
    now = utc_now()
    filters = {
        "case_ref": case_ref,
        "symbol": symbol.upper() if symbol else None,
        "layer": layer.upper() if layer else None,
        "range_source_id": str(range_source_id) if range_source_id else None,
        "event_source_id": str(event_source_id) if event_source_id else None,
    }
    try:
        with closing(open_source_market_db(source_db)) as source_connection, connect(path) as connection:
            ranges = latest_ranges(connection)
            events = latest_events(connection)
            selected = select_events(events, ranges, filters)
            affected_range_ids = selected_range_ids(selected)
            if filters["range_source_id"]:
                affected_range_ids.add(filters["range_source_id"])
            if not filters["event_source_id"]:
                affected_range_ids.update(range_ids_in_scope(ranges, filters))
            clear_scope(connection, filters, affected_range_ids)
            built_evidence = 0
            built_lifecycles: set[str] = set()
            evidence_by_range: dict[str, list[tuple[dict[str, Any], int]]] = {}
            for event in selected:
                evidence = evaluate_event(connection, source_connection, ranges, event, now=now, as_of=as_of)
                evidence_id = insert_event_evidence(connection, evidence)
                built_evidence += 1
                if evidence["evidence_status"] != "MISSING_RANGE":
                    evidence_by_range.setdefault(evidence["range_source_id"], []).append((evidence, evidence_id))
            for range_id in sorted(evidence_by_range):
                evidence, evidence_id = select_lifecycle_evidence(evidence_by_range[range_id])
                insert_resolved_lifecycle(connection, lifecycle_from_evidence(ranges[range_id], evidence, evidence_id))
                built_lifecycles.add(range_id)
            for range_id, range_row in ranges.items():
                if filters["range_source_id"] and range_id != filters["range_source_id"]:
                    continue
                if filters["case_ref"] and range_row.case_ref != filters["case_ref"]:
                    continue
                if filters["symbol"] and range_row.symbol != filters["symbol"]:
                    continue
                if filters["layer"] and range_row.structure_layer != filters["layer"]:
                    continue
                if range_id not in built_lifecycles and range_id in affected_range_ids:
                    lifecycle = raw_active_lifecycle(range_row, as_of=as_of, timestamp=now)
                    insert_resolved_lifecycle(connection, lifecycle)
                    built_lifecycles.add(range_id)
            connection.commit()
    except SourceMarketDbError as exc:
        raise EventOhlcEvidenceError(str(exc)) from exc
    return {
        "filters": filters,
        "events_processed": built_evidence,
        "lifecycles_resolved": len(built_lifecycles),
    }


def summarize_event_ohlc(
    db_path: str | Path,
    *,
    case_ref: str | None = None,
    symbol: str | None = None,
    layer: str | None = None,
    range_source_id: str | None = None,
    evidence_status: str | None = None,
    resolution_status: str | None = None,
) -> dict[str, Any]:
    path = require_existing_db(db_path)
    where, params = summary_where(
        case_ref=case_ref,
        symbol=symbol.upper() if symbol else None,
        layer=layer.upper() if layer else None,
        range_source_id=str(range_source_id) if range_source_id else None,
        evidence_status=evidence_status,
        resolution_status=resolution_status,
    )
    with connect(path) as connection:
        rows = connection.execute(
            f"""
            SELECT evidence_status, resolution_status, transition_status, COUNT(*) AS count
            FROM event_ohlc_evidence
            {where}
            GROUP BY evidence_status, resolution_status, transition_status
            ORDER BY evidence_status, resolution_status, transition_status
            """,
            tuple(params),
        ).fetchall()
    groups = [dict(row) for row in rows]
    return {
        "filters": {
            "case_ref": case_ref,
            "symbol": symbol.upper() if symbol else None,
            "layer": layer.upper() if layer else None,
            "range_source_id": str(range_source_id) if range_source_id else None,
            "evidence_status": evidence_status,
            "resolution_status": resolution_status,
        },
        "events_processed": sum(int(row["count"]) for row in groups),
        "MATCH": count_group(groups, "evidence_status", "MATCH"),
        "INVALID_CHRONOLOGY": count_group(groups, "evidence_status", "INVALID_CHRONOLOGY"),
        "BOUNDARY_NOT_BREACHED": count_group(groups, "evidence_status", "BOUNDARY_NOT_BREACHED"),
        "TIME_MISMATCH": count_group(groups, "evidence_status", "TIME_MISMATCH"),
        "MISSING_DATA": count_group(groups, "resolution_status", "MISSING_DATA"),
        "OHLC_DERIVED": count_group(groups, "resolution_status", "OHLC_DERIVED"),
        "MAPPED_CONFIRMED": count_group(groups, "resolution_status", "MAPPED_CONFIRMED"),
        "UNBROKEN_THROUGH_AS_OF": count_group(groups, "resolution_status", "UNBROKEN_THROUGH_AS_OF"),
        "invalid_transition_count": count_group(groups, "transition_status", "INVALID"),
        "groups": groups,
    }


def format_build_summary(summary: dict[str, Any], *, as_json: bool = False) -> str:
    if as_json:
        return deterministic_json(summary)
    return "\n".join(f"{key}: {value}" for key, value in summary.items())


def format_event_ohlc_summary(summary: dict[str, Any], *, as_json: bool = False) -> str:
    if as_json:
        return deterministic_json(summary)
    return "\n".join(f"{key}: {value}" for key, value in summary.items() if key != "groups")


def evaluate_event(
    connection: sqlite3.Connection,
    source_connection: sqlite3.Connection,
    ranges: dict[str, RawRange],
    event: RawEvent,
    *,
    now: str,
    as_of: str | None,
) -> dict[str, Any]:
    reason_codes: set[str] = set()
    transition_reasons: set[str] = set()
    if event.event_type not in SUPPORTED_EVENTS:
        reason_codes.add("UNSUPPORTED_EVENT_TYPE")
        return missing_range_event(event, now, as_of or now, "UNSUPPORTED_EVENT", "UNRESOLVED", reason_codes)

    range_id = event.active_range_id or event.range_id or event.old_range_id
    if not range_id or range_id not in ranges:
        reason_codes.add("MISSING_RANGE")
        return missing_range_event(event, now, as_of or now, "MISSING_RANGE", "UNRESOLVED", reason_codes)
    range_row = ranges[range_id]
    boundary = boundary_for(range_row, event.event_type)
    if boundary is None:
        reason_codes.add("INCOMPLETE_RANGE")
        return incomplete_range_event(event, range_row, now, as_of or now, reason_codes)

    formation = range_formation_time(range_row)
    if formation is None:
        reason_codes.add("INCOMPLETE_RANGE")
        return incomplete_range_event(event, range_row, now, as_of or now, reason_codes)
    mapped_event_time = normalize_optional_time(event.event_time or event.candle_time)
    if mapped_event_time and normalize_time(mapped_event_time) < normalize_time(formation):
        reason_codes.add("EVENT_PRECEDES_RANGE_FORMATION")

    if event.break_level_price is not None and differs(event.break_level_price, boundary["price"]):
        reason_codes.add("MAPPED_BREAK_LEVEL_DIFFERS_FROM_RANGE_BOUNDARY")

    search_end = normalize_optional_time(as_of) if as_of else latest_candle_time(
        source_connection,
        symbol=range_row.symbol,
        timeframe=range_row.source_timeframe,
    )
    if search_end is None:
        reason_codes.add("MISSING_CANDLES")
        return base_evidence(
            event,
            range_row,
            boundary,
            formation,
            now,
            as_of or now,
            evidence_status="MISSING_CANDLES",
            resolution_status="MISSING_DATA",
            resolution_confidence="low",
            reason_codes=reason_codes,
            transition_status="NEEDS_REVIEW",
            transition_reasons=transition_reasons,
        )
    candles = load_candles(
        source_connection,
        symbol=range_row.symbol,
        timeframe=range_row.source_timeframe,
        start_time=formation,
        end_time=search_end,
    )
    if not candles:
        reason_codes.add("MISSING_CANDLES")
        return base_evidence(
            event,
            range_row,
            boundary,
            formation,
            now,
            search_end,
            evidence_status="MISSING_CANDLES",
            resolution_status="MISSING_DATA",
            resolution_confidence="low",
            reason_codes=reason_codes,
            transition_status="NEEDS_REVIEW",
            transition_reasons=transition_reasons,
        )

    event_candle = load_event_candle(source_connection, range_row, mapped_event_time)
    boundary_contact = first_contact(candles, boundary, event.event_type)
    wick = first_wick(candles, boundary, event.event_type)
    close = first_close(candles, boundary, event.event_type)
    if event_candle is None:
        reason_codes.add("MAPPED_EVENT_CANDLE_NOT_FOUND")
    elif not candle_wick_breaches(event_candle, boundary, event.event_type):
        reason_codes.add("BOUNDARY_NOT_BREACHED_AT_MAPPED_TIME")
    if event_candle and event.event_price is not None:
        extreme = event_candle.high if event.event_type == "BOS_UP" else event_candle.low
        if differs(event.event_price, extreme):
            reason_codes.add("MAPPED_EVENT_PRICE_DIFFERS_FROM_SOURCE_EXTREME")
    if wick is None:
        reason_codes.add("NO_WICK_BREACH_THROUGH_AS_OF")
    if close is None:
        reason_codes.add("NO_CLOSE_BREACH_THROUGH_AS_OF")
    if mapped_event_time and wick:
        if normalize_time(mapped_event_time) < normalize_time(wick[0].time):
            reason_codes.add("FIRST_ACTUAL_BREACH_OCCURS_LATER")
        elif normalize_time(mapped_event_time) > normalize_time(wick[0].time):
            reason_codes.add("FIRST_ACTUAL_BREACH_OCCURS_EARLIER")

    evidence_status = choose_evidence_status(reason_codes, mapped_event_time, wick, event_candle, boundary, event.event_type)
    if evidence_status == "MATCH":
        resolution_status = "MAPPED_CONFIRMED"
        effective_break_time = mapped_event_time
        effective_break_kind = "CLOSE" if close and close[0].time == mapped_event_time else "WICK"
        resolution_source = "MAPPED_EVENT_AND_OHLC"
        confidence = "high"
    elif wick:
        resolution_status = "OHLC_DERIVED"
        effective_break_time = wick[0].time
        effective_break_kind = "WICK"
        resolution_source = "OHLC"
        confidence = "medium"
    elif "MISSING_CANDLES" in reason_codes:
        resolution_status = "MISSING_DATA"
        effective_break_time = None
        effective_break_kind = None
        resolution_source = "MISSING_DATA"
        confidence = "low"
    else:
        resolution_status = "UNBROKEN_THROUGH_AS_OF"
        effective_break_time = None
        effective_break_kind = None
        resolution_source = "OHLC"
        confidence = "medium"

    transition_status = transition_for(connection, event, range_row, ranges, reason_codes, transition_reasons)
    evidence = base_evidence(
        event,
        range_row,
        boundary,
        formation,
        now,
        search_end,
        evidence_status=evidence_status,
        resolution_status=resolution_status,
        resolution_confidence=confidence,
        reason_codes=reason_codes,
        transition_status=transition_status,
        transition_reasons=transition_reasons,
    )
    evidence.update(
        {
            "source_event_candle_time": event_candle.time if event_candle else None,
            "source_event_open": event_candle.open if event_candle else None,
            "source_event_high": event_candle.high if event_candle else None,
            "source_event_low": event_candle.low if event_candle else None,
            "source_event_close": event_candle.close if event_candle else None,
            "first_boundary_contact_time": boundary_contact.time if boundary_contact else None,
            "first_wick_breach_time": wick[0].time if wick else None,
            "first_wick_breach_price": wick[1] if wick else None,
            "first_close_breach_time": close[0].time if close else None,
            "first_close_breach_price": close[1] if close else None,
            "candles_to_wick_breach": candle_index(candles, wick[0]) if wick else None,
            "candles_to_close_breach": candle_index(candles, close[0]) if close else None,
            "effective_break_time": effective_break_time,
            "effective_break_kind": effective_break_kind,
            "_resolution_source": resolution_source,
        }
    )
    return evidence


def latest_ranges(connection: sqlite3.Connection) -> dict[str, RawRange]:
    rows = connection.execute("SELECT * FROM raw_ranges ORDER BY id ASC").fetchall()
    latest: dict[str, sqlite3.Row] = {}
    for row in rows:
        if row["source_record_id"] is not None:
            latest[str(row["source_record_id"])] = row
    return {key: range_from_row(row) for key, row in latest.items()}


def latest_events(connection: sqlite3.Connection) -> list[RawEvent]:
    rows = connection.execute("SELECT * FROM raw_events ORDER BY id ASC").fetchall()
    latest: dict[str, RawEvent] = {}
    for row in rows:
        event = event_from_row(row)
        if event.source_record_id:
            latest[event.source_record_id] = event
    return list(latest.values())


def range_from_row(row: sqlite3.Row) -> RawRange:
    payload = parse_payload(row["raw_payload_json"])
    return RawRange(
        raw_id=int(row["id"]),
        import_run_id=int(row["import_run_id"]),
        source_record_id=str(row["source_record_id"]),
        case_ref=text_value(payload, "case_ref", "raw_case_id", "case_id"),
        symbol=str(row["symbol"] or text_value(payload, "symbol") or "UNKNOWN").upper(),
        structure_layer=str(text_value(payload, "structure_layer", "layer", "range_type") or row["range_type"] or "").upper(),
        source_timeframe=str(row["timeframe"] or text_value(payload, "source_timeframe", "timeframe") or "").upper(),
        status=text_value(payload, "status", "range_status"),
        active_from_time=normalize_optional_time(text_value(payload, "active_from_time", "range_start_time")),
        inactive_from_time=normalize_optional_time(text_value(payload, "inactive_from_time")),
        range_high_price=numeric_value(payload, "range_high_price", "high", "range_high"),
        range_low_price=numeric_value(payload, "range_low_price", "low", "range_low"),
        range_high_time=normalize_optional_time(text_value(payload, "range_high_time", "rh_time")),
        range_low_time=normalize_optional_time(text_value(payload, "range_low_time", "rl_time")),
        broken_by_event_id=text_value(payload, "broken_by_event_id", "broken_by_event", "broken_by"),
        new_range_id=text_value(payload, "new_range_id"),
        old_range_id=text_value(payload, "old_range_id"),
        created_by_event_id=text_value(payload, "created_by_event_id"),
    )


def event_from_row(row: sqlite3.Row) -> RawEvent:
    payload = parse_payload(row["raw_payload_json"])
    event_type = str(row["event_type"] or text_value(payload, "event_type", "type") or "").upper()
    return RawEvent(
        raw_id=int(row["id"]),
        import_run_id=int(row["import_run_id"]),
        source_record_id=text_value(payload, "id", "event_source_id", "source_id", "event_id") or str(row["source_record_id"]),
        raw_range_id=row["raw_range_id"],
        event_type=event_type,
        direction=text_value(payload, "direction", "direction_of_break") or ("UP" if event_type == "BOS_UP" else "DOWN"),
        event_time=normalize_optional_time(str(row["event_time_utc"]) if row["event_time_utc"] else text_value(payload, "event_time", "time", "candle_time")),
        event_price=float(row["price"]) if row["price"] is not None else numeric_value(payload, "event_price", "price", "candle_low", "candle_high"),
        break_level_price=numeric_value(payload, "break_level_price", "break_level", "event_price", "price"),
        candle_time=normalize_optional_time(text_value(payload, "candle_time", "event_time", "time")),
        active_range_id=text_value(payload, "active_range_id"),
        range_id=text_value(payload, "range_id"),
        new_range_id=text_value(payload, "new_range_id"),
        old_range_id=text_value(payload, "old_range_id"),
        case_ref=text_value(payload, "case_ref", "raw_case_id", "case_id"),
        structure_layer=text_value(payload, "structure_layer", "layer"),
        source_timeframe=text_value(payload, "source_timeframe", "timeframe"),
    )


def select_events(events: list[RawEvent], ranges: dict[str, RawRange], filters: dict[str, str | None]) -> list[RawEvent]:
    selected = []
    for event in events:
        range_id = event.active_range_id or event.range_id or event.old_range_id
        range_row = ranges.get(range_id or "")
        if filters["event_source_id"] and event.source_record_id != filters["event_source_id"]:
            continue
        if filters["range_source_id"] and range_id != filters["range_source_id"]:
            continue
        if filters["case_ref"] and (range_row.case_ref if range_row else event.case_ref) != filters["case_ref"]:
            continue
        if filters["symbol"] and (range_row.symbol if range_row else None) != filters["symbol"]:
            continue
        if filters["layer"] and (range_row.structure_layer if range_row else (event.structure_layer or "").upper()) != filters["layer"]:
            continue
        if event.event_type in SUPPORTED_EVENTS or filters["event_source_id"]:
            selected.append(event)
    return sorted(selected, key=lambda item: (item.event_time or "", item.source_record_id))


def selected_range_ids(events: list[RawEvent]) -> set[str]:
    return {range_id for event in events if (range_id := event.active_range_id or event.range_id or event.old_range_id)}


def range_ids_in_scope(ranges: dict[str, RawRange], filters: dict[str, str | None]) -> set[str]:
    return {
        range_id
        for range_id, row in ranges.items()
        if (not filters["range_source_id"] or range_id == filters["range_source_id"])
        and (not filters["case_ref"] or row.case_ref == filters["case_ref"])
        and (not filters["symbol"] or row.symbol == filters["symbol"])
        and (not filters["layer"] or row.structure_layer == filters["layer"])
    }


def clear_scope(
    connection: sqlite3.Connection,
    filters: dict[str, str | None],
    affected_range_ids: set[str],
) -> None:
    event_where, event_params = scope_where(filters, include_event=True)
    connection.execute(f"DELETE FROM event_ohlc_evidence{event_where}", tuple(event_params))
    if affected_range_ids:
        placeholders = ", ".join("?" for _ in affected_range_ids)
        connection.execute(
            f"DELETE FROM resolved_range_lifecycles WHERE range_source_id IN ({placeholders})",
            tuple(sorted(affected_range_ids)),
        )
    elif not any(filters.values()):
        connection.execute("DELETE FROM resolved_range_lifecycles")


def scope_where(filters: dict[str, str | None], *, include_event: bool) -> tuple[str, list[Any]]:
    clauses = []
    params: list[Any] = []
    mapping = {
        "case_ref": "case_ref",
        "symbol": "symbol",
        "layer": "structure_layer",
        "range_source_id": "range_source_id",
    }
    if include_event:
        mapping["event_source_id"] = "event_source_id"
    for key, column in mapping.items():
        if filters[key]:
            clauses.append(f"{column} = ?")
            params.append(filters[key])
    return (" WHERE " + " AND ".join(clauses), params) if clauses else ("", [])


def boundary_for(range_row: RawRange, event_type: str) -> dict[str, Any] | None:
    if event_type == "BOS_UP":
        if range_row.range_high_price is None or range_row.range_high_time is None:
            return None
        return {"type": "RANGE_HIGH", "price": range_row.range_high_price, "time": range_row.range_high_time}
    if event_type == "BOS_DOWN":
        if range_row.range_low_price is None or range_row.range_low_time is None:
            return None
        return {"type": "RANGE_LOW", "price": range_row.range_low_price, "time": range_row.range_low_time}
    return None


def range_formation_time(range_row: RawRange) -> str | None:
    if not (range_row.active_from_time and range_row.range_high_time and range_row.range_low_time):
        return None
    return format_time(max(normalize_time(range_row.active_from_time), normalize_time(range_row.range_high_time), normalize_time(range_row.range_low_time)))


def first_contact(candles: list[SourceCandle], boundary: dict[str, Any], event_type: str) -> SourceCandle | None:
    for candle in candles:
        if event_type == "BOS_UP" and candle.high >= boundary["price"] - tolerance(boundary["price"]):
            return candle
        if event_type == "BOS_DOWN" and candle.low <= boundary["price"] + tolerance(boundary["price"]):
            return candle
    return None


def first_wick(candles: list[SourceCandle], boundary: dict[str, Any], event_type: str) -> tuple[SourceCandle, float] | None:
    for candle in candles:
        if candle_wick_breaches(candle, boundary, event_type):
            return candle, candle.high if event_type == "BOS_UP" else candle.low
    return None


def first_close(candles: list[SourceCandle], boundary: dict[str, Any], event_type: str) -> tuple[SourceCandle, float] | None:
    for candle in candles:
        if event_type == "BOS_UP" and candle.close > boundary["price"] + tolerance(boundary["price"]):
            return candle, candle.close
        if event_type == "BOS_DOWN" and candle.close < boundary["price"] - tolerance(boundary["price"]):
            return candle, candle.close
    return None


def candle_wick_breaches(candle: SourceCandle, boundary: dict[str, Any], event_type: str) -> bool:
    if event_type == "BOS_UP":
        return candle.high > boundary["price"] + tolerance(boundary["price"])
    return candle.low < boundary["price"] - tolerance(boundary["price"])


def find_candle(candles: list[SourceCandle], candle_time: str | None) -> SourceCandle | None:
    if not candle_time:
        return None
    for candle in candles:
        if candle.time == candle_time:
            return candle
    return None


def load_event_candle(source_connection: sqlite3.Connection, range_row: RawRange, mapped_event_time: str | None) -> SourceCandle | None:
    if not mapped_event_time:
        return None
    candles = load_candles(
        source_connection,
        symbol=range_row.symbol,
        timeframe=range_row.source_timeframe,
        start_time=mapped_event_time,
        end_time=mapped_event_time,
    )
    return candles[0] if candles else None


def candle_index(candles: list[SourceCandle], candle: SourceCandle) -> int:
    return candles.index(candle)


def choose_evidence_status(
    reason_codes: set[str],
    mapped_event_time: str | None,
    wick: tuple[SourceCandle, float] | None,
    event_candle: SourceCandle | None,
    boundary: dict[str, Any],
    event_type: str,
) -> str:
    if "MISSING_RANGE" in reason_codes:
        return "MISSING_RANGE"
    if "INCOMPLETE_RANGE" in reason_codes:
        return "INCOMPLETE_RANGE"
    if "UNSUPPORTED_EVENT_TYPE" in reason_codes:
        return "UNSUPPORTED_EVENT"
    if "MISSING_CANDLES" in reason_codes:
        return "MISSING_CANDLES"
    if "EVENT_PRECEDES_RANGE_FORMATION" in reason_codes:
        return "INVALID_CHRONOLOGY"
    if event_candle is not None and not candle_wick_breaches(event_candle, boundary, event_type):
        return "BOUNDARY_NOT_BREACHED"
    if wick and mapped_event_time and wick[0].time != mapped_event_time:
        return "TIME_MISMATCH"
    if wick and event_candle and mapped_event_time == wick[0].time and candle_wick_breaches(event_candle, boundary, event_type):
        return "MATCH"
    return "NEEDS_REVIEW"


def transition_for(
    connection: sqlite3.Connection,
    event: RawEvent,
    range_row: RawRange,
    ranges: dict[str, RawRange],
    reason_codes: set[str],
    transition_reasons: set[str],
) -> str:
    if event.new_range_id and range_row.new_range_id and event.new_range_id != range_row.new_range_id:
        transition_reasons.add("NEW_RANGE_ID_MISMATCH")
        return "INVALID"
    new_range_id = event.new_range_id or range_row.new_range_id
    if not new_range_id:
        return "NOT_PRESENT"
    new_range = ranges.get(new_range_id)
    if new_range is None:
        transition_reasons.add("TRANSITION_RANGE_NOT_FOUND")
        return "INVALID"
    if {"EVENT_PRECEDES_RANGE_FORMATION", "BOUNDARY_NOT_BREACHED_AT_MAPPED_TIME", "MISSING_RANGE"} & reason_codes:
        transition_reasons.add("CREATING_EVENT_INVALID")
    expected_old_id = event.old_range_id or range_row.source_record_id
    if new_range.old_range_id and expected_old_id and new_range.old_range_id != expected_old_id:
        transition_reasons.add("OLD_RANGE_ID_MISMATCH")
    if new_range.created_by_event_id and new_range.created_by_event_id != event.source_record_id:
        transition_reasons.add("CREATED_BY_EVENT_ID_MISMATCH")
    for claimed_old_id in (event.active_range_id, event.range_id, event.old_range_id):
        if claimed_old_id and claimed_old_id != range_row.source_record_id:
            transition_reasons.add("OLD_RANGE_ID_MISMATCH")
    return "INVALID" if transition_reasons else "VALID"


def base_evidence(
    event: RawEvent,
    range_row: RawRange,
    boundary: dict[str, Any],
    formation: str,
    now: str,
    as_of: str,
    *,
    evidence_status: str,
    resolution_status: str,
    resolution_confidence: str,
    reason_codes: set[str],
    transition_status: str,
    transition_reasons: set[str],
) -> dict[str, Any]:
    return {
        "built_at_utc": now,
        "import_run_id": range_row.import_run_id,
        "case_ref": range_row.case_ref,
        "symbol": range_row.symbol,
        "structure_layer": range_row.structure_layer,
        "source_timeframe": range_row.source_timeframe,
        "range_source_id": range_row.source_record_id,
        "event_source_id": event.source_record_id,
        "raw_range_id": range_row.raw_id,
        "raw_event_id": event.raw_id,
        "event_type": event.event_type,
        "direction": event.direction,
        "range_active_from_time": range_row.active_from_time,
        "range_formation_time": formation,
        "boundary_type": boundary["type"],
        "boundary_price": boundary["price"],
        "boundary_anchor_time": boundary["time"],
        "mapped_event_time": event.event_time,
        "mapped_event_price": event.event_price,
        "mapped_break_level_price": event.break_level_price,
        "source_event_candle_time": None,
        "source_event_open": None,
        "source_event_high": None,
        "source_event_low": None,
        "source_event_close": None,
        "first_boundary_contact_time": None,
        "first_wick_breach_time": None,
        "first_wick_breach_price": None,
        "first_close_breach_time": None,
        "first_close_breach_price": None,
        "candles_to_wick_breach": None,
        "candles_to_close_breach": None,
        "mapped_new_range_id": event.new_range_id or range_row.new_range_id,
        "transition_status": transition_status,
        "transition_reason_codes_json": codes_json(transition_reasons),
        "evidence_status": evidence_status,
        "reason_codes_json": codes_json(reason_codes),
        "resolution_status": resolution_status,
        "resolution_confidence": resolution_confidence,
        "effective_break_time": None,
        "effective_break_kind": None,
        "as_of_time": as_of,
        "created_at_utc": now,
        "updated_at_utc": now,
    }


def missing_range_event(
    event: RawEvent,
    now: str,
    as_of: str,
    evidence_status: str,
    resolution_status: str,
    reason_codes: set[str],
) -> dict[str, Any]:
    return {
        "built_at_utc": now,
        "import_run_id": event.import_run_id,
        "case_ref": event.case_ref,
        "symbol": "UNKNOWN",
        "structure_layer": (event.structure_layer or "UNKNOWN").upper(),
        "source_timeframe": (event.source_timeframe or "UNKNOWN").upper(),
        "range_source_id": event.active_range_id or event.range_id or event.old_range_id or "",
        "event_source_id": event.source_record_id,
        "raw_range_id": None,
        "raw_event_id": event.raw_id,
        "event_type": event.event_type,
        "direction": event.direction,
        "range_active_from_time": None,
        "range_formation_time": "",
        "boundary_type": "",
        "boundary_price": 0.0,
        "boundary_anchor_time": "",
        "mapped_event_time": event.event_time,
        "mapped_event_price": event.event_price,
        "mapped_break_level_price": event.break_level_price,
        "source_event_candle_time": None,
        "source_event_open": None,
        "source_event_high": None,
        "source_event_low": None,
        "source_event_close": None,
        "first_boundary_contact_time": None,
        "first_wick_breach_time": None,
        "first_wick_breach_price": None,
        "first_close_breach_time": None,
        "first_close_breach_price": None,
        "candles_to_wick_breach": None,
        "candles_to_close_breach": None,
        "mapped_new_range_id": event.new_range_id,
        "transition_status": "INVALID" if "MISSING_RANGE" in reason_codes else "NEEDS_REVIEW",
        "transition_reason_codes_json": codes_json({"CREATING_EVENT_INVALID"} if "MISSING_RANGE" in reason_codes else set()),
        "evidence_status": evidence_status,
        "reason_codes_json": codes_json(reason_codes),
        "resolution_status": resolution_status,
        "resolution_confidence": "low",
        "effective_break_time": None,
        "effective_break_kind": None,
        "as_of_time": as_of,
        "created_at_utc": now,
        "updated_at_utc": now,
    }


def incomplete_range_event(event: RawEvent, range_row: RawRange, now: str, as_of: str, reason_codes: set[str]) -> dict[str, Any]:
    boundary = {"type": "", "price": 0.0, "time": ""}
    return base_evidence(
        event,
        range_row,
        boundary,
        "",
        now,
        as_of,
        evidence_status="INCOMPLETE_RANGE",
        resolution_status="NEEDS_REVIEW",
        resolution_confidence="low",
        reason_codes=reason_codes,
        transition_status="NEEDS_REVIEW",
        transition_reasons=set(),
    )


def lifecycle_from_evidence(range_row: RawRange, evidence: dict[str, Any], evidence_id: int) -> dict[str, Any]:
    effective_active = range_row.active_from_time or evidence["range_formation_time"]
    if evidence["resolution_status"] in {"MAPPED_CONFIRMED", "OHLC_DERIVED"}:
        effective_status = "BROKEN"
        inactive = evidence["effective_break_time"]
        source = evidence.get("_resolution_source") or "OHLC"
    elif evidence["resolution_status"] == "UNBROKEN_THROUGH_AS_OF":
        effective_status = "ACTIVE"
        inactive = None
        source = "OHLC"
    elif evidence["resolution_status"] == "MISSING_DATA":
        effective_status = range_row.status or "UNKNOWN"
        inactive = None
        source = "MISSING_DATA"
    else:
        effective_status = range_row.status or "UNKNOWN"
        inactive = None
        source = "UNRESOLVED"
    return lifecycle_payload(
        range_row,
        effective_status=effective_status,
        effective_active=effective_active,
        effective_inactive=inactive,
        resolution_source=source,
        resolution_status=evidence["resolution_status"],
        resolution_confidence=evidence["resolution_confidence"],
        supporting_event=evidence["event_source_id"],
        evidence_id=evidence_id,
        reason_codes=json.loads(evidence["reason_codes_json"]),
        as_of=evidence["as_of_time"],
        timestamp=evidence["created_at_utc"],
    )


def select_lifecycle_evidence(
    evidence_rows: list[tuple[dict[str, Any], int]],
) -> tuple[dict[str, Any], int]:
    factual = [item for item in evidence_rows if item[0].get("effective_break_time")]
    if factual:
        return min(
            factual,
            key=lambda item: (
                item[0]["effective_break_time"],
                0 if item[0]["resolution_status"] == "MAPPED_CONFIRMED" else 1,
                item[0]["event_source_id"],
                item[1],
            ),
        )
    precedence = {
        "UNBROKEN_THROUGH_AS_OF": 0,
        "MISSING_DATA": 1,
        "NEEDS_REVIEW": 2,
        "UNRESOLVED": 3,
    }
    return min(
        evidence_rows,
        key=lambda item: (
            precedence.get(item[0]["resolution_status"], 4),
            item[0]["event_source_id"],
            item[1],
        ),
    )


def raw_active_lifecycle(range_row: RawRange, *, as_of: str | None, timestamp: str) -> dict[str, Any]:
    raw_status = (range_row.status or "ACTIVE").upper()
    is_active = raw_status == "ACTIVE"
    effective_inactive = range_row.inactive_from_time if not is_active else None
    if effective_inactive and range_row.active_from_time and effective_inactive < range_row.active_from_time:
        effective_inactive = None
    return lifecycle_payload(
        range_row,
        effective_status=raw_status,
        effective_active=range_row.active_from_time or "",
        effective_inactive=effective_inactive,
        resolution_source="RAW_ACTIVE" if is_active else "RAW_FALLBACK",
        resolution_status="NEEDS_REVIEW",
        resolution_confidence="low",
        supporting_event=None,
        evidence_id=None,
        reason_codes=[],
        as_of=as_of or timestamp,
        timestamp=timestamp,
    )


def lifecycle_payload(
    range_row: RawRange,
    *,
    effective_status: str,
    effective_active: str,
    effective_inactive: str | None,
    resolution_source: str,
    resolution_status: str,
    resolution_confidence: str,
    supporting_event: str | None,
    evidence_id: int | None,
    reason_codes: list[str],
    as_of: str,
    timestamp: str,
) -> dict[str, Any]:
    return {
        "built_at_utc": timestamp,
        "import_run_id": range_row.import_run_id,
        "case_ref": range_row.case_ref,
        "symbol": range_row.symbol,
        "structure_layer": range_row.structure_layer,
        "source_timeframe": range_row.source_timeframe,
        "range_source_id": range_row.source_record_id,
        "raw_range_id": range_row.raw_id,
        "raw_status": range_row.status,
        "raw_active_from_time": range_row.active_from_time,
        "raw_inactive_from_time": range_row.inactive_from_time,
        "raw_broken_by_event_id": range_row.broken_by_event_id,
        "effective_status": effective_status,
        "effective_active_from_time": effective_active,
        "effective_inactive_from_time": effective_inactive,
        "resolution_source": resolution_source,
        "resolution_status": resolution_status,
        "resolution_confidence": resolution_confidence,
        "supporting_event_source_id": supporting_event,
        "supporting_evidence_id": evidence_id,
        "reason_codes_json": codes_json(reason_codes),
        "as_of_time": as_of,
        "created_at_utc": timestamp,
        "updated_at_utc": timestamp,
    }


def insert_event_evidence(connection: sqlite3.Connection, evidence: dict[str, Any]) -> int:
    evidence = {key: value for key, value in evidence.items() if not key.startswith("_")}
    keys = tuple(evidence)
    placeholders = ", ".join("?" for _ in keys)
    cursor = connection.execute(
        f"INSERT INTO event_ohlc_evidence ({', '.join(keys)}) VALUES ({placeholders})",
        tuple(evidence[key] for key in keys),
    )
    return int(cursor.lastrowid)


def insert_resolved_lifecycle(connection: sqlite3.Connection, lifecycle: dict[str, Any]) -> None:
    keys = tuple(lifecycle)
    placeholders = ", ".join("?" for _ in keys)
    connection.execute(
        f"INSERT INTO resolved_range_lifecycles ({', '.join(keys)}) VALUES ({placeholders})",
        tuple(lifecycle[key] for key in keys),
    )


def summary_where(**filters: str | None) -> tuple[str, list[Any]]:
    clauses = []
    params: list[Any] = []
    mapping = {
        "case_ref": "case_ref",
        "symbol": "symbol",
        "layer": "structure_layer",
        "range_source_id": "range_source_id",
        "evidence_status": "evidence_status",
        "resolution_status": "resolution_status",
    }
    for key, value in filters.items():
        if value:
            clauses.append(f"{mapping[key]} = ?")
            params.append(value)
    return ("WHERE " + " AND ".join(clauses), params) if clauses else ("", [])


def count_group(groups: list[dict[str, Any]], field: str, value: str) -> int:
    return sum(int(row["count"]) for row in groups if row[field] == value)


def tolerance(price: float) -> float:
    return max(1e-9, abs(price) * 1e-9)


def differs(first: float, second: float) -> bool:
    return abs(first - second) > tolerance(second)


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


def normalize_optional_time(value: str | None) -> str | None:
    if not value:
        return None
    return format_time(normalize_time(value))


def normalize_time(value: str) -> datetime:
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def format_time(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def codes_json(codes: set[str] | list[str]) -> str:
    return json.dumps(sorted(codes), separators=(",", ":"))


def utc_now() -> str:
    return format_time(datetime.now(UTC))
