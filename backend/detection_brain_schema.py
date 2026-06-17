"""Phase 1 Detection Brain schema migrations.

Contract: docs/architecture/PHASE_0_DETECTION_BRAIN_CONTRACTS.md
PHASE_0_CONTRACTS_LOCKED = TRUE — do not violate without architecture revision.
"""

from __future__ import annotations

import sqlite3
from typing import Any

DETECTION_BRAIN_SCHEMA = "detection_brain_v0"
PHASE_0_CONTRACTS_LOCKED = True

DETECTOR_TABLES = (
    "detector_suggestions",
    "detector_corrections",
    "retracement_measurements",
    "mapping_sessions",
    "detector_version_registry",
)

DETECTOR_ANALYTICS_VIEWS = (
    "v_detector_correction_facts",
)


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(r[1]) for r in rows}


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> bool:
    existing = _table_columns(conn, table)
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        print(f"[detection_brain] added column {table}.{column}")
        return True
    return False


def _migrate_map_ranges_phase1(conn: sqlite3.Connection) -> None:
    """Add Phase 1 columns; backfill range_scale from legacy range_scope."""
    print("[detection_brain] map_ranges Phase 1 migration")
    columns = [
        ("range_scale", "TEXT NOT NULL DEFAULT 'MAJOR'"),
        ("range_role", "TEXT"),
        ("internal_structure_status", "TEXT DEFAULT 'UNKNOWN'"),
        ("confirmed_from_suggestion_id", "TEXT"),
        ("detector_version_at_confirm", "TEXT"),
        ("user_action_at_confirm", "TEXT"),
    ]
    for column, definition in columns:
        _ensure_column(conn, "map_ranges", column, definition)

    cols = _table_columns(conn, "map_ranges")
    if "range_scope" in cols and "range_scale" in cols:
        conn.execute(
            """
            UPDATE map_ranges
            SET range_scale = UPPER(TRIM(range_scope))
            WHERE range_scope IS NOT NULL
              AND TRIM(range_scope) != ''
              AND UPPER(TRIM(range_scope)) IN ('MAJOR', 'MINOR')
              AND (
                range_scale IS NULL
                OR TRIM(range_scale) = ''
                OR (UPPER(TRIM(range_scale)) = 'MAJOR' AND UPPER(TRIM(range_scope)) = 'MINOR')
              )
            """
        )
    conn.execute(
        """
        UPDATE map_ranges
        SET range_scale = 'MAJOR'
        WHERE range_scale IS NULL OR TRIM(range_scale) = ''
        """
    )
    conn.execute(
        """
        UPDATE map_ranges
        SET internal_structure_status = 'UNKNOWN'
        WHERE internal_structure_status IS NULL OR TRIM(internal_structure_status) = ''
        """
    )


def _migrate_map_events_phase1(conn: sqlite3.Connection) -> None:
    print("[detection_brain] map_events Phase 1 migration")
    columns = [
        ("confirmed_from_suggestion_id", "TEXT"),
        ("detector_version_at_confirm", "TEXT"),
    ]
    for column, definition in columns:
        _ensure_column(conn, "map_events", column, definition)
    # engine_source may already exist from v149 HTF semi-auto migration.
    _ensure_column(conn, "map_events", "engine_source", "TEXT")


def _create_detector_suggestions(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS detector_suggestions (
            suggestion_id           TEXT PRIMARY KEY,
            schema_version          TEXT NOT NULL DEFAULT 'detection_brain_v0',
            detector_version        TEXT NOT NULL,
            engine_source           TEXT NOT NULL,
            candidate_kind          TEXT NOT NULL,
            candidate_index         INTEGER NOT NULL DEFAULT 0,
            status                  TEXT NOT NULL DEFAULT 'PENDING',
            symbol                  TEXT NOT NULL,
            structure_layer         TEXT NOT NULL,
            source_timeframe        TEXT NOT NULL,
            chart_timeframe         TEXT NOT NULL,
            case_id                 INTEGER,
            case_ref                TEXT,
            raw_case_id             TEXT,
            parent_range_id         INTEGER,
            active_range_id         INTEGER,
            old_range_id            INTEGER,
            candle_time_utc_ms      INTEGER NOT NULL,
            candle_index            INTEGER,
            suggested_rh            REAL,
            suggested_rl            REAL,
            suggested_rh_time_ms    INTEGER,
            suggested_rl_time_ms    INTEGER,
            suggested_rh_price_int  INTEGER,
            suggested_rl_price_int  INTEGER,
            price_scale             INTEGER,
            range_scale             TEXT,
            range_role              TEXT,
            internal_structure_status TEXT,
            event_side              TEXT,
            event_price             REAL,
            event_price_int         INTEGER,
            break_rule              TEXT,
            movement_rule           TEXT,
            primitive               TEXT,
            derived_event_code      TEXT,
            confidence              TEXT NOT NULL DEFAULT 'MEDIUM',
            reason_text             TEXT NOT NULL DEFAULT '',
            meta_json               TEXT,
            user_action             TEXT,
            reviewed_at_utc_ms      INTEGER,
            reviewed_by             TEXT NOT NULL DEFAULT 'josh',
            promoted_range_id       INTEGER,
            promoted_event_id       INTEGER,
            promoted_raw_event_id   TEXT,
            session_id              TEXT,
            supersedes_suggestion_id TEXT,
            correction_id           TEXT,
            created_at_utc_ms       INTEGER NOT NULL,
            updated_at_utc_ms       INTEGER
        )
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_detector_suggestions_open_slot
        ON detector_suggestions (
            symbol,
            source_timeframe,
            structure_layer,
            COALESCE(parent_range_id, -1),
            candidate_kind,
            candidate_index
        )
        WHERE status = 'PENDING'
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_detector_suggestions_case_status "
        "ON detector_suggestions(case_ref, status, candidate_kind)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_detector_suggestions_session "
        "ON detector_suggestions(session_id, status)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_detector_suggestions_candle "
        "ON detector_suggestions(symbol, source_timeframe, candle_time_utc_ms)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_detector_suggestions_active_range "
        "ON detector_suggestions(active_range_id, status)"
    )


