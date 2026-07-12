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
    if not phase or not phase["on_confide"]:
        return finish(row, "NEEDS_REVIEW", "INCOMPLETE", "NEEDS_REVIEW", "low", {"MISSING_WEEKLY_PHASE_SEQUENCE"})
    row["supporting_weekly_phase_sequence_id"] = phase["id"]
    cutoff = effective_cutoff(as_of, canonical_time(phase["on_confide"]), reasons)
    row["on_confide"] = cutoff

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
    row.update(
        creation_break_direction=direction,
        creation_break_time=break_time,
        creation_break_level=float(evidence["boundary_price"]),
        creation_break_kind=evidence["effective_break_kind"],
        pending_from_time=break_time,
        supporting_event_evidence_id=evidence["id"],
    )
    if parse_time(break_time) > parse_time(cutoff):
        return finish(row, "UNRESOLVED", "INCOMPLETE", "UNRESOLVED", "low", reasons | {"CREATION_BREAK_AFTER_AS_OF"})

    reclaim = latest_break_reclaim(connection, str(link["old_range_id"]))
    if reclaim is None:
        return finish(row, "NEEDS_REVIEW", "INCOMPLETE", "NEEDS_REVIEW", "low", reasons | {"MISSING_CREATION_BREAK_RECLAIM"})
    row["supporting_break_reclaim_id"] = reclaim["id"]
    reclaim_errors = validate_break_reclaim(evidence, reclaim)
    if reclaim_errors:
        return finish(row, "NEEDS_REVIEW", "INCOMPLETE", "NEEDS_REVIEW", "low", reasons | reclaim_errors)
    if str(reclaim["supporting_event_source_id"]) != str(evidence["event_source_id"]):
        reasons.add("EQUI,crENT_CREATION_BREAK_EVENT_USED_FOR_RECLAIM")

    confidence = "high" if link["source"] == "EXPLICIT" else "medium"
    reclaim_time = reclaim["effective_reclaim_time"]
    if reclaim["current_state"] == RECLAIMED_STATE:
        if not reclaim_time:
            return finish(row, "NEEDS_REVIEW", "INCOMPLETE", "NEEDS_REVIEW", "low", reasons | {"RECLAIMED_WITHOUT_RECLAIM_TIME"})
        reclaim_time = canonical_time(reclaim_time)
        if parse_time(reclaim_time) < parse_time(break_time):
            return finish(row, "NEEDS_REVIEW", "INCOMPLETE", "NEEDS_REVIEW", "low", reasons | {"CREATION_RECLAIM_BEFORE_BREAK"})
        row.update(
            creation_reclaim_time=reclaim_time,
            creation_reclaim_kind=reclaim["effective_reclaim_kind"],
        )
        if parse_time(reclaim_time) <= parse_time(cutoff):
            row["confirmed_from_time"] = reclaim_time
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
     