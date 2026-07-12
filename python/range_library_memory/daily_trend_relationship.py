"""Classify Daily BOS direction against the knowable Weekly direction context."""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .db import connect
from .inspection import deterministic_json, require_existing_db
from .schema import init_schema
from .weekly_direction_context import direction_state_at

CONFIRMED = {"CONFIRMED_UP", "CONFIRMED_DOWN"}
PENDING_WEEKLY = {"PENDING_RECLAIM_UP", "PENDING_RECLAIM_DOWN"}
UNUSABLE_DAILY_STATES = {"NEEDS_REVIEW", "INCOMPLETE_RANGE", "MISSING_CANDLES"}


class DailyTrendRelationshipError(RuntimeError):
    """Raised when Daily trend relationships cannot be built safely."""


def build_daily_trend_relationships(
    db_path: str | Path,
    *,
    case_ref: str | None = None,
    symbol: str | None = None,
    daily_source_id: str | None = None,
    weekly_source_id: str | None = None,
    as_of: str | None = None,
) -> dict[str, Any]:
    path = init_schema(db_path)
    filters = normalize_filters(case_ref, symbol, daily_source_id, weekly_source_id)
    built_at = utc_now()
    with connect(path) as connection:
        dailies = load_daily_timelines(connection)
        selected = select_dailies(dailies, filters)
        selected_ids = {str(row["daily_range_source_id"]) for row in selected}
        clear_scope(connection, filters, selected_ids)
        rows = [evaluate_daily(connection, row, as_of=as_of, built_at=built_at) for row in selected]
        for row in rows:
            insert_row(connection, row)
        connection.commit()
    return build_summary(filters, rows)


def summarize_daily_trend_relationships(
    db_path: str | Path,
    *,
    case_ref: str | None = None,
    symbol: str | None = None,
    daily_source_id: str | None = None,
    weekly_source_id: str | None = None,
    trend_relationship: str | None = None,
    observation_status: str | None = None,
) -> dict[str, Any]:
    path = require_existing_db(db_path)
    filters = normalize_filters(case_ref, symbol, daily_source_id, weekly_source_id)
    filters.update(
        trend_relationship=upper(trend_relationship),
        observation_status=upper(observation_status),
    )
    columns = {
        "case_ref": "case_ref",
        "symbol": "symbol",
        "daily_source_id": "daily_range_source_id",
        "weekly_source_id": "parent_weekly_source_id",
        "trend_relationship": "trend_relationship",
        "observation_status": "observation_status",
    }
    clauses: list[str] = []
    params: list[Any] = []
    for key, value in filters.items():
        if value is not None:
            clauses.append(f"{columns[key]} = ?")
            params.append(value)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with connect(path) as connection:
        grouped = connection.execute(
            f"""
            SELECT trend_relationship,
                   observation_status,
                   resolution_status,
                   weekly_direction_at_daily_break,
                   COUNT(*) AS count
            FROM daily_trend_relationships
            {where}
            GROUP BY trend_relationship,
                     observation_status,
                     resolution_status,
                     weekly_direction_at_daily_break
            ORDER BY trend_relationship,
                     observation_status,
                     resolution_status,
                     weekly_direction_at_daily_break
            """,
            tuple(params),
        ).fetchall()
    groups = [dict(row) for row in grouped]
    return {"filters": filters, "total": sum(int(row["count"]) for row in groups), "groups": groups}


def format_summary(summary: dict[str, Any], *, as_json: bool = False) -> str:
    if as_json:
        return deterministic_json(summary)
    if "groups" not in summary:
        return "\n".join(f"{key}: {value}" for key, value in summary.items() if key != "filters")
    lines = [f"total: {summary['total']}", "relationship | observation | resolution | weekly-at-break | count"]
    lines.extend(
        f"{row['trend_relationship']} | {row['observation_status']} | "
        f"{row['resolution_status']} | {row['weekly_direction_at_daily_break']} | {row['count']}"
        for row in summary["groups"]
    )
    return "\n".join(lines)


