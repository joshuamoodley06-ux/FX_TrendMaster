"""Factual T0/T1/T2 Weekly phase timelines."""

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
from .source_market_db import SourceMarketDbError, latest_candle_time, open_source_market_db
from .weekly_break_reclaim import canonical_time, parse_time


class WeeklyPhaseSequenceError(RuntimeError):
    """Raised when Weekly phase sequences cannot be built safely."""


def build_weekly_phase_sequences(
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
            ranges = select_weeklies(connection, filters)
            clear_scope(connection, filters)
            rows = [evaluate(connection, source, weekly, as_of=as_of, built_at=built_at) for weekly in ranges]
            for row in rows:
                insert_row(connection, row)
            connection.commit()
    except SourceMarketDbError as exc:
        raise WeeklyPhaseSequenceError(str(exc)) from exc
    return build_summary(filters, rows)


def summarize_weekly_phase_sequences(
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
    columns = {"case_ref": "case_ref", "symbol": "symbol", "weekly_source_id": "weekly_range_source_id",
               "state": "current_phase_state", "observation_status": "observation_status"}
    clauses: list[str] = []
    params: list[Any] = []
    for key, value in filters.items():
        if value:
            clauses.append(f"{columns[key]} = ?")
            params.append(value)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with connect(path) as connection:
        rows = connection.execute(
            f"""SELECT current_phase_state, observation_status, COUNT(*) AS count
                FROM weekly_phase_sequences{where}
                GROUP BY current_phase_state, observation_status
                ORDER BY current_phase_state, observation_status""", tuple(params)
        ).fetchall()
    groups = [dict(row) for row in rows]
    return {"filters": filters, "total": sum(int(row["count"]) for row in groups), "groups": groups}


def format_summary(summary: dict[str, Any], *, as_json: bool = False) -> str:
    if as_json:
        return deterministic_json(summary)
    if "groups" in summary:
        return "\n".join([f"total: {summary['total']}"] + [f"{r['current_phase_state']} | {r['observation_status']} | {r['count']}" for r in summary["groups"]])
    return "\n".join(f"{key}: {value}" for key, value in summary.items() if key != "filters")


def evaluate(connection: sqlite3.Connection, source: sqlite3.Connection, weekly: dict[str, Any], *, as_of: str | None, built_at: str) -> dict[str, Any]:
    reasons: set[str] = set()
    latest = latest_candle_time(source, symbol=weekly["symbol"], timeframe="W1")
    if not latest:
        return finish(base_row(weekly, built_at, built_at), "MISSING_CANDLES", "INCOMPLETE", "MISSING_DATA", "low", {"MISSING_W1_CANDLES"})
    latest = canonical_time(latest)
    if as_of:
        requested = canonical_time(as_of)
        if parse_time(requested) > parse_time(latest):
            effective_as_of = latest
            reasons.add("AS_OF_CAPPED_TO_LATEST_W1_DATA")
        else:
            effective_as_of = requested
    else:
        effective_as_of = latest
    row = base_row(weekly, built_at, effective_as_of)

    if not weekly["high_time"] or not weekly["low_time"]:
        return finish(row, "INCOMPLETE_RANGE", "INCOMPLETE", "INCOMPLETE_RANGE", "low", reasons | {"MISSING_RANGE_ANCHOR_TIME"})
    times = [parse_time(weekly["high_time"]), parse_time(weekly["low_time"])]
    if weekly["active_time"]:
        times.append(parse_time(weekly["active_time"]))
    t0 = canonical_dt(max(times))
    row["t0_formation_time"] = t0

    reclaim = connection.execute(
        "SELECT * FROM weekly_break_reclaim_lifecycles WHERE weekly_range_source_id=? ORDER BY id DESC LIMIT 1",
        (weekly["source_id"],),
    ).fetchone()
    reclaim_state = reclaim["current_state"] if reclaim else None
    reclaim_time = reclaim["effective_reclaim_time"] if reclaim else None
    complete_break = bool(reclaim and reclaim["break_time"] and reclaim["break_direction"] and reclaim["break_level"] is not None)
    factual_break = bool(complete_break and reclaim_state in {"RECLAIMED", "ABANDONED_PENDING_RECLAIM"})
    if factual_break:
        row.update({"t1_break_time": canonical_time(reclaim["break_time"]), "t1_break_direction": reclaim["break_direction"],
                    "t1_break_level": reclaim["break_level"], "t1_break_kind": reclaim["break_kind"],
                    "supporting_break_reclaim_id": reclaim["id"]})
        if reclaim_state == "RECLAIMED" and reclaim_time:
            row.update({"t2_reclaim_time": canonical_time(reclaim_time),
                        "t2_reclaim_kind": reclaim["effective_reclaim_kind"]})

    contradictory_reasons: set[str] = set()
    if reclaim_state == "RECLAIMED" and not reclaim_time:
        contradictory_reasons.add("RECLAIMED_WITHOUT_RECLAIM_TIME")
    if reclaim_state == "ABANDONED_PENDING_RECLAIM" and reclaim_time:
        contradictory_reasons.add("PENDING_STATE_WITH_RECLAIM_TIME")
    if reclaim_time and not complete_break:
        contradictory_reasons.add("RECLAIM_TIME_WITHOUT_FACTUAL_BREAK")

    t1, t2 = row["t1_break_time"], row["t2_reclaim_time"]
    if parse_time(t0) > parse_time(effective_as_of) or (t1 and parse_time(t1) > parse_time(effective_as_of)) or (t2 and parse_time(t2) > parse_time(effective_as_of)):
        reasons.add("MILESTONE_AFTER_AS_OF")
    if t1 and parse_time(t1) < parse_time(t0):
        reasons.add("BREAK_BEFORE_RANGE_FORMATION")
    if t1 and t2 and parse_time(t2) < parse_time(t1):
        reasons.add("RECLAIM_BEFORE_BREAK")
    if reasons & {"MILESTONE_AFTER_AS_OF", "BREAK_BEFORE_RANGE_FORMATION", "RECLAIM_BEFORE_BREAK"} or contradictory_reasons:
        return finish(row, "NEEDS_REVIEW", "INCOMPLETE", "NEEDS_REVIEW", "low", reasons | contradictory_reasons)

    if t1:
        row["formation_to_break_days"] = elapsed_days(t0, t1)
    if t1 and t2:
        row["break_to_reclaim_days"] = elapsed_days(t1, t2)
        row["same_candle_break_reclaim"] = int(t1 == t2)
        row["current_phase_start_time"] = t2
        row["current_phase_age_days"] = elapsed_days(t2, effective_as_of)
        return finish(row, "RECLAIMED", "OBSERVED", "RESOLVED", "high", reasons)
    if t1 and reclaim and reclaim["current_state"] == "ABANDONED_PENDING_RECLAIM":
        row["current_phase_start_time"] = t1
        row["current_phase_age_days"] = elapsed_days(t1, effective_as_of)
        return finish(row, "BREAK_PENDING_RECLAIM", "CENSORED", "PENDING", "high", reasons)
    if weekly["status"] == "UNKNOWN":
        return finish(row, "NEEDS_REVIEW", "INCOMPLETE", "NEEDS_REVIEW", "low", reasons | {"MISSING_RAW_STATUS"})
    if weekly["status"] in {"BROKEN", "ABANDONED", "ARCHIVED"}:
        return finish(row, "NEEDS_REVIEW", "INCOMPLETE", "NEEDS_REVIEW", "low", reasons | {"RAW_BROKEN_WITHOUT_FACTUAL_BREAK"})
    if weekly["status"] in {"ACTIVE", "FORMING"}:
        row["current_phase_start_time"] = t0
        row["current_phase_age_days"] = elapsed_days(t0, effective_as_of)
        return finish(row, "ACTIVE_PRE_BREAK", "CENSORED", "PENDING", "medium", reasons | {"NO_FACTUAL_BREAK_YET"})
    return finish(row, "NEEDS_REVIEW", "INCOMPLETE", "NEEDS_REVIEW", "low", reasons | {"UNSUPPORTED_RAW_STATUS_WITHOUT_FACTUAL_BREAK"})


def select_weeklies(connection: sqlite3.Connection, filters: dict[str, str | None]) -> list[dict[str, Any]]:
    clauses = ["UPPER(COALESCE(json_extract(raw_payload_json,'$.structure_layer'),range_type,''))='WEEKLY'"]
    params: list[Any] = []
    if filters["case_ref"]: clauses.append("json_extract(raw_payload_json,'$.case_ref')=?"); params.append(filters["case_ref"])
    if filters["symbol"]: clauses.append("UPPER(symbol)=?"); params.append(filters["symbol"])
    if filters["weekly_source_id"]: clauses.append("source_record_id=?"); params.append(filters["weekly_source_id"])
    rows = connection.execute(f"""SELECT * FROM raw_ranges WHERE {' AND '.join(clauses)}
        AND id IN (SELECT MAX(id) FROM raw_ranges GROUP BY source_record_id) ORDER BY source_record_id""", tuple(params)).fetchall()
    result = []
    for value in rows:
        payload = json.loads(value["raw_payload_json"])
        result.append({"raw_id": value["id"], "import_run_id": value["import_run_id"], "source_id": str(value["source_record_id"]),
                       "case_ref": payload.get("case_ref"), "symbol": str(value["symbol"] or payload.get("symbol") or "").upper(),
                       "timeframe": str(payload.get("source_timeframe") or value["timeframe"] or "W1").upper(),
                       "status": normalize_status(payload.get("status")),
                       "active_time": optional_time(payload.get("active_from_time")),
                       "high_time": optional_time(payload.get("range_high_time")), "low_time": optional_time(payload.get("range_low_time")),
                       "high": number(payload.get("range_high_price", value["high"])), "low": number(payload.get("range_low_price", value["low"]))})
    return result


def clear_scope(connection: sqlite3.Connection, filters: dict[str, str | None]) -> None:
    clauses: list[str] = []; params: list[Any] = []
    for key, column in {"case_ref": "case_ref", "symbol": "symbol", "weekly_source_id": "weekly_range_source_id"}.items():
        if filters[key]: clauses.append(f"{column}=?"); params.append(filters[key])
    connection.execute("DELETE FROM weekly_phase_sequences" + (" WHERE " + " AND ".join(clauses) if clauses else ""), tuple(params))


def base_row(w: dict[str, Any], built_at: str, as_of: str) -> dict[str, Any]:
    return {"built_at_utc": built_at, "import_run_id": w["import_run_id"], "case_ref": w["case_ref"], "symbol": w["symbol"],
            "source_timeframe": "W1", "weekly_range_source_id": w["source_id"], "raw_range_id": w["raw_id"],
            "raw_status": w["status"], "range_high": w["high"], "range_low": w["low"], "t0_formation_time": None,
            "t1_break_time": None, "t1_break_direction": None, "t1_break_level": None, "t1_break_kind": None,
            "t2_reclaim_time": None, "t2_reclaim_kind": None, "same_candle_break_reclaim": 0,
            "formation_to_break_days": None, "break_to_reclaim_days": None, "current_phase_state": "NEEDS_REVIEW",
            "current_phase_start_time": None, "current_phase_age_days": None, "observation_status": "INCOMPLETE",
            "resolution_status": "NEEDS_REVIEW", "resolution_confidence": "low", "supporting_break_reclaim_id": None,
            "reason_codes_json": "[]", "as_of_time": as_of, "created_at_utc": built_at, "updated_at_utc": built_at}


def finish(row: dict[str, Any], state: str, observation: str, resolution: str, confidence: str, reasons: set[str]) -> dict[str, Any]:
    row.update({"current_phase_state": state, "observation_status": observation, "resolution_status": resolution,
                "resolution_confidence": confidence, "reason_codes_json": json.dumps(sorted(reasons), separators=(",", ":"))})
    return row


def insert_row(connection: sqlite3.Connection, row: dict[str, Any]) -> None:
    keys = tuple(row); connection.execute(f"INSERT INTO weekly_phase_sequences ({','.join(keys)}) VALUES ({','.join('?' for _ in keys)})", tuple(row[k] for k in keys))


def build_summary(filters: dict[str, str | None], rows: list[dict[str, Any]]) -> dict[str, Any]:
    count = lambda state: sum(1 for row in rows if row["current_phase_state"] == state)
    return {"filters": filters, "weekly_ranges_selected": len(rows), "rows_built": len(rows),
            "active_pre_break_count": count("ACTIVE_PRE_BREAK"), "break_pending_reclaim_count": count("BREAK_PENDING_RECLAIM"),
            "reclaimed_count": count("RECLAIMED"), "needs_review_count": count("NEEDS_REVIEW"),
            "incomplete_range_count": count("INCOMPLETE_RANGE"), "missing_candles_count": count("MISSING_CANDLES"),
            "same_candle_break_reclaim_count": sum(int(row["same_candle_break_reclaim"]) for row in rows)}


def normalized_filters(case_ref: str | None, symbol: str | None, source_id: str | None) -> dict[str, str | None]:
    return {"case_ref": case_ref, "symbol": symbol.upper() if symbol else None, "weekly_source_id": str(source_id) if source_id else None}


def optional_time(value: Any) -> str | None:
    return canonical_time(str(value)) if value not in (None, "") else None


def number(value: Any) -> float | None:
    try: return float(value) if value is not None else None
    except (TypeError, ValueError): return None


def normalize_status(value: Any) -> str:
    if value is None or not str(value).strip():
        return "UNKNOWN"
    return str(value).strip().upper()


def elapsed_days(start: str, end: str) -> float:
    return (parse_time(end) - parse_time(start)).total_seconds() / 86400.0


def canonical_dt(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def utc_now() -> str:
    return canonical_dt(datetime.now(UTC))
