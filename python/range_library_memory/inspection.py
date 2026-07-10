"""Read-only inspection helpers for Range Library Memory."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .db import connect


class InspectionError(RuntimeError):
    """Raised when inspection cannot safely read the requested database."""


def list_runs(db_path: str | Path, *, limit: int) -> list[dict[str, Any]]:
    path = require_existing_db(db_path)
    with connect(path) as connection:
        rows = connection.execute(
            """
            SELECT import_runs.id,
                   import_runs.run_uuid,
                   import_runs.source_path,
                   import_runs.source_kind,
                   import_runs.status,
                   import_runs.started_at_utc,
                   import_runs.finished_at_utc,
                   COALESCE(range_import_results.ranges_seen, 0) AS ranges_seen,
                   COALESCE(range_import_results.ranges_inserted, 0) AS ranges_inserted,
                   COALESCE(range_import_results.ranges_reused, 0) AS ranges_reused,
                   COALESCE(range_import_results.events_seen, 0) AS events_seen,
                   COALESCE(range_import_results.events_inserted, 0) AS events_inserted,
                   COALESCE(range_import_results.events_reused, 0) AS events_reused,
                   COALESCE(range_import_results.validation_issue_count, 0) AS validation_issue_count,
                   COALESCE(range_import_results.duplicate_candidate_count, 0) AS duplicate_candidate_count
            FROM import_runs
            LEFT JOIN range_import_results
              ON range_import_results.import_run_id = import_runs.id
            ORDER BY import_runs.started_at_utc DESC, import_runs.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def show_run(db_path: str | Path, *, import_run_id: int) -> dict[str, Any]:
    path = require_existing_db(db_path)
    with connect(path) as connection:
        run = connection.execute(
            "SELECT * FROM import_runs WHERE id = ?",
            (import_run_id,),
        ).fetchone()
        if run is None:
            raise InspectionError(f"Import run not found: {import_run_id}")

        results = connection.execute(
            "SELECT * FROM range_import_results WHERE import_run_id = ?",
            (import_run_id,),
        ).fetchone()
        validation_issues = connection.execute(
            """
            SELECT issue_code, severity, COUNT(*) AS count
            FROM validation_issues
            WHERE import_run_id = ?
            GROUP BY issue_code, severity
            ORDER BY issue_code, severity
            """,
            (import_run_id,),
        ).fetchall()
        duplicate_candidates = connection.execute(
            """
            SELECT rule_code, candidate_type, confidence, COUNT(*) AS count
            FROM duplicate_candidates
            WHERE import_run_id = ?
            GROUP BY rule_code, candidate_type, confidence
            ORDER BY rule_code, candidate_type, confidence
            """,
            (import_run_id,),
        ).fetchall()

    return {
        "import_run": dict(run),
        "range_import_results": dict(results) if results else None,
        "validation_issues_by_code": [dict(row) for row in validation_issues],
        "duplicate_candidates_by_rule": [dict(row) for row in duplicate_candidates],
    }


def format_list_runs(runs: list[dict[str, Any]], *, as_json: bool = False) -> str:
    if as_json:
        return deterministic_json({"runs": runs})
    if not runs:
        return "No import runs found."
    lines = [
        "id | run_uuid | source_path | source_kind | status | started_at_utc | finished_at_utc | "
        "ranges_seen | ranges_inserted | ranges_reused | events_seen | events_inserted | events_reused | "
        "validation_issue_count | duplicate_candidate_count"
    ]
    for run in runs:
        lines.append(
            " | ".join(
                str(run[key] if run[key] is not None else "")
                for key in (
                    "id",
                    "run_uuid",
                    "source_path",
                    "source_kind",
                    "status",
                    "started_at_utc",
                    "finished_at_utc",
                    "ranges_seen",
                    "ranges_inserted",
                    "ranges_reused",
                    "events_seen",
                    "events_inserted",
                    "events_reused",
                    "validation_issue_count",
                    "duplicate_candidate_count",
                )
            )
        )
    return "\n".join(lines)


def format_show_run(details: dict[str, Any], *, as_json: bool = False) -> str:
    if as_json:
        return deterministic_json(details)

    run = details["import_run"]
    results = details["range_import_results"] or {}
    lines = [
        "Import Run",
        f"id: {run['id']}",
        f"run_uuid: {run['run_uuid']}",
        f"source_path: {run['source_path']}",
        f"source_kind: {run['source_kind']}",
        f"status: {run['status']}",
        f"started_at_utc: {run['started_at_utc']}",
        f"finished_at_utc: {run['finished_at_utc'] or ''}",
        "",
        "Range Import Results",
    ]
    for key in (
        "ranges_seen",
        "ranges_inserted",
        "ranges_reused",
        "events_seen",
        "events_inserted",
        "events_reused",
        "validation_issue_count",
        "duplicate_candidate_count",
    ):
        lines.append(f"{key}: {results.get(key, 0)}")

    lines.extend(["", "Validation Issues"])
    if details["validation_issues_by_code"]:
        for row in details["validation_issues_by_code"]:
            lines.append(f"{row['issue_code']} ({row['severity']}): {row['count']}")
    else:
        lines.append("none")

    lines.extend(["", "Duplicate Candidates"])
    if details["duplicate_candidates_by_rule"]:
        for row in details["duplicate_candidates_by_rule"]:
            lines.append(f"{row['rule_code']} ({row['candidate_type']}, {row['confidence']}): {row['count']}")
    else:
        lines.append("none")

    return "\n".join(lines)


def require_existing_db(db_path: str | Path) -> Path:
    path = Path(db_path)
    if not path.is_file():
        raise InspectionError(f"Database does not exist: {path}")
    return path


def deterministic_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))
