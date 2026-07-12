"""Historical Weekly direction context derived from the break that created each Weekly range."""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

from .db import connect
from .inspection import deterministic_json, require_existing_db
from .schema import init_schema

FACTUAL_RESOLUTIONS = {"MAPPED_CONFIRMED", "OHLC_DERIVED"}
RECLAIMED_STATE = "RECLAIMED"
PENDING_STATE = "ABANDONED_PENDING_RECLAIM"


class WeeklyDirectionContextError(RuntimeError):
    """Raised when Weekly direction context cannot be built safely."""


def build_weekly_direction_contexts(
    db_path: str | Path,
    *,
    case_ref: str | None = None,
    symbol: str | None = None,
    weekly_source_id: str | None = None,
    as_of: str | None = None,
) -> dict[str, Any]:
    path = init_schema(db_path)
    filters = normalize_filters(case_ref, symbol, weekly_source_id)
    built_at = utc_now()
    with connect(path) as connection:
        weeklies = load_weeklies(connection)
        selected = select_weeklies(weeklies, filters)
        selected_ids = {row["source_id"] for row in selected}
        clear_scope(connection, filters, selected_ids)
        rows = [evaluate_weekly(connection, row, as_of=as_of, built_at=built_at) for row in selected]
        for row in rows:
            insert_row(connection, row)
        connection.commit()
    return build_summary(filters, rows)