def evaluate_daily(
    connection: sqlite3.Connection,
    daily: sqlite3.Row,
    *,
    as_of: str | None,
    built_at: str,
) -> dict[str, Any]:
    reasons: set[str] = set()
    row = base_row(daily, built_at)
    daily_cutoff = canonical_time(daily["as_of_time"])
    requested_cutoff = canonical_time(as_of) if as_of else daily_cutoff
    cutoff = min_time(requested_cutoff, daily_cutoff)
    if as_of and parse_time(requested_cutoff) > parse_time(daily_cutoff):
        reasons.add("AS_OF_CAPPED_TO_DAILY_TIMELINE_DATA")
    row["as_of_time"] = cutoff

    if daily["current_daily_state"] in UNUSABLE_DAILY_STATES:
        return finish(
            row,
            "NEEDS_REVIEW",
            "INCOMPLETE",
            "NEEDS_REVIEW",
            "low",
            reasons | {"DAILY_TIMELINE_NOT_CLASSIFIABLE"},
        )

    if daily["parent_membership_state"] != "VALID" or daily["parent_link_status"] != "VALID":
        reason = (
            "PARENT_LINK_NEEDS_REVIEW"
            if daily["parent_membership_state"] == "NEEDS_REVIEW"
            else "ORPHAN_DAILY_HAS_NO_WEEKLY_CONTEXT"
            if daily["parent_membership_state"] == "ORPHAN"
            else "MISSING_VALID_WEEKLY_PARENT"
        )
        return finish(row, "NEEDS_REVIEW", "INCOMPLETE", "NEEDS_REVIEW", "low", reasons | {reason})

    parent_id = daily["parent_weekly_source_id"]
    context = latest_weekly_context(connection, str(parent_id)) if parent_id else None
    if context is None:
        return finish(row, "NEEDS_REVIEW", "INCOMPLETE", "NEEDS_REVIEW", "low", reasons | {"MISSING_WEEKLY_DIRECTION_CONTEXT"})
    row["weekly_direction_context_id"] = context["id"]
    context_cutoff = canonical_time(context["as_of_time"])
    if parse_time(context_cutoff) < parse_time(cutoff):
        cutoff = context_cutoff
        row["as_of_time"] = cutoff
        reasons.add("AS_OF_CAPPED_TO_WEEKLY_DIRECTION_DATA")

    if context["current_direction_state"] == "NEEDS_REVIEW":
        return finish(row, "NEEDS_REVIEW", "INCOMPLETE", "NEEDS_REVIEW", "low", reasons | {"WEEKLY_DIRECTION_CONTEXT_NEEDS_REVIEW"})

    t0 = daily["t0_formation_time"]
    if not t0:
        return finish(row, "NEEDS_REVIEW", "INCOMPLETE", "NEEDS_REVIEW", "low", reasons | {"MISSING_DAILY_FORMATION_TIME"})
    t0 = canonical_time(t0)
    if parse_time(t0) > parse_time(cutoff):
        return finish(row, "PENDING", "CENSORED", "PENDING", "low", reasons | {"DAILY_NOT_FORMED_AS_OF"})
    row["daily_t0_formation_time"] = t0

    formation_state = direction_state_at(context, t0)
    row["weekly_direction_at_daily_formation"] = formation_state

    t1 = daily["t1_break_time"]
    direction = daily["t1_break_direction"]
    if not t1 or not direction or parse_time(canonical_time(t1)) > parse_time(cutoff):
        if t1 and parse_time(canonical_time(t1)) > parse_time(cutoff):
            reasons.add("DAILY_BREAK_AFTER_AS_OF")
        reasons.add("DAILY_BREAK_PENDING")
        return finish(row, "PENDING", "CENSORED", "PENDING", "medium", reasons)

    t1 = canonical_time(t1)
    direction = str(direction).upper()
    row.update(
        daily_t1_break_time=t1,
        daily_break_direction=direction,
        classification_time=t1,
    )
    if direction not in {"UP", "DOWN"}:
        return finish(row, "NEEDS_REVIEW", "INCOMPLETE", "NEEDS_REVIEW", "low", reasons | {"INVALID_DAILY_BREAK_DIRECTION"})

    break_state = direction_state_at(context, t1)
    row["weekly_direction_at_daily_break"] = break_state
    row["weekly_context_changed_during_daily"] = int(formation_state != break_state)

    if break_state == "NEEDS_REVIEW":
        return finish(row, "NEEDS_REVIEW", "INCOMPLETE", "NEEDS_REVIEW", "low", reasons | {"WEEKLY_DIRECTION_CONTEXT_NEEDS_REVIEW_AT_BREAK"})
    if break_state in PENDING_WEEKLY:
        return finish(row, "TRANSITION", "OBSERVED", "RESOLVED", "medium", reasons | {"WEEKLY_RECLAIM_PENDING_AT_DAILY_BREAK"})
    if break_state == "UNRESOLVED":
        return finish(row, "TRANSITION", "OBSERVED", "RESOLVED", "low", reasons | {"WEEKLY_DIRECTION_UNRESOLVED_AT_DAILY_BREAK"})
    if break_state not in CONFIRMED:
        return finish(row, "NEEDS_REVIEW", "INCOMPLETE", "NEEDS_REVIEW", "low", reasons | {"UNSUPPORTED_WEEKLY_DIRECTION_STATE"})

    weekly_direction = break_state.removeprefix("CONFIRMED_")
    row["weekly_confirmed_direction"] = weekly_direction
    relationship = "PROTREND" if direction == weekly_direction else "COUNTERTREND"
    return finish(row, relationship, "OBSERVED", "RESOLVED", "high", reasons)


