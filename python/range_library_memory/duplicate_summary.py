"""Read-only duplicate candidate summaries."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .db import connect
from .inspection import deterministic_json, require_existing_db


def summarize_duplicates(
    db_path: str | Path,
    *,
    case_ref: str | None = None,
    rule_code: str | None = None,
    candidate_type: str | None = None,
    confidence: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    path = require_existing_db(db_path)
    filters = {
        "case_ref": case_ref,
        "rule_code": rule_code,
        "candidate_type": candidate_type,
        "confidence": confidence,
        "status": status,
    }
    clauses: list[str] = []
    params: list[Any] = []
    if rule_code:
        clauses.append("dc.rule_code = ?")
        params.append(rule_code)
    if candidate_type:
        clauses.append("dc.candidate_type = ?")
        params.append(candidate_type)
    if confidence:
        clauses.append("dc.confidence = ?")
        params.append(confidence)
    if status:
        clauses.append("dc.review_status = ?")
        params.append(status)
    if case_ref:
        clauses.append(
            """
            (
                left_range.raw_payload_json LIKE ?
                OR right_range.raw_payload_json LIKE ?
                OR left_event.raw_payload_json LIKE ?
                OR right_event.raw_payload_json LIKE ?
            )
            """
        )
        pattern = f'%"case_ref":"{case_ref}"%'
        params.extend([pattern, pattern, pattern, pattern])

    where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with connect(path) as connection:
        rows = connection.execute(
            f"""
            SELECT dc.rule_code,
                   dc.candidate_type,
                   dc.confidence,
                   dc.review_status AS status,
                   COUNT(*) AS count
            FROM duplicate_candidates dc
            LEFT JOIN raw_ranges left_range
              ON left_range.id = dc.left_raw_range_id
            LEFT JOIN raw_ranges right_range
              ON right_range.id = dc.right_raw_range_id
            LEFT JOIN raw_events left_event
              ON left_event.id = dc.left_raw_event_id
            LEFT JOIN raw_events right_event
              ON right_event.id = dc.right_raw_event_id
            {where_clause}
            GROUP BY dc.rule_code,
                     dc.candidate_type,
                     dc.confidence,
                     dc.review_status
            ORDER BY dc.rule_code ASC,
                     dc.candidate_type ASC,
                     dc.confidence ASC,
                     dc.review_status ASC
            """,
            tuple(params),
        ).fetchall()
    groups = [dict(row) for row in rows]
    return {
        "filters": filters,
        "total": sum(int(group["count"]) for group in groups),
        "groups": groups,
    }


def format_duplicate_summary(summary: dict[str, Any], *, as_json: bool = False) -> str:
    if as_json:
        return deterministic_json(summary)
    groups = summary["groups"]
    if not groups:
        return "No duplicate candidates found."
    keys = ("rule_code", "candidate_type", "confidence", "status", "count")
    lines = [" | ".join(keys)]
    for group in groups:
        lines.append(" | ".join(str(group[key] if group[key] is not None else "") for key in keys))
    return "\n".join(lines)