def summarize_weekly_direction_contexts(
    db_path: str | Path,
    *,
    case_ref: str | None = None,
    symbol: str | None = None,
    weekly_source_id: str | None = None,
    direction_state: str | None = None,
    observation_status: str | None = None,
) -> dict[str, Any]:
    path = require_existing_db(db_path)
    filters = normalize_filters(case_ref, symbol, weekly_source_id)
    filters.update(
        direction_state=upper(direction_state),
        observation_status=upper(observation_status),
    )
    columns = {
        "case_ref": "case_ref",
        "symbol": "symbol",
        "weekly_source_id": "weekly_range_source_id",
        "direction_state": "current_direction_state",
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
            SELECT current_direction_state,
                   observation_status,
                   resolution_status,
                   creation_link_source,
                   COUNT(*) AS count
            FROM weekly_direction_contexts
            {where}
            GROUP BY current_direction_state,
                     observation_status,
                     resolution_status,
                     creation_link_source
            ORDER BY current_direction_state,
                     observation_status,
                     resolution_status,
                     creation_link_source
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
    lines = [f"total: {summary['total']}", "direction | observation | resolution | link | count"]
    lines.extend(
        f"{row['current_direction_state']} | {row['observation_status']} | "
        f"{row['resolution_status']} | {row['creation_link_source']} | {row['count']}"
        for row in summary["groups"]
    )
    return "\n".join(lines)


def direction_state_at(context: Mapping[str, Any], milestone_time: str) -> str:
    """Return the Weekly direction state knowable at a historical milestone."""
    current = str(context["current_direction_state"])
    if current == "NEEDS_REVIEW":
        return "NEEDS_REVIEW"
    if current == "UNRESOLVED":
        return "UNRESOLVED"
    break_time = context["creation_break_time"]
    direction = context["creation_break_direction"]
    if not break_time or direction not in {"UP", "DOWN"}:
        return "NEEDS_REVIEW"
    point = parse_time(milestone_time)
    if point < parse_time(str(break_time)):
        return "UNRESOLVED"
    confirmed_from = context["confirmed_from_time"]
    if confirmed_from and point >= parse_time(str(confirmed_from)):
        return f"CONFIRMED_{direction}"
    return f"PENDING_RECLAIM_{direction}"


def evaluate_weekly(
    connection: sqlite3.Connection,
    weekly: dict[str, Any],
    *,
    as_of: str | None,
    built_at: str,
) -> dict[str, Any]:
    reasons: set[str] = set()
    row = base_row(weekly, built_at)
    phase = latest_weekly_phase(connection, weekly["source_id"])
    if not phase or not phase["as_of_time"]:
        return finish(row, "NEEDS_REVIEW", "INCOMPLETE", "NEEDS_REVIEW", "low", {"MISSING_WEEKLY_PHASE_SEQUENCE"})
    row["supporting_weekly_phase_sequence_id"] = phase["id"]
    cutoff = effective_cutoff(as_of, canonical_time(phase["as_of_time"]), reasons)
    row["as_of_time"] = cutoff

    link = resolve_creation_link(connection, weekly)
    row.update(
        creation_link_source=link["source"],
        creation_old_weekly_source_id=link["old_range_id"],
        creation_event_source_id=link["event_source_id"],
    )
    reasons.update(link["reasons"])
    if link["status"] == "UNRESOLVED":
        return finish(row, "UNRESOLVED", "INCOMPLETE", "UNRESOLVED", "low", reasons)
    if link["status"] == "NEEDS_REVIEW":
        return finish(row, "NEEDS_REVIEW", "INCOMPLETE", "NEEDS_REVIEW", "low", reasons)

    evidence = link["evidence"]
    if evidence is None:
        return finish(row, "NEEDS_REVIEW", "INCOMPLETE", "NEEDS_REVIEW", "low", reasons | {"MISSING_CREATION_EVENT_EVIDENCE"})
    evidence_errors = validate_creation_evidence(weekly, link, evidence)
    if evidence_errors:
        return finish(row, "NEEDS_REVIEW", "INCOMPLETE", "NEEDS_REVIEW", "low", reasons | evidence_errors)

    direction = "UP" if evidence["event_type"] == "BOS_UP" else "DOWN"
    break_time = canonical_time(evidence["effective_break_time"])
    if parse_time(break_time) > parse_time(cutoff):
        return finish(row, "UNRESOLVED", "INCOMPLETE", "UNRESOLVED", "low", reasons | {"CREATION_BREAK_AFTER_AS_OF"})
    row.update(
        creation_break_direction=direction,
        creation_break_time=break_time,
        creation_break_level=float(evidence["boundary_price"]),
        creation_break_kind=evidence["effective_break_kind"],
        pending_from_time=break_time,
        supporting_event_evidence_id=evidence["id"],
    )

    reclaim = latest_break_reclaim(connection, str(link["old_range_id"]))
    if reclaim is None:
        return finish(row, "NEEDS_REVIEW", "INCOMPLETE", "NEEDS_REVIEW", "low", reasons | {"MISSING_CREATION_BREAK_RECLAIM"})
    row["supporting_break_reclaim_id"] = reclaim["id"]
    reclaim_errors = validate_break_reclaim(evidence, reclaim)
    if reclaim_errors:
        return finish(row, "NEEDS_REVIEW", "INCOMPLETE", "NEEDS_REVIEW", "low", reasons | reclaim_errors)
    if str(reclaim["supporting_event_source_id"]) != str(evidence["event_source_id"]):
        reasons.add("EQUIVALENT_CREATION_BREAK_EVENT_USED_FOR_RECLAIM")

    confidence = "high" if link["source"] == "EXPLICIT" else "medium"
    reclaim_time = reclaim["effective_reclaim_time"]
    if reclaim["current_state"] == RECLAIMED_STATE:
        if not reclaim_time:
            return finish(row, "NEEDS_REVIEW", "INCOMPLETE", "NEEDS_REVIEW", "low", reasons | {"RECLAIMED_WITHOUT_RECLAIM_TIME"})
        reclaim_time = canonical_time(reclaim_time)
        if parse_time(reclaim_time) < parse_time(break_time):
            return finish(row, "NEEDS_REVIEW", "INCOMPLETE", "NEEDS_REVIEW", "low", reasons | {"CREATION_RECLAIM_BEFORE_BREAK"})
        if parse_time(reclaim_time) <= parse_time(cutoff):
            row.update(
                creation_reclaim_time=reclaim_time,
                creation_reclaim_kind=reclaim["effective_reclaim_kind"],
                confirmed_from_time=reclaim_time,
            )
            return finish(row, f"CONFIRMED_{direction}", "OBSERVED", "RESOLVED", confidence, reasons)
        reasons.add("CREATION_RECLAIM_AFTER_AS_OF")
        return finish(row, f"PENDING_RECLAIM_{direction}", "CENSORED", "PENDING", confidence, reasons)

    if reclaim["current_state"] == PENDING_STATE:
        if reclaim_time:
            return finish(row, "NEEDS_REVIEW", "INCOMPLETE", "NEEDS_REVIEW", "low", reasons | {"PENDING_STATE_WITH_RECLAIM_TIME"})
        return finish(row, f"PENDING_RECLAIM_{direction}", "CENSORED", "PENDING", confidence, reasons)

    return finish(
        row,
        "NEEDS_REVIEW",
        "INCOMPLETE",
        "NEEDS_REVIEW",
        "low",
        reasons | {f"UNUSABLE_CREATION_RECLAIM_STATE:{reclaim['current_state']}"},
    )


def resolve_creation_link(connection: sqlite3.Connection, weekly: dict[str, Any]) -> dict[str, Any]:
    raw_old = weekly["old_range_id"]
    raw_event = weekly["created_by_event_id"]
    candidates = connection.execute(
        """
        SELECT *
        FROM event_ohlc_evidence
        WHERE structure_layer = 'WEEKLY'
          AND mapped_new_range_id = ?
        ORDER BY id DESC
        """,
        (weekly["source_id"],),
    ).fetchall()

    if raw_old or raw_event:
        if not raw_old or not raw_event:
            return {
                "status": "NEEDS_REVIEW",
                "source": "EXPLICIT_PARTIAL",
                "old_range_id": raw_old,
                "event_source_id": raw_event,
                "evidence": None,
                "reasons": {"PARTIAL_EXPLICIT_CREATION_LINK"},
            }
        evidence = connection.execute(
            """
            SELECT *
            FROM event_ohlc_evidence
            WHERE structure_layer = 'WEEKLY'
              AND range_source_id = ?
              AND event_source_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (str(raw_old), str(raw_event)),
        ).fetchone()
        return {
            "status": "RESOLVED" if evidence else "NEEDS_REVIEW",
            "source": "EXPLICIT",
            "old_range_id": str(raw_old),
            "event_source_id": str(raw_event),
            "evidence": evidence,
            "reasons": set() if evidence else {"EXPLICIT_CREATION_EVIDENCE_NOT_FOUND"},
        }

    factual_candidates = [
        row
        for row in candidates
        if row["resolution_status"] in FACTUAL_RESOLUTIONS
        and row["event_type"] in {"BOS_UP", "BOS_DOWN"}
        and row["effective_break_time"]
    ]
    if not factual_candidates:
        return {
            "status": "UNRESOLVED",
            "source": "NONE",
            "old_range_id": None,
            "event_source_id": None,
            "evidence": None,
            "reasons": {"NO_CREATION_LINK"},
        }
    unique = {(str(row["range_source_id"]), str(row["event_source_id"])) for row in factual_candidates}
    if len(unique) != 1:
        return {
            "status": "NEEDS_REVIEW",
            "source": "EVIDENCE_DERIVED",
            "old_range_id": None,
            "event_source_id": None,
            "evidence": None,
            "reasons": {"AMBIGUOUS_CREATION_EVIDENCE"},
        }
    evidence = factual_candidates[0]
    return {
        "status": "RESOLVED",
        "source": "EVIDENCE_DERIVED",
        "old_range_id": str(evidence["range_source_id"]),
        "event_source_id": str(evidence["event_source_id"]),
        "evidence": evidence,
        "reasons": {"CREATION_LINK_DERIVED_FROM_EVENT_EVIDENCE"},
    }


def validate_creation_evidence(
    weekly: dict[str, Any],
    link: dict[str, Any],
    evidence: sqlite3.Row,
) -> set[str]:
    errors: set[str] = set()
    if evidence["resolution_status"] not in FACTUAL_RESOLUTIONS:
        errors.add("CREATION_EVENT_NOT_FACTUAL")
    if evidence["event_type"] not in {"BOS_UP", "BOS_DOWN"}:
        errors.add("UNSUPPORTED_CREATION_EVENT")
    if not evidence["effective_break_time"] or evidence["boundary_price"] is None:
        errors.add("INCOMPLETE_CREATION_BREAK_EVIDENCE")
    if str(evidence["range_source_id"]) != str(link["old_range_id"]):
        errors.add("CREATION_OLD_RANGE_MISMATCH")
    if str(evidence["event_source_id"]) != str(link["event_source_id"]):
        errors.add("CREATION_EVENT_ID_MISMATCH")
    if evidence["mapped_new_range_id"] and str(evidence["mapped_new_range_id"]) != weekly["source_id"]:
        errors.add("CREATION_NEW_RANGE_MISMATCH")
    return errors


def validate_break_reclaim(evidence: sqlite3.Row, reclaim: sqlite3.Row) -> set[str]:
    errors: set[str] = set()
    expected_direction = "UP" if evidence["event_type"] == "BOS_UP" else "DOWN"
    if reclaim["break_direction"] != expected_direction:
        errors.add("CREATION_BREAK_DIRECTION_MISMATCH")
    if not reclaim["break_time"] or canonical_time(reclaim["break_time"]) != canonical_time(evidence["effective_break_time"]):
        errors.add("CREATION_BREAK_TIME_MISMATCH")
    if reclaim["break_level"] is None or prices_differ(float(reclaim["break_level"]), float(evidence["boundary_price"])):
        errors.add("CREATION_BREAK_LEVEL_MISMATCH")
    return errors


def load_weeklies(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT *
        FROM raw_ranges
        WHERE UPPER(COALESCE(json_extract(raw_payload_json, '$.structure_layer'), range_type, '')) = 'WEEKLY'
          AND id IN (SELECT MAX(id) FROM raw_ranges GROUP BY source_record_id)
        ORDER BY source_record_id
        """
    ).fetchall()
    result: list[dict[str, Any]] = []
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
                "status": normalize_status(payload.get("status")),
                "old_range_id": string_id(payload.get("old_range_id")),
                "created_by_event_id": string_id(payload.get("created_by_event_id")),
            }
        )
    return result