def _create_detector_corrections(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS detector_corrections (
            correction_id           TEXT PRIMARY KEY,
            schema_version          TEXT NOT NULL DEFAULT 'detection_brain_v0',
            suggestion_id           TEXT NOT NULL,
            session_id              TEXT,
            candidate_kind          TEXT NOT NULL,
            detector_version        TEXT NOT NULL,
            symbol                  TEXT NOT NULL,
            structure_layer         TEXT NOT NULL,
            source_timeframe        TEXT NOT NULL,
            user_action             TEXT NOT NULL,
            error_category          TEXT NOT NULL,
            notes                   TEXT NOT NULL DEFAULT '',
            suggested_snapshot_json TEXT NOT NULL,
            final_snapshot_json     TEXT,
            promoted_range_id       INTEGER,
            promoted_event_id       INTEGER,
            promoted_raw_event_id   TEXT,
            created_at_utc_ms       INTEGER NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_detector_corrections_suggestion "
        "ON detector_corrections(suggestion_id, created_at_utc_ms)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_detector_corrections_session "
        "ON detector_corrections(session_id, created_at_utc_ms)"
    )


def _create_retracement_measurements(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS retracement_measurements (
            measurement_id            TEXT PRIMARY KEY,
            schema_version            TEXT NOT NULL DEFAULT 'detection_brain_v0',
            detector_version          TEXT NOT NULL,
            measurement_status        TEXT NOT NULL DEFAULT 'SUGGESTED',
            case_ref                  TEXT,
            case_id                   INTEGER,
            old_range_id              INTEGER NOT NULL,
            new_range_id              INTEGER NOT NULL,
            bos_event_id              INTEGER NOT NULL,
            suggestion_id             TEXT,
            session_id                TEXT,
            symbol                    TEXT NOT NULL,
            structure_layer           TEXT NOT NULL,
            source_timeframe          TEXT NOT NULL,
            bos_direction             TEXT NOT NULL,
            retracement_direction     TEXT NOT NULL,
            old_range_boundary_touched TEXT NOT NULL,
            retrace_start_time_ms     INTEGER NOT NULL,
            retrace_end_time_ms       INTEGER,
            retrace_high              REAL,
            retrace_low               REAL,
            deepest_retrace_price     REAL,
            max_retrace_percent       REAL,
            retrace_depth_percent     REAL,
            respected_level           REAL,
            breached_618              INTEGER NOT NULL DEFAULT 0,
            breached_70               INTEGER NOT NULL DEFAULT 0,
            breached_75               INTEGER NOT NULL DEFAULT 0,
            profile_classification    TEXT,
            meta_json                 TEXT,
            user_action               TEXT,
            reviewed_at_utc_ms        INTEGER,
            created_at_utc_ms         INTEGER NOT NULL,
            updated_at_utc_ms         INTEGER
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_retracement_measurements_ranges "
        "ON retracement_measurements(old_range_id, new_range_id, measurement_status)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_retracement_measurements_case "
        "ON retracement_measurements(case_ref, source_timeframe)"
    )


def _create_mapping_sessions(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS mapping_sessions (
            session_id                TEXT PRIMARY KEY,
            schema_version            TEXT NOT NULL DEFAULT 'detection_brain_v0',
            symbol                    TEXT NOT NULL,
            case_id                   INTEGER,
            case_ref                  TEXT,
            raw_case_id               TEXT,
            structure_layer           TEXT NOT NULL,
            source_timeframe          TEXT NOT NULL,
            chart_timeframe           TEXT NOT NULL,
            replay_candle_time_utc_ms INTEGER,
            replay_candle_index       INTEGER,
            current_parent_range_id   INTEGER,
            current_active_range_id   INTEGER,
            current_old_range_id      INTEGER,
            workflow_mode             TEXT NOT NULL DEFAULT 'GUIDED',
            autopilot_step            TEXT,
            target_range_scale        TEXT NOT NULL DEFAULT 'MAJOR',
            internal_structure_status TEXT,
            path_outcome              TEXT,
            active_suggestion_id      TEXT,
            active_candidate_kind     TEXT,
            detector_versions_json    TEXT NOT NULL DEFAULT '{}',
            state_json                TEXT,
            status                    TEXT NOT NULL DEFAULT 'ACTIVE',
            created_at_utc_ms         INTEGER NOT NULL,
            updated_at_utc_ms         INTEGER,
            last_resumed_at_utc_ms    INTEGER
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_mapping_sessions_lookup "
        "ON mapping_sessions(symbol, case_ref, structure_layer, status)"
    )


def _create_detector_version_registry(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS detector_version_registry (
            detector_version    TEXT PRIMARY KEY,
            domain              TEXT NOT NULL,
            major_number        INTEGER NOT NULL,
            release_notes       TEXT NOT NULL DEFAULT '',
            rule_summary_json   TEXT,
            supersedes_version  TEXT,
            created_at_utc_ms   INTEGER NOT NULL
        )
        """
    )


def _create_detector_analytics_views(conn: sqlite3.Connection) -> None:
    """Phase 3.5 reporting views — derived from detector_corrections only."""
    conn.execute(
        """
        CREATE VIEW IF NOT EXISTS v_detector_correction_facts AS
        SELECT
            c.correction_id,
            c.suggestion_id,
            c.candidate_kind,
            c.detector_version,
            c.symbol,
            c.structure_layer,
            c.source_timeframe,
            c.user_action,
            c.error_category,
            c.created_at_utc_ms,
            UPPER(COALESCE(
                NULLIF(TRIM(json_extract(c.suggested_snapshot_json, '$.range_scale')), ''),
                NULLIF(TRIM(json_extract(c.final_snapshot_json, '$.range_scale')), ''),
                'UNKNOWN'
            )) AS range_scale
        FROM detector_corrections c
        WHERE c.user_action IN ('APPROVE', 'EDIT', 'REJECT')
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_detector_corrections_version_action "
        "ON detector_corrections(detector_version, user_action)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_detector_corrections_kind_tf "
        "ON detector_corrections(candidate_kind, source_timeframe)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_detector_corrections_error "
        "ON detector_corrections(error_category, detector_version)"
    )


def init_detection_brain_schema(conn: sqlite3.Connection) -> None:
    """Idempotent Phase 1 schema setup. Safe on existing databases."""
    print(f"[detection_brain] init schema {DETECTION_BRAIN_SCHEMA}")
    _migrate_map_ranges_phase1(conn)
    _migrate_map_events_phase1(conn)
    _create_detector_suggestions(conn)
    _create_detector_corrections(conn)
    _create_retracement_measurements(conn)
    _create_mapping_sessions(conn)
    _create_detector_version_registry(conn)
    _create_detector_analytics_views(conn)


def detection_brain_schema_status(conn: sqlite3.Connection) -> dict[str, Any]:
    """Smoke-check helper: table presence, row counts, key columns."""
    status: dict[str, Any] = {
        "ok": True,
        "schema_version": DETECTION_BRAIN_SCHEMA,
        "phase_0_contracts_locked": PHASE_0_CONTRACTS_LOCKED,
        "tables": {},
        "map_ranges_columns": sorted(_table_columns(conn, "map_ranges")) if _table_columns(conn, "map_ranges") else [],
        "map_events_columns": sorted(_table_columns(conn, "map_events")) if _table_columns(conn, "map_events") else [],
    }
    required_map_range_cols = {
        "range_scale",
        "range_role",
        "internal_structure_status",
        "confirmed_from_suggestion_id",
        "detector_version_at_confirm",
        "user_action_at_confirm",
    }
    required_map_event_cols = {
        "confirmed_from_suggestion_id",
        "detector_version_at_confirm",
        "engine_source",
    }
    map_range_cols = set(status["map_ranges_columns"])
    map_event_cols = set(status["map_events_columns"])
    status["map_ranges_phase1_ready"] = required_map_range_cols.issubset(map_range_cols)
    status["map_events_phase1_ready"] = required_map_event_cols.issubset(map_event_cols)

    for table in DETECTOR_TABLES:
        try:
            count = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
            status["tables"][table] = {"exists": True, "count": int(count)}
        except sqlite3.OperationalError:
            status["tables"][table] = {"exists": False, "count": 0}
            status["ok"] = False

    if not status["map_ranges_phase1_ready"] or not status["map_events_phase1_ready"]:
        status["ok"] = False

    status["analytics_views"] = {}
    for view in DETECTOR_ANALYTICS_VIEWS:
        try:
            conn.execute(f"SELECT 1 FROM {view} LIMIT 1")
            status["analytics_views"][view] = True
        except sqlite3.OperationalError:
            status["analytics_views"][view] = False
            status["ok"] = False
    return status
