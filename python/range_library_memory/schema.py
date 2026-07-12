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
    "parent_child_relationships",
    "event_ohlc_evidence",
    "resolved_range_lifecycles",
    "weekly_break_reclaim_lifecycles",
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

CREATE TABLE IF NOT EXISTS parent_child_relationships (
    id INTEGER PRIMARY KEY,
    import_run_id INTEGER REFERENCES import_runs(id),
    case_ref TEXT,
    symbol TEXT,
    relationship_type TEXT NOT NULL,
    parent_range_id TEXT,
    child_range_id TEXT,
    parent_layer TEXT,
    child_layer TEXT,
    parent_timeframe TEXT,
    child_timeframe TEXT,
    link_source TEXT NOT NULL,
    link_status TEXT NOT NULL,
    link_confidence TEXT NOT NULL,
    review_status TEXT NOT NULL DEFAULT 'open',
    child_position_in_parent TEXT NOT NULL,
    child_boundary_interaction TEXT NOT NULL,
    child_lifecycle_relationship TEXT NOT NULL,
    notes TEXT,
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS event_ohlc_evidence (
    id INTEGER PRIMARY KEY,
    built_at_utc TEXT NOT NULL,
    import_run_id INTEGER,
    case_ref TEXT,
    symbol TEXT NOT NULL,
    structure_layer TEXT NOT NULL,
    source_timeframe TEXT NOT NULL,
    range_source_id TEXT NOT NULL,
    event_source_id TEXT,
    raw_range_id INTEGER,
    raw_event_id INTEGER,
    event_type TEXT NOT NULL,
    direction TEXT NOT NULL,
    range_active_from_time TEXT,
    range_formation_time TEXT NOT NULL,
    boundary_type TEXT NOT NULL,
    boundary_price REAL NOT NULL,
    boundary_anchor_time TEXT NOT NULL,
    mapped_event_time TEXT,
    mapped_event_price REAL,
    mapped_break_level_price REAL,
    source_event_candle_time TEXT,
    source_event_open REAL,
    source_event_high REAL,
    source_event_low REAL,
    source_event_close REAL,
    first_boundary_contact_time TEXT,
    first_wick_breach_time TEXT,
    first_wick_breach_price REAL,
    first_close_breach_time TEXT,
    first_close_breach_price REAL,
    candles_to_wick_breach INTEGER,
    candles_to_close_breach INTEGER,
    mapped_new_range_id TEXT,
    transition_status TEXT NOT NULL,
    transition_reason_codes_json TEXT NOT NULL,
    evidence_status TEXT NOT NULL,
    reason_codes_json TEXT NOT NULL,
    resolution_status TEXT NOT NULL,
    resolution_confidence TEXT NOT NULL,
    effective_break_time TEXT,
    effective_break_kind TEXT,
    as_of_time TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_event_ohlc_evidence_range_source_id
    ON event_ohlc_evidence(range_source_id);
CREATE INDEX IF NOT EXISTS idx_event_ohlc_evidence_event_source_id
    ON event_ohlc_evidence(event_source_id);
CREATE INDEX IF NOT EXISTS idx_event_ohlc_evidence_scope
    ON event_ohlc_evidence(case_ref, symbol, structure_layer, source_timeframe);

CREATE TABLE IF NOT EXISTS resolved_range_lifecycles (
    id INTEGER PRIMARY KEY,
    built_at_utc TEXT NOT NULL,
    import_run_id INTEGER,
    case_ref TEXT,
    symbol TEXT NOT NULL,
    structure_layer TEXT NOT NULL,
    source_timeframe TEXT NOT NULL,
    range_source_id TEXT NOT NULL,
    raw_range_id INTEGER,
    raw_status TEXT,
    raw_active_from_time TEXT,
    raw_inactive_from_time TEXT,
    raw_broken_by_event_id TEXT,
    effective_status TEXT NOT NULL,
    effective_active_from_time TEXT NOT NULL,
    effective_inactive_from_time TEXT,
    resolution_source TEXT NOT NULL,
    resolution_status TEXT NOT NULL,
    resolution_confidence TEXT NOT NULL,
    supporting_event_source_id TEXT,
    supporting_evidence_id INTEGER,
    reason_codes_json TEXT NOT NULL,
    as_of_time TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_resolved_range_lifecycles_range_source_id
    ON resolved_range_lifecycles(range_source_id);
CREATE INDEX IF NOT EXISTS idx_resolved_range_lifecycles_scope
    ON resolved_range_lifecycles(case_ref, symbol, structure_layer, source_timeframe);

CREATE TABLE IF NOT EXISTS weekly_break_reclaim_lifecycles (
    id INTEGER PRIMARY KEY,
    built_at_utc TEXT NOT NULL,
    import_run_id INTEGER,
    case_ref TEXT,
    symbol TEXT NOT NULL,
    source_timeframe TEXT NOT NULL,
    weekly_range_source_id TEXT NOT NULL UNIQUE,
    raw_range_id INTEGER,
    range_high REAL,
    range_low REAL,
    range_height REAL,
    break_direction TEXT,
    break_level REAL,
    break_time TEXT,
    break_kind TEXT,
    supporting_event_source_id TEXT,
    supporting_evidence_id INTEGER,
    abandoned_from_time TEXT,
    first_wick_reclaim_time TEXT,
    first_wick_reclaim_price REAL,
    first_close_reclaim_time TEXT,
    first_close_reclaim_price REAL,
    effective_reclaim_time TEXT,
    effective_reclaim_kind TEXT,
    same_candle_close_reclaim INTEGER NOT NULL DEFAULT 0,
    same_candle_wick_order_status TEXT,
    reclaim_depth_price REAL,
    reclaim_depth_percent_of_range REAL,
    candles_to_wick_reclaim INTEGER,
    candles_to_close_reclaim INTEGER,
    candles_to_effective_reclaim INTEGER,
    calendar_days_to_effective_reclaim REAL,
    candles_pending_as_of INTEGER,
    calendar_days_pending_as_of REAL,
    current_state TEXT NOT NULL,
    observation_status TEXT NOT NULL,
    resolution_status TEXT NOT NULL,
    resolution_confidence TEXT NOT NULL,
    reason_codes_json TEXT NOT NULL,
    as_of_time TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_weekly_break_reclaim_source_id
    ON weekly_break_reclaim_lifecycles(weekly_range_source_id);
CREATE INDEX IF NOT EXISTS idx_weekly_break_reclaim_scope
    ON weekly_break_reclaim_lifecycles(case_ref, symbol);
CREATE INDEX IF NOT EXISTS idx_weekly_break_reclaim_state
    ON weekly_break_reclaim_lifecycles(current_state);
CREATE INDEX IF NOT EXISTS idx_weekly_break_reclaim_break_time
    ON weekly_break_reclaim_lifecycles(break_time);
CREATE INDEX IF NOT EXISTS idx_weekly_break_reclaim_reclaim_time
    ON weekly_break_reclaim_lifecycles(effective_reclaim_time);
"""


def init_schema(db_path: str | Path) -> Path:
    """Create the Range Library Memory v1 schema if it does not exist."""
    path = Path(db_path)
    with connect(path, initialize=True) as connection:
        connection.executescript(SCHEMA_SQL)
    return path
