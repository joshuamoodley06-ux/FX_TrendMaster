"""Factual Daily range timelines joined to existing Weekly context."""
from __future__ import annotations

import argparse
import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .db import connect
from .inspection import deterministic_json, require_existing_db
from .schema import init_schema
from .source_market_db import SourceCandle, SourceMarketDbError, latest_candle_time, load_candles, open_source_market_db

FACTUAL = {"MAPPED_CONFIRMED", "OHLC_DERIVED"}
INACTIVE = {"BROKEN", "ABANDONED", "ARCHIVED"}
ACTIVE = {"ACTIVE", "FORMING"}
PARENT_REVIEW = {"CONFLICT", "NEEDS_REVIEW"}
BAD_WEEKLY = {"NEEDS_REVIEW", "INCOMPLETE_RANGE", "MISSING_CANDLES"}

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS daily_range_timelines (
 id INTEGER PRIMARY KEY,
 built_at_utc TEXT NOT NULL,
 import_run_id INTEGER,
 case_ref TEXT,
 symbol TEXT NOT NULL,
 source_timeframe TEXT NOT NULL,
 daily_range_source_id TEXT NOT NULL UNIQUE,
 raw_range_id INTEGER,
 raw_status TEXT,
 range_high REAL,
 range_low REAL,
 range_height REAL,
 t0_formation_time TEXT,
 t1_break_time TEXT,
 t1_break_direction TEXT,
 t1_break_level REAL,
 t1_break_kind TEXT,
 supporting_event_source_id TEXT,
 supporting_evidence_id INTEGER,
 first_wick_reclaim_time TEXT,
 first_wick_reclaim_price REAL,
 first_close_reclaim_time TEXT,
 first_close_reclaim_price REAL,
 t2_reclaim_time TEXT,
 t2_reclaim_kind TEXT,
 same_candle_close_reclaim INTEGER NOT NULL DEFAULT 0,
 same_candle_wick_order_status TEXT,
 reclaim_depth_price REAL,
 reclaim_depth_percent_of_range REAL,
 formation_to_break_days REAL,
 break_to_reclaim_days REAL,
 candles_to_wick_reclaim INTEGER,
 candles_to_close_reclaim INTEGER,
 candles_to_effective_reclaim INTEGER,
 current_daily_state TEXT NOT NULL,
 current_daily_phase_start_time TEXT,
 current_daily_phase_age_days REAL,
 parent_relationship_id INTEGER,
 parent_weekly_source_id TEXT,
 parent_link_source TEXT,
 parent_link_status TEXT,
 parent_link_confidence TEXT,
 parent_membership_state TEXT NOT NULL,
 parent_weekly_phase_sequence_id INTEGER,
 weekly_phase_at_daily_formation TEXT,
 weekly_phase_at_daily_break TEXT,
 daily_sequence_in_weekly INTEGER,
 observation_status TEXT NOT NULL,
 resolution_status TEXT NOT NULL,
 resolution_confidence TEXT NOT NULL,
 reason_codes_json TEXT NOT NULL,
 as_of_time TEXT NOT NULL,
 created_at_utc TEXT NOT NULL,
 updated_at_utc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_daily_timeline_source ON daily_range_timelines(daily_range_source_id);
CREATE INDEX IF NOT EXISTS idx_daily_timeline_scope ON daily_range_timelines(case_ref,symbol);
CREATE INDEX IF NOT EXISTS idx_daily_timeline_parent ON daily_range_timelines(parent_weekly_source_id);
CREATE INDEX IF NOT EXISTS idx_daily_timeline_parent_status ON daily_range_timelines(parent_link_status);
CREATE INDEX IF NOT EXISTS idx_daily_timeline_state ON daily_range_timelines(current_daily_state);
CREATE INDEX IF NOT EXISTS idx_daily_timeline_t0 ON daily_range_timelines(t0_formation_time);
CREATE INDEX IF NOT EXISTS idx_daily_timeline_t1 ON daily_range_timelines(t1_break_time);
CREATE INDEX IF NOT EXISTS idx_daily_timeline_t2 ON daily_range_timelines(t2_reclaim_time);
CREATE INDEX IF NOT EXISTS idx_daily_timeline_sequence
 ON daily_range_timelines(parent_weekly_source_id,daily_sequence_in_weekly);
"""


class DailyRangeTimelineError(RuntimeError):
    pass


def build_daily_range_timelines(
    db_path: str | Path,
    *,
    source_db: str | Path,
    case_ref: str | None = None,
    symbol: str | None = None,
    daily_source_id: str | None = None,
    weekly_source_id: str | None = None,
    as_of: str | None = None,
) -> dict[str, Any]:
    path = init_schema(db_path)
    filters = norm_filters(case_ref, symbol, daily_source_id, weekly_source_id)
    built_at = utc_now()
    try:
        with closing(open_source_market_db(source_db)) as source, connect(path) as con:
            con.executescript(SCHEMA_SQL)
            dailies = load_dailies(con)
            rels = latest_relationships(con)
            selected = select_dailies(dailies, rels, filters)
            seq = sequence_map(dailies, rels)
            clear_scope(con, filters, {d["source_id"] for d in selected})
            rows = [
                evaluate(
                    con,
                    source,
                    daily,
                    relationship=rels.get(daily["source_id"]),
                    sequence_number=seq.get(daily["source_id"]),
                    as_of=as_of,
                    built_at=built_at,
                )
                for daily in selected
            ]
            for row in rows:
                insert_row(con, row)
            con.commit()
    except SourceMarketDbError as exc:
        raise DailyRangeTimelineError(str(exc)) from exc
    return build_summary(filters, rows)


def summarize_daily_range_timelines(
    db_path: str | Path,
    *,
    case_ref: str | None = None,
    symbol: str | None = None,
    daily_source_id: str | None = None,
    weekly_source_id: str | None = None,
    daily_state: str | None = None,
    parent_link_status: str | None = None,
    weekly_phase: str | None = None,
    observation_status: str | None = None,
) -> dict[str, Any]:
    path = require_existing_db(db_path)
    filters = norm_filters(case_ref, symbol, daily_source_id, weekly_source_id)
    filters.update(
        daily_state=upper(daily_state),
        parent_link_status=upper(parent_link_status),
        weekly_phase=upper(weekly_phase),
        observation_status=upper(observation_status),
    )
    columns = {
        "case_ref": "case_ref",
        "symbol": "symbol",
        "daily_source_id": "daily_range_source_id",
        "weekly_source_id": "parent_weekly_source_id",
        "daily_state": "current_daily_state",
        "parent_link_status": "parent_link_status",
        "weekly_phase": "weekly_phase_at_daily_formation",
        "observation_status": "observation_status",
    }
    clauses, params = [], []
    for key, value in filters.items():
        if value is not None:
            clauses.append(f"{columns[key]}=?")
            params.append(value)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with connect(path) as con:
        rows = con.execute(
            f"""SELECT current_daily_state,observation_status,parent_membership_state,
                       COALESCE(parent_link_status,'') parent_link_status,COUNT(*) count
                FROM daily_range_timelines{where}
                GROUP BY current_daily_state,observation_status,parent_membership_state,
                         COALESCE(parent_link_status,'')
                ORDER BY current_daily_state,observation_status,parent_membership_state,parent_link_status""",
            tuple(params),
        ).fetchall()
    groups = [dict(row) for row in rows]
    return {"filters": filters, "total": sum(int(r["count"]) for r in groups), "groups": groups}


def format_summary(summary: dict[str, Any], *, as_json: bool = False) -> str:
    if as_json:
        return deterministic_json(summary)
    if "groups" not in summary:
        return "\n".join(f"{k}: {v}" for k, v in summary.items() if k != "filters")
    lines = [f"total: {summary['total']}", "state | observation | parent | link | count"]
    lines += [
        f"{r['current_daily_state']} | {r['observation_status']} | "
        f"{r['parent_membership_state']} | {r['parent_link_status']} | {r['count']}"
        for r in summary["groups"]
    ]
    return "\n".join(lines)


def evaluate(
    con: sqlite3.Connection,
    source: sqlite3.Connection,
    daily: dict[str, Any],
    *,
    relationship: sqlite3.Row | None,
    sequence_number: int | None,
    as_of: str | None,
    built_at: str,
) -> dict[str, Any]:
    reasons: set[str] = set()
    row = base_row(daily, built_at)
    attach_parent(con, row, relationship, sequence_number, reasons)

    if not daily["high_time"] or not daily["low_time"]:
        row["as_of_time"] = canonical_time(as_of) if as_of else built_at
        return finish(row, "INCOMPLETE_RANGE", "INCOMPLETE", "INCOMPLETE_RANGE", "low",
                      reasons | {"MISSING_RANGE_ANCHOR_TIME"})

    times = [parse_time(daily["high_time"]), parse_time(daily["low_time"])]
    if daily["active_time"]:
        times.append(parse_time(daily["active_time"]))
    t0 = canonical_dt(max(times))
    row["t0_formation_time"] = t0
    row["weekly_phase_at_daily_formation"] = parent_phase(con, row, t0)

    latest = latest_candle_time(source, symbol=daily["symbol"], timeframe="D1")
    if not latest:
        row["as_of_time"] = canonical_time(as_of) if as_of else built_at
        return finish(row, "MISSING_CANDLES", "INCOMPLETE", "MISSING_DATA", "low",
                      reasons | {"MISSING_D1_CANDLES"})

    latest = canonical_time(latest)
    cutoff = latest
    if as_of:
        requested = canonical_time(as_of)
        if parse_time(requested) > parse_time(latest):
            reasons.add("AS_OF_CAPPED_TO_LATEST_D1_DATA")
        else:
            cutoff = requested
    row["as_of_time"] = cutoff
    if parse_time(t0) > parse_time(cutoff):
        row["daily_sequence_in_weekly"] = None
        return finish(row, "NEEDS_REVIEW", "INCOMPLETE", "NEEDS_REVIEW", "low",
                      reasons | {"MILESTONE_AFTER_AS_OF"})

    height = daily["high"] - daily["low"] if None not in (daily["high"], daily["low"]) else None
    row["range_height"] = height
    if height is None or height <= 0:
        return finish(row, "NEEDS_REVIEW", "INCOMPLETE", "NEEDS_REVIEW", "low",
                      reasons | {"INVALID_RANGE_HEIGHT"})

    lifecycle = latest_lifecycle(con, daily["source_id"])
    evidence = supporting_evidence(con, lifecycle)
    contradictions = evidence_errors(lifecycle, evidence)
    if contradictions:
        return finish(row, "NEEDS_REVIEW", "INCOMPLETE", "NEEDS_REVIEW", "low",
                      reasons | contradictions)

    factual = bool(
        lifecycle
        and lifecycle["resolution_status"] in FACTUAL
        and lifecycle["effective_inactive_from_time"]
        and evidence
        and evidence["event_type"] in {"BOS_UP", "BOS_DOWN"}
        and evidence["effective_break_time"]
        and evidence["boundary_price"] is not None
    )
    if factual:
        direction = "UP" if evidence["event_type"] == "BOS_UP" else "DOWN"
        t1 = canonical_time(evidence["effective_break_time"])
        row.update(
            t1_break_time=t1,
            t1_break_direction=direction,
            t1_break_level=float(evidence["boundary_price"]),
            t1_break_kind=evidence["effective_break_kind"],
            supporting_event_source_id=evidence["event_source_id"],
            supporting_evidence_id=evidence["id"],
        )
        row["weekly_phase_at_daily_break"] = parent_phase(con, row, t1)
        if parse_time(t1) < parse_time(t0):
            return finish(row, "NEEDS_REVIEW", "INCOMPLETE", "NEEDS_REVIEW", "low",
                          reasons | {"BREAK_BEFORE_RANGE_FORMATION"})
        if parse_time(t1) > parse_time(cutoff):
            return finish(row, "NEEDS_REVIEW", "INCOMPLETE", "NEEDS_REVIEW", "low",
                          reasons | {"MILESTONE_AFTER_AS_OF"})
        row["formation_to_break_days"] = days(t0, t1)
        return evaluate_reclaim(row, source, daily, cutoff, reasons)

    if daily["status"] == "UNKNOWN":
        return finish(row, "NEEDS_REVIEW", "INCOMPLETE", "NEEDS_REVIEW", "low",
                      reasons | {"MISSING_RAW_STATUS"})
    if daily["status"] in INACTIVE:
        return finish(row, "NEEDS_REVIEW", "INCOMPLETE", "NEEDS_REVIEW", "low",
                      reasons | {"RAW_BROKEN_WITHOUT_FACTUAL_BREAK"})
    if daily["status"] in ACTIVE:
        row["current_daily_phase_start_time"] = t0
        row["current_daily_phase_age_days"] = days(t0, cutoff)
        return finish(row, "ACTIVE_PRE_BREAK", "CENSORED", "PENDING", "medium",
                      reasons | {"NO_FACTUAL_BREAK_YET"})
    return finish(row, "NEEDS_REVIEW", "INCOMPLETE", "NEEDS_REVIEW", "low",
                  reasons | {"UNSUPPORTED_RAW_STATUS_WITHOUT_FACTUAL_BREAK"})


def evaluate_reclaim(
    row: dict[str, Any],
    source: sqlite3.Connection,
    daily: dict[str, Any],
    cutoff: str,
    reasons: set[str],
) -> dict[str, Any]:
    t1, direction, level = row["t1_break_time"], row["t1_break_direction"], float(row["t1_break_level"])
    candles = load_candles(source, symbol=daily["symbol"], timeframe="D1", start_time=t1, end_time=cutoff)
    if not candles:
        return finish(row, "MISSING_CANDLES", "INCOMPLETE", "MISSING_DATA", "low",
                      reasons | {"MISSING_D1_CANDLES_AFTER_BREAK"})
    break_index = next((i for i, c in enumerate(candles) if c.time == t1), None)
    if break_index is None:
        return finish(row, "NEEDS_REVIEW", "INCOMPLETE", "NEEDS_REVIEW", "low",
                      reasons | {"BREAK_CANDLE_NOT_FOUND"})

    wick: tuple[int, SourceCandle] | None = None
    close: tuple[int, SourceCandle] | None = None
    first = candles[break_index]
    same_close, same_wick = close_reclaim(first, direction, level), wick_reclaim(first, direction, level)
    if same_wick and not same_close:
        reasons.add("SAME_CANDLE_WICK_ORDER_UNKNOWN")
        row["same_candle_wick_order_status"] = "UNKNOWN"
    if same_close:
        wick = close = (break_index, first)
        row["same_candle_close_reclaim"] = 1
        row["same_candle_wick_order_status"] = "PROVEN_BY_CLOSE"

    for i in range(break_index + 1, len(candles)):
        candle = candles[i]
        if wick is None and wick_reclaim(candle, direction, level):
            wick = (i, candle)
        if close is None and close_reclaim(candle, direction, level):
            close = (i, candle)
        if wick and close:
            break

    if wick:
        row.update(first_wick_reclaim_time=wick[1].time,
                   first_wick_reclaim_price=extreme(wick[1], direction),
                   candles_to_wick_reclaim=wick[0] - break_index)
    if close:
        row.update(first_close_reclaim_time=close[1].time,
                   first_close_reclaim_price=close[1].close,
                   candles_to_close_reclaim=close[0] - break_index)

    candidates = [item for item in (wick, close) if item]
    if not candidates:
        row["current_daily_phase_start_time"] = t1
        row["current_daily_phase_age_days"] = days(t1, cutoff)
        return finish(row, "BREAK_PENDING_RECLAIM", "CENSORED", "PENDING", "high", reasons)

    idx = min(item[0] for item in candidates)
    candle = candles[idx]
    wick_now = wick is not None and wick[0] == idx
    close_now = close is not None and close[0] == idx
    kind = "WICK_AND_CLOSE" if wick_now and close_now else "WICK" if wick_now else "CLOSE"
    t2 = candle.time
    depth = reclaim_depth(candle, direction, level)
    row.update(
        t2_reclaim_time=t2,
        t2_reclaim_kind=kind,
        reclaim_depth_price=depth,
        reclaim_depth_percent_of_range=depth / float(row["range_height"]) * 100.0,
        break_to_reclaim_days=days(t1, t2),
        candles_to_effective_reclaim=idx - break_index,
        current_daily_phase_start_time=t2,
        current_daily_phase_age_days=days(t2, cutoff),
    )
    return finish(row, "RECLAIMED", "OBSERVED", "RESOLVED", "high", reasons)


def load_dailies(con: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = con.execute(
        """SELECT * FROM raw_ranges
           WHERE UPPER(COALESCE(json_extract(raw_payload_json,'$.structure_layer'),range_type,''))='DAILY'
             AND id IN (SELECT MAX(id) FROM raw_ranges GROUP BY source_record_id)
           ORDER BY source_record_id"""
    ).fetchall()
    result = []
    for row in rows:
        try:
            payload = json.loads(row["raw_payload_json"])
        except (TypeError, json.JSONDecodeError):
            payload = {}
        result.append(
            {
                "raw_id": row["id"],
                "import_run_id": row["import_run_id"],
                "source_id": str(row["source_record_id"]),
                "case_ref": payload.get("case_ref"),
                "symbol": str(row["symbol"] or payload.get("symbol") or "").upper(),
                "status": norm_status(payload.get("status")),
                "active_time": optional_time(payload.get("active_from_time")),
                "high_time": optional_time(payload.get("range_high_time")),
                "low_time": optional_time(payload.get("range_low_time")),
                "high": number(payload.get("range_high_price", row["high"])),
                "low": number(payload.get("range_low_price", row["low"])),
            }
        )
    return result


def latest_relationships(con: sqlite3.Connection) -> dict[str, sqlite3.Row]:
    rows = con.execute(
        """SELECT r.* FROM parent_child_relationships r
           JOIN (
             SELECT child_range_id,MAX(id) max_id
             FROM parent_child_relationships
             WHERE relationship_type='weekly_daily'
             GROUP BY child_range_id
           ) x ON x.max_id=r.id
           WHERE r.relationship_type='weekly_daily'"""
    ).fetchall()
    return {str(r["child_range_id"]): r for r in rows if r["child_range_id"] is not None}


def select_dailies(
    dailies: list[dict[str, Any]],
    rels: dict[str, sqlite3.Row],
    filters: dict[str, str | None],
) -> list[dict[str, Any]]:
    selected = []
    for daily in dailies:
        if filters["case_ref"] and daily["case_ref"] != filters["case_ref"]:
            continue
        if filters["symbol"] and daily["symbol"] != filters["symbol"]:
            continue
        if filters["daily_source_id"] and daily["source_id"] != filters["daily_source_id"]:
            continue
        if filters["weekly_source_id"]:
            rel = rels.get(daily["source_id"])
            if rel is None or str(rel["parent_range_id"]) != filters["weekly_source_id"]:
                continue
        selected.append(daily)
    return selected


def sequence_map(
    dailies: list[dict[str, Any]],
    rels: dict[str, sqlite3.Row],
) -> dict[str, int]:
    groups: dict[str, list[tuple[datetime, tuple[int, int | str], str]]] = {}
    for daily in dailies:
        rel = rels.get(daily["source_id"])
        if not rel or str(rel["link_status"]).upper() != "VALID":
            continue
        if rel["parent_range_id"] is None or not daily["high_time"] or not daily["low_time"]:
            continue
        times = [parse_time(daily["high_time"]), parse_time(daily["low_time"])]
        if daily["active_time"]:
            times.append(parse_time(daily["active_time"]))
        groups.setdefault(str(rel["parent_range_id"]), []).append(
            (max(times), source_key(daily["source_id"]), daily["source_id"])
        )
    result: dict[str, int] = {}
    for items in groups.values():
        for index, (_, _, source_id) in enumerate(sorted(items, key=lambda x: (x[0], x[1])), start=1):
            result[source_id] = index
    return result


def attach_parent(
    con: sqlite3.Connection,
    row: dict[str, Any],
    rel: sqlite3.Row | None,
    sequence_number: int | None,
    reasons: set[str],
) -> None:
    if rel is None:
        reasons.add("MISSING_PARENT_RELATIONSHIP")
        return
    row.update(
        parent_relationship_id=rel["id"],
        parent_weekly_source_id=rel["parent_range_id"],
        parent_link_source=rel["link_source"],
        parent_link_status=rel["link_status"],
        parent_link_confidence=rel["link_confidence"],
    )
    status = str(rel["link_status"] or "").upper()
    if status == "VALID":
        row["parent_membership_state"] = "VALID"
        row["daily_sequence_in_weekly"] = sequence_number
        weekly = latest_weekly(con, str(rel["parent_range_id"]) if rel["parent_range_id"] else None)
        if weekly:
            row["parent_weekly_phase_sequence_id"] = weekly["id"]
        else:
            row["weekly_phase_at_daily_formation"] = row["weekly_phase_at_daily_break"] = "PARENT_NEEDS_REVIEW"
            reasons.add("MISSING_PARENT_WEEKLY_PHASE_SEQUENCE")
    elif status == "ORPHAN":
        row["parent_membership_state"] = "ORPHAN"
    else:
        row["parent_membership_state"] = "NEEDS_REVIEW"
        row["weekly_phase_at_daily_formation"] = row["weekly_phase_at_daily_break"] = "PARENT_NEEDS_REVIEW"
        reasons.add("PARENT_LINK_NEEDS_REVIEW" if status in PARENT_REVIEW else "UNSUPPORTED_PARENT_LINK_STATUS")


def parent_phase(con: sqlite3.Connection, row: dict[str, Any], milestone: str | None) -> str | None:
    if milestone is None:
        return None
    if row["parent_membership_state"] != "VALID":
        return row["weekly_phase_at_daily_formation"]
    weekly = latest_weekly(con, row["parent_weekly_source_id"])
    if not weekly or weekly["current_phase_state"] in BAD_WEEKLY or not weekly["t0_formation_time"]:
        return "PARENT_NEEDS_REVIEW"
    point, t0 = parse_time(milestone), parse_time(weekly["t0_formation_time"])
    t1 = parse_time(weekly["t1_break_time"]) if weekly["t1_break_time"] else None
    t2 = parse_time(weekly["t2_reclaim_time"]) if weekly["t2_reclaim_time"] else None
    if point < t0:
        return "BEFORE_WEEKLY_FORMATION"
    if t1 is None or point < t1:
        return "WEEKLY_PRE_BREAK"
    if t2 is None:
        return "WEEKLY_BREAK_TO_RECLAIM" if weekly["current_phase_state"] == "BREAK_PENDING_RECLAIM" else "PARENT_NEEDS_REVIEW"
    if t2 < t1:
        return "PARENT_NEEDS_REVIEW"
    return "WEEKLY_BREAK_TO_RECLAIM" if point < t2 else "WEEKLY_POST_RECLAIM"


def latest_weekly(con: sqlite3.Connection, source_id: str | None) -> sqlite3.Row | None:
    if not source_id:
        return None
    return con.execute(
        "SELECT * FROM weekly_phase_sequences WHERE weekly_range_source_id=? ORDER BY id DESC LIMIT 1",
        (source_id,),
    ).fetchone()


def latest_lifecycle(con: sqlite3.Connection, source_id: str) -> sqlite3.Row | None:
    return con.execute(
        """SELECT * FROM resolved_range_lifecycles
           WHERE range_source_id=? AND structure_layer='DAILY'
           ORDER BY id DESC LIMIT 1""",
        (source_id,),
    ).fetchone()


def supporting_evidence(con: sqlite3.Connection, lifecycle: sqlite3.Row | None) -> sqlite3.Row | None:
    if not lifecycle or lifecycle["supporting_evidence_id"] is None:
        return None
    return con.execute(
        "SELECT * FROM event_ohlc_evidence WHERE id=? AND structure_layer='DAILY' LIMIT 1",
        (lifecycle["supporting_evidence_id"],),
    ).fetchone()


def evidence_errors(lifecycle: sqlite3.Row | None, evidence: sqlite3.Row | None) -> set[str]:
    if lifecycle is None:
        return set()
    claims = lifecycle["resolution_status"] in FACTUAL or lifecycle["supporting_evidence_id"] is not None
    bad = set()
    if lifecycle["resolution_status"] in FACTUAL and not lifecycle["effective_inactive_from_time"]:
        bad.add("CONTRADICTORY_BREAK_EVIDENCE")
    if claims and evidence is None:
        bad.add("CONTRADICTORY_BREAK_EVIDENCE")
        return bad
    if evidence and (
        evidence["event_type"] not in {"BOS_UP", "BOS_DOWN"}
        or evidence["resolution_status"] not in FACTUAL
        or not evidence["effective_break_time"]
        or evidence["boundary_price"] is None
    ):
        bad.add("CONTRADICTORY_BREAK_EVIDENCE")
    return bad


def clear_scope(
    con: sqlite3.Connection,
    filters: dict[str, str | None],
    selected_ids: set[str],
) -> None:
    if all(value is None for value in filters.values()):
        con.execute("DELETE FROM daily_range_timelines")
    elif selected_ids:
        ids = sorted(selected_ids, key=source_key)
        con.execute(
            f"DELETE FROM daily_range_timelines WHERE daily_range_source_id IN ({','.join('?' for _ in ids)})",
            tuple(ids),
        )


def base_row(daily: dict[str, Any], built_at: str) -> dict[str, Any]:
    return {
        "built_at_utc": built_at,
        "import_run_id": daily["import_run_id"],
        "case_ref": daily["case_ref"],
        "symbol": daily["symbol"],
        "source_timeframe": "D1",
        "daily_range_source_id": daily["source_id"],
        "raw_range_id": daily["raw_id"],
        "raw_status": daily["status"],
        "range_high": daily["high"],
        "range_low": daily["low"],
        "range_height": None,
        "t0_formation_time": None,
        "t1_break_time": None,
        "t1_break_direction": None,
        "t1_break_level": None,
        "t1_break_kind": None,
        "supporting_event_source_id": None,
        "supporting_evidence_id": None,
        "first_wick_reclaim_time": None,
        "first_wick_reclaim_price": None,
        "first_close_reclaim_time": None,
        "first_close_reclaim_price": None,
        "t2_reclaim_time": None,
        "t2_reclaim_kind": None,
        "same_candle_close_reclaim": 0,
        "same_candle_wick_order_status": "NOT_APPLICABLE",
        "reclaim_depth_price": None,
        "reclaim_depth_percent_of_range": None,
        "formation_to_break_days": None,
        "break_to_reclaim_days": None,
        "candles_to_wick_reclaim": None,
        "candles_to_close_reclaim": None,
        "candles_to_effective_reclaim": None,
        "current_daily_state": "NEEDS_REVIEW",
        "current_daily_phase_start_time": None,
        "current_daily_phase_age_days": None,
        "parent_relationship_id": None,
        "parent_weekly_source_id": None,
        "parent_link_source": None,
        "parent_link_status": None,
        "parent_link_confidence": None,
        "parent_membership_state": "MISSING_RELATIONSHIP",
        "parent_weekly_phase_sequence_id": None,
        "weekly_phase_at_daily_formation": None,
        "weekly_phase_at_daily_break": None,
        "daily_sequence_in_weekly": None,
        "observation_status": "INCOMPLETE",
        "resolution_status": "NEEDS_REVIEW",
        "resolution_confidence": "low",
        "reason_codes_json": "[]",
        "as_of_time": built_at,
        "created_at_utc": built_at,
        "updated_at_utc": built_at,
    }


def finish(
    row: dict[str, Any],
    state: str,
    observation: str,
    resolution: str,
    confidence: str,
    reasons: set[str],
) -> dict[str, Any]:
    row.update(
        current_daily_state=state,
        observation_status=observation,
        resolution_status=resolution,
        resolution_confidence=confidence,
        reason_codes_json=json.dumps(sorted(reasons), separators=(",", ":")),
    )
    return row


def insert_row(con: sqlite3.Connection, row: dict[str, Any]) -> None:
    keys = tuple(row)
    con.execute(
        f"INSERT INTO daily_range_timelines ({','.join(keys)}) VALUES ({','.join('?' for _ in keys)})",
        tuple(row[k] for k in keys),
    )


def build_summary(filters: dict[str, str | None], rows: list[dict[str, Any]]) -> dict[str, Any]:
    count = lambda state: sum(1 for r in rows if r["current_daily_state"] == state)
    return {
        "filters": filters,
        "daily_ranges_selected": len(rows),
        "rows_built": len(rows),
        "active_pre_break_count": count("ACTIVE_PRE_BREAK"),
        "break_pending_reclaim_count": count("BREAK_PENDING_RECLAIM"),
        "reclaimed_count": count("RECLAIMED"),
        "needs_review_count": count("NEEDS_REVIEW"),
        "incomplete_range_count": count("INCOMPLETE_RANGE"),
        "missing_candles_count": count("MISSING_CANDLES"),
        "valid_parent_count": sum(r["parent_membership_state"] == "VALID" for r in rows),
        "orphan_count": sum(r["parent_membership_state"] == "ORPHAN" for r in rows),
        "parent_conflict_count": sum(r["parent_link_status"] == "CONFLICT" for r in rows),
        "parent_needs_review_count": sum(r["parent_link_status"] == "NEEDS_REVIEW" for r in rows),
        "missing_relationship_count": sum(r["parent_membership_state"] == "MISSING_RELATIONSHIP" for r in rows),
        "same_candle_close_reclaim_count": sum(int(r["same_candle_close_reclaim"]) for r in rows),
    }


def norm_filters(
    case_ref: str | None,
    symbol: str | None,
    daily_source_id: str | None,
    weekly_source_id: str | None,
) -> dict[str, str | None]:
    return {
        "case_ref": case_ref,
        "symbol": symbol.upper() if symbol else None,
        "daily_source_id": str(daily_source_id) if daily_source_id else None,
        "weekly_source_id": str(weekly_source_id) if weekly_source_id else None,
    }


def norm_status(value: Any) -> str:
    return "UNKNOWN" if value is None or not str(value).strip() else str(value).strip().upper()


def upper(value: str | None) -> str | None:
    return value.upper() if value else None


def optional_time(value: Any) -> str | None:
    return canonical_time(str(value)) if value not in (None, "") else None


def number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def wick_reclaim(c: SourceCandle, direction: str, level: float) -> bool:
    return c.low <= level if direction == "UP" else c.high >= level


def close_reclaim(c: SourceCandle, direction: str, level: float) -> bool:
    return c.close <= level if direction == "UP" else c.close >= level


def extreme(c: SourceCandle, direction: str) -> float:
    return c.low if direction == "UP" else c.high


def reclaim_depth(c: SourceCandle, direction: str, level: float) -> float:
    return max(0.0, level - c.low) if direction == "UP" else max(0.0, c.high - level)


def days(start: str, end: str) -> float:
    return (parse_time(end) - parse_time(start)).total_seconds() / 86400.0


def canonical_time(value: str | None) -> str:
    if not value:
        raise DailyRangeTimelineError("Timestamp is required")
    return canonical_dt(parse_time(value))


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def canonical_dt(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def utc_now() -> str:
    return canonical_dt(datetime.now(UTC))


def source_key(value: str) -> tuple[int, int | str]:
    text = str(value)
    return (0, int(text)) if text.isdigit() else (1, text)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="daily_range_timeline")
    subs = parser.add_subparsers(dest="command", required=True)
    build = subs.add_parser("build-daily-range-timelines")
    build.add_argument("--db-path", required=True)
    build.add_argument("--source-db", required=True)
    build.add_argument("--case-ref")
    build.add_argument("--symbol")
    build.add_argument("--daily-source-id")
    build.add_argument("--weekly-source-id")
    build.add_argument("--as-of")
    build.add_argument("--json", action="store_true")
    summary = subs.add_parser("daily-range-timeline-summary")
    summary.add_argument("--db-path", required=True)
    summary.add_argument("--case-ref")
    summary.add_argument("--symbol")
    summary.add_argument("--daily-source-id")
    summary.add_argument("--weekly-source-id")
    summary.add_argument("--daily-state")
    summary.add_argument("--parent-link-status")
    summary.add_argument("--weekly-phase")
    summary.add_argument("--observation-status")
    summary.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command == "build-daily-range-timelines":
        result = build_daily_range_timelines(
            args.db_path,
            source_db=args.source_db,
            case_ref=args.case_ref,
            symbol=args.symbol,
            daily_source_id=args.daily_source_id,
            weekly_source_id=args.weekly_source_id,
            as_of=args.as_of,
        )
    else:
        result = summarize_daily_range_timelines(
            args.db_path,
            case_ref=args.case_ref,
            symbol=args.symbol,
            daily_source_id=args.daily_source_id,
            weekly_source_id=args.weekly_source_id,
            daily_state=args.daily_state,
            parent_link_status=args.parent_link_status,
            weekly_phase=args.weekly_phase,
            observation_status=args.observation_status,
        )
    print(format_summary(result, as_json=args.json))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