def load_daily_timelines(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    return connection.execute(
        "SELECT * FROM daily_range_timelines ORDER BY daily_range_source_id"
    ).fetchall()


def select_dailies(rows: list[sqlite3.Row], filters: dict[str, str | None]) -> list[sqlite3.Row]:
    selected: list[sqlite3.Row] = []
    for row in rows:
        if filters["case_ref"] and row["case_ref"] != filters["case_ref"]:
            continue
        if filters["symbol"] and row["symbol"] != filters["symbol"]:
            continue
        if filters["daily_source_id"] and str(row["daily_range_source_id"]) != filters["daily_source_id"]:
            continue
        if filters["weekly_source_id"] and str(row["parent_weekly_source_id"]) != filters["weekly_source_id"]:
            continue
        selected.append(row)
    return selected


def latest_weekly_context(connection: sqlite3.Connection, source_id: str) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT * FROM weekly_direction_contexts WHERE weekly_range_source_id = ? ORDER BY id DESC LIMIT 1",
        (source_id,),
    ).fetchone()


def clear_scope(
    connection: sqlite3.Connection,
    filters: dict[str, str | None],
    selected_ids: set[str],
) -> None:
    if all(value is None for value in filters.values()):
        connection.execute("DELETE FROM daily_trend_relationships")
        return
    columns = {
        "case_ref": "case_ref",
        "symbol": "symbol",
        "daily_source_id": "daily_range_source_id",
        "weekly_source_id": "parent_weekly_source_id",
    }
    clauses: list[str] = []
    params: list[Any] = []
    for key, value in filters.items():
        if value is not None:
            clauses.append(f"{columns[key]} = ?")
            params.append(value)
    if clauses:
        connection.execute(
            "DELETE FROM daily_trend_relationships WHERE " + " AND ".join(clauses),
            tuple(params),
        )
    if selected_ids:
        ordered = sorted(selected_ids, key=source_sort_key)
        connection.execute(
            f"DELETE FROM daily_trend_relationships WHERE daily_range_source_id IN ({','.join('?' for _ in ordered)})",
            tuple(ordered),
        )


def base_row(daily: sqlite3.Row, built_at: str) -> dict[str, Any]:
    return {
        "built_at_utc": built_at,
        "import_run_id": daily["import_run_id"],
        "case_ref": daily["case_ref"],
        "symbol": daily["symbol"],
        "daily_range_source_id": str(daily["daily_range_source_id"]),
        "daily_timeline_id": daily["id"],
        "parent_weekly_source_id": daily["parent_weekly_source_id"],
        "weekly_direction_context_id": None,
        "parent_link_status": daily["parent_link_status"],
        "daily_t0_formation_time": None,
        "daily_t1_break_time": None,
        "daily_break_direction": None,
        "weekly_direction_at_daily_formation": None,
        "weekly_direction_at_daily_break": None,
        "weekly_confirmed_direction": None,
        "weekly_context_changed_during_daily": None,
        "classification_time": None,
        "trend_relationship": "NEEDS_REVIEW",
        "observation_status": "INCOMPLETE",
        "resolution_status": "NEEDS_REVIEW",
        "resolution_confidence": "low",
        "reason_codes_json": "[]",
        "as_of_time": daily["as_of_time"],
        "created_at_utc": built_at,
        "updated_at_utc": built_at,
    }


