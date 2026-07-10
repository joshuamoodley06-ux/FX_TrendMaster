"""Manual review helpers for validation issues and duplicate candidates."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .db import connect
from .inspection import InspectionError, deterministic_json, require_existing_db
from .validation import utc_now

ALLOWED_DUPLICATE_STATUSES = ("open", "confirmed_duplicate", "not_duplicate", "ignored")


def list_issues(db_path: str | Path, *, status: str, limit: int) -> list[dict[str, Any]]:
    path = require_existing_db(db_path)
    where_clause = "resolved_at_utc IS NULL" if status == "open" else "resolved_at_utc IS NOT NULL"
    with connect(path) as connection:
        rows = connection.execute(
            f"""
            SELECT id,
                   import_run_id,
                   raw_range_id,
                   raw_event_id,
                   severity,
                   issue_code,
                   field_name,
                   observed_value,
                   created_at_utc,
                   resolved_at_utc,
                   resolution_notes
            FROM validation_issues
            WHERE {where_clause}
            ORDER BY created_at_utc DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def resolve_issue(db_path: str | Path, *, issue_id: int, notes: str) -> None:
    path = require_existing_db(db_path)
    with connect(path) as connection:
        cursor = connection.execute(
            """
            UPDATE validation_issues
            SET resolved_at_utc = ?,
                resolution_notes = ?
            WHERE id = ?
            """,
            (utc_now(), notes, issue_id),
        )
        if cursor.rowcount == 0:
            raise InspectionError(f"Validation issue not found: {issue_id}")
        connection.commit()


def list_duplicates(db_path: str | Path, *, status: str, limit: int) -> list[dict[str, Any]]:
    path = require_existing_db(db_path)
    with connect(path) as connection:
        rows = connection.execute(
            """
            SELECT id,
                   import_run_id,
                   candidate_type,
                   left_raw_range_id,
                   right_raw_range_id,
                   left_raw_event_id,
                   right_raw_event_id,
                   rule_code,
                   confidence,
                   reason,
                   created_at_utc,
                   review_status,
                   review_notes
            FROM duplicate_candidates
            WHERE review_status = ?
            ORDER BY created_at_utc DESC, id DESC
            LIMIT ?
            """,
            (status, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def review_duplicate(db_path: str | Path, *, candidate_id: int, status: str, notes: str) -> None:
    if status not in ALLOWED_DUPLICATE_STATUSES:
        raise InspectionError(
            "Invalid duplicate review status: "
            f"{status}. Allowed statuses: {', '.join(ALLOWED_DUPLICATE_STATUSES)}"
        )
    path = require_existing_db(db_path)
    with connect(path) as connection:
        cursor = connection.execute(
            """
            UPDATE duplicate_candidates
            SET review_status = ?,
                review_notes = ?
            WHERE id = ?
            """,
            (status, notes, candidate_id),
        )
        if cursor.rowcount == 0:
            raise InspectionError(f"Duplicate candidate not found: {candidate_id}")
        connection.commit()


def format_issues(issues: list[dict[str, Any]], *, as_json: bool = False) -> str:
    if as_json:
        return deterministic_json({"issues": issues})
    if not issues:
        return "No validation issues found."
    keys = (
        "id",
        "import_run_id",
        "raw_range_id",
        "raw_event_id",
        "severity",
        "issue_code",
        "field_name",
        "observed_value",
        "created_at_utc",
        "resolved_at_utc",
        "resolution_notes",
    )
    return format_rows(issues, keys)


def format_duplicates(candidates: list[dict[str, Any]], *, as_json: bool = False) -> str:
    if as_json:
        return deterministic_json({"duplicates": candidates})
    if not candidates:
        return "No duplicate candidates found."
    keys = (
        "id",
        "import_run_id",
        "candidate_type",
        "left_raw_range_id",
        "right_raw_range_id",
        "left_raw_event_id",
        "right_raw_event_id",
        "rule_code",
        "confidence",
        "reason",
        "created_at_utc",
        "review_status",
        "review_notes",
    )
    return format_rows(candidates, keys)


def format_rows(rows: list[dict[str, Any]], keys: tuple[str, ...]) -> str:
    lines = [" | ".join(keys)]
    for row in rows:
        lines.append(" | ".join(str(row[key] if row[key] is not None else "") for key in keys))
    return "\n".join(lines)
