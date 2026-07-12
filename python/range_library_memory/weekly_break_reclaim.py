"""Derived Weekly break-to-reclaim lifecycle measurements."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .db import connect
from .inspection import deterministic_json, require_existing_db
from .schema import init_schema
from .source_market_db import (
    SourceCandle,
    SourceMarketDbError,
    latest_candle_time,
    load_candles,
    open_source_market_db,
)


class WeeklyBreakReclaimError(RuntimeError):
    """Raised when Weekly reclaim lifecycles cannot be built safely."""


def build_weekly_break_reclaim(
    db_path: str | Path,
    *,
    source_db: str | Path,
    case_ref: str | None = None,
    symbol: str | None = None,
    weekly_source_id: str | None = None,
    as_of: str | None = None,
) -> dict[str, Any]:
    path = init_schema(db_path)
    filters = normalized_filters(case_ref, symbol, weekly_source_id)
    built_at = utc_now()
    try:
        with closing(open_source_market_db(source_db)) as source, connect(path) as connection:
            ranges = select_weekly_ranges(connection, filters)
            clear_scope(connection, filters)
            rows: list[dict[str, Any]] = []
            for weekly in ranges:
                row = evaluate_weekly(connection, source, weekly, as_of=as_of, built_at=built_at)
                insert_row(connection, row)
                rows.append(row)
            connection.commit()
    except SourceMarketDbError as exc:
        raise WeeklyBreakReclaimError(str(exc)) from exc
    return build_summary(filters, rows)


def summarize_weekly_break_reclaim(
    db_path: str | Path,
    *,
    case_ref: str | None = None,
    symbol: str | None = None,
    weekly_source_id: str | None = None,
    state: str | None = None,
    observation_status: str | None = None,
) -> dict[str, Any]:
    path = require_existing_db(db_path)
    filters = normalized_filters(case_ref, symbol, weekly_source_id)
    filters.update({"state": state, "observation_status": observation_status})
    clauses: list[str] = []
    params: list[Any] = []
    columns = {
        "case_ref": "case_ref", "symbol": "symbol", "weekly_source_id": "weekly_range_source_id",
        "state": "current_state", "observation_status": "observation_status",
    }
    for key, value in filters.items():
        if value:
            clauses.append(f"{columns[key]} = ?")
            params.append(value)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with connect(path) as connection:
        rows = connection.execute(
            f"""SELECT current_state, observation_status, COUNT(*) AS count
                FROM weekly_break_reclaim_lifecycles{where}
                GROUP BY current_state, observation_status
                ORDER BY current_state, observation_status""", tuple(params)
        ).fetchall()
    groups = [dict(row) for row in rows]
    return {"filters": filters, "total": sum(int(row["count"]) for row in groups), "groups": groups}


def format_summary(summary: dict[str, Any], *, as_json: bool = False) -> str:
    if as_json:
        return deterministic_json(summary)
    if "groups" in summary:
        lines = [f"total: {summary['total']}"]
        lines.extend(f"{r['current_state']} | {r['observation_status']} | {r['count']}" for r in summary["groups"])
        return "\n".join(lines)
    return "\n".join(f"{key}: {value}" for key, value in summary.items() if key != "filters")


def evaluate_weekly(
    connection: sqlite3.Connection,
    source: sqlite3.Connection,
    weekly: dict[str, Any],
    *,
    as_of: str | None,
    built_at: str,
) -> dict[str, Any]:
    reasons: set[str] = set()
    effective_as_of = canonical_time(as_of) if as_of else latest_candle_time(source, symbol=weekly["symbol"], timeframe="W1")
    base = base_row(weekly, built_at, effective_as_of or built_at)
    if not effective_as_of:
        return finish(base, "MISSING_CANDLES", "INCOMPLETE", "MISSING_DATA", "low", {"MISSING_W1_CANDLES"})

    lifecycle = connection.execute(
        """SELECT * FROM resolved_range_lifecycles
           WHERE range_source_id = ? AND structure_layer = 'WEEKLY'
           ORDER BY id DESC LIMIT 1""", (weekly["source_id"],)
    ).fetchone()
    if lifecycle is None or lifecycle["resolution_status"] not in {"MAPPED_CONFIRMED", "OHLC_DERIVED"} or not lifecycle["effective_inactive_from_time"]:
        return finish(base, "MISSING_BREAK_EVIDENCE", "INCOMPLETE", "MISSING_BREAK_EVIDENCE", "low", {"NO_FACTUAL_RESOLVED_BREAK"})

    evidence = None
    if lifecycle["supporting_evidence_id"] is not None:
        evidence = connection.execute(
            "SELECT * FROM event_ohlc_evidence WHERE id = ?", (lifecycle["supporting_evidence_id"],)
        ).fetchone()
    if evidence is None or not evidence["effective_break_time"] or evidence["event_type"] not in {"BOS_UP", "BOS_DOWN"}:
        return finish(base, "NEEDS_REVIEW", "INCOMPLETE", "NEEDS_REVIEW", "low", {"SUPPORTING_BREAK_EVIDENCE_MISSING"})

    direction = "UP" if evidence["event_type"] == "BOS_UP" else "DOWN"
    break_time = canonical_time(evidence["effective_break_time"])
    if parse_time(break_time) > parse_time(effective_as_of):
        return finish(base, "MISSING_BREAK_EVIDENCE", "INCOMPLETE", "MISSING_BREAK_EVIDENCE", "low", {"BREAK_AFTER_AS_OF"})
    break_level = float(evidence["boundary_price"])
    range_height = weekly["high"] - weekly["low"] if weekly["high"] is not None and weekly["low"] is not None else None
    base.update({
        "break_direction": direction, "break_level": break_level, "break_time": break_time,
        "break_kind": evidence["effective_break_kind"], "supporting_event_source_id": evidence["event_source_id"],
        "supporting_evidence_id": evidence["id"], "abandoned_from_time": break_time,
    })
    if range_height is None or range_height <= 0:
        base["range_height"] = range_height
        return finish(base, "NEEDS_REVIEW", "INCOMPLETE", "NEEDS_REVIEW", "low", {"INVALID_RANGE_HEIGHT"})
    base["range_height"] = range_height

    candles = load_candles(source, symbol=weekly["symbol"], timeframe="W1", start_time=break_time, end_time=effective_as_of)
    if not candles:
        return finish(base, "MISSING_CANDLES", "INCOMPLETE", "MISSING_DATA", "low", {"MISSING_W1_CANDLES"})
    break_index = next((i for i, c in enumerate(candles) if c.time == break_time), None)
    if break_index is None:
        return finish(base, "NEEDS_REVIEW", "INCOMPLETE", "NEEDS_REVIEW", "low", {"BREAK_CANDLE_NOT_FOUND"})

    wick: tuple[int, SourceCandle] | None = None
    close: tuple[int, SourceCandle] | None = None
    break_candle = candles[break_index]
    same_close = is_close_reclaim(break_candle, direction, break_level)
    same_wick = is_wick_reclaim(break_candle, direction, break_level)
    if same_wick and not same_close:
        reasons.add("SAME_CANDLE_WICK_ORDER_UNKNOWN")
        base["same_candle_wick_order_status"] = "UNKNOWN"
    if same_close:
        wick = (break_index, break_candle)
        close = (break_index, break_candle)
        base["same_candle_close_reclaim"] = 1
        base["same_candle_wick_order_status"] = "PROVEN_BY_CLOSE"
    for index in range(break_index + 1, len(candles)):
        candle = candles[index]
        if wick is None and is_wick_reclaim(candle, direction, break_level):
            wick = (index, candle)
        if close is None and is_close_reclaim(candle, direction, break_level):
            close = (index, candle)
        if wick and close:
            break

    if wick:
        base.update({"first_wick_reclaim_time": wick[1].time, "first_wick_reclaim_price": reclaim_extreme(wick[1], direction), "candles_to_wick_reclaim": wick[0] - break_index})
    if close:
        base.update({"first_close_reclaim_time": close[1].time, "first_close_reclaim_price": close[1].close, "candles_to_close_reclaim": close[0] - break_index})

    candidates = [item for item in (wick, close) if item is not None]
    if candidates:
        effective_index = min(item[0] for item in candidates)
        effective_candle = candles[effective_index]
        wick_at_effective = wick is not None and wick[0] == effective_index
        close_at_effective = close is not None and close[0] == effective_index
        kind = "WICK_AND_CLOSE" if wick_at_effective and close_at_effective else ("WICK" if wick_at_effective else "CLOSE")
        depth = reclaim_depth(effective_candle, direction, break_level)
        base.update({
            "effective_reclaim_time": effective_candle.time, "effective_reclaim_kind": kind,
            "reclaim_depth_price": depth, "reclaim_depth_percent_of_range": depth / range_height * 100.0,
            "candles_to_effective_reclaim": effective_index - break_index,
            "calendar_days_to_effective_reclaim": elapsed_days(break_time, effective_candle.time),
            "candles_pending_as_of": None, "calendar_days_pending_as_of": None,
        })
        return finish(base, "RECLAIMED", "OBSERVED", "RESOLVED", "high", reasons)

    base.update({
        "candles_pending_as_of": len(candles) - 1 - break_index,
        "calendar_days_pending_as_of": elapsed_days(break_time, effective_as_of),
    })
    return finish(base, "ABANDONED_PENDING_RECLAIM", "CENSORED", "PENDING", "high", reasons)


def select_weekly_ranges(connection: sqlite3.Connection, filters: dict[str, str | None]) -> list[dict[str, Any]]:
    clauses = ["UPPER(COALESCE(json_extract(raw_payload_json, '$.structure_layer'), range_type, '')) = 'WEEKLY'"]
    params: list[Any] = []
    if filters["case_ref"]:
        clauses.append("json_extract(raw_payload_json, '$.case_ref') = ?"); params.append(filters["case_ref"])
    if filters["symbol"]:
        clauses.append("UPPER(symbol) = ?"); params.append(filters["symbol"])
    if filters["weekly_source_id"]:
        clauses.append("source_record_id = ?"); params.append(filters["weekly_source_id"])
    rows = connection.execute(
        f"""SELECT * FROM raw_ranges WHERE {' AND '.join(clauses)}
            AND id IN (SELECT MAX(id) FROM raw_ranges GROUP BY source_record_id)
            ORDER BY source_record_id""", tuple(params)
    ).fetchall()
    result = []
    for row in rows:
        payload = json.loads(row["raw_payload_json"])
        result.append({
            "raw_id": row["id"], "import_run_id": row["import_run_id"], "source_id": str(row["source_record_id"]),
            "case_ref": payload.get("case_ref"), "symbol": str(row["symbol"] or payload.get("symbol") or "").upper(),
            "timeframe": str(payload.get("source_timeframe") or row["timeframe"] or "W1").upper(),
            "high": number(payload.get("range_high_price", row["high"])), "low": number(payload.get("range_low_price", row["low"])),
        })
    return result


def clear_scope(connection: sqlite3.Connection, filters: dict[str, str | None]) -> None:
    clauses = []; params: list[Any] = []
    mapping = {"case_ref": "case_ref", "symbol": "symbol", "weekly_source_id": "weekly_range_source_id"}
    for key, value in filters.items():
        if value:
            clauses.append(f"{mapping[key]} = ?"); params.append(value)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    connection.execute(f"DELETE FROM weekly_break_reclaim_lifecycles{where}", tuple(params))


def base_row(weekly: dict[str, Any], built_at: str, as_of: str) -> dict[str, Any]:
    return {
        "built_at_utc": built_at, "import_run_id": weekly["import_run_id"], "case_ref": weekly["case_ref"],
        "symbol": weekly["symbol"], "source_timeframe": "W1", "weekly_range_source_id": weekly["source_id"],
        "raw_range_id": weekly["raw_id"], "range_high": weekly["high"], "range_low": weekly["low"],
        "range_height": None, "break_direction": None, "break_level": None, "break_time": None, "break_kind": None,
        "supporting_event_source_id": None, "supporting_evidence_id": None, "abandoned_from_time": None,
        "first_wick_reclaim_time": None, "first_wick_reclaim_price": None, "first_close_reclaim_time": None,
        "first_close_reclaim_price": None, "effective_reclaim_time": None, "effective_reclaim_kind": None,
        "same_candle_close_reclaim": 0, "same_candle_wick_order_status": "NOT_APPLICABLE",
        "reclaim_depth_price": None, "reclaim_depth_percent_of_range": None, "candles_to_wick_reclaim": None,
        "candles_to_close_reclaim": None, "candles_to_effective_reclaim": None,
        "calendar_days_to_effective_reclaim": None, "candles_pending_as_of": None,
        "calendar_days_pending_as_of": None, "current_state": "NEEDS_REVIEW", "observation_status": "INCOMPLETE",
        "resolution_status": "NEEDS_REVIEW", "resolution_confidence": "low", "reason_codes_json": "[]",
        "as_of_time": as_of, "created_at_utc": built_at, "updated_at_utc": built_at,
    }


def finish(base: dict[str, Any], state: str, observation: str, resolution: str, confidence: str, reasons: set[str]) -> dict[str, Any]:
    base.update({"current_state": state, "observation_status": observation, "resolution_status": resolution,
                 "resolution_confidence": confidence, "reason_codes_json": json.dumps(sorted(reasons), separators=(",", ":"))})
    return base


def insert_row(connection: sqlite3.Connection, row: dict[str, Any]) -> None:
    keys = tuple(row); placeholders = ",".join("?" for _ in keys)
    connection.execute(f"INSERT INTO weekly_break_reclaim_lifecycles ({','.join(keys)}) VALUES ({placeholders})", tuple(row[k] for k in keys))


def build_summary(filters: dict[str, str | None], rows: list[dict[str, Any]]) -> dict[str, Any]:
    count = lambda state: sum(1 for row in rows if row["current_state"] == state)
    return {"filters": filters, "weekly_ranges_selected": len(rows), "rows_built": len(rows),
            "reclaimed_count": count("RECLAIMED"), "pending_count": count("ABANDONED_PENDING_RECLAIM"),
            "missing_break_count": count("MISSING_BREAK_EVIDENCE"), "missing_candle_count": count("MISSING_CANDLES"),
            "needs_review_count": count("NEEDS_REVIEW"),
            "same_candle_close_reclaim_count": sum(int(row["same_candle_close_reclaim"]) for row in rows)}


def normalized_filters(case_ref: str | None, symbol: str | None, weekly_source_id: str | None) -> dict[str, str | None]:
    return {"case_ref": case_ref, "symbol": symbol.upper() if symbol else None,
            "weekly_source_id": str(weekly_source_id) if weekly_source_id else None}


def is_wick_reclaim(c: SourceCandle, direction: str, level: float) -> bool:
    return c.low <= level if direction == "UP" else c.high >= level


def is_close_reclaim(c: SourceCandle, direction: str, level: float) -> bool:
    return c.close <= level if direction == "UP" else c.close >= level


def reclaim_extreme(c: SourceCandle, direction: str) -> float:
    return c.low if direction == "UP" else c.high


def reclaim_depth(c: SourceCandle, direction: str, level: float) -> float:
    return max(0.0, level - c.low) if direction == "UP" else max(0.0, c.high - level)


def elapsed_days(start: str, end: str) -> float:
    return (parse_time(end) - parse_time(start)).total_seconds() / 86400.0


def canonical_time(value: str | None) -> str:
    if not value:
        raise WeeklyBreakReclaimError("Timestamp is required")
    return parse_time(value).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_time(value: str) -> datetime:
    text = str(value).strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None: parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def number(value: Any) -> float | None:
    try: return float(value) if value is not None else None
    except (TypeError, ValueError): return None


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