def select_weeklies(rows: list[dict[str, Any]], filters: dict[str, str | None]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for row in rows:
        if filters["case_ref"] and row["case_ref"] != filters["case_ref"]:
            continue
        if filters["symbol"] and row["symbol"] != filters["symbol"]:
            continue
        if filters["weekly_source_id"] and row["source_id"] != filters["weekly_source_id"]:
            continue
        selected.append(row)
    return selected


def latest_weekly_phase(connection: sqlite3.Connection, source_id: str) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT * FROM weekly_phase_sequences WHERE weekly_range_source_id = ? ORDER BY id DESC LIMIT 1",
        (source_id,),
    ).fetchone()


def latest_break_reclaim(connection: sqlite3.Connection, source_id: str) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT * FROM weekly_break_reclaim_lifecycles WHERE weekly_range_source_id = ? ORDER BY id DESC LIMIT 1",
        (source_id,),
    ).fetchone()


def clear_scope(
    connection: sqlite3.Connection,
    filters: dict[str, str | None],
    selected_ids: set[str],
) -> None:
    if all(value is None for value in filters.values()):
        connection.execute("DELETE FROM weekly_direction_contexts")
        return
    columns = {
        "case_ref": "case_ref",
        "symbol": "symbol",
        "weekly_source_id": "weekly_range_source_id",
    }
    clauses: list[str] = []
    params: list[Any] = []
    for key, value in filters.items():
        if value is not None:
            clauses.append(f"{columns[key]} = ?")
            params.append(value)
    if clauses:
        connection.execute(
            "DELETE FROM weekly_direction_contexts WHERE " + " AND ".join(clauses),
            tuple(params),
        )
    if selected_ids:
        ordered = sorted(selected_ids, key=source_sort_key)
        connection.execute(
            f"DELETE FROM weekly_direction_contexts WHERE weekly_range_source_id IN ({','.join('?' for _ in ordered)})",
            tuple(ordered),
        )