def finish(
    row: dict[str, Any],
    relationship: str,
    observation: str,
    resolution: str,
    confidence: str,
    reasons: set[str],
) -> dict[str, Any]:
    row.update(
        trend_relationship=relationship,
        observation_status=observation,
        resolution_status=resolution,
        resolution_confidence=confidence,
        reason_codes_json=json.dumps(sorted(reasons), separators=(",", ":")),
    )
    return row


def insert_row(connection: sqlite3.Connection, row: dict[str, Any]) -> None:
    keys = tuple(row)
    connection.execute(
        f"INSERT INTO daily_trend_relationships ({','.join(keys)}) VALUES ({','.join('?' for _ in keys)})",
        tuple(row[key] for key in keys),
    )


def build_summary(filters: dict[str, str | None], rows: list[dict[str, Any]]) -> dict[str, Any]:
    count = lambda state: sum(1 for row in rows if row["trend_relationship"] == state)
    return {
        "filters": filters,
        "daily_ranges_selected": len(rows),
        "rows_built": len(rows),
        "protrend_count": count("PROTREND"),
        "countertrend_count": count("COUNTERTREND"),
        "transition_count": count("TRANSITION"),
        "pending_count": count("PENDING"),
        "needs_review_count": count("NEEDS_REVIEW"),
        "weekly_context_changed_count": sum(row["weekly_context_changed_during_daily"] == 1 for row in rows),
    }


def normalize_filters(
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


def upper(value: str | None) -> str | None:
    return value.upper() if value else None


def min_time(first: str, second: str) -> str:
    return first if parse_time(first) <= parse_time(second) else second


def canonical_time(value: str | None) -> str:
    if not value:
        raise DailyTrendRelationshipError("Timestamp is required")
    return canonical_datetime(parse_time(value))


def parse_time(value: str) -> datetime:
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise DailyTrendRelationshipError(f"Invalid timestamp: {value}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def canonical_datetime(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def utc_now() -> str:
    return canonical_datetime(datetime.now(UTC))


def source_sort_key(value: str) -> tuple[int, int | str]:
    text = str(value)
    return (0, int(text)) if text.isdigit() else (1, text)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="daily_trend_relationship")
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build-daily-trend-relationships")
    build.add_argument("--db-path", required=True)
    build.add_argument("--case-ref")
    build.add_argument("--symbol")
    build.add_argument("--daily-source-id")
    build.add_argument("--weekly-source-id")
    build.add_argument("--as-of")
    build.add_argument("--json", action="store_true")
    summary = subparsers.add_parser("daily-trend-relationship-summary")
    summary.add_argument("--db-path", required=True)
    summary.add_argument("--case-ref")
    summary.add_argument("--symbol")
    summary.add_argument("--daily-source-id")
    summary.add_argument("--weekly-source-id")
    summary.add_argument("--trend-relationship")
    summary.add_argument("--observation-status")
    summary.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "build-daily-trend-relationships":
        result = build_daily_trend_relationships(
            args.db_path,
            case_ref=args.case_ref,
            symbol=args.symbol,
            daily_source_id=args.daily_source_id,
            weekly_source_id=args.weekly_source_id,
            as_of=args.as_of,
        )
    else:
        result = summarize_daily_trend_relationships(
            args.db_path,
            case_ref=args.case_ref,
            symbol=args.symbol,
            daily_source_id=args.daily_source_id,
            weekly_source_id=args.weekly_source_id,
            trend_relationship=args.trend_relationship,
            observation_status=args.observation_status,
        )
    print(format_summary(result, as_json=args.json))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
