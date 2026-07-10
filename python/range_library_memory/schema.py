"""Idempotent SQLite schema initialization for Range Library Memory v1."""

from __future__ import annotations

from pathlib import Path

from .db import connect

REQUIRED_TABLES = (
    "import_runs",
    "raw_ranges",
    "raw_events",
    "range_import_results",
    "validation_issues",
    "duplicate_candidates",
)


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS import_runs (
    id INTEGER PRIMARY KEY,
    run_uuid TEXT NOT NULL UNIQUE,
    source_path TEXT NOT NULL,
    source_sha256 TEXT,
    source_kind TEXT NOT NULL,
    started_at_utc TEXT NOT NULL,
    finished_at_utc TEXT,
    status TEXT NOT NULL,
    requested_by TEXT,
    tool_version TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS raw_ranges (
    id INTEGER PRIMARY KEY,
    import_run_id INTEGER NOT NULL REFERENCES import_runs(id),
    source_record_id TEXT,
    symbol TEXT,
    timeframe TEXT,
    range_type TEXT,
    start_time_utc TEXT,
    end_time_utc TEXT,
    high REAL,
    low REAL,
    raw_payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS raw_events (
    id INTEGER PRIMARY KEY,
    import_run_id INTEGER NOT NULL REFERENCES import_runs(id),
    raw_range_id INTEGER REFERENCES raw_ranges(id),
    source_record_id TEXT,
    event_type TEXT,
    event_time_utc TEXT,
    price REAL,
    raw_payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS range_import_results (
    id INTEGER PRIMARY KEY,
    import_run_id INTEGER NOT NULL UNIQUE REFERENCES import_runs(id),
    ranges_seen INTEGER NOT NULL DEFAULT 0,
    ranges_inserted INTEGER NOT NULL DEFAULT 0,
    ranges_reused INTEGER NOT NULL DEFAULT 0,
    events_seen INTEGER NOT NULL DEFAULT 0,
    events_inserted INTEGER NOT NULL DEFAULT 0,
    events_reused INTEGER NOT NULL DEFAULT 0,
    validation_issue_count INTEGER NOT NULL DEFAULT 0,
    duplicate_candidate_count INTEGER NOT NULL DEFAULT 0,
    summary_json TEXT,
    created_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS validation_issues (
    id INTEGER PRIMARY KEY,
    import_run_id INTEGER REFERENCES import_runs(id),
    raw_range_id INTEGER REFERENCES raw_ranges(id),
    raw_event_id INTEGER REFERENCES raw_events(id),
    severity TEXT NOT NULL,
    issue_code TEXT NOT NULL,
    message TEXT NOT NULL,
    field_name TEXT,
    observed_value TEXT,
    created_at_utc TEXT NOT NULL,
    resolved_at_utc TEXT,
    resolution_notes TEXT
);

CREATE TABLE IF NOT EXISTS duplicate_candidates (
    id INTEGER PRIMARY KEY,
    import_run_id INTEGER REFERENCES import_runs(id),
    candidate_type TEXT NOT NULL,
    left_raw_range_id INTEGER REFERENCES raw_ranges(id),
    right_raw_range_id INTEGER REFERENCES raw_ranges(id),
    left_raw_event_id INTEGER REFERENCES raw_events(id),
    right_raw_event_id INTEGER REFERENCES raw_events(id),
    rule_code TEXT NOT NULL,
    confidence TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    review_status TEXT NOT NULL DEFAULT 'open',
    review_notes TEXT
);
"""


def init_schema(db_path: str | Path) -> Path:
    """Create the Range Library Memory v1 schema if it does not exist."""
    path = Path(db_path)
    with connect(path, initialize=True) as connection:
        connection.executescript(SCHEMA_SQL)
    return path