def base_row(weekly: dict[str, Any], built_at: str) -> dict[str, Any]:
    return {
        "built_at_utc": built_at,
        "import_run_id": weekly["import_run_id"],
        "case_ref": weekly["case_ref"],
        "symbol": weekly["symbol"],
        "source_timeframe": "W1",
        "weekly_range_source_id": weekly["source_id"],
        "raw_range_id": weekly["raw_id"],
        "raw_status": weekly["status"],
        "creation_link_source": "NONE",
        "creation_old_weekly_source_id": None,
        "creation_event_source_id": None,
        "creation_break_direction": None,
        "creation_break_time": None,
        "creation_break_level": None,
        "creation_break_kind": None,
        "creation_reclaim_time": None,
        "creation_reclaim_kind": None,
        "pending_from_time": None,
        "confirmed_from_time": None,
        "current_direction_state": "UNRESOLVED",
        "observation_status": "INCOMPLETE",
        "resolution_status": "UNRESOLVED",
        "resolution_confidence": "low",
        "supporting_event_evidence_id": None,
        "supporting_break_reclaim_id": None,
        "supporting_weekly_phase_sequence_id": None,
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
        current_direction_state=state,
        observation_status=observation,
        resolution_status=resolution,
        resolution_confidence=confidence,
        reason_codes_json=json.dumps(sorted(reasons), separators=(",", ":")),
    )
    return row


def insert_row(connection: sqlite3.Connection, row: dict[str, Any]) -> None:
    keys = tuple(row)
    connection.execute(
        f"INSERT INTO weekly_direction_contexts ({','.join(keys)}) VALUES ({','.join('?' for _ in keys)})",
        tuple(row[key] for key in keys),
    )


def build_summary(filters: dict[str, str | None], rows: list[dict[str, Any]]) -> dict[str, Any]:
    count = lambda state: sum(1 for row in rows if row["current_direction_state"] == state)
    return {
        "filters": filters,
        "weekly_ranges_selected": len(rows),
        "rows_built": len(rows),
        "confirmed_up_count": count("CONFIRMED_UP"),
        "confirmed_down_count": count("CONFIRMED_DOWN"),
        "pending_reclaim_up_count": count("PENDING_RECLAIM_UP"),
        "pending_reclaim_down_count": count("PENDING_RECLAIM_DOWN"),
        "unresolved_count": count("UNRESOLVED"),
        "needs_review_count": count("NEEDS_REVIEW"),
        "explicit_link_count": sum(row["creation_link_source"] == "EXPLICIT" for row in rows),
        "derived_link_count": sum(row["creation_link_source"] == "EVIDENCE_DERIVED" for row in rows),
    }


def normalize_filters(
    case_ref: str | None,
    symbol: str | None,
    weekly_source_id: str | None,
) -> dict[str, str | None]:
    return {
        "case_ref": case_ref,
        "symbol": symbol.upper() if symbol else None,
        "weekly_source_id": str(weekly_source_id) if weekly_source_id else None,
    }


def normalize_status(value: Any) -> str:
    return "UNKNOWN" if value is None or not str(value).strip() else str(value).strip().upper()


def string_id(value: Any) -> str | None:
    return None if value in (None, "") else str(value)


def upper(value: str | None) -> str | None:
    return value.upper() if value else None


def effective_cutoff(as_of: str | None, latest: str, reasons: set[str]) -> str:
    if not as_of:
        return latest
    requested = canonical_time(as_of)
    if parse_time(requested) > parse_time(latest):
        reasons.add("AS_OF_CAPPED_TO_WEEKLY_PHASE_DATA")
        return latest
    return requested


def prices_differ(first: float, second: float) -> bool:
    tolerance = max(abs(first), abs(second), 1.0) * 1e-9
    return abs(first - second) > tolerance


def canonical_time(value: str | None) -> str:
    if not value:
        raise WeeklyDirectionContextError("Timestamp is required")
    return canonical_datetime(parse_time(value))


def parse_time(value: str) -> datetime:
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise WeeklyDirectionContextError(f"Invalid timestamp: {value}") from exc
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
    parser = argparse.ArgumentParser(prog="weekly_direction_context")
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build-weekly-direction-contexts")
    build.add_argument("--db-path", required=True)
    build.add_argument("--case-ref")
    build.add_argument("--symbol")
    build.add_argument("--weekly-source-id")
    build.add_argument("--as-of")
    build.add_argument("--json", action="store_true")
    summary = subparsers.add_parser("weekly-direction-context-summary")
    summary.add_argument("--db-path", required=True)
    summary.add_argument("--case-ref")
    summary.add_argument("--symbol")
    summary.add_argument("--weekly-source-id")
    summary.add_argument("--direction-state")
    summary.add_argument("--observation-status")
    summary.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "build-weekly-direction-contexts":
        result = build_weekly_direction_contexts(
            args.db_path,
            case_ref=args.case_ref,
            symbol=args.symbol,
            weekly_source_id=args.weekly_source_id,
            as_of=args.as_of,
        )
    else:
        result = summarize_weekly_direction_contexts(
            args.db_path,
            case_ref=args.case_ref,
            symbol=args.symbol,
            weekly_source_id=args.weekly_source_id,
            direction_state=args.direction_state,
            observation_status=args.observation_status,
        )
    print(format_summary(result, as_json=args.json))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
