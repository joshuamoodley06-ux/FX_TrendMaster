from __future__ import annotations

import csv
import json
import hashlib
import uuid
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def _resolve_db_path() -> Path:
    """Resolve the SQLite file used by the VPS backend.

    Priority:
      1. DATABASE_PATH env var
      2. RAW_MAPPING_DB_PATH env var
      3. MARKET_MEMORY_DB_PATH env var
      4. ./data/raw_mapping_v159.db beside this backend file

    Relative env paths are resolved from the backend folder so systemd/pm2 cwd changes
    do not silently create a database somewhere stupid. Because naturally that would
    happen at 01:00 before a test run.
    """
    backend_dir = Path(__file__).resolve().parent
    raw = (
        os.environ.get("DATABASE_PATH")
        or os.environ.get("RAW_MAPPING_DB_PATH")
        or os.environ.get("MARKET_MEMORY_DB_PATH")
    )
    if raw:
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = backend_dir / path
        return path
    return backend_dir / "data" / "raw_mapping_v159.db"


DB_PATH = _resolve_db_path()
def _default_common_files_path() -> Path:
    r"""Return MT5 Common\Files path for the current Windows user, with env override."""
    override = os.environ.get("MT5_COMMON_FILES_PATH")
    if override:
        return Path(override)
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "MetaQuotes" / "Terminal" / "Common" / "Files"
    # Linux/container fallback for tests. Windows user should use APPDATA or env override.
    return Path.home() / "AppData" / "Roaming" / "MetaQuotes" / "Terminal" / "Common" / "Files"

COMMON_FILES_PATH = _default_common_files_path()
MARKET_MEMORY_DIR = COMMON_FILES_PATH / "market_memory"

TIMEFRAMES = {"MN1", "W1", "D1", "H4", "H1", "M15", "M5"}

MOS_LIFECYCLE_STATES = {"REVERSAL_DEVELOPMENT", "EXPANSION", "MITIGATION", "OBJECTIVE_COMPLETION"}
MOS_PHASE_PARTS = {"RETEST", "RECLAIM", "IMPULSE", "BOS", "FAIL"}
MOS_PARENT_CONTEXT_MODES = {
    "WEEKLY_ACTIVE_PARENT",
    "WEEKLY_ABANDONED_DAILY_IN_MOTION",
    "WEEKLY_FORMING_NO_DAILY_RANGE",
    "DAILY_ACTIVE_ORPHAN",
    "DAILY_ADOPTED_BY_NEW_WEEKLY",
}
MOS_DAILY_RANGE_STATUSES = {
    "NO_ACTIVE_DAILY_RANGE",
    "DAILY_RANGE_FORMING",
    "DAILY_RANGE_ACTIVE",
    "DAILY_RANGE_RETESTING",
    "DAILY_RANGE_ABANDONED",
}
MOS_PROFILE_TYPES = {
    "DEEP_RECLAIM_SD_PROFILE",
    "SHALLOW_RECLAIM_SR_PROFILE",
    "NO_RECLAIM_CONTINUATION_PROFILE",
    "FAILED_RECLAIM_ABANDONED_RANGE",
}
MOS_ZONES = {
    "UNMAPPED_EXPANSION",
    "WEEKLY_EXTREME_DISCOUNT",
    "WEEKLY_EXTREME_PREMIUM",
    "WEEKLY_EXTERNAL_HIGH",
    "WEEKLY_EXTERNAL_LOW",
    "DAILY_DISCOUNT",
    "DAILY_PREMIUM",
    "DAILY_FAIR_PRICE",
}
MOS_OBJECTIVE_SEEDS = [
    ("WEEKLY_PREMIUM", "Weekly Premium", "WEEKLY", None),
    ("WEEKLY_FAIR_PRICE", "Weekly Fair Price", "WEEKLY", None),
    ("WEEKLY_DISCOUNT", "Weekly Discount", "WEEKLY", None),
    ("WEEKLY_EXTERNAL_HIGH", "Weekly External High", "WEEKLY", None),
    ("WEEKLY_EXTERNAL_LOW", "Weekly External Low", "WEEKLY", None),
    ("WEEKLY_EXTREME_PREMIUM", "Weekly Extreme Premium", "WEEKLY", None),
    ("WEEKLY_EXTREME_DISCOUNT", "Weekly Extreme Discount", "WEEKLY", None),
    ("DAILY_PREMIUM", "Daily Premium", "DAILY", None),
    ("DAILY_FAIR_PRICE", "Daily Fair Price", "DAILY", None),
    ("DAILY_DISCOUNT", "Daily Discount", "DAILY", None),
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str, *, log_existing: bool = False) -> None:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    existing = {str(r[1]) for r in rows}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        print(f"[schema] added column {table}.{column} {definition}")
    elif log_existing:
        print(f"[schema] existing column {table}.{column}")


def _ensure_columns(conn: sqlite3.Connection, table: str, columns: list[tuple[str, str]], label: str) -> None:
    print(f"[schema] {label}: checking {table}")
    for column, definition in columns:
        _ensure_column(conn, table, column, definition, log_existing=True)


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS candles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                time TEXT NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume REAL DEFAULT 0,
                source TEXT DEFAULT 'unknown',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(symbol, timeframe, time)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_candles_lookup ON candles(symbol, timeframe, time)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS map_ranges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                name TEXT,
                range_high REAL NOT NULL,
                range_low REAL NOT NULL,
                bias TEXT,
                destination TEXT,
                status TEXT DEFAULT 'active',
                parent_range_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS map_points (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                range_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                time TEXT,
                price REAL NOT NULL,
                zone_percent REAL,
                zone TEXT,
                label TEXT,
                point_type TEXT DEFAULT 'manual',
                source TEXT DEFAULT 'manual',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS map_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                range_id INTEGER,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                event_type TEXT NOT NULL,
                event_name TEXT,
                time TEXT,
                price REAL NOT NULL,
                zone_percent REAL,
                zone TEXT,
                notes TEXT,
                source TEXT DEFAULT 'manual',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS route_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                range_id INTEGER,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                route_label TEXT,
                route_points_json TEXT,
                outcome TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        # V139 market memory persistence upgrades. SQLite has no elegant IF NOT EXISTS for columns,
        # so we do the boring migration dance. Humanity endures.
        _ensure_column(conn, "map_ranges", "range_key", "TEXT DEFAULT 'active'")
        _ensure_column(conn, "map_ranges", "range_high_time", "TEXT")
        _ensure_column(conn, "map_ranges", "range_low_time", "TEXT")
        _ensure_column(conn, "map_ranges", "ref_high_price", "REAL")
        _ensure_column(conn, "map_ranges", "ref_high_time", "TEXT")
        _ensure_column(conn, "map_ranges", "ref_low_price", "REAL")
        _ensure_column(conn, "map_ranges", "ref_low_time", "TEXT")
        _ensure_column(conn, "map_ranges", "notes", "TEXT")
        _ensure_column(conn, "map_events", "client_event_id", "TEXT")
        _ensure_column(conn, "map_events", "candle_open", "REAL")
        _ensure_column(conn, "map_events", "candle_high", "REAL")
        _ensure_column(conn, "map_events", "candle_low", "REAL")
        _ensure_column(conn, "map_events", "candle_close", "REAL")
        # v149 HTF semi-auto state engine metadata.
        _ensure_column(conn, "map_events", "primitive", "TEXT")
        _ensure_column(conn, "map_events", "derived_event_code", "TEXT")
        _ensure_column(conn, "map_events", "movement_rule", "TEXT")
        _ensure_column(conn, "map_events", "range_status_after", "TEXT")
        _ensure_column(conn, "map_events", "engine_source", "TEXT")
        _ensure_column(conn, "map_events", "logic_version", "TEXT")
        _ensure_column(conn, "map_events", "candidate_id", "TEXT")
        _ensure_column(conn, "map_events", "confidence", "TEXT")
        _ensure_column(conn, "map_events", "meta_json", "TEXT")
        # v151: explicit case link for HTF candidate/event audit. UI counters are cute, SQL needs receipts.
        _ensure_column(conn, "map_events", "case_id", "INTEGER")
        _ensure_column(conn, "map_events", "candidate_status", "TEXT")
        _ensure_column(conn, "map_ranges", "range_start_time", "TEXT")
        _ensure_column(conn, "map_ranges", "range_end_time", "TEXT")
        _ensure_column(conn, "map_ranges", "active_candle_count", "INTEGER")
        _ensure_column(conn, "map_ranges", "current_high_price", "REAL")
        _ensure_column(conn, "map_ranges", "current_high_time", "TEXT")
        _ensure_column(conn, "map_ranges", "current_low_price", "REAL")
        _ensure_column(conn, "map_ranges", "current_low_time", "TEXT")
        _ensure_column(conn, "map_ranges", "last_transition", "TEXT")
        _ensure_column(conn, "map_ranges", "next_watch", "TEXT")
        _ensure_column(conn, "map_ranges", "state_json", "TEXT")
        # v153: universal structural range schema for HTF + Daily/LTF mapping.
        # Store physical range movement. Analytics derives sweeps, phases, OBs and objectives later.
        _ensure_column(conn, "map_ranges", "case_id", "INTEGER")
        _ensure_column(conn, "map_ranges", "source", "TEXT DEFAULT 'electron'")
        _ensure_column(conn, "map_ranges", "layer", "TEXT")
        _ensure_column(conn, "map_ranges", "parent_timeframe", "TEXT")
        _ensure_column(conn, "map_ranges", "parent_case_id", "INTEGER")
        _ensure_column(conn, "map_ranges", "created_by_event_id", "INTEGER")
        _ensure_column(conn, "map_ranges", "broken_by_event_id", "INTEGER")
        _ensure_column(conn, "map_ranges", "direction_of_break", "TEXT")
        _ensure_column(conn, "map_ranges", "active_from_time", "TEXT")
        _ensure_column(conn, "map_ranges", "inactive_from_time", "TEXT")
        _ensure_column(conn, "map_ranges", "old_range_id", "INTEGER")
        _ensure_column(conn, "map_ranges", "new_range_id", "INTEGER")
        _ensure_column(conn, "map_ranges", "structure_version", "TEXT DEFAULT 'STRUCTURE_ONLY_V1'")
        _ensure_column(conn, "map_ranges", "meta_json", "TEXT")
        _ensure_column(conn, "map_events", "parent_range_id", "INTEGER")
        _ensure_column(conn, "map_events", "active_range_id", "INTEGER")
        _ensure_column(conn, "map_events", "old_range_id", "INTEGER")
        _ensure_column(conn, "map_events", "new_range_id", "INTEGER")
        _ensure_column(conn, "map_events", "layer", "TEXT")
        _ensure_column(conn, "map_events", "parent_timeframe", "TEXT")
        _ensure_column(conn, "map_events", "structural_event", "TEXT")
        # v158: ML-ready structure ledger fields. Chronology is explicit; same-bar order is not guessed.
        _ensure_column(conn, "map_events", "case_event_index", "INTEGER")
        _ensure_column(conn, "map_events", "bar_sequence_mode", "TEXT")
        _ensure_column(conn, "map_events", "sequence_source", "TEXT")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS event_features (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL UNIQUE,
                case_id INTEGER,
                range_id INTEGER,
                parent_range_id INTEGER,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                event_type TEXT NOT NULL,
                event_time TEXT,
                close_pct REAL,
                high_pct REAL,
                low_pct REAL,
                zone_percent REAL,
                range_width REAL,
                candle_count INTEGER,
                feature_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        # Phase 1 hierarchy-ready schema only. This is intentionally add-only:
        # no data rewrites, no hard FK constraints, and parent_range_id stays nullable.
        _ensure_columns(conn, "map_ranges", [
            ("case_id", "INTEGER"),
            ("raw_case_id", "TEXT"),
            ("case_ref", "TEXT"),
            ("symbol", "TEXT"),
            ("structure_layer", "TEXT"),
            ("chart_timeframe", "TEXT"),
            ("source_timeframe", "TEXT"),
            ("parent_range_id", "INTEGER"),
            ("parent_timeframe", "TEXT"),
            ("parent_case_id", "INTEGER"),
            ("range_high_price", "REAL"),
            ("range_low_price", "REAL"),
            ("range_high_time", "TEXT"),
            ("range_low_time", "TEXT"),
            ("break_high_price", "REAL"),
            ("break_low_price", "REAL"),
            ("break_high_time", "TEXT"),
            ("break_low_time", "TEXT"),
            ("range_start_time", "TEXT"),
            ("range_end_time", "TEXT"),
            ("duration_minutes", "INTEGER"),
            ("status", "TEXT"),
            ("direction_of_break", "TEXT"),
            ("active_from_time", "TEXT"),
            ("inactive_from_time", "TEXT"),
            ("old_range_id", "INTEGER"),
            ("new_range_id", "INTEGER"),
            ("created_by_event_id", "INTEGER"),
            ("broken_by_event_id", "INTEGER"),
            ("structure_version", "TEXT"),
            ("parent_link_status", "TEXT DEFAULT 'NEEDS_REVIEW'"),
            ("meta_json", "TEXT"),
            ("updated_at", "TEXT"),
        ], "Phase 1 range hierarchy migration")
        _ensure_columns(conn, "map_events", [
            ("event_id", "TEXT"),
            ("case_id", "INTEGER"),
            ("raw_case_id", "TEXT"),
            ("case_ref", "TEXT"),
            ("symbol", "TEXT"),
            ("structure_layer", "TEXT"),
            ("chart_timeframe", "TEXT"),
            ("source_timeframe", "TEXT"),
            ("active_range_id", "INTEGER"),
            ("parent_range_id", "INTEGER"),
            ("old_range_id", "INTEGER"),
            ("new_range_id", "INTEGER"),
            ("event_type", "TEXT"),
            ("structural_event", "TEXT"),
            ("break_level_type", "TEXT"),
            ("break_level_price", "REAL"),
            ("break_level_time", "TEXT"),
            ("event_time", "TEXT"),
            ("event_price", "REAL"),
            ("candle_time", "TEXT"),
            ("candle_open", "REAL"),
            ("candle_high", "REAL"),
            ("candle_low", "REAL"),
            ("candle_close", "REAL"),
            ("direction", "TEXT"),
            ("calculation_engine_version", "TEXT"),
            ("ruleset_version", "TEXT"),
            ("meta_json", "TEXT"),
            ("updated_at", "TEXT"),
        ], "Phase 1 event hierarchy migration")
        _ensure_columns(conn, "event_features", [
            ("calculation_engine_version", "TEXT"),
            ("ruleset_version", "TEXT"),
            ("analysis_type", "TEXT"),
            ("created_at", "TEXT"),
            ("result_json", "TEXT"),
            ("meta_json", "TEXT"),
        ], "Phase 1 analytics versioning migration")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_event_features_case_tf ON event_features(case_id,symbol,timeframe,event_time)")
        # v159: raw mapping ledger. This is the append-only evidence locker.
        # Mapping writes go here only; parent/range/features are compiled later by the local processor.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS raw_mapping_cases (
                case_id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                case_name TEXT NOT NULL,
                base_timeframe TEXT NOT NULL,
                price_scale_default INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                notes TEXT NOT NULL DEFAULT '',
                schema_version TEXT NOT NULL DEFAULT 'raw_mapping_v1',
                created_at_utc_ms INTEGER NOT NULL,
                updated_at_utc_ms INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS raw_mapping_events (
                event_id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                candle_time_utc_ms INTEGER NOT NULL,
                candle_index INTEGER NULL,
                price REAL NULL,
                price_int INTEGER NULL,
                price_scale INTEGER NULL,
                event_type TEXT NOT NULL CHECK (event_type IN (
                    'SET_INITIAL_ANCHOR','SET_ANCHOR','ADJUST_ANCHOR',
                    'MANUAL_BOS','AUTO_BOS','RECLAIM','ABANDON_RANGE',
                    'DELETE_RECORD','NOTE'
                )),
                event_side TEXT NOT NULL CHECK (event_side IN ('HIGH','LOW','NONE')),
                source TEXT NOT NULL CHECK (source IN ('manual','auto','system','import')),
                created_order INTEGER NOT NULL,
                is_deleted INTEGER NOT NULL DEFAULT 0 CHECK (is_deleted IN (0,1)),
                supersedes_event_id TEXT NULL,
                schema_version TEXT NOT NULL DEFAULT 'raw_mapping_v1',
                notes TEXT NOT NULL DEFAULT '',
                created_at_utc_ms INTEGER NOT NULL,
                updated_at_utc_ms INTEGER NULL,
                raw_payload_json TEXT NULL,
                FOREIGN KEY(case_id) REFERENCES raw_mapping_cases(case_id)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_raw_mapping_case_order ON raw_mapping_events(case_id,created_order)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_raw_mapping_case_time ON raw_mapping_events(case_id,timeframe,candle_time_utc_ms)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_raw_mapping_symbol_tf_time ON raw_mapping_events(symbol,timeframe,candle_time_utc_ms)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_raw_mapping_supersedes ON raw_mapping_events(supersedes_event_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_map_events_lookup ON map_events(symbol,timeframe,time,event_type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_map_ranges_lookup ON map_ranges(symbol,timeframe,range_key,status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_map_ranges_case_tf ON map_ranges(case_id,symbol,timeframe,status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_map_ranges_parent ON map_ranges(parent_range_id,symbol,timeframe)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_map_events_case_tf ON map_events(case_id,symbol,timeframe,time)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_map_events_case_seq ON map_events(case_id,case_event_index)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS htf_state_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                case_id INTEGER,
                range_id INTEGER,
                range_high REAL,
                range_low REAL,
                range_start_time TEXT,
                range_end_time TEXT,
                state_json TEXT,
                logic_version TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS range_objectives (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                range_id INTEGER,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                case_id INTEGER,
                objective_rank INTEGER DEFAULT 1,
                objective_type TEXT,
                objective_direction TEXT,
                target_price REAL,
                target_point_role TEXT,
                status TEXT DEFAULT 'OPEN',
                reason TEXT,
                rule_id TEXT,
                first_touch_time TEXT,
                hit_time TEXT,
                failed_time TEXT,
                candles_to_touch INTEGER,
                candles_to_hit INTEGER,
                candles_to_fail INTEGER,
                meta_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

        # MOS v1 core: Story Anchor -> Chapter -> Phase. Keep this tiny.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS narrative_stories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                story_anchor TEXT NOT NULL,
                anchor_price REAL NOT NULL,
                activated_timestamp TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS story_chapters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                story_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                chapter_catalyst TEXT NOT NULL,
                trigger_price REAL NOT NULL,
                created_timestamp TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(story_id) REFERENCES narrative_stories(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS market_phases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chapter_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                phase_number INTEGER NOT NULL,
                phase_part TEXT NOT NULL,
                direction TEXT NOT NULL,
                active_objective TEXT NOT NULL,
                established_price REAL NOT NULL,
                established_timestamp TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(chapter_id) REFERENCES story_chapters(id) ON DELETE CASCADE
            )
            """
        )
        # MOS v1.1: current zone belongs to the latest operational coordinate.
        _ensure_column(conn, "market_phases", "current_zone", "TEXT DEFAULT 'UNKNOWN'")
        # MOS v1.2: anchor class separates WHY the story started (liquidity vs rejection).
        _ensure_column(conn, "narrative_stories", "anchor_class", "TEXT DEFAULT 'UNKNOWN'")
        # MOS v150 compatibility layer: objective lookup, profiles, transitions, runtime GPS cache, and immutable playback ledger.
        _ensure_column(conn, "narrative_stories", "parent_context_mode", "TEXT DEFAULT 'WEEKLY_ACTIVE_PARENT'")
        _ensure_column(conn, "narrative_stories", "daily_range_status", "TEXT DEFAULT 'NO_ACTIVE_DAILY_RANGE'")
        _ensure_column(conn, "market_phases", "lifecycle_state", "TEXT DEFAULT 'EXPANSION'")
        _ensure_column(conn, "market_phases", "objective_id", "INTEGER")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS objective_types (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                objective_level TEXT NOT NULL,
                parent_objective_id INTEGER DEFAULT NULL,
                FOREIGN KEY(parent_objective_id) REFERENCES objective_types(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS price_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                story_id INTEGER,
                chapter_id INTEGER,
                bos_direction TEXT NOT NULL,
                broken_range_high REAL,
                broken_range_low REAL,
                bos_price REAL NOT NULL,
                reclaim_price REAL,
                reclaim_depth_percent REAL,
                profile_type TEXT NOT NULL,
                created_timestamp TEXT NOT NULL,
                FOREIGN KEY(story_id) REFERENCES narrative_stories(id) ON DELETE SET NULL,
                FOREIGN KEY(chapter_id) REFERENCES story_chapters(id) ON DELETE SET NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS state_transitions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                story_id INTEGER NOT NULL,
                previous_lifecycle TEXT NOT NULL,
                new_lifecycle TEXT NOT NULL,
                previous_phase TEXT NOT NULL,
                new_phase TEXT NOT NULL,
                trigger_event TEXT NOT NULL,
                transition_timestamp TEXT NOT NULL,
                FOREIGN KEY(story_id) REFERENCES narrative_stories(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS market_coordinates (
                symbol TEXT PRIMARY KEY,
                story_id INTEGER NOT NULL,
                chapter_id INTEGER,
                active_objective_id INTEGER,
                active_profile_id INTEGER,
                parent_context_mode TEXT NOT NULL DEFAULT 'WEEKLY_ACTIVE_PARENT',
                daily_range_status TEXT NOT NULL DEFAULT 'NO_ACTIVE_DAILY_RANGE',
                current_zone TEXT NOT NULL DEFAULT 'DAILY_DISCOUNT',
                current_lifecycle TEXT NOT NULL DEFAULT 'EXPANSION',
                current_phase INTEGER NOT NULL DEFAULT 1,
                current_phase_part TEXT NOT NULL DEFAULT 'RETEST',
                last_updated TEXT NOT NULL,
                FOREIGN KEY(story_id) REFERENCES narrative_stories(id),
                FOREIGN KEY(chapter_id) REFERENCES story_chapters(id),
                FOREIGN KEY(active_objective_id) REFERENCES objective_types(id),
                FOREIGN KEY(active_profile_id) REFERENCES price_profiles(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS playback_frames (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                story_id INTEGER NOT NULL,
                frame_timestamp TEXT NOT NULL,
                parent_context_mode TEXT NOT NULL,
                daily_range_status TEXT NOT NULL,
                lifecycle_state TEXT NOT NULL,
                phase_number INTEGER NOT NULL,
                phase_part TEXT NOT NULL,
                profile_type TEXT NOT NULL,
                objective_code TEXT NOT NULL,
                current_zone TEXT NOT NULL,
                established_price REAL NOT NULL,
                trigger_event TEXT NOT NULL,
                expected_next_event TEXT NOT NULL,
                invalidation_condition TEXT NOT NULL,
                FOREIGN KEY(story_id) REFERENCES narrative_stories(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS mos_seed_ideas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                seed_name TEXT NOT NULL,
                symbol TEXT NOT NULL,
                replay_timeframe TEXT NOT NULL,
                replay_candle_time TEXT,
                replay_candle_index INTEGER,
                weekly_high REAL,
                weekly_high_time TEXT,
                weekly_low REAL,
                weekly_low_time TEXT,
                daily_high REAL,
                daily_high_time TEXT,
                daily_low REAL,
                daily_low_time TEXT,
                mos_payload_json TEXT NOT NULL,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        for code, name, level, parent_id in MOS_OBJECTIVE_SEEDS:
            conn.execute(
                "INSERT OR IGNORE INTO objective_types(code,name,objective_level,parent_objective_id) VALUES(?,?,?,?)",
                (code, name, level, parent_id),
            )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mos_stories_active ON narrative_stories(symbol,timeframe,status,activated_timestamp)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mos_chapters_lookup ON story_chapters(story_id,created_timestamp)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mos_phases_current ON market_phases(chapter_id,established_timestamp DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mos_coordinates_symbol ON market_coordinates(symbol)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mos_profiles_lookup ON price_profiles(symbol,profile_type,reclaim_depth_percent)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mos_transitions_story_time ON state_transitions(story_id,transition_timestamp)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mos_playback_chronology ON playback_frames(story_id,frame_timestamp,id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mos_seed_ideas_lookup ON mos_seed_ideas(symbol,created_at DESC)")
        # v147: Case containers grew up from the old Seed Idea form. Existing DBs need
        # nullable columns so updates can persist scope/timeframe/range metadata without
        # creating a confetti cannon of duplicate rows.
        for col, ddl in [
            ("case_scope", "ALTER TABLE mos_seed_ideas ADD COLUMN case_scope TEXT"),
            ("case_timeframe", "ALTER TABLE mos_seed_ideas ADD COLUMN case_timeframe TEXT"),
            ("case_high", "ALTER TABLE mos_seed_ideas ADD COLUMN case_high REAL"),
            ("case_high_time", "ALTER TABLE mos_seed_ideas ADD COLUMN case_high_time TEXT"),
            ("case_low", "ALTER TABLE mos_seed_ideas ADD COLUMN case_low REAL"),
            ("case_low_time", "ALTER TABLE mos_seed_ideas ADD COLUMN case_low_time TEXT"),
            ("range_start_date", "ALTER TABLE mos_seed_ideas ADD COLUMN range_start_date TEXT"),
            ("range_end_date", "ALTER TABLE mos_seed_ideas ADD COLUMN range_end_date TEXT"),
            ("event_count", "ALTER TABLE mos_seed_ideas ADD COLUMN event_count INTEGER"),
            ("anchors_json", "ALTER TABLE mos_seed_ideas ADD COLUMN anchors_json TEXT"),
        ]:
            try:
                existing = [r["name"] for r in conn.execute("PRAGMA table_info(mos_seed_ideas)").fetchall()]
                if col not in existing:
                    conn.execute(ddl)
            except Exception:
                pass
        conn.commit()


def normalise_timeframe(tf: str) -> str:
    val = (tf or "D1").strip().upper()
    aliases = {"MN": "MN1", "MONTHLY": "MN1", "MACRO": "MN1", "WEEKLY": "W1", "DAILY": "D1", "4H": "H4", "1H": "H1", "15M": "M15", "5M": "M5"}
    val = aliases.get(val, val)
    if val not in TIMEFRAMES:
        raise ValueError(f"Unsupported timeframe: {tf}")
    return val


def normalise_candle_query_time(value: str | None, *, bound: str = "exact") -> str | None:
    """Accept ISO or dotted MT5 times for SQL range filters."""
    if value in (None, ""):
        return None
    raw = str(value).strip()
    if not raw:
        return None
    if "T" in raw:
        raw = raw.replace("T", " ")
    if raw[0:4].isdigit() and raw[4:5] == "-":
        raw = raw.replace("-", ".")
    # Date-only filters must include the full UTC day; MT5 rows use "YYYY.MM.DD HH:MM".
    if bound in {"start", "end"} and len(raw) == 10 and raw[4:5] == "." and raw[7:8] == ".":
        if bound == "start":
            return f"{raw} 00:00"
        # Exclusive upper bound: first minute of the next day avoids string compare bugs
        # where "2026.06.04 ..." sorts after "2026.06.12".
        try:
            dt = datetime.strptime(raw, "%Y.%m.%d") + timedelta(days=1)
            return dt.strftime("%Y.%m.%d %H:%M")
        except Exception:
            return f"{raw} 23:59"
    return raw


def parse_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return default
        return float(str(v).replace(",", "."))
    except Exception:
        return default


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except Exception:
        return None


def _optional_text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    return text or None


def _case_refs_from_payload(payload: dict[str, Any]) -> tuple[int | None, str | None, str | None]:
    """Keep legacy integer cases separate from raw UUID mapping cases."""
    case_id = _optional_int(payload.get("case_id"))
    raw_case_id = _optional_text(payload.get("raw_case_id"))
    if raw_case_id is None and payload.get("case_id") not in (None, "") and case_id is None:
        raw_case_id = _optional_text(payload.get("case_id"))
    case_ref = _optional_text(payload.get("case_ref"))
    if case_ref is None:
        if raw_case_id:
            case_ref = f"raw:{raw_case_id}"
        elif case_id is not None:
            case_ref = f"case:{case_id}"
    return case_id, raw_case_id, case_ref


def normalise_candle(row: dict[str, Any], symbol: str | None = None, timeframe: str | None = None, source: str = "unknown") -> dict[str, Any]:
    sym = str(row.get("symbol") or symbol or "XAUUSD").strip()
    tf = normalise_timeframe(str(row.get("timeframe") or timeframe or "D1"))
    t = row.get("time") or row.get("timestamp") or row.get("date")
    if t is None:
        raise ValueError("Candle missing time/timestamp")
    t = str(t).strip()
    return {
        "symbol": sym,
        "timeframe": tf,
        "time": t,
        "open": parse_float(row.get("open")),
        "high": parse_float(row.get("high")),
        "low": parse_float(row.get("low")),
        "close": parse_float(row.get("close")),
        "volume": parse_float(row.get("volume", row.get("tick_volume", 0))),
        "source": source,
    }


def upsert_candles(candles: list[dict[str, Any]], source: str = "unknown") -> dict[str, Any]:
    init_db()
    inserted = 0
    updated = 0
    skipped = 0
    now = now_iso()
    with connect() as conn:
        for raw in candles:
            try:
                c = normalise_candle(raw, source=source)
                cur = conn.execute(
                    """
                    INSERT INTO candles(symbol,timeframe,time,open,high,low,close,volume,source,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(symbol,timeframe,time) DO UPDATE SET
                        open=excluded.open,
                        high=excluded.high,
                        low=excluded.low,
                        close=excluded.close,
                        volume=excluded.volume,
                        source=excluded.source,
                        updated_at=excluded.updated_at
                    """,
                    (c["symbol"], c["timeframe"], c["time"], c["open"], c["high"], c["low"], c["close"], c["volume"], c["source"], now, now),
                )
                # sqlite rowcount is 1 for insert/update, so detect existence with changes is pointless. Keep count as upserted.
                inserted += 1
            except Exception:
                skipped += 1
        conn.commit()
    return {"ok": True, "upserted": inserted + updated, "inserted_or_updated": inserted, "skipped": skipped, "db": str(DB_PATH)}


def get_candles(symbol: str = "XAUUSD", timeframe: str = "D1", limit: int = 500, start: str | None = None, end: str | None = None) -> dict[str, Any]:
    init_db()
    tf = normalise_timeframe(timeframe)
    limit = max(1, min(int(limit or 500), 10000))
    start = normalise_candle_query_time(start, bound="start")
    end = normalise_candle_query_time(end, bound="end")
    sql = "SELECT symbol,timeframe,time,open,high,low,close,volume,source FROM candles WHERE symbol=? AND timeframe=?"
    params: list[Any] = [symbol, tf]
    if start:
        sql += " AND time >= ?"
        params.append(start)
    if end:
        sql += " AND time < ?"
        params.append(end)
    sql += " ORDER BY time DESC LIMIT ?"
    params.append(limit)
    with connect() as conn:
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    rows.reverse()
    return {"ok": True, "symbol": symbol, "timeframe": tf, "count": len(rows), "candles": rows}


def status() -> dict[str, Any]:
    init_db()
    with connect() as conn:
        total = conn.execute("SELECT COUNT(*) AS n FROM candles").fetchone()["n"]
        by_tf = [dict(r) for r in conn.execute("SELECT symbol,timeframe,COUNT(*) AS count,MIN(time) AS first_time,MAX(time) AS last_time FROM candles GROUP BY symbol,timeframe ORDER BY symbol,timeframe").fetchall()]
    return {"ok": True, "db": str(DB_PATH), "candles": total, "groups": by_tf}


def import_csv_file(path: Path, symbol: str | None = None, timeframe: str | None = None) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        # Support comma or semicolon CSV. Because of course there must be choices.
        sample = f.read(4096)
        f.seek(0)
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t") if sample.strip() else csv.excel
        reader = csv.DictReader(f, dialect=dialect)
        for row in reader:
            lowered = {str(k).strip().lower(): v for k, v in row.items() if k is not None}
            rows.append({
                "symbol": lowered.get("symbol") or symbol,
                "timeframe": lowered.get("timeframe") or timeframe,
                "time": lowered.get("time") or lowered.get("timestamp") or lowered.get("date"),
                "open": lowered.get("open"),
                "high": lowered.get("high"),
                "low": lowered.get("low"),
                "close": lowered.get("close"),
                "volume": lowered.get("volume") or lowered.get("tick_volume"),
            })
    result = upsert_candles(rows, source=f"csv:{path.name}")
    result.update({"file": str(path), "rows_read": len(rows)})
    return result


def import_common_files(symbol: str = "XAUUSD", timeframes: list[str] | None = None) -> dict[str, Any]:
    tfs = [normalise_timeframe(t) for t in (timeframes or ["MN1", "W1", "D1", "H4", "H1", "M15"])]
    results = []
    for tf in tfs:
        candidates = [
            MARKET_MEMORY_DIR / f"{symbol}_{tf}.csv",
            COMMON_FILES_PATH / f"{symbol}_{tf}.csv",
            COMMON_FILES_PATH / f"josh_candles_{symbol.lower()}_{tf.lower()}.csv",
        ]
        found = next((p for p in candidates if p.exists()), None)
        if found:
            try:
                results.append(import_csv_file(found, symbol=symbol, timeframe=tf))
            except Exception as e:
                results.append({"ok": False, "file": str(found), "error": str(e)})
        else:
            results.append({"ok": False, "symbol": symbol, "timeframe": tf, "error": "file not found", "checked": [str(p) for p in candidates]})
    return {"ok": True, "symbol": symbol, "results": results}


def _event_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    if d.get("client_event_id"):
        d["id"] = str(d["client_event_id"])
    else:
        d["id"] = str(d.get("id"))
    return d


def _parent_timeframe_for(tf: str) -> str | None:
    order = ["MN1", "W1", "D1", "H4", "H1", "M15"]
    t = normalise_timeframe(tf)
    try:
        i = order.index(t)
    except ValueError:
        return None
    return order[i - 1] if i > 0 else None


STRUCTURE_LAYER_ORDER = ["MACRO", "WEEKLY", "DAILY", "INTRADAY", "MICRO"]


def _structure_layer_for_timeframe(tf: str | None) -> str:
    t = normalise_timeframe(tf or "D1")
    if t == "MN1":
        return "MACRO"
    if t == "W1":
        return "WEEKLY"
    if t == "D1":
        return "DAILY"
    if t in {"H4", "H1"}:
        return "INTRADAY"
    if t in {"M15", "M5"}:
        return "MICRO"
    return "WEEKLY"


def _source_timeframe_for_layer(layer: str | None) -> str:
    l = str(layer or "").upper()
    return {
        "MACRO": "MN1",
        "WEEKLY": "W1",
        "DAILY": "D1",
        "INTRADAY": "H1",
        "MICRO": "M15",
    }.get(l, "D1")


def _normalise_structure_layer(value: Any, fallback_timeframe: str | None = None) -> str:
    raw = str(value or "").strip().upper()
    aliases = {
        "MN1": "MACRO",
        "MN": "MACRO",
        "MONTHLY": "MACRO",
        "MACRO": "MACRO",
        "W1": "WEEKLY",
        "WEEK": "WEEKLY",
        "D1": "DAILY",
        "DAY": "DAILY",
        "H4": "INTRADAY",
        "H1": "INTRADAY",
        "M15": "MICRO",
        "M5": "MICRO",
    }
    layer = aliases.get(raw, raw)
    if layer in STRUCTURE_LAYER_ORDER:
        return layer
    return _structure_layer_for_timeframe(fallback_timeframe or "D1")


def _expected_parent_layer(layer: str) -> str | None:
    l = _normalise_structure_layer(layer)
    if l == "MACRO":
        return None
    if l == "WEEKLY":
        return "MACRO"
    if l == "DAILY":
        return "WEEKLY"
    if l == "INTRADAY":
        return "DAILY"
    if l == "MICRO":
        return "INTRADAY"
    return None


def _parse_time_ms(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        if isinstance(value, (int, float)):
            return int(value)
        s = str(value).strip()
        if s.isdigit():
            return int(s)
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    except Exception:
        return None


def _boundary_span_window(row: sqlite3.Row | dict[str, Any]) -> tuple[int | None, int | None]:
    """RH/RL anchor boundary span — not lifecycle."""
    d = _row_dict(row)
    start_candidates = [
        d.get("range_start_time"),
        d.get("range_high_time"),
        d.get("range_low_time"),
    ]
    end_candidates = [
        d.get("range_end_time"),
        d.get("range_high_time"),
        d.get("range_low_time"),
    ]
    starts = [x for x in (_parse_time_ms(v) for v in start_candidates) if x is not None]
    ends = [x for x in (_parse_time_ms(v) for v in end_candidates) if x is not None]
    start = min(starts) if starts else None
    end = max(ends) if ends else None
    if start is not None and end is not None and end < start:
        start, end = end, start
    return start, end


def _parent_lifecycle_window(row: sqlite3.Row | dict[str, Any]) -> tuple[int | None, int | None]:
    """Lifecycle window. Upper bound only when parent is BROKEN/ABANDONED/ARCHIVED."""
    d = _row_dict(row)
    start_candidates = [d.get("active_from_time"), d.get("range_start_time")]
    starts = [x for x in (_parse_time_ms(v) for v in start_candidates) if x is not None]
    p_start = min(starts) if starts else None
    status = _normalize_range_status(d.get("status"))
    p_end: int | None = None
    if status in {"BROKEN", "ABANDONED", "ARCHIVED"}:
        p_end = _parse_time_ms(d.get("inactive_from_time"))
    return p_start, p_end


def _child_lifecycle_contradiction_for_parent(
    child: sqlite3.Row | dict[str, Any],
    parent: sqlite3.Row | dict[str, Any],
) -> str | None:
    """True lifecycle contradiction — invalidates parent link review status."""
    _p_start, p_end = _parent_lifecycle_window(parent)
    c_start, c_end = _boundary_span_window(child)
    if p_end is None:
        return None
    if c_start is not None and c_start > p_end:
        return "child range starts after parent inactive window"
    if c_end is not None and c_end > p_end:
        return "child range ends after parent inactive window"
    return None


def _child_boundary_time_informational_warnings(
    child: sqlite3.Row | dict[str, Any],
    parent: sqlite3.Row | dict[str, Any],
) -> list[str]:
    """Anchor-span timing notes only — do not change parent_link_status."""
    warnings: list[str] = []
    p_start, p_end = _boundary_span_window(parent)
    c_start, c_end = _boundary_span_window(child)
    if p_start is None and p_end is None:
        return warnings
    if c_start is None and c_end is None:
        return warnings
    if p_start is not None and c_start is not None and c_start < p_start:
        warnings.append("child range starts before parent active window")
    if p_end is not None and c_end is not None and c_end > p_end:
        warnings.append("child range ends after parent anchor span")
    if p_start is not None and c_end is not None and c_end < p_start:
        warnings.append("child range ends before parent anchor span starts")
    if p_end is not None and c_start is not None and c_start > p_end:
        warnings.append("child range starts after parent anchor span ends")
    return warnings


def _child_price_overlaps_parent(
    child: sqlite3.Row | dict[str, Any],
    parent: sqlite3.Row | dict[str, Any],
    *,
    tolerance_pct: float = 0.001,
) -> tuple[bool, str | None]:
    c_high = _range_price(child, "HIGH")
    c_low = _range_price(child, "LOW")
    p_high = _range_price(parent, "HIGH")
    p_low = _range_price(parent, "LOW")
    if any(v in (None, 0) for v in (c_high, c_low, p_high, p_low)):
        return True, None
    parent_span = max(float(p_high) - float(p_low), 0.0001)
    tol = max(0.01, parent_span * tolerance_pct)
    overlaps = float(c_high) >= (float(p_low) - tol) and float(c_low) <= (float(p_high) + tol)
    if not overlaps:
        return False, "child price range does not overlap parent price boundaries"
    return True, None


def _row_dict(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    return dict(row)


def _range_layer(row: sqlite3.Row | dict[str, Any]) -> str:
    d = _row_dict(row)
    return _normalise_structure_layer(
        d.get("structure_layer") or d.get("layer"),
        d.get("source_timeframe") or d.get("timeframe"),
    )


def _range_source_timeframe(row: sqlite3.Row | dict[str, Any]) -> str:
    d = _row_dict(row)
    return normalise_timeframe(str(d.get("source_timeframe") or d.get("timeframe") or _source_timeframe_for_layer(_range_layer(d))))


def _range_price(row: sqlite3.Row | dict[str, Any], side: str) -> float | None:
    d = _row_dict(row)
    if side == "HIGH":
        return parse_float(d.get("range_high_price", d.get("range_high")), None)
    return parse_float(d.get("range_low_price", d.get("range_low")), None)


def _has_parent_cycle(conn: sqlite3.Connection, child_id: int, parent_id: int) -> bool:
    seen = {child_id}
    current: int | None = parent_id
    while current is not None:
        if current in seen:
            return True
        seen.add(current)
        row = conn.execute("SELECT parent_range_id FROM map_ranges WHERE id=?", (current,)).fetchone()
        if row is None or row["parent_range_id"] in (None, ""):
            return False
        try:
            current = int(row["parent_range_id"])
        except Exception:
            return False
    return False


def _validate_parent_link(
    conn: sqlite3.Connection,
    *,
    child_id: int | None,
    symbol: str,
    case_id: Any,
    raw_case_id: Any = None,
    case_ref: Any = None,
    structure_layer: str,
    parent_range_id: Any,
) -> tuple[str, list[str], sqlite3.Row | None]:
    layer = _normalise_structure_layer(structure_layer)
    parent_id: int | None
    try:
        parent_id = int(parent_range_id) if parent_range_id not in (None, "") else None
    except Exception:
        return "INVALID_PARENT", ["parent_range_id is not an integer"], None

    if parent_id is None:
        if layer == "MACRO":
            return "VALID", [], None
        return "ORPHAN", [], None
    if layer == "MACRO":
        return "NEEDS_REVIEW", ["MACRO range should not have parent_range_id"], None
    if child_id is not None and int(child_id) == parent_id:
        return "INVALID_PARENT", ["range cannot be its own parent"], None

    parent = conn.execute("SELECT * FROM map_ranges WHERE id=?", (parent_id,)).fetchone()
    if parent is None:
        return "INVALID_PARENT", [f"parent range {parent_id} does not exist"], None
    if str(parent["symbol"]) != str(symbol):
        return "INVALID_PARENT", ["parent symbol does not match child symbol"], parent

    parent_keys = set(parent.keys())
    parent_case = parent["case_id"] if "case_id" in parent_keys else None
    parent_raw_case = parent["raw_case_id"] if "raw_case_id" in parent_keys else None
    parent_case_ref = parent["case_ref"] if "case_ref" in parent_keys else None
    if case_id not in (None, "") and parent_case not in (None, "") and str(parent_case) != str(case_id):
        return "INVALID_PARENT", ["parent case_id does not match child case_id"], parent
    if raw_case_id not in (None, "") and parent_raw_case not in (None, "") and str(parent_raw_case) != str(raw_case_id):
        return "INVALID_PARENT", ["parent raw_case_id does not match child raw_case_id"], parent
    if case_ref not in (None, "") and parent_case_ref not in (None, "") and str(parent_case_ref) != str(case_ref):
        return "INVALID_PARENT", ["parent case_ref does not match child case_ref"], parent

    expected_parent = _expected_parent_layer(layer)
    parent_layer = _range_layer(parent)
    if expected_parent and parent_layer != expected_parent:
        return "INVALID_PARENT", [f"{layer} parent must be {expected_parent}, got {parent_layer}"], parent
    if child_id is not None and _has_parent_cycle(conn, int(child_id), parent_id):
        return "INVALID_PARENT", ["parent link would create a circular chain"], parent

    child_row = None
    if child_id is not None:
        child_row = conn.execute("SELECT * FROM map_ranges WHERE id=?", (int(child_id),)).fetchone()
    link_warnings: list[str] = []
    if child_row is not None:
        lifecycle_issue = _child_lifecycle_contradiction_for_parent(child_row, parent)
        if lifecycle_issue:
            return "NEEDS_REVIEW", [lifecycle_issue], parent
        link_warnings.extend(_child_boundary_time_informational_warnings(child_row, parent))
        price_ok, price_warning = _child_price_overlaps_parent(child_row, parent)
        if not price_ok and price_warning:
            return "NEEDS_REVIEW", link_warnings + [price_warning], parent

    return "VALID", link_warnings, parent


def _range_row_to_structural_dict(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    d = dict(row)
    layer = _range_layer(d)
    source_tf = _range_source_timeframe(d)
    chart_tf = str(d.get("chart_timeframe") or d.get("timeframe") or source_tf)
    high = _range_price(d, "HIGH")
    low = _range_price(d, "LOW")
    out = dict(d)
    out.update({
        "range_id": d.get("id"),
        "structure_layer": d.get("structure_layer") or layer,
        "chart_timeframe": chart_tf,
        "source_timeframe": source_tf,
        "range_high_price": high,
        "range_low_price": low,
        "parent_link_status": d.get("parent_link_status") or "NEEDS_REVIEW",
    })
    return out


def _structural_event_name(event_type: str) -> str:
    t = str(event_type or "").upper()
    if t in {"RANGE_HIGH", "RANGE_LOW", "BOS_UP", "BOS_DOWN", "RANGE_INVALIDATED", "RANGE_ABANDONED"}:
        return t
    if t.endswith("_BOS_UP"):
        return t
    if t.endswith("_BOS_DOWN"):
        return t
    if t.endswith("_RANGE_HIGH") or "RANGE_HIGH" in t:
        return t
    if t.endswith("_RANGE_LOW") or "RANGE_LOW" in t:
        return t
    return t


def _is_range_high_event(event_type: str, structural_event: str | None = None) -> bool:
    t = str(structural_event or event_type or "").upper()
    return t in {"RANGE_HIGH", "SET_WEEKLY_RANGE_HIGH", "SET_DAILY_RANGE_HIGH", "SET_MACRO_RANGE_HIGH"} or t.endswith("_RANGE_HIGH") or t.endswith("HIGH_SET")


def _is_range_low_event(event_type: str, structural_event: str | None = None) -> bool:
    t = str(structural_event or event_type or "").upper()
    return t in {"RANGE_LOW", "SET_WEEKLY_RANGE_LOW", "SET_DAILY_RANGE_LOW", "SET_MACRO_RANGE_LOW"} or t.endswith("_RANGE_LOW") or t.endswith("LOW_SET")


def _is_bos_event(event_type: str, structural_event: str | None = None) -> bool:
    t = str(structural_event or event_type or "").upper()
    return t.endswith("BOS_UP") or t.endswith("BOS_DOWN") or t in {"BOS_UP", "BOS_DOWN", "BREAK_HIGH_SELECTED", "BREAK_LOW_SELECTED"}


def _normalise_bos_event_type(event_type: str | None, structural_event: str | None = None) -> str:
    t = str(structural_event or event_type or "").upper()
    if t == "BREAK_HIGH_SELECTED":
        return "BOS_UP"
    if t == "BREAK_LOW_SELECTED":
        return "BOS_DOWN"
    if t.endswith("BOS_UP") or t == "BOS_UP":
        return "BOS_UP"
    if t.endswith("BOS_DOWN") or t == "BOS_DOWN":
        return "BOS_DOWN"
    return t


ALLOWED_RANGE_STATUSES = {"ACTIVE", "BROKEN", "ABANDONED", "NEEDS_REVIEW"}


def _normalize_range_status(value: Any) -> str | None:
    raw = _optional_text(value)
    if raw is None:
        return None
    normalized = raw.upper()
    if normalized == "ARCHIVED":
        return "ARCHIVED"
    if normalized in ALLOWED_RANGE_STATUSES:
        return normalized
    return "NEEDS_REVIEW"


def _range_status_is_broken(status: Any) -> bool:
    return _normalize_range_status(status) == "BROKEN"


def _effective_range_status(
    payload: dict[str, Any],
    merged: dict[str, Any],
    lifecycle_resolved: dict[str, Any] | None = None,
) -> str:
    resolved = lifecycle_resolved or {}
    return (
        resolved.get("status")
        or _normalize_range_status(payload.get("status"))
        or _normalize_range_status(merged.get("status"))
        or "ACTIVE"
    )


def _apply_active_lifecycle_normalization(
    payload: dict[str, Any],
    merged: dict[str, Any],
    lifecycle_resolved: dict[str, Any],
) -> str:
    """ACTIVE ranges must never retain break lifecycle fields, regardless of payload."""
    effective_status = _effective_range_status(payload, merged, lifecycle_resolved)
    normalized_status = _normalize_range_status(effective_status) or "ACTIVE"
    if normalized_status == "ACTIVE":
        payload["broken_by_event_id"] = None
        payload["direction_of_break"] = None
        payload["inactive_from_time"] = None
        lifecycle_resolved["broken_by_event_id"] = None
        lifecycle_resolved["direction_of_break"] = None
        lifecycle_resolved["inactive_from_time"] = None
    if "status" in payload or lifecycle_resolved.get("status") is not None:
        payload["status"] = normalized_status
        lifecycle_resolved["status"] = normalized_status
    return normalized_status


def _write_broken_by_event_id(payload: dict[str, Any], effective_status: str) -> Any:
    if effective_status == "ACTIVE":
        return None
    return payload.get("broken_by_event_id")


def _write_direction_of_break(payload: dict[str, Any], effective_status: str) -> Any:
    if effective_status == "ACTIVE":
        return None
    return payload.get("direction_of_break")


def _write_inactive_from_time(payload: dict[str, Any], effective_status: str) -> Any:
    if effective_status == "ACTIVE":
        return None
    inactive = payload.get("inactive_from_time")
    if inactive not in (None, ""):
        return _optional_text(inactive)
    return _optional_text(payload.get("range_end_time"))


def _range_part_of_chain(row: sqlite3.Row | dict[str, Any]) -> bool:
    d = _row_dict(row)
    return any(d.get(field) not in (None, "") for field in ("old_range_id", "created_by_event_id", "new_range_id"))


def _resolve_map_event(conn: sqlite3.Connection, event_ref: Any) -> sqlite3.Row | None:
    if event_ref in (None, ""):
        return None
    ref = str(event_ref).strip()
    event_int = _optional_int(event_ref)
    return conn.execute(
        "SELECT * FROM map_events WHERE event_id=? OR client_event_id=? OR id=? LIMIT 1",
        (ref, ref, event_int if event_int is not None else -1),
    ).fetchone()


def _map_event_storage_id(event_row: sqlite3.Row | None) -> int | None:
    if event_row is None:
        return None
    try:
        return int(event_row["id"])
    except Exception:
        return None


def _validate_bos_event_reference(
    conn: sqlite3.Connection,
    event_ref: Any,
    *,
    symbol: str,
    case_id: Any,
    raw_case_id: Any,
    case_ref: Any,
    direction_of_break: Any = None,
) -> tuple[str, list[str], sqlite3.Row | None, int | None]:
    warnings: list[str] = []
    if event_ref in (None, ""):
        return "NEEDS_REVIEW", ["event reference missing"], None, None

    event_row = _resolve_map_event(conn, event_ref)
    if event_row is None:
        return "NEEDS_REVIEW", [f"event reference {event_ref} does not exist"], None, None

    bos_type = _normalise_bos_event_type(event_row["event_type"], event_row["structural_event"] if "structural_event" in event_row.keys() else None)
    if bos_type not in {"BOS_UP", "BOS_DOWN"}:
        warnings.append(f"event {event_ref} is not a BOS event")
        return "NEEDS_REVIEW", warnings, event_row, _map_event_storage_id(event_row)

    event_keys = set(event_row.keys())
    if str(event_row["symbol"]) != str(symbol):
        warnings.append("BOS event symbol does not match range symbol")
    event_case_id = event_row["case_id"] if "case_id" in event_keys else None
    event_raw_case_id = event_row["raw_case_id"] if "raw_case_id" in event_keys else None
    event_case_ref = event_row["case_ref"] if "case_ref" in event_keys else None
    if case_id not in (None, "") and event_case_id not in (None, "") and str(event_case_id) != str(case_id):
        warnings.append("BOS event case_id does not match range case_id")
    if raw_case_id not in (None, "") and event_raw_case_id not in (None, "") and str(event_raw_case_id) != str(raw_case_id):
        warnings.append("BOS event raw_case_id does not match range raw_case_id")
    if case_ref not in (None, "") and event_case_ref not in (None, "") and str(event_case_ref) != str(case_ref):
        warnings.append("BOS event case_ref does not match range case_ref")

    if direction_of_break not in (None, ""):
        expected_dir = "UP" if bos_type == "BOS_UP" else "DOWN"
        if str(direction_of_break).upper() != expected_dir:
            warnings.append(f"direction_of_break {direction_of_break} does not match BOS event {bos_type}")

    status = "NEEDS_REVIEW" if warnings else "VALID"
    return status, warnings, event_row, _map_event_storage_id(event_row)


def _has_old_range_chain_cycle(conn: sqlite3.Connection, range_id: int, old_range_id: int) -> bool:
    seen = {int(range_id)}
    current: int | None = int(old_range_id)
    while current is not None:
        if current in seen:
            return True
        seen.add(current)
        row = conn.execute("SELECT old_range_id FROM map_ranges WHERE id=?", (current,)).fetchone()
        if row is None or row["old_range_id"] in (None, ""):
            return False
        try:
            current = int(row["old_range_id"])
        except Exception:
            return False
    return False


def _has_new_range_chain_cycle(conn: sqlite3.Connection, range_id: int, new_range_id: int) -> bool:
    seen = {int(range_id)}
    current: int | None = int(new_range_id)
    while current is not None:
        if current in seen:
            return True
        seen.add(current)
        row = conn.execute("SELECT new_range_id FROM map_ranges WHERE id=?", (current,)).fetchone()
        if row is None or row["new_range_id"] in (None, ""):
            return False
        try:
            current = int(row["new_range_id"])
        except Exception:
            return False
    return False


def _validate_range_chain_fields(
    conn: sqlite3.Connection,
    range_id: int | None,
    payload: dict[str, Any],
    merged: dict[str, Any],
    *,
    symbol: str,
    case_id: Any,
    raw_case_id: Any,
    case_ref: Any,
) -> tuple[str, list[str], dict[str, Any]]:
    warnings: list[str] = []
    resolved: dict[str, Any] = {}
    chain_status = "VALID"
    chain_fields = ("old_range_id", "new_range_id", "created_by_event_id", "active_from_time")
    if not any(field in payload for field in chain_fields):
        return chain_status, warnings, resolved

    old_range_id = payload.get("old_range_id") if "old_range_id" in payload else merged.get("old_range_id")
    new_range_id = payload.get("new_range_id") if "new_range_id" in payload else merged.get("new_range_id")
    created_by_event_id = payload.get("created_by_event_id") if "created_by_event_id" in payload else merged.get("created_by_event_id")

    if range_id is not None:
        rid = int(range_id)
        if "old_range_id" in payload and old_range_id not in (None, ""):
            try:
                old_id = int(old_range_id)
            except Exception:
                return "INVALID_CHAIN", ["old_range_id must be an integer"], resolved
            if old_id == rid:
                return "INVALID_CHAIN", ["old_range_id cannot equal current range_id"], resolved
            old_row = conn.execute("SELECT id FROM map_ranges WHERE id=?", (old_id,)).fetchone()
            if old_row is None:
                warnings.append(f"old_range_id {old_id} does not exist")
                chain_status = "NEEDS_REVIEW"
            elif _has_old_range_chain_cycle(conn, rid, old_id):
                return "INVALID_CHAIN", ["circular old_range_id chain"], resolved
            resolved["old_range_id"] = old_id

        if "new_range_id" in payload and new_range_id not in (None, ""):
            try:
                new_id = int(new_range_id)
            except Exception:
                return "INVALID_CHAIN", ["new_range_id must be an integer"], resolved
            if new_id == rid:
                return "INVALID_CHAIN", ["new_range_id cannot equal current range_id"], resolved
            new_row = conn.execute("SELECT id FROM map_ranges WHERE id=?", (new_id,)).fetchone()
            if new_row is None:
                warnings.append(f"new_range_id {new_id} does not exist")
                chain_status = "NEEDS_REVIEW"
            elif _has_new_range_chain_cycle(conn, rid, new_id):
                return "INVALID_CHAIN", ["circular new_range_id chain"], resolved
            resolved["new_range_id"] = new_id

    if "created_by_event_id" in payload and created_by_event_id not in (None, ""):
        ev_status, ev_warnings, _ev_row, storage_id = _validate_bos_event_reference(
            conn,
            created_by_event_id,
            symbol=symbol,
            case_id=case_id,
            raw_case_id=raw_case_id,
            case_ref=case_ref,
        )
        warnings.extend(ev_warnings)
        if ev_status == "NEEDS_REVIEW":
            chain_status = "NEEDS_REVIEW"
        if storage_id is not None:
            resolved["created_by_event_id"] = storage_id
        else:
            maybe_int = _optional_int(created_by_event_id)
            if maybe_int is not None:
                resolved["created_by_event_id"] = maybe_int
    elif "old_range_id" in payload and old_range_id not in (None, ""):
        warnings.append("old_range_id supplied without created_by_event_id")
        chain_status = "NEEDS_REVIEW"

    if "active_from_time" in payload:
        resolved["active_from_time"] = _optional_text(payload.get("active_from_time"))

    return chain_status, warnings, resolved


def _validate_range_lifecycle_fields(
    conn: sqlite3.Connection,
    payload: dict[str, Any],
    merged: dict[str, Any],
    *,
    symbol: str,
    case_id: Any,
    raw_case_id: Any,
    case_ref: Any,
) -> tuple[str, list[str], dict[str, Any]]:
    warnings: list[str] = []
    resolved: dict[str, Any] = {}
    lifecycle_status = "VALID"
    lifecycle_fields = ("status", "direction_of_break", "broken_by_event_id", "inactive_from_time")
    if not any(field in payload for field in lifecycle_fields):
        effective_status = _normalize_range_status(merged.get("status")) or _normalize_range_status(payload.get("status"))
        if effective_status == "ACTIVE" and any(
            field in payload for field in ("direction_of_break", "broken_by_event_id", "inactive_from_time", "range_end_time")
        ):
            resolved["broken_by_event_id"] = None
            resolved["direction_of_break"] = None
            resolved["inactive_from_time"] = None
        return lifecycle_status, warnings, resolved

    if "status" in payload:
        status = _normalize_range_status(payload.get("status"))
        if status:
            resolved["status"] = status
            if status == "ACTIVE":
                resolved["broken_by_event_id"] = None
                resolved["direction_of_break"] = None
                resolved["inactive_from_time"] = None
                return lifecycle_status, warnings, resolved

    effective_status = resolved.get("status") or _normalize_range_status(merged.get("status"))
    if effective_status == "ACTIVE" and "status" in payload:
        resolved["broken_by_event_id"] = None
        resolved["direction_of_break"] = None
        resolved["inactive_from_time"] = None
        return lifecycle_status, warnings, resolved

    effective_status = resolved.get("status") or _normalize_range_status(merged.get("status"))
    if effective_status != "BROKEN":
        return lifecycle_status, warnings, resolved

    direction = payload.get("direction_of_break") if "direction_of_break" in payload else merged.get("direction_of_break")
    broken_ref = payload.get("broken_by_event_id") if "broken_by_event_id" in payload else merged.get("broken_by_event_id")
    inactive = payload.get("inactive_from_time") if "inactive_from_time" in payload else merged.get("inactive_from_time")

    if direction in (None, ""):
        warnings.append("BROKEN range missing direction_of_break")
        lifecycle_status = "NEEDS_REVIEW"
    else:
        dir_up = str(direction).upper()
        if dir_up not in {"UP", "DOWN"}:
            warnings.append("direction_of_break must be UP or DOWN")
            lifecycle_status = "NEEDS_REVIEW"
        elif "direction_of_break" in payload:
            resolved["direction_of_break"] = dir_up

    if inactive in (None, ""):
        warnings.append("BROKEN range missing inactive_from_time")
        lifecycle_status = "NEEDS_REVIEW"
    elif "inactive_from_time" in payload:
        resolved["inactive_from_time"] = _optional_text(inactive)

    if broken_ref in (None, ""):
        warnings.append("BROKEN range missing broken_by_event_id")
        lifecycle_status = "NEEDS_REVIEW"
    elif "broken_by_event_id" in payload:
        ev_status, ev_warnings, _ev_row, storage_id = _validate_bos_event_reference(
            conn,
            broken_ref,
            symbol=symbol,
            case_id=case_id,
            raw_case_id=raw_case_id,
            case_ref=case_ref,
            direction_of_break=resolved.get("direction_of_break") or direction,
        )
        warnings.extend(ev_warnings)
        if ev_status == "NEEDS_REVIEW":
            lifecycle_status = "NEEDS_REVIEW"
        if storage_id is not None:
            resolved["broken_by_event_id"] = storage_id
        else:
            maybe_int = _optional_int(broken_ref)
            if maybe_int is not None:
                resolved["broken_by_event_id"] = maybe_int

    return lifecycle_status, warnings, resolved


def _audit_range_lifecycle_and_chain(
    conn: sqlite3.Connection,
    row: dict[str, Any],
) -> dict[str, list[str]]:
    issues: dict[str, list[str]] = {
        "broken_missing_broken_by_event_id": [],
        "broken_missing_inactive_from_time": [],
        "chain_missing_created_by_event_id": [],
        "invalid_old_range_id": [],
        "invalid_created_by_event_id": [],
        "lifecycle_needs_review": [],
    }
    range_id = int(row.get("range_id") or row.get("id"))
    symbol = str(row.get("symbol") or "XAUUSD")
    case_id = row.get("case_id")
    raw_case_id = row.get("raw_case_id")
    case_ref = row.get("case_ref")
    is_broken = _range_status_is_broken(row.get("status"))
    in_chain = _range_part_of_chain(row)

    if is_broken:
        if row.get("broken_by_event_id") in (None, ""):
            issues["broken_missing_broken_by_event_id"].append("missing broken_by_event_id")
        else:
            ev_status, ev_warnings, _ev_row, _storage_id = _validate_bos_event_reference(
                conn,
                row.get("broken_by_event_id"),
                symbol=symbol,
                case_id=case_id,
                raw_case_id=raw_case_id,
                case_ref=case_ref,
                direction_of_break=row.get("direction_of_break"),
            )
            if ev_status == "NEEDS_REVIEW":
                issues["lifecycle_needs_review"].extend(ev_warnings)
        if row.get("inactive_from_time") in (None, ""):
            issues["broken_missing_inactive_from_time"].append("missing inactive_from_time")
        if row.get("direction_of_break") in (None, ""):
            issues["lifecycle_needs_review"].append("missing direction_of_break")

    if in_chain or row.get("old_range_id") not in (None, ""):
        if row.get("old_range_id") not in (None, ""):
            try:
                old_id = int(row.get("old_range_id"))
            except Exception:
                issues["invalid_old_range_id"].append("old_range_id is not an integer")
            else:
                if old_id == range_id:
                    issues["invalid_old_range_id"].append("old_range_id equals current range_id")
                elif conn.execute("SELECT id FROM map_ranges WHERE id=?", (old_id,)).fetchone() is None:
                    issues["invalid_old_range_id"].append(f"old_range_id {old_id} does not exist")
                elif _has_old_range_chain_cycle(conn, range_id, old_id):
                    issues["invalid_old_range_id"].append("circular old_range_id chain")
        if row.get("old_range_id") not in (None, "") and row.get("created_by_event_id") in (None, ""):
            issues["chain_missing_created_by_event_id"].append("old_range_id without created_by_event_id")
        if row.get("created_by_event_id") not in (None, ""):
            ev_status, ev_warnings, _ev_row, _storage_id = _validate_bos_event_reference(
                conn,
                row.get("created_by_event_id"),
                symbol=symbol,
                case_id=case_id,
                raw_case_id=raw_case_id,
                case_ref=case_ref,
            )
            if ev_status == "NEEDS_REVIEW":
                issues["invalid_created_by_event_id"].extend(ev_warnings)

    return issues


def _find_active_range_id(conn: sqlite3.Connection, symbol: str, timeframe: str, case_id: int | None) -> int | None:
    clauses = ["symbol=?", "timeframe=?", "status!='archived'"]
    params: list[Any] = [symbol, timeframe]
    if case_id is not None:
        clauses.append("case_id=?")
        params.append(int(case_id))
    row = conn.execute(
        f"SELECT id FROM map_ranges WHERE {' AND '.join(clauses)} ORDER BY CASE WHEN status='active' THEN 0 ELSE 1 END, id DESC LIMIT 1",
        params,
    ).fetchone()
    return int(row["id"]) if row else None


def _find_parent_range(conn: sqlite3.Connection, symbol: str, timeframe: str, case_id: int | None) -> tuple[int | None, str | None]:
    parent_tf = _parent_timeframe_for(timeframe)
    if not parent_tf:
        return None, None
    parent_id = _find_active_range_id(conn, symbol, parent_tf, case_id)
    return parent_id, parent_tf


def _ensure_structural_range_for_event(conn: sqlite3.Connection, payload: dict[str, Any], event_type: str, price: float | None, event_time: Any, case_id: int | None, parent_range_id: int | None, parent_timeframe: str | None) -> int | None:
    symbol = str(payload.get("symbol") or "XAUUSD")
    timeframe = normalise_timeframe(payload.get("timeframe") or "D1")
    structural_event = str(payload.get("structural_event") or event_type or "").upper()
    active_id = payload.get("active_range_id") or payload.get("range_id")
    try:
        return int(active_id) if active_id not in (None, "") else None
    except Exception:
        pass
    # Read range high/low from payload/meta first. Range anchors are facts; analysis can decorate later.
    meta = {}
    try:
        raw_meta = payload.get("meta_json")
        meta = json.loads(raw_meta) if isinstance(raw_meta, str) and raw_meta.strip() else (raw_meta or {})
    except Exception:
        meta = {}
    high = parse_float(payload.get("range_high") or payload.get("range_high_price") or meta.get("range_high"), None)
    low = parse_float(payload.get("range_low") or payload.get("range_low_price") or meta.get("range_low"), None)
    if _is_range_high_event(event_type, structural_event):
        high = price if price is not None else high
    if _is_range_low_event(event_type, structural_event):
        low = price if price is not None else low
    range_key = str(payload.get("range_key") or (f"case_{case_id}_{timeframe}_active" if case_id is not None else "active"))
    existing = conn.execute(
        "SELECT * FROM map_ranges WHERE symbol=? AND timeframe=? AND COALESCE(range_key,'active')=? AND status!='archived' ORDER BY id DESC LIMIT 1",
        (symbol, timeframe, range_key),
    ).fetchone()
    now = now_iso()
    if existing:
        conn.execute(
            """
            UPDATE map_ranges SET
                range_high=COALESCE(?, range_high), range_low=COALESCE(?, range_low),
                range_high_time=COALESCE(?, range_high_time), range_low_time=COALESCE(?, range_low_time),
                case_id=COALESCE(?, case_id), parent_range_id=COALESCE(?, parent_range_id), parent_timeframe=COALESCE(?, parent_timeframe),
                layer=COALESCE(?, layer), active_from_time=COALESCE(active_from_time, ?), structure_version=COALESCE(structure_version, 'STRUCTURE_ONLY_V1'), updated_at=?
            WHERE id=?
            """,
            (
                high,
                low,
                event_time if _is_range_high_event(event_type, structural_event) else None,
                event_time if _is_range_low_event(event_type, structural_event) else None,
                case_id,
                parent_range_id,
                parent_timeframe,
                timeframe,
                event_time,
                now,
                existing["id"],
            ),
        )
        return int(existing["id"])
    # If one side does not exist yet, store 0 temporarily because old schema had NOT NULL constraints.
    cur = conn.execute(
        """
        INSERT INTO map_ranges(symbol,timeframe,name,range_high,range_low,range_high_time,range_low_time,bias,destination,status,range_key,notes,source,case_id,parent_range_id,layer,parent_timeframe,parent_case_id,active_from_time,structure_version,meta_json,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            symbol,
            timeframe,
            payload.get("name") or f"{symbol} {timeframe} structure range",
            high if high is not None else 0,
            low if low is not None else 0,
            event_time if _is_range_high_event(event_type, structural_event) else payload.get("range_high_time"),
            event_time if _is_range_low_event(event_type, structural_event) else payload.get("range_low_time"),
            None,
            None,
            "active",
            range_key,
            "Structure-only range; analytics derives zones/phases later.",
            payload.get("source") or "electron",
            case_id,
            parent_range_id,
            timeframe,
            parent_timeframe,
            case_id,
            payload.get("active_from_time") or payload.get("range_start_time") or event_time,
            "STRUCTURE_ONLY_V1",
            json.dumps({"created_from_event": event_type, "case_id": case_id}, ensure_ascii=False),
            now,
            now,
        ),
    )
    return int(cur.lastrowid)


def _upsert_event_features(conn: sqlite3.Connection, event_db_id: int, payload: dict[str, Any], case_id: int | None, active_range_id: int | None, parent_range_id: int | None, symbol: str, timeframe: str, event_type: str, event_time: Any, meta: dict[str, Any], zone_percent: float | None) -> None:
    now = now_iso()
    close_pct = parse_float(meta.get("close_pct"), None)
    high_pct = parse_float(meta.get("high_pct") or meta.get("pct_high"), None)
    low_pct = parse_float(meta.get("low_pct") or meta.get("pct_low"), None)
    candle_count = None
    try:
        candle_count = int(meta.get("candle_count")) if meta.get("candle_count") is not None else None
    except Exception:
        candle_count = None
    rh = parse_float(meta.get("range_high") or payload.get("range_high"), None)
    rl = parse_float(meta.get("range_low") or payload.get("range_low"), None)
    range_width = abs(rh - rl) if rh is not None and rl is not None else None
    conn.execute(
        """
        INSERT INTO event_features(event_id,case_id,range_id,parent_range_id,symbol,timeframe,event_type,event_time,close_pct,high_pct,low_pct,zone_percent,range_width,candle_count,feature_json,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(event_id) DO UPDATE SET
            case_id=excluded.case_id, range_id=excluded.range_id, parent_range_id=excluded.parent_range_id,
            close_pct=excluded.close_pct, high_pct=excluded.high_pct, low_pct=excluded.low_pct, zone_percent=excluded.zone_percent,
            range_width=excluded.range_width, candle_count=excluded.candle_count, feature_json=excluded.feature_json, updated_at=excluded.updated_at
        """,
        (event_db_id, case_id, active_range_id, parent_range_id, symbol, timeframe, event_type, event_time, close_pct, high_pct, low_pct, zone_percent, range_width, candle_count, json.dumps(meta, ensure_ascii=False, default=str), now, now),
    )


def save_map_event(payload: dict[str, Any]) -> dict[str, Any]:
    """Upsert one structure map event from Electron.

    v158 turns the event ledger into ML-grade structure facts:
    - active/parent range IDs are filled where possible
    - each case event gets a strict case_event_index
    - same-candle multi-BOS events are tagged as unknown order instead of guessed
    - flat event_features rows are maintained for stats/ML ingestion
    """
    init_db()
    now = now_iso()
    client_event_id = str(payload.get("client_event_id") or payload.get("id") or "").strip() or None
    symbol = str(payload.get("symbol") or "XAUUSD")
    timeframe = normalise_timeframe(payload.get("timeframe") or "D1")
    event_type = str(payload.get("event_type") or "CUSTOM")
    structural_event = str(payload.get("structural_event") or event_type)
    price = parse_float(payload.get("price"))
    event_time = payload.get("time")

    def _parse_meta(v):
        if isinstance(v, dict):
            return dict(v)
        if isinstance(v, str) and v.strip():
            try:
                return json.loads(v)
            except Exception:
                return {"_raw": v}
        return {}

    meta = _parse_meta(payload.get("meta_json"))
    raw_case_id = payload.get("case_id") or meta.get("case_id") or payload.get("active_case_id")
    try:
        case_id = int(raw_case_id) if raw_case_id is not None and str(raw_case_id).strip() != "" else None
    except Exception:
        case_id = None
    if case_id is not None:
        meta["case_id"] = case_id
    candidate_status = str(payload.get("candidate_status") or meta.get("candidate_status") or "").upper() or None
    if candidate_status:
        meta["candidate_status"] = candidate_status

    with connect() as conn:
        parent_range_id = payload.get("parent_range_id") or meta.get("parent_range_id")
        parent_timeframe = payload.get("parent_timeframe") or meta.get("parent_timeframe")
        try:
            parent_range_id = int(parent_range_id) if parent_range_id not in (None, "") else None
        except Exception:
            parent_range_id = None
        if parent_range_id is None:
            parent_range_id, inferred_parent_tf = _find_parent_range(conn, symbol, timeframe, case_id)
            parent_timeframe = parent_timeframe or inferred_parent_tf
        if parent_timeframe:
            meta["parent_timeframe"] = parent_timeframe
        if parent_range_id is not None:
            meta["parent_range_id"] = parent_range_id

        active_range_id = payload.get("active_range_id") or payload.get("range_id") or meta.get("active_range_id") or meta.get("range_id")
        try:
            active_range_id = int(active_range_id) if active_range_id not in (None, "") else None
        except Exception:
            active_range_id = None
        if active_range_id is None and (_is_range_high_event(event_type, structural_event) or _is_range_low_event(event_type, structural_event) or _is_bos_event(event_type, structural_event)):
            active_range_id = _ensure_structural_range_for_event(conn, payload, event_type, price, event_time, case_id, parent_range_id, parent_timeframe)
        if active_range_id is not None:
            meta["active_range_id"] = active_range_id
            meta["range_id"] = active_range_id

        case_event_index = payload.get("case_event_index") or meta.get("case_event_index")
        try:
            case_event_index = int(case_event_index) if case_event_index not in (None, "") else None
        except Exception:
            case_event_index = None
        if case_event_index is None and case_id is not None:
            row = conn.execute("SELECT COALESCE(MAX(case_event_index),0)+1 AS n FROM map_events WHERE case_id=?", (case_id,)).fetchone()
            case_event_index = int(row["n"] or 1)
        if case_event_index is not None:
            meta["case_event_index"] = case_event_index

        bar_sequence_mode = payload.get("bar_sequence_mode") or meta.get("bar_sequence_mode")
        sequence_source = payload.get("sequence_source") or meta.get("sequence_source") or ("AUTO_HTF_OHLC" if _is_bos_event(event_type, structural_event) else "USER_OR_APP")
        if not bar_sequence_mode and case_id is not None and event_time:
            same = conn.execute(
                "SELECT id,event_type FROM map_events WHERE case_id=? AND symbol=? AND timeframe=? AND time=? LIMIT 1",
                (case_id, symbol, timeframe, event_time),
            ).fetchone()
            if same and str(same["event_type"]).upper() != event_type.upper():
                bar_sequence_mode = "SAME_CANDLE_UNKNOWN"
                # Do not let the first event on the same candle pretend it had clean chronology either.
                conn.execute("UPDATE map_events SET bar_sequence_mode=COALESCE(NULLIF(bar_sequence_mode,''), 'SAME_CANDLE_UNKNOWN'), sequence_source=COALESCE(NULLIF(sequence_source,''), 'AUTO_HTF_OHLC') WHERE id=?", (same["id"],))
        bar_sequence_mode = bar_sequence_mode or "NORMAL"
        meta["bar_sequence_mode"] = bar_sequence_mode
        meta["sequence_source"] = sequence_source

        meta_json = json.dumps(meta, ensure_ascii=False, default=str) if meta else payload.get("meta_json")
        zone_percent = parse_float(payload.get("zone_percent"), None)

        old_range_id = payload.get("old_range_id")
        new_range_id = payload.get("new_range_id")
        try: old_range_id = int(old_range_id) if old_range_id not in (None, "") else None
        except Exception: old_range_id = None
        try: new_range_id = int(new_range_id) if new_range_id not in (None, "") else None
        except Exception: new_range_id = None

        if client_event_id:
            existing = conn.execute(
                "SELECT id FROM map_events WHERE client_event_id=? AND symbol=? AND timeframe=?",
                (client_event_id, symbol, timeframe),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE map_events SET
                        event_type=?, event_name=?, time=?, price=?, zone_percent=?, zone=?, notes=?, source=?,
                        candle_open=?, candle_high=?, candle_low=?, candle_close=?,
                        primitive=?, derived_event_code=?, movement_rule=?, range_status_after=?, engine_source=?, logic_version=?, candidate_id=?, confidence=?, meta_json=?, case_id=?, candidate_status=?,
                        parent_range_id=?, active_range_id=?, old_range_id=?, new_range_id=?, layer=?, parent_timeframe=?, structural_event=?, case_event_index=?, bar_sequence_mode=?, sequence_source=?, updated_at=?
                    WHERE id=?
                    """,
                    (
                        event_type, payload.get("event_name") or payload.get("label"), event_time, price, zone_percent, payload.get("zone"), payload.get("notes"), payload.get("source") or "electron",
                        parse_float(payload.get("candle_open"), None), parse_float(payload.get("candle_high"), None), parse_float(payload.get("candle_low"), None), parse_float(payload.get("candle_close"), None),
                        payload.get("primitive"), payload.get("derived_event_code"), payload.get("movement_rule"), payload.get("range_status_after"), payload.get("engine_source"), payload.get("logic_version"), payload.get("candidate_id"), payload.get("confidence"), meta_json, case_id, candidate_status,
                        parent_range_id, active_range_id, old_range_id, new_range_id, payload.get("layer") or timeframe, parent_timeframe, structural_event, case_event_index, bar_sequence_mode, sequence_source, now, existing["id"],
                    ),
                )
                if active_range_id is not None and _is_bos_event(event_type, structural_event):
                    conn.execute("UPDATE map_ranges SET broken_by_event_id=COALESCE(broken_by_event_id, ?), direction_of_break=COALESCE(direction_of_break, ?), updated_at=? WHERE id=?", (existing["id"], "UP" if str(event_type).upper().endswith("BOS_UP") else "DOWN", now, active_range_id))
                _upsert_event_features(conn, int(existing["id"]), payload, case_id, active_range_id, parent_range_id, symbol, timeframe, event_type, event_time, meta, zone_percent)
                conn.commit()
                return {"ok": True, "id": existing["id"], "client_event_id": client_event_id, "updated": True, "case_event_index": case_event_index, "active_range_id": active_range_id, "parent_range_id": parent_range_id}

        cur = conn.execute(
            """
            INSERT INTO map_events(range_id,symbol,timeframe,event_type,event_name,time,price,zone_percent,zone,notes,source,created_at,updated_at,client_event_id,candle_open,candle_high,candle_low,candle_close,primitive,derived_event_code,movement_rule,range_status_after,engine_source,logic_version,candidate_id,confidence,meta_json,case_id,candidate_status,parent_range_id,active_range_id,old_range_id,new_range_id,layer,parent_timeframe,structural_event,case_event_index,bar_sequence_mode,sequence_source)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                active_range_id, symbol, timeframe, event_type, payload.get("event_name") or payload.get("label"), event_time, price, zone_percent, payload.get("zone"), payload.get("notes"), payload.get("source") or "electron", now, now, client_event_id,
                parse_float(payload.get("candle_open"), None), parse_float(payload.get("candle_high"), None), parse_float(payload.get("candle_low"), None), parse_float(payload.get("candle_close"), None),
                payload.get("primitive"), payload.get("derived_event_code"), payload.get("movement_rule"), payload.get("range_status_after"), payload.get("engine_source"), payload.get("logic_version"), payload.get("candidate_id"), payload.get("confidence"), meta_json, case_id, candidate_status,
                parent_range_id, active_range_id, old_range_id, new_range_id, payload.get("layer") or timeframe, parent_timeframe, structural_event, case_event_index, bar_sequence_mode, sequence_source,
            ),
        )
        event_db_id = int(cur.lastrowid)
        if active_range_id is not None and _is_bos_event(event_type, structural_event):
            conn.execute("UPDATE map_ranges SET broken_by_event_id=COALESCE(broken_by_event_id, ?), direction_of_break=COALESCE(direction_of_break, ?), updated_at=? WHERE id=?", (event_db_id, "UP" if str(event_type).upper().endswith("BOS_UP") else "DOWN", now, active_range_id))
        _upsert_event_features(conn, event_db_id, payload, case_id, active_range_id, parent_range_id, symbol, timeframe, event_type, event_time, meta, zone_percent)
        conn.commit()
        return {"ok": True, "id": event_db_id, "client_event_id": client_event_id, "created": True, "case_event_index": case_event_index, "active_range_id": active_range_id, "parent_range_id": parent_range_id}


ALLOWED_STRUCTURAL_EVENT_TYPES = {
    "RANGE_CREATED",
    "RANGE_HIGH_SELECTED",
    "RANGE_LOW_SELECTED",
    "BREAK_HIGH_SELECTED",
    "BREAK_LOW_SELECTED",
    "BOS_UP",
    "BOS_DOWN",
    "ACTIVE_RANGE_CHANGED",
    "OLD_RANGE_SAVED",
    "RANGE_REBASED",
    "RANGE_ABANDONED",
}


def _meta_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return dict(parsed) if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _event_is_undone(row: sqlite3.Row | dict[str, Any]) -> bool:
    d = dict(row)
    meta = _meta_dict(d.get("meta_json"))
    return bool(meta.get("undone") or meta.get("deleted_at"))


def save_structural_map_event(payload: dict[str, Any]) -> dict[str, Any]:
    init_db()
    now = now_iso()
    event_type = str(payload.get("event_type") or payload.get("structural_event") or "").upper()
    if event_type not in ALLOWED_STRUCTURAL_EVENT_TYPES:
        return {"ok": False, "status": 400, "error": f"Invalid structural event_type: {event_type}"}

    symbol = str(payload.get("symbol") or "XAUUSD")
    source_timeframe = normalise_timeframe(str(payload.get("source_timeframe") or payload.get("timeframe") or "D1"))
    chart_timeframe = normalise_timeframe(str(payload.get("chart_timeframe") or payload.get("timeframe") or source_timeframe))
    structure_layer = _normalise_structure_layer(payload.get("structure_layer"), source_timeframe)
    active_range_id = payload.get("active_range_id") or payload.get("range_id")
    parent_range_id = payload.get("parent_range_id")
    case_id, raw_case_id, case_ref = _case_refs_from_payload(payload)

    try:
        active_range_id_int = int(active_range_id) if active_range_id not in (None, "") else None
    except Exception:
        return {"ok": False, "status": 400, "error": "active_range_id must be an integer when supplied"}
    try:
        parent_range_id_int = int(parent_range_id) if parent_range_id not in (None, "") else None
    except Exception:
        return {"ok": False, "status": 400, "error": "parent_range_id must be an integer when supplied"}

    break_level_type = str(payload.get("break_level_type") or "").upper() or None
    break_level_price = parse_float(payload.get("break_level_price"), None)
    if event_type == "BOS_UP":
        if break_level_type != "BH" or break_level_price is None:
            return {"ok": False, "status": 400, "error": "BOS_UP requires break_level_type=BH and break_level_price"}
    if event_type == "BOS_DOWN":
        if break_level_type != "BL" or break_level_price is None:
            return {"ok": False, "status": 400, "error": "BOS_DOWN requires break_level_type=BL and break_level_price"}

    event_id = str(payload.get("event_id") or str(uuid.uuid4()))
    event_time = payload.get("event_time") or payload.get("time") or payload.get("candle_time") or now
    event_price = parse_float(payload.get("event_price", payload.get("price", break_level_price)), 0)
    meta_json = json.dumps(payload.get("meta_json"), ensure_ascii=False, default=str) if isinstance(payload.get("meta_json"), dict) else payload.get("meta_json")

    with connect() as conn:
        if active_range_id_int is not None:
            active = conn.execute("SELECT * FROM map_ranges WHERE id=?", (active_range_id_int,)).fetchone()
            if active is None:
                return {"ok": False, "status": 400, "error": "active_range_id does not exist"}
            if str(active["symbol"]) != symbol:
                return {"ok": False, "status": 400, "error": "active range symbol does not match event symbol"}
        if parent_range_id_int is not None:
            parent = conn.execute("SELECT * FROM map_ranges WHERE id=?", (parent_range_id_int,)).fetchone()
            if parent is None:
                return {"ok": False, "status": 400, "error": "parent_range_id does not exist"}
            if str(parent["symbol"]) != symbol:
                return {"ok": False, "status": 400, "error": "parent range symbol does not match event symbol"}

        existing = conn.execute("SELECT * FROM map_events WHERE event_id=?", (event_id,)).fetchone()
        if existing:
            return {"ok": True, "duplicate": True, "event": _event_row_to_dict(existing)}

        cur = conn.execute(
            """
            INSERT INTO map_events(range_id,symbol,timeframe,event_type,event_name,time,price,notes,source,created_at,updated_at,event_id,case_id,raw_case_id,case_ref,structure_layer,chart_timeframe,source_timeframe,active_range_id,parent_range_id,old_range_id,new_range_id,structural_event,break_level_type,break_level_price,break_level_time,event_time,event_price,candle_time,candle_open,candle_high,candle_low,candle_close,direction,calculation_engine_version,ruleset_version,meta_json)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                active_range_id_int,
                symbol,
                source_timeframe,
                event_type,
                payload.get("event_name") or event_type,
                event_time,
                event_price,
                payload.get("notes"),
                payload.get("source") or "backend-structural",
                now,
                now,
                event_id,
                case_id,
                raw_case_id,
                case_ref,
                structure_layer,
                chart_timeframe,
                source_timeframe,
                active_range_id_int,
                parent_range_id_int,
                payload.get("old_range_id"),
                payload.get("new_range_id"),
                payload.get("structural_event") or event_type,
                break_level_type,
                break_level_price,
                payload.get("break_level_time"),
                event_time,
                event_price,
                payload.get("candle_time") or event_time,
                parse_float(payload.get("candle_open"), None),
                parse_float(payload.get("candle_high"), None),
                parse_float(payload.get("candle_low"), None),
                parse_float(payload.get("candle_close"), None),
                payload.get("direction"),
                payload.get("calculation_engine_version"),
                payload.get("ruleset_version"),
                meta_json,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM map_events WHERE id=?", (cur.lastrowid,)).fetchone()
    return {"ok": True, "id": cur.lastrowid, "event_id": event_id, "event": _event_row_to_dict(row)}


def get_map_events(symbol: str = "XAUUSD", timeframe: str | None = None, limit: int = 1000, case_id: int | None = None, raw_case_id: str | None = None, case_ref: str | None = None, structure_layer: str | None = None, source_timeframe: str | None = None, active_range_id: int | None = None, parent_range_id: int | None = None, event_type: str | None = None) -> dict[str, Any]:
    init_db()
    limit = max(1, min(int(limit or 1000), 5000))
    clauses = ["symbol=?"]
    args: list[Any] = [symbol]
    tf = normalise_timeframe(timeframe) if timeframe else None
    if tf:
        clauses.append("timeframe=?")
        args.append(tf)
    if case_id is not None:
        clauses.append("case_id=?")
        args.append(int(case_id))
    if raw_case_id:
        clauses.append("raw_case_id=?")
        args.append(str(raw_case_id))
    if case_ref:
        clauses.append("case_ref=?")
        args.append(str(case_ref))
    if structure_layer:
        clauses.append("COALESCE(structure_layer, layer)=?")
        args.append(_normalise_structure_layer(structure_layer, source_timeframe or timeframe or "D1"))
    if source_timeframe:
        clauses.append("COALESCE(source_timeframe, timeframe)=?")
        args.append(normalise_timeframe(source_timeframe))
    if active_range_id is not None:
        clauses.append("active_range_id=?")
        args.append(int(active_range_id))
    if parent_range_id is not None:
        clauses.append("parent_range_id=?")
        args.append(int(parent_range_id))
    if event_type:
        clauses.append("event_type=?")
        args.append(str(event_type).upper())
    sql = f"SELECT * FROM map_events WHERE {' AND '.join(clauses)} ORDER BY COALESCE(event_time, time, created_at) ASC, id ASC LIMIT ?"
    args.append(limit)
    with connect() as conn:
        rows = conn.execute(sql, args).fetchall()
    events = [_event_row_to_dict(r) for r in rows if not _event_is_undone(r)]
    return {"ok": True, "symbol": symbol, "timeframe": tf, "case_id": case_id, "raw_case_id": raw_case_id, "case_ref": case_ref, "structure_layer": structure_layer, "source_timeframe": source_timeframe, "active_range_id": active_range_id, "parent_range_id": parent_range_id, "event_type": event_type, "count": len(events), "events": events}



def save_htf_state_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    init_db()
    now = now_iso()
    symbol = str(payload.get("symbol") or "XAUUSD")
    timeframe = normalise_timeframe(payload.get("timeframe") or "D1")
    state = payload.get("state") or {}
    state_json = state if isinstance(state, str) else json.dumps(state, default=str)
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO htf_state_snapshots(symbol,timeframe,case_id,range_id,range_high,range_low,range_start_time,range_end_time,state_json,logic_version,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                symbol,
                timeframe,
                payload.get("case_id"),
                payload.get("range_id"),
                parse_float(payload.get("range_high"), None),
                parse_float(payload.get("range_low"), None),
                payload.get("range_start_time"),
                payload.get("range_end_time"),
                state_json,
                payload.get("logic_version") or "htf_semi_auto_v087_8",
                now,
                now,
            ),
        )
        conn.commit()
        return {"ok": True, "id": cur.lastrowid, "symbol": symbol, "timeframe": timeframe}


def get_htf_state_snapshots(symbol: str = "XAUUSD", timeframe: str = "D1", limit: int = 50) -> dict[str, Any]:
    init_db()
    tf = normalise_timeframe(timeframe)
    limit = max(1, min(int(limit or 50), 500))
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM htf_state_snapshots
            WHERE symbol=? AND timeframe=?
            ORDER BY id DESC
            LIMIT ?
            """,
            (symbol, tf, limit),
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["state"] = json.loads(d.get("state_json") or "{}")
        except Exception:
            d["state"] = d.get("state_json")
        out.append(d)
    return {"ok": True, "symbol": symbol, "timeframe": tf, "count": len(out), "states": out}


def delete_map_event(event_id: str) -> dict[str, Any]:
    init_db()
    with connect() as conn:
        cur = conn.execute("DELETE FROM map_events WHERE client_event_id=?", (str(event_id),))
        deleted = cur.rowcount
        if not deleted:
            try:
                numeric_id = int(str(event_id))
                cur = conn.execute("DELETE FROM map_events WHERE id=?", (numeric_id,))
                deleted = cur.rowcount
            except Exception:
                pass
        conn.commit()
    return {"ok": True, "deleted": deleted, "event_id": event_id}


def clear_map_events_for_candle(symbol: str, timeframe: str, time: str) -> dict[str, Any]:
    init_db()
    tf = normalise_timeframe(timeframe)
    with connect() as conn:
        cur = conn.execute("DELETE FROM map_events WHERE symbol=? AND timeframe=? AND time=?", (symbol, tf, time))
        deleted = cur.rowcount
        conn.commit()
    return {"ok": True, "deleted": deleted, "symbol": symbol, "timeframe": tf, "time": time}


def _range_row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return _range_row_to_structural_dict(row)


def upsert_map_range(payload: dict[str, Any]) -> dict[str, Any]:
    init_db()
    now = now_iso()
    symbol = str(payload.get("symbol") or "XAUUSD")
    source_timeframe = normalise_timeframe(str(payload.get("source_timeframe") or payload.get("timeframe") or "D1"))
    chart_timeframe = normalise_timeframe(str(payload.get("chart_timeframe") or payload.get("timeframe") or source_timeframe))
    timeframe = source_timeframe
    structure_layer = _normalise_structure_layer(payload.get("structure_layer") or payload.get("layer"), source_timeframe)
    range_key = str(payload.get("range_key") or "active")
    high_price = parse_float(payload.get("range_high_price", payload.get("range_high")), None)
    low_price = parse_float(payload.get("range_low_price", payload.get("range_low")), None)
    parent_range_id = payload.get("parent_range_id")
    case_id, raw_case_id, case_ref = _case_refs_from_payload(payload)
    parent_case_id = payload.get("parent_case_id") or case_id
    parent_timeframe = payload.get("parent_timeframe") or (_source_timeframe_for_layer(_expected_parent_layer(structure_layer)) if _expected_parent_layer(structure_layer) else None)
    meta_json = json.dumps(payload.get("meta_json"), ensure_ascii=False, default=str) if isinstance(payload.get("meta_json"), dict) else payload.get("meta_json")

    with connect() as conn:
        range_id = payload.get("range_id") or payload.get("id")
        existing = None
        if range_id not in (None, ""):
            try:
                existing = conn.execute("SELECT * FROM map_ranges WHERE id=?", (int(range_id),)).fetchone()
            except Exception:
                existing = None
        if existing is None:
            lookup_clauses = ["symbol=?", "timeframe=?", "COALESCE(range_key,'active')=?", "status!='archived'"]
            lookup_args: list[Any] = [symbol, timeframe, range_key]
            if case_id is not None:
                lookup_clauses.append("case_id=?")
                lookup_args.append(case_id)
            if raw_case_id:
                lookup_clauses.append("raw_case_id=?")
                lookup_args.append(raw_case_id)
            if case_ref:
                lookup_clauses.append("case_ref=?")
                lookup_args.append(case_ref)
            existing = conn.execute(
                f"SELECT * FROM map_ranges WHERE {' AND '.join(lookup_clauses)} ORDER BY id DESC LIMIT 1",
                lookup_args,
            ).fetchone()

        child_id = int(existing["id"]) if existing else None
        parent_link_status, validation_warnings, parent = _validate_parent_link(
            conn,
            child_id=child_id,
            symbol=symbol,
            case_id=case_id,
            raw_case_id=raw_case_id,
            case_ref=case_ref,
            structure_layer=structure_layer,
            parent_range_id=parent_range_id,
        )
        if parent is not None:
            parent_timeframe = parent_timeframe or _range_source_timeframe(parent)
            parent_case_id = parent_case_id or parent["case_id"]
        if parent_link_status == "INVALID_PARENT":
            return {"ok": False, "status": 400, "error": "Invalid parent_range_id", "warnings": validation_warnings, "parent_link_status": parent_link_status}

        merged_payload = {**(dict(existing) if existing else {}), **payload}
        lifecycle_status, lifecycle_warnings, lifecycle_resolved = _validate_range_lifecycle_fields(
            conn,
            payload,
            merged_payload,
            symbol=symbol,
            case_id=case_id,
            raw_case_id=raw_case_id,
            case_ref=case_ref,
        )
        chain_status, chain_warnings, chain_resolved = _validate_range_chain_fields(
            conn,
            child_id,
            payload,
            merged_payload,
            symbol=symbol,
            case_id=case_id,
            raw_case_id=raw_case_id,
            case_ref=case_ref,
        )
        if chain_status == "INVALID_CHAIN":
            return {
                "ok": False,
                "status": 400,
                "error": "Invalid range chain fields",
                "warnings": validation_warnings + lifecycle_warnings + chain_warnings,
                "parent_link_status": parent_link_status,
                "chain_validation_status": chain_status,
            }
        combined_warnings = validation_warnings + lifecycle_warnings + chain_warnings
        for key, value in {**lifecycle_resolved, **chain_resolved}.items():
            payload[key] = value
        effective_status = _apply_active_lifecycle_normalization(payload, merged_payload, lifecycle_resolved)

        if existing:
            conn.execute(
                """
                UPDATE map_ranges SET
                    range_high=COALESCE(?, range_high), range_low=COALESCE(?, range_low),
                    range_high_price=COALESCE(?, range_high_price), range_low_price=COALESCE(?, range_low_price),
                    range_high_time=COALESCE(?, range_high_time), range_low_time=COALESCE(?, range_low_time),
                    break_high_price=COALESCE(?, break_high_price), break_low_price=COALESCE(?, break_low_price),
                    break_high_time=COALESCE(?, break_high_time), break_low_time=COALESCE(?, break_low_time),
                    range_start_time=COALESCE(?, range_start_time), range_end_time=COALESCE(?, range_end_time),
                    duration_minutes=COALESCE(?, duration_minutes), status=COALESCE(?, status),
                    ref_high_price=COALESCE(?, ref_high_price), ref_high_time=COALESCE(?, ref_high_time), ref_low_price=COALESCE(?, ref_low_price), ref_low_time=COALESCE(?, ref_low_time),
                    bias=COALESCE(?, bias), destination=COALESCE(?, destination), notes=COALESCE(?, notes), source=COALESCE(?, source),
                    case_id=COALESCE(?, case_id), raw_case_id=COALESCE(?, raw_case_id), case_ref=COALESCE(?, case_ref), parent_range_id=?, layer=COALESCE(?, layer), structure_layer=COALESCE(?, structure_layer),
                    chart_timeframe=COALESCE(?, chart_timeframe), source_timeframe=COALESCE(?, source_timeframe), parent_timeframe=COALESCE(?, parent_timeframe),
                    parent_case_id=COALESCE(?, parent_case_id), created_by_event_id=COALESCE(?, created_by_event_id), broken_by_event_id=COALESCE(?, broken_by_event_id),
                    direction_of_break=COALESCE(?, direction_of_break), active_from_time=COALESCE(?, active_from_time), inactive_from_time=COALESCE(?, inactive_from_time),
                    old_range_id=COALESCE(?, old_range_id), new_range_id=COALESCE(?, new_range_id), structure_version=COALESCE(?, structure_version),
                    parent_link_status=?, meta_json=COALESCE(?, meta_json), updated_at=?
                WHERE id=?
                """,
                (
                    high_price,
                    low_price,
                    high_price,
                    low_price,
                    payload.get("range_high_time"),
                    payload.get("range_low_time"),
                    parse_float(payload.get("break_high_price"), None),
                    parse_float(payload.get("break_low_price"), None),
                    payload.get("break_high_time"),
                    payload.get("break_low_time"),
                    payload.get("range_start_time"),
                    payload.get("range_end_time"),
                    payload.get("duration_minutes"),
                    effective_status,
                    parse_float(payload.get("ref_high_price"), None),
                    payload.get("ref_high_time"),
                    parse_float(payload.get("ref_low_price"), None),
                    payload.get("ref_low_time"),
                    payload.get("bias"),
                    payload.get("destination"),
                    payload.get("notes"),
                    payload.get("source") or "electron",
                    case_id,
                    raw_case_id,
                    case_ref,
                    parent_range_id,
                    payload.get("layer") or timeframe,
                    structure_layer,
                    chart_timeframe,
                    source_timeframe,
                    parent_timeframe,
                    parent_case_id,
                    payload.get("created_by_event_id"),
                    _write_broken_by_event_id(payload, effective_status),
                    _write_direction_of_break(payload, effective_status),
                    payload.get("active_from_time") or payload.get("range_start_time"),
                    _write_inactive_from_time(payload, effective_status),
                    payload.get("old_range_id"),
                    payload.get("new_range_id"),
                    payload.get("structure_version") or "STRUCTURE_ONLY_V1",
                    parent_link_status,
                    meta_json,
                    now,
                    existing["id"],
                ),
            )
            if effective_status == "ACTIVE":
                conn.execute(
                    "UPDATE map_ranges SET broken_by_event_id=NULL, direction_of_break=NULL, inactive_from_time=NULL WHERE id=?",
                    (existing["id"],),
                )
            conn.commit()
            row = conn.execute("SELECT * FROM map_ranges WHERE id=?", (existing["id"],)).fetchone()
            return {
                "ok": True,
                "id": existing["id"],
                "range_id": existing["id"],
                "updated": True,
                "parent_link_status": parent_link_status,
                "lifecycle_validation_status": lifecycle_status,
                "chain_validation_status": chain_status,
                "warnings": combined_warnings,
                "range": _range_row_to_dict(row),
            }

        # map_ranges columns range_high/range_low are NOT NULL from the earlier prototype.
        # If only one anchor exists, store 0 for missing side and let frontend replace it later.
        cur = conn.execute(
            """
            INSERT INTO map_ranges(symbol,timeframe,name,range_high,range_low,range_high_price,range_low_price,range_high_time,range_low_time,break_high_price,break_low_price,break_high_time,break_low_time,range_start_time,range_end_time,duration_minutes,ref_high_price,ref_high_time,ref_low_price,ref_low_time,bias,destination,status,range_key,notes,source,case_id,raw_case_id,case_ref,parent_range_id,layer,structure_layer,chart_timeframe,source_timeframe,parent_timeframe,parent_case_id,created_by_event_id,broken_by_event_id,direction_of_break,active_from_time,inactive_from_time,old_range_id,new_range_id,structure_version,parent_link_status,meta_json,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                symbol,
                timeframe,
                payload.get("name") or f"{symbol} {timeframe} active range",
                high_price if high_price is not None else 0,
                low_price if low_price is not None else 0,
                high_price,
                low_price,
                payload.get("range_high_time"),
                payload.get("range_low_time"),
                parse_float(payload.get("break_high_price"), None),
                parse_float(payload.get("break_low_price"), None),
                payload.get("break_high_time"),
                payload.get("break_low_time"),
                payload.get("range_start_time"),
                payload.get("range_end_time"),
                payload.get("duration_minutes"),
                parse_float(payload.get("ref_high_price"), None),
                payload.get("ref_high_time"),
                parse_float(payload.get("ref_low_price"), None),
                payload.get("ref_low_time"),
                payload.get("bias"),
                payload.get("destination"),
                effective_status,
                range_key,
                payload.get("notes"),
                payload.get("source") or "electron",
                case_id,
                raw_case_id,
                case_ref,
                parent_range_id,
                payload.get("layer") or timeframe,
                structure_layer,
                chart_timeframe,
                source_timeframe,
                parent_timeframe,
                parent_case_id,
                payload.get("created_by_event_id"),
                _write_broken_by_event_id(payload, effective_status),
                _write_direction_of_break(payload, effective_status),
                payload.get("active_from_time") or payload.get("range_start_time"),
                _write_inactive_from_time(payload, effective_status),
                payload.get("old_range_id"),
                payload.get("new_range_id"),
                payload.get("structure_version") or "STRUCTURE_ONLY_V1",
                parent_link_status,
                meta_json,
                now,
                now,
            ),
        )
        if effective_status == "ACTIVE":
            conn.execute(
                "UPDATE map_ranges SET broken_by_event_id=NULL, direction_of_break=NULL, inactive_from_time=NULL WHERE id=?",
                (cur.lastrowid,),
            )
        conn.commit()
        row = conn.execute("SELECT * FROM map_ranges WHERE id=?", (cur.lastrowid,)).fetchone()
        return {
            "ok": True,
            "id": cur.lastrowid,
            "range_id": cur.lastrowid,
            "created": True,
            "parent_link_status": parent_link_status,
            "lifecycle_validation_status": lifecycle_status,
            "chain_validation_status": chain_status,
            "warnings": combined_warnings,
            "range": _range_row_to_dict(row),
        }


def get_map_range(symbol: str = "XAUUSD", timeframe: str = "D1", range_key: str = "active") -> dict[str, Any]:
    init_db()
    tf = normalise_timeframe(timeframe)
    with connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM map_ranges
            WHERE symbol=? AND timeframe=? AND COALESCE(range_key,'active')=? AND status!='archived'
            ORDER BY updated_at DESC, id DESC LIMIT 1
            """,
            (symbol, tf, range_key),
        ).fetchone()
    return {"ok": True, "symbol": symbol, "timeframe": tf, "range": _range_row_to_dict(row)}


def list_map_ranges(symbol: str = "XAUUSD", timeframe: str | None = None, case_id: int | None = None, raw_case_id: str | None = None, case_ref: str | None = None, limit: int = 1000, structure_layer: str | None = None, source_timeframe: str | None = None, parent_range_id: int | None = None) -> dict[str, Any]:
    """Return structural ranges for a symbol/case/timeframe.

    This is the boring-but-useful range ledger Amy/analytics will read later.
    It intentionally does not store sweeps/P2/OB labels. Those get derived.
    """
    init_db()
    limit = max(1, min(int(limit or 1000), 5000))
    clauses = ["symbol=?"]
    args: list[Any] = [symbol]
    if timeframe:
        clauses.append("timeframe=?")
        args.append(normalise_timeframe(timeframe))
    if case_id is not None:
        clauses.append("case_id=?")
        args.append(int(case_id))
    if raw_case_id:
        clauses.append("raw_case_id=?")
        args.append(str(raw_case_id))
    if case_ref:
        clauses.append("case_ref=?")
        args.append(str(case_ref))
    if structure_layer:
        layer = _normalise_structure_layer(structure_layer, source_timeframe or timeframe or "D1")
        clauses.append("COALESCE(structure_layer, layer)=?")
        args.append(layer)
    if source_timeframe:
        tf = normalise_timeframe(source_timeframe)
        clauses.append("COALESCE(source_timeframe, timeframe)=?")
        args.append(tf)
    if parent_range_id is not None:
        clauses.append("parent_range_id=?")
        args.append(int(parent_range_id))
    sql = f"SELECT * FROM map_ranges WHERE {' AND '.join(clauses)} ORDER BY COALESCE(range_start_time, active_from_time, created_at) ASC, id ASC LIMIT ?"
    args.append(limit)
    with connect() as conn:
        rows = conn.execute(sql, args).fetchall()
        ranges = []
        for r in rows:
            d = _range_row_to_dict(r)
            if d is None:
                continue
            status, warnings, _ = _validate_parent_link(
                conn,
                child_id=int(d["range_id"]),
                symbol=str(d["symbol"]),
                case_id=d.get("case_id"),
                raw_case_id=d.get("raw_case_id"),
                case_ref=d.get("case_ref"),
                structure_layer=str(d.get("structure_layer") or ""),
                parent_range_id=d.get("parent_range_id"),
            )
            d["parent_link_status"] = d.get("parent_link_status") if d.get("parent_link_status") not in (None, "", "NEEDS_REVIEW") else status
            if warnings:
                d["parent_link_warnings"] = warnings
            ranges.append(d)
    return {"ok": True, "symbol": symbol, "timeframe": timeframe, "case_id": case_id, "raw_case_id": raw_case_id, "case_ref": case_ref, "structure_layer": structure_layer, "source_timeframe": source_timeframe, "parent_range_id": parent_range_id, "count": len(ranges), "ranges": ranges}


def get_range_tree(symbol: str = "XAUUSD", case_id: int | None = None, raw_case_id: str | None = None, case_ref: str | None = None, parent_timeframe: str = "W1", child_timeframe: str = "D1", parent_layer: str | None = None, child_layer: str | None = None) -> dict[str, Any]:
    """Return parent->child structural range hierarchy for adjacent structure layers."""
    init_db()
    parent_tf = normalise_timeframe(parent_timeframe)
    child_tf = normalise_timeframe(child_timeframe)
    parent_l = _normalise_structure_layer(parent_layer, parent_tf) if parent_layer else _structure_layer_for_timeframe(parent_tf)
    child_l = _normalise_structure_layer(child_layer, child_tf) if child_layer else _structure_layer_for_timeframe(child_tf)
    parent_result = list_map_ranges(symbol=symbol, case_id=case_id, raw_case_id=raw_case_id, case_ref=case_ref, structure_layer=parent_l, source_timeframe=parent_tf, limit=5000)
    child_result = list_map_ranges(symbol=symbol, case_id=case_id, raw_case_id=raw_case_id, case_ref=case_ref, structure_layer=child_l, source_timeframe=child_tf, limit=5000)
    parents = parent_result.get("ranges") or []
    children = child_result.get("ranges") or []
    by_parent: dict[str, list[dict[str, Any]]] = {}
    orphans: list[dict[str, Any]] = []
    for child in children:
        pid = child.get("parent_range_id")
        if pid is None or str(pid) == "":
            orphans.append(child)
        else:
            by_parent.setdefault(str(pid), []).append(child)
    tree = []
    for parent in parents:
        tree.append({"parent": parent, "children": by_parent.get(str(parent.get("range_id") or parent.get("id")), [])})
    return {
        "ok": True,
        "symbol": symbol,
        "case_id": case_id,
        "raw_case_id": raw_case_id,
        "case_ref": case_ref,
        "parent_layer": parent_l,
        "child_layer": child_l,
        "parent_timeframe": parent_tf,
        "child_timeframe": child_tf,
        "parents": len(parents),
        "children": len(children),
        "orphans": orphans,
        "tree": tree,
    }


def reparent_map_range(child_range_id: int, parent_range_id: int | None) -> dict[str, Any]:
    init_db()
    now = now_iso()
    with connect() as conn:
        child = conn.execute("SELECT * FROM map_ranges WHERE id=?", (int(child_range_id),)).fetchone()
        if child is None:
            return {"ok": False, "status": 404, "error": "Child range not found"}
        status, warnings, parent = _validate_parent_link(
            conn,
            child_id=int(child_range_id),
            symbol=str(child["symbol"]),
            case_id=child["case_id"],
            raw_case_id=child["raw_case_id"] if "raw_case_id" in child.keys() else None,
            case_ref=child["case_ref"] if "case_ref" in child.keys() else None,
            structure_layer=_range_layer(child),
            parent_range_id=parent_range_id,
        )
        if status == "INVALID_PARENT":
            return {"ok": False, "status": 400, "error": "Invalid parent_range_id", "warnings": warnings, "parent_link_status": status}
        conn.execute(
            "UPDATE map_ranges SET parent_range_id=?, parent_timeframe=?, parent_case_id=?, parent_link_status=?, updated_at=? WHERE id=?",
            (
                parent_range_id,
                _range_source_timeframe(parent) if parent is not None else None,
                parent["case_id"] if parent is not None else None,
                status,
                now,
                int(child_range_id),
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM map_ranges WHERE id=?", (int(child_range_id),)).fetchone()
    return {"ok": True, "range_id": int(child_range_id), "parent_range_id": parent_range_id, "parent_link_status": status, "warnings": warnings, "range": _range_row_to_dict(row)}


def hierarchy_audit(symbol: str = "XAUUSD", case_id: int | None = None, raw_case_id: str | None = None, case_ref: str | None = None) -> dict[str, Any]:
    init_db()
    clauses = ["symbol=?"]
    args: list[Any] = [symbol]
    if case_id is not None:
        clauses.append("case_id=?")
        args.append(int(case_id))
    if raw_case_id:
        clauses.append("raw_case_id=?")
        args.append(str(raw_case_id))
    if case_ref:
        clauses.append("case_ref=?")
        args.append(str(case_ref))
    where = " AND ".join(clauses)

    with connect() as conn:
        ranges = [_range_row_to_structural_dict(r) for r in conn.execute(f"SELECT * FROM map_ranges WHERE {where} ORDER BY id ASC", args).fetchall()]
        events = [dict(r) for r in conn.execute(f"SELECT * FROM map_events WHERE {where} ORDER BY id ASC", args).fetchall() if not _event_is_undone(r)]

        counts_by_layer = {layer: 0 for layer in STRUCTURE_LAYER_ORDER}
        orphan_weekly: list[dict[str, Any]] = []
        orphan_daily: list[dict[str, Any]] = []
        orphan_intraday: list[dict[str, Any]] = []
        invalid_parent_links: list[dict[str, Any]] = []
        needs_parent_review: list[dict[str, Any]] = []
        missing_rh_rl: list[dict[str, Any]] = []
        broken_missing_broken_by_event_id: list[dict[str, Any]] = []
        broken_missing_inactive_from_time: list[dict[str, Any]] = []
        chain_missing_created_by_event_id: list[dict[str, Any]] = []
        invalid_old_range_id_rows: list[dict[str, Any]] = []
        invalid_created_by_event_id_rows: list[dict[str, Any]] = []
        lifecycle_needs_review: list[dict[str, Any]] = []
        weekly_linked_macro = 0
        daily_linked_weekly = 0
        intraday_linked_daily = 0
        macro_exists_in_case = any(
            _normalise_structure_layer(r.get("structure_layer"), r.get("source_timeframe")) == "MACRO"
            for r in ranges
        )

        for r in ranges:
            layer = _normalise_structure_layer(r.get("structure_layer"), r.get("source_timeframe"))
            counts_by_layer[layer] = counts_by_layer.get(layer, 0) + 1
            status, warnings, parent = _validate_parent_link(
                conn,
                child_id=int(r["range_id"]),
                symbol=str(r["symbol"]),
                case_id=r.get("case_id"),
                raw_case_id=r.get("raw_case_id"),
                case_ref=r.get("case_ref"),
                structure_layer=layer,
                parent_range_id=r.get("parent_range_id"),
            )
            r["parent_link_status"] = status
            if warnings:
                r["parent_link_warnings"] = warnings
            if layer == "WEEKLY" and status == "ORPHAN":
                orphan_weekly.append(r)
            if layer == "DAILY" and status == "ORPHAN":
                orphan_daily.append(r)
            if layer == "INTRADAY" and status == "ORPHAN":
                orphan_intraday.append(r)
            if status == "INVALID_PARENT":
                invalid_parent_links.append({"range": r, "warnings": warnings})
            if status == "NEEDS_REVIEW":
                needs_parent_review.append({"range": r, "warnings": warnings})
            if layer == "WEEKLY" and r.get("parent_range_id") not in (None, "") and parent is not None and _range_layer(parent) == "MACRO":
                weekly_linked_macro += 1
            if layer == "DAILY" and r.get("parent_range_id") not in (None, "") and parent is not None and _range_layer(parent) == "WEEKLY":
                daily_linked_weekly += 1
            if layer == "INTRADAY" and r.get("parent_range_id") not in (None, "") and parent is not None and _range_layer(parent) == "DAILY":
                intraday_linked_daily += 1
            if _range_price(r, "HIGH") in (None, 0) or _range_price(r, "LOW") in (None, 0):
                missing_rh_rl.append(r)

            lifecycle_issues = _audit_range_lifecycle_and_chain(conn, r)
            if lifecycle_issues.get("broken_missing_broken_by_event_id"):
                broken_missing_broken_by_event_id.append({"range": r, "issues": lifecycle_issues["broken_missing_broken_by_event_id"]})
            if lifecycle_issues.get("broken_missing_inactive_from_time"):
                broken_missing_inactive_from_time.append({"range": r, "issues": lifecycle_issues["broken_missing_inactive_from_time"]})
            if lifecycle_issues.get("chain_missing_created_by_event_id"):
                chain_missing_created_by_event_id.append({"range": r, "issues": lifecycle_issues["chain_missing_created_by_event_id"]})
            if lifecycle_issues.get("invalid_old_range_id"):
                invalid_old_range_id_rows.append({"range": r, "issues": lifecycle_issues["invalid_old_range_id"]})
            if lifecycle_issues.get("invalid_created_by_event_id"):
                invalid_created_by_event_id_rows.append({"range": r, "issues": lifecycle_issues["invalid_created_by_event_id"]})
            if lifecycle_issues.get("lifecycle_needs_review"):
                lifecycle_needs_review.append({"range": r, "issues": lifecycle_issues["lifecycle_needs_review"]})

        orphan_weekly_without_macro_parent = orphan_weekly if macro_exists_in_case else []
        legacy_weekly_root_ranges = orphan_weekly if not macro_exists_in_case else []

        bos_missing_bh_bl = []
        events_without_active_range = []
        for ev in events:
            event_type = str(ev.get("event_type") or ev.get("structural_event") or "").upper()
            bos_type = _normalise_bos_event_type(ev.get("event_type"), ev.get("structural_event"))
            if bos_type in {"BOS_UP", "BOS_DOWN"}:
                expected = "BH" if bos_type == "BOS_UP" else "BL"
                if str(ev.get("break_level_type") or "").upper() != expected or ev.get("break_level_price") in (None, ""):
                    bos_missing_bh_bl.append(ev)
            if ev.get("active_range_id") in (None, "") and bos_type in {"BOS_UP", "BOS_DOWN"}:
                events_without_active_range.append(ev)

    macro_weekly_tree = get_range_tree(
        symbol=symbol,
        case_id=case_id,
        raw_case_id=raw_case_id,
        case_ref=case_ref,
        parent_timeframe="MN1",
        child_timeframe="W1",
        parent_layer="MACRO",
        child_layer="WEEKLY",
    )
    weekly_daily_tree = get_range_tree(
        symbol=symbol,
        case_id=case_id,
        raw_case_id=raw_case_id,
        case_ref=case_ref,
        parent_timeframe="W1",
        child_timeframe="D1",
        parent_layer="WEEKLY",
        child_layer="DAILY",
    )
    warnings = []
    if orphan_weekly_without_macro_parent:
        warnings.append({"code": "ORPHAN_WEEKLY_WITHOUT_MACRO_PARENT", "count": len(orphan_weekly_without_macro_parent)})
    if legacy_weekly_root_ranges:
        warnings.append({"code": "LEGACY_WEEKLY_ROOT_RANGES", "count": len(legacy_weekly_root_ranges), "note": "Weekly ranges without Macro parent in a case with no Macro ranges yet"})
    if orphan_daily:
        warnings.append({"code": "ORPHAN_DAILY_RANGES", "count": len(orphan_daily)})
    if orphan_intraday:
        warnings.append({"code": "ORPHAN_INTRADAY_RANGES", "count": len(orphan_intraday)})
    if needs_parent_review:
        warnings.append({"code": "RANGES_NEEDING_PARENT_REVIEW", "count": len(needs_parent_review)})
    if broken_missing_broken_by_event_id:
        warnings.append({"code": "BROKEN_RANGES_MISSING_BROKEN_BY_EVENT_ID", "count": len(broken_missing_broken_by_event_id)})
    if broken_missing_inactive_from_time:
        warnings.append({"code": "BROKEN_RANGES_MISSING_INACTIVE_FROM_TIME", "count": len(broken_missing_inactive_from_time)})
    if chain_missing_created_by_event_id:
        warnings.append({"code": "CHAIN_RANGES_MISSING_CREATED_BY_EVENT_ID", "count": len(chain_missing_created_by_event_id)})
    if invalid_old_range_id_rows:
        warnings.append({"code": "INVALID_OLD_RANGE_ID", "count": len(invalid_old_range_id_rows)})
    if invalid_created_by_event_id_rows:
        warnings.append({"code": "INVALID_CREATED_BY_EVENT_ID", "count": len(invalid_created_by_event_id_rows)})
    if lifecycle_needs_review:
        warnings.append({"code": "LIFECYCLE_NEEDS_REVIEW", "count": len(lifecycle_needs_review)})
    errors = []
    if invalid_parent_links:
        errors.append({"code": "INVALID_PARENT_LINKS", "count": len(invalid_parent_links)})
    if missing_rh_rl:
        errors.append({"code": "RANGES_MISSING_RH_RL", "count": len(missing_rh_rl)})
    if bos_missing_bh_bl:
        errors.append({"code": "BOS_EVENTS_MISSING_BH_BL", "count": len(bos_missing_bh_bl)})

    return {
        "ok": True,
        "symbol": symbol,
        "case_id": case_id,
        "raw_case_id": raw_case_id,
        "case_ref": case_ref,
        "structure_layer_order": STRUCTURE_LAYER_ORDER,
        "summary": {
            "total_ranges": len(ranges),
            "ranges_by_structure_layer": counts_by_layer,
            "macro_ranges": counts_by_layer.get("MACRO", 0),
            "weekly_ranges": counts_by_layer.get("WEEKLY", 0),
            "daily_ranges": counts_by_layer.get("DAILY", 0),
            "intraday_ranges": counts_by_layer.get("INTRADAY", 0),
            "micro_ranges": counts_by_layer.get("MICRO", 0),
            "weekly_ranges_linked_to_macro": weekly_linked_macro,
            "daily_ranges_linked_to_weekly": daily_linked_weekly,
            "intraday_ranges_linked_to_daily": intraday_linked_daily,
            "orphan_weekly_ranges": len(orphan_weekly),
            "orphan_weekly_without_macro_parent": len(orphan_weekly_without_macro_parent),
            "legacy_weekly_root_ranges": len(legacy_weekly_root_ranges),
            "orphan_daily_ranges": len(orphan_daily),
            "orphan_intraday_ranges": len(orphan_intraday),
            "invalid_parent_links": len(invalid_parent_links),
            "ranges_needing_parent_review": len(needs_parent_review),
            "ranges_missing_rh_rl": len(missing_rh_rl),
            "bos_events_missing_bh_bl": len(bos_missing_bh_bl),
            "events_not_linked_to_active_range_id": len(events_without_active_range),
            "macro_context_expected": macro_exists_in_case,
            "broken_ranges_missing_broken_by_event_id": len(broken_missing_broken_by_event_id),
            "broken_ranges_missing_inactive_from_time": len(broken_missing_inactive_from_time),
            "chain_ranges_missing_created_by_event_id": len(chain_missing_created_by_event_id),
            "invalid_old_range_id": len(invalid_old_range_id_rows),
            "invalid_created_by_event_id": len(invalid_created_by_event_id_rows),
            "lifecycle_needs_review": len(lifecycle_needs_review),
        },
        "errors": errors,
        "warnings": warnings,
        "incomplete": {
            "orphan_weekly_ranges": orphan_weekly,
            "orphan_weekly_without_macro_parent": orphan_weekly_without_macro_parent,
            "legacy_weekly_root_ranges": legacy_weekly_root_ranges,
            "orphan_daily_ranges": orphan_daily,
            "orphan_intraday_ranges": orphan_intraday,
            "ranges_needing_parent_review": needs_parent_review,
            "broken_ranges_missing_broken_by_event_id": broken_missing_broken_by_event_id,
            "broken_ranges_missing_inactive_from_time": broken_missing_inactive_from_time,
            "chain_ranges_missing_created_by_event_id": chain_missing_created_by_event_id,
            "invalid_old_range_id": invalid_old_range_id_rows,
            "invalid_created_by_event_id": invalid_created_by_event_id_rows,
            "lifecycle_needs_review": lifecycle_needs_review,
            "events_not_linked_to_active_range_id": events_without_active_range,
        },
        "invalid_parent_links": invalid_parent_links,
        "ranges_needing_parent_review": needs_parent_review,
        "ranges_missing_rh_rl": missing_rh_rl,
        "bos_events_missing_bh_bl": bos_missing_bh_bl,
        "macro_weekly_tree": macro_weekly_tree,
        "weekly_daily_tree": weekly_daily_tree,
        "range_tree": weekly_daily_tree,
    }


def patch_map_range(range_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    init_db()
    now = now_iso()
    with connect() as conn:
        existing = conn.execute("SELECT * FROM map_ranges WHERE id=?", (int(range_id),)).fetchone()
        if existing is None:
            return {"ok": False, "status": 404, "error": "Range not found"}
        existing_d = dict(existing)
        merged = {**existing_d, **(payload or {})}
        case_id, raw_case_id, case_ref = _case_refs_from_payload(merged)
        structure_layer = _normalise_structure_layer(merged.get("structure_layer") or merged.get("layer"), merged.get("source_timeframe") or merged.get("timeframe"))
        parent_range_id = merged.get("parent_range_id")
        status, warnings, parent = _validate_parent_link(
            conn,
            child_id=int(range_id),
            symbol=str(merged.get("symbol") or existing_d.get("symbol")),
            case_id=case_id,
            raw_case_id=raw_case_id,
            case_ref=case_ref,
            structure_layer=structure_layer,
            parent_range_id=parent_range_id,
        )
        if status == "INVALID_PARENT":
            return {"ok": False, "status": 400, "error": "Invalid parent_range_id", "warnings": warnings, "parent_link_status": status}

        lifecycle_status, lifecycle_warnings, lifecycle_resolved = _validate_range_lifecycle_fields(
            conn,
            payload or {},
            merged,
            symbol=str(merged.get("symbol") or existing_d.get("symbol")),
            case_id=case_id,
            raw_case_id=raw_case_id,
            case_ref=case_ref,
        )
        chain_status, chain_warnings, chain_resolved = _validate_range_chain_fields(
            conn,
            int(range_id),
            payload or {},
            merged,
            symbol=str(merged.get("symbol") or existing_d.get("symbol")),
            case_id=case_id,
            raw_case_id=raw_case_id,
            case_ref=case_ref,
        )
        if chain_status == "INVALID_CHAIN":
            return {
                "ok": False,
                "status": 400,
                "error": "Invalid range chain fields",
                "warnings": warnings + lifecycle_warnings + chain_warnings,
                "parent_link_status": status,
                "chain_validation_status": chain_status,
            }
        combined_warnings = warnings + lifecycle_warnings + chain_warnings

        updates: dict[str, Any] = {"updated_at": now, "parent_link_status": status}
        if parent is not None:
            updates["parent_timeframe"] = _range_source_timeframe(parent)
            updates["parent_case_id"] = parent["case_id"] if "case_id" in parent.keys() else None
        updates.update(lifecycle_resolved)
        updates.update(chain_resolved)
        effective_status = _apply_active_lifecycle_normalization(payload or {}, merged, lifecycle_resolved)
        updates.update(
            {
                "broken_by_event_id": _write_broken_by_event_id({**merged, **updates}, effective_status),
                "direction_of_break": _write_direction_of_break({**merged, **updates}, effective_status),
                "inactive_from_time": _write_inactive_from_time({**merged, **updates}, effective_status),
            }
        )
        if effective_status == "ACTIVE":
            updates["broken_by_event_id"] = None
            updates["direction_of_break"] = None
            updates["inactive_from_time"] = None

        float_fields = {"range_high_price", "range_low_price", "break_high_price", "break_low_price"}
        text_fields = {
            "range_high_time", "range_low_time", "break_high_time", "break_low_time", "structure_layer",
            "chart_timeframe", "source_timeframe", "direction_of_break", "case_ref", "raw_case_id",
            "inactive_from_time", "active_from_time",
        }
        int_fields = {"parent_range_id", "case_id", "old_range_id", "new_range_id", "broken_by_event_id", "created_by_event_id"}
        passthrough_fields = {"meta_json"}

        for field in float_fields:
            if field in payload:
                updates[field] = parse_float(payload.get(field), None)
        for field in text_fields:
            if field in payload and field not in lifecycle_resolved and field not in chain_resolved:
                if effective_status == "ACTIVE" and field in {"direction_of_break", "inactive_from_time"}:
                    continue
                updates[field] = _optional_text(payload.get(field))
        for field in int_fields:
            if field in payload and field not in lifecycle_resolved and field not in chain_resolved:
                if effective_status == "ACTIVE" and field == "broken_by_event_id":
                    continue
                if field in {"broken_by_event_id", "created_by_event_id"}:
                    _ev_status, _ev_warnings, _ev_row, storage_id = _validate_bos_event_reference(
                        conn,
                        payload.get(field),
                        symbol=str(merged.get("symbol") or existing_d.get("symbol")),
                        case_id=case_id,
                        raw_case_id=raw_case_id,
                        case_ref=case_ref,
                        direction_of_break=payload.get("direction_of_break") or merged.get("direction_of_break"),
                    )
                    combined_warnings.extend(_ev_warnings)
                    if storage_id is not None:
                        updates[field] = storage_id
                    else:
                        updates[field] = _optional_int(payload.get(field))
                else:
                    updates[field] = _optional_int(payload.get(field))
        if "status" in payload and "status" not in lifecycle_resolved:
            normalized_status = _normalize_range_status(payload.get("status"))
            if normalized_status:
                updates["status"] = normalized_status
        if "case_id" in payload and updates.get("case_id") is None and payload.get("case_id") not in (None, "") and "raw_case_id" not in payload:
            updates["raw_case_id"] = _optional_text(payload.get("case_id"))
        if "case_ref" not in payload and ("case_id" in payload or "raw_case_id" in payload):
            updates["case_ref"] = case_ref
        if "meta_json" in payload:
            if isinstance(payload.get("meta_json"), dict):
                updates["meta_json"] = json.dumps({**_meta_dict(existing_d.get("meta_json")), **payload.get("meta_json")}, ensure_ascii=False, default=str)
            else:
                updates["meta_json"] = payload.get("meta_json")

        if "range_high_price" in updates:
            updates["range_high"] = updates["range_high_price"]
        if "range_low_price" in updates:
            updates["range_low"] = updates["range_low_price"]
        if "source_timeframe" in updates and updates["source_timeframe"]:
            updates["timeframe"] = normalise_timeframe(str(updates["source_timeframe"]))
        if "structure_layer" in updates and updates["structure_layer"]:
            updates["structure_layer"] = _normalise_structure_layer(updates["structure_layer"], merged.get("source_timeframe") or merged.get("timeframe"))

        set_sql = ", ".join([f"{field}=?" for field in updates.keys()])
        args = list(updates.values()) + [int(range_id)]
        conn.execute(f"UPDATE map_ranges SET {set_sql} WHERE id=?", args)
        conn.commit()
        row = conn.execute("SELECT * FROM map_ranges WHERE id=?", (int(range_id),)).fetchone()
    return {
        "ok": True,
        "range_id": int(range_id),
        "updated": True,
        "parent_link_status": status,
        "lifecycle_validation_status": lifecycle_status,
        "chain_validation_status": chain_status,
        "warnings": combined_warnings,
        "range": _range_row_to_dict(row),
    }


def patch_structural_map_event(event_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    init_db()
    now = now_iso()
    event_type_aliases = {
        "RH": "RANGE_HIGH",
        "RANGE_HIGH": "RANGE_HIGH",
        "RANGE_HIGH_SELECTED": "RANGE_HIGH_SELECTED",
        "RL": "RANGE_LOW",
        "RANGE_LOW": "RANGE_LOW",
        "RANGE_LOW_SELECTED": "RANGE_LOW_SELECTED",
        "BH": "BOS_UP",
        "BREAK_HIGH": "BOS_UP",
        "BREAK_HIGH_SELECTED": "BOS_UP",
        "BOS_UP": "BOS_UP",
        "BL": "BOS_DOWN",
        "BREAK_LOW": "BOS_DOWN",
        "BREAK_LOW_SELECTED": "BOS_DOWN",
        "BOS_DOWN": "BOS_DOWN",
    }
    with connect() as conn:
        existing = conn.execute("SELECT * FROM map_events WHERE event_id=? OR id=?", (str(event_id), _optional_int(event_id) or -1)).fetchone()
        if existing is None:
            return {"ok": False, "status": 404, "error": "Structural event not found"}
        existing_d = dict(existing)
        merged = {**existing_d, **(payload or {})}
        case_id, raw_case_id, case_ref = _case_refs_from_payload(merged)

        updates: dict[str, Any] = {"updated_at": now}
        if "event_type" in payload or "structural_event" in payload:
            raw_type = str(payload.get("event_type") or payload.get("structural_event") or "").upper()
            next_type = event_type_aliases.get(raw_type, raw_type)
            allowed_patch_types = set(ALLOWED_STRUCTURAL_EVENT_TYPES) | {"RANGE_HIGH", "RANGE_LOW"}
            if next_type not in allowed_patch_types:
                return {"ok": False, "status": 400, "error": f"Invalid structural event_type: {next_type}"}
            updates["event_type"] = next_type
            updates["structural_event"] = str(payload.get("structural_event") or next_type).upper()
            if next_type == "BOS_UP" and "break_level_type" not in payload:
                updates["break_level_type"] = "BH"
            if next_type == "BOS_DOWN" and "break_level_type" not in payload:
                updates["break_level_type"] = "BL"

        float_fields = {"break_level_price", "event_price", "candle_open", "candle_high", "candle_low", "candle_close"}
        text_fields = {"break_level_type", "break_level_time", "event_time", "candle_time", "raw_case_id", "case_ref", "direction"}
        int_fields = {"active_range_id", "parent_range_id", "case_id"}
        for field in float_fields:
            if field in payload:
                updates[field] = parse_float(payload.get(field), None)
        for field in text_fields:
            if field in payload:
                updates[field] = _optional_text(payload.get(field))
        for field in int_fields:
            if field in payload:
                updates[field] = _optional_int(payload.get(field))
        if "case_id" in payload and updates.get("case_id") is None and payload.get("case_id") not in (None, "") and "raw_case_id" not in payload:
            updates["raw_case_id"] = _optional_text(payload.get("case_id"))
        if "case_ref" not in payload and ("case_id" in payload or "raw_case_id" in payload):
            updates["case_ref"] = case_ref
        if "meta_json" in payload:
            updates["meta_json"] = json.dumps(payload.get("meta_json"), ensure_ascii=False, default=str) if isinstance(payload.get("meta_json"), dict) else payload.get("meta_json")
        if "event_time" in updates:
            updates["time"] = updates["event_time"]
        if "event_price" in updates:
            updates["price"] = updates["event_price"]

        set_sql = ", ".join([f"{field}=?" for field in updates.keys()])
        args = list(updates.values()) + [int(existing_d["id"])]
        conn.execute(f"UPDATE map_events SET {set_sql} WHERE id=?", args)
        conn.commit()
        row = conn.execute("SELECT * FROM map_events WHERE id=?", (int(existing_d["id"]),)).fetchone()
    return {"ok": True, "id": int(existing_d["id"]), "event_id": row["event_id"] if row and "event_id" in row.keys() else event_id, "updated": True, "event": _event_row_to_dict(row)}


def delete_map_range(symbol: str = "XAUUSD", timeframe: str = "D1", range_key: str = "active") -> dict[str, Any]:
    init_db()
    tf = normalise_timeframe(timeframe)
    now = now_iso()
    with connect() as conn:
        cur = conn.execute(
            "UPDATE map_ranges SET status='archived', updated_at=? WHERE symbol=? AND timeframe=? AND COALESCE(range_key,'active')=? AND status!='archived'",
            (now, symbol, tf, range_key),
        )
        conn.commit()
    return {"ok": True, "archived": cur.rowcount, "symbol": symbol, "timeframe": tf, "range_key": range_key}


# -------------------------------
# MOS v1: minimal GPS/state core
# -------------------------------

def anchor_class_for(story_anchor: str) -> str:
    """Classify the parent reason for the story.

    Liquidity anchors = reference highs/lows taken.
    Rejection anchors = weekly high/low/premium/discount/external rejection.
    Everything else stays manual/unknown for now. Boring, but safe.
    """
    txt = str(story_anchor or "").upper()
    if "REF_" in txt and "TAKEN" in txt:
        return "LIQUIDITY"
    if "REJECTION" in txt:
        return "REJECTION"
    if "CHOCH" in txt or "BOS" in txt:
        return "STRUCTURE"
    return "MANUAL"


def get_mock_gps_snapshot(symbol: str = "XAUUSD", timeframe: str = "W1") -> dict[str, Any]:
    """Sprint-2 mock payload. This proves the Electron GPS panel language before automation."""
    return {
        "ok": True,
        "status": "MOCK_TRACKING_ACTIVE",
        "symbol": symbol,
        "timeframe": normalise_timeframe(timeframe),
        "coordinates": {
            "story_anchor": "WEEKLY_REF_LOW_TAKEN",
            "anchor_class": anchor_class_for("WEEKLY_REF_LOW_TAKEN"),
            "chapter": "DAILY_BOS_UP",
            "phase": "P1",
            "phase_part": "RETEST",
            "objective": "WEEKLY_PREMIUM",
            "current_zone": "DISCOUNT",
        },
    }

def create_narrative_story(payload: dict[str, Any]) -> dict[str, Any]:
    init_db()
    now = now_iso()
    symbol = str(payload.get("symbol") or "XAUUSD")
    timeframe = normalise_timeframe(payload.get("timeframe") or "W1")
    story_anchor = str(payload.get("story_anchor") or payload.get("anchor") or "MANUAL_STORY_ANCHOR").upper()
    anchor_class = str(payload.get("anchor_class") or anchor_class_for(story_anchor)).upper()
    price = parse_float(payload.get("anchor_price", payload.get("price", 0)))
    ts = str(payload.get("activated_timestamp") or payload.get("timestamp") or now)
    terminate_existing = bool(payload.get("terminate_existing", True))
    with connect() as conn:
        if terminate_existing:
            conn.execute("UPDATE narrative_stories SET status='TERMINATED', updated_at=? WHERE symbol=? AND timeframe=? AND status='ACTIVE'", (now, symbol, timeframe))
        cur = conn.execute(
            """
            INSERT INTO narrative_stories(symbol,timeframe,story_anchor,anchor_class,anchor_price,activated_timestamp,status,created_at,updated_at)
            VALUES(?,?,?,?,?,?,'ACTIVE',?,?)
            """,
            (symbol, timeframe, story_anchor, anchor_class, price, ts, now, now),
        )
        conn.commit()
        story_id = cur.lastrowid
    return {"ok": True, "story_id": story_id, "symbol": symbol, "timeframe": timeframe, "story_anchor": story_anchor}

def _get_active_story(conn: sqlite3.Connection, symbol: str, timeframe: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM narrative_stories WHERE symbol=? AND timeframe=? AND status='ACTIVE' ORDER BY activated_timestamp DESC, id DESC LIMIT 1",
        (symbol, timeframe),
    ).fetchone()

def create_story_chapter(payload: dict[str, Any]) -> dict[str, Any]:
    init_db()
    now = now_iso()
    symbol = str(payload.get("symbol") or "XAUUSD")
    timeframe = normalise_timeframe(payload.get("timeframe") or "D1")
    story_timeframe = normalise_timeframe(payload.get("story_timeframe") or "W1")
    chapter_catalyst = str(payload.get("chapter_catalyst") or payload.get("event_type") or "MANUAL_CHAPTER")
    price = parse_float(payload.get("trigger_price", payload.get("price", 0)))
    ts = str(payload.get("created_timestamp") or payload.get("timestamp") or now)
    story_id = payload.get("story_id")
    with connect() as conn:
        if not story_id:
            story = _get_active_story(conn, symbol, story_timeframe)
            if not story:
                # Orphan guard: useful during early manual testing.
                cur = conn.execute(
                    """
                    INSERT INTO narrative_stories(symbol,timeframe,story_anchor,anchor_price,activated_timestamp,status,created_at,updated_at)
                    VALUES(?,?,?,?,?,'ACTIVE',?,?)
                    """,
                    (symbol, story_timeframe, "ORPHAN_START", price, ts, now, now),
                )
                story_id = cur.lastrowid
            else:
                story_id = story["id"]
        cur = conn.execute(
            """
            INSERT INTO story_chapters(story_id,symbol,timeframe,chapter_catalyst,trigger_price,created_timestamp,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?)
            """,
            (int(story_id), symbol, timeframe, chapter_catalyst, price, ts, now, now),
        )
        conn.commit()
        chapter_id = cur.lastrowid
    return {"ok": True, "chapter_id": chapter_id, "story_id": int(story_id), "chapter_catalyst": chapter_catalyst}

def create_market_phase(payload: dict[str, Any]) -> dict[str, Any]:
    init_db()
    now = now_iso()
    symbol = str(payload.get("symbol") or "XAUUSD")
    timeframe = normalise_timeframe(payload.get("timeframe") or "D1")
    chapter_id = payload.get("chapter_id")
    phase_number = int(payload.get("phase_number") or 1)
    phase_part = str(payload.get("phase_part") or "RETEST").upper()
    direction = str(payload.get("direction") or "BULLISH").upper()
    objective = str(payload.get("active_objective") or payload.get("objective") or "MANUAL_OBJECTIVE")
    current_zone = str(payload.get("current_zone") or payload.get("zone") or "UNKNOWN").upper()
    price = parse_float(payload.get("established_price", payload.get("price", 0)))
    ts = str(payload.get("established_timestamp") or payload.get("timestamp") or now)
    if phase_number not in {1, 2, 3}:
        raise ValueError("phase_number must be 1, 2, or 3")
    if phase_part not in {"RETEST", "RECLAIM", "IMPULSE", "BOS", "FAIL"}:
        raise ValueError("phase_part must be RETEST, RECLAIM, IMPULSE, BOS, or FAIL")
    with connect() as conn:
        if not chapter_id:
            row = conn.execute(
                "SELECT id FROM story_chapters WHERE symbol=? ORDER BY created_timestamp DESC, id DESC LIMIT 1",
                (symbol,),
            ).fetchone()
            if not row:
                raise ValueError("No chapter_id supplied and no existing chapter found")
            chapter_id = row["id"]
        cur = conn.execute(
            """
            INSERT INTO market_phases(chapter_id,symbol,timeframe,phase_number,phase_part,direction,active_objective,established_price,established_timestamp,created_at,updated_at,current_zone)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (int(chapter_id), symbol, timeframe, phase_number, phase_part, direction, objective, price, ts, now, now, current_zone),
        )
        conn.commit()
        phase_id = cur.lastrowid
    return {"ok": True, "phase_id": phase_id, "chapter_id": int(chapter_id), "current_state": f"P{phase_number}_{phase_part}", "current_zone": current_zone}

def _phase_num_from_value(value: Any) -> int:
    txt = str(value or "P1").upper().strip()
    if txt.startswith("P"):
        txt = txt[1:]
    try:
        n = int(txt)
    except Exception:
        n = 1
    return max(1, min(3, n))

def _direction_from_chapter(chapter: str, fallback: str = "BULLISH") -> str:
    txt = str(chapter or "").upper()
    if "DOWN" in txt or "LOW" in txt and "RECLAIM" not in txt:
        return "BEARISH"
    if "UP" in txt or "HIGH" in txt and "RECLAIM" not in txt:
        return "BULLISH"
    return fallback.upper() if fallback else "BULLISH"

def save_manual_gps_state(payload: dict[str, Any]) -> dict[str, Any]:
    """Save the manual Market GPS front-door coordinate into MOS v1 tables.

    This is intentionally boring: one active story, latest chapter, latest phase coordinate.
    No automation, no prophecy, no moon base.
    """
    init_db()
    now = now_iso()
    symbol = str(payload.get("symbol") or "XAUUSD")
    story_timeframe = normalise_timeframe(payload.get("story_timeframe") or payload.get("timeframe") or "W1")
    chapter_timeframe = normalise_timeframe(payload.get("chapter_timeframe") or "D1")
    story_anchor = str(payload.get("story_anchor") or "WEEKLY_REF_LOW_TAKEN").upper()
    anchor_class = str(payload.get("anchor_class") or anchor_class_for(story_anchor)).upper()
    chapter_catalyst = str(payload.get("chapter") or payload.get("chapter_catalyst") or "DAILY_BOS_UP").upper()
    phase_number = _phase_num_from_value(payload.get("phase") or payload.get("phase_number") or "P1")
    phase_part = str(payload.get("phase_part") or payload.get("state") or "RETEST").upper()
    if phase_part not in {"RETEST", "RECLAIM", "IMPULSE", "BOS", "FAIL"}:
        phase_part = "RETEST"
    direction = str(payload.get("direction") or _direction_from_chapter(chapter_catalyst)).upper()
    objective = str(payload.get("objective") or payload.get("active_objective") or "WEEKLY_PREMIUM").upper()
    current_zone = str(payload.get("current_zone") or payload.get("zone") or "DISCOUNT").upper()
    price = parse_float(payload.get("price") or payload.get("anchor_price") or payload.get("trigger_price") or payload.get("established_price") or 0)
    timestamp = str(payload.get("timestamp") or payload.get("activated_timestamp") or payload.get("created_timestamp") or payload.get("established_timestamp") or now)

    with connect() as conn:
        # Story: reuse the current active story only if the anchor matches. Otherwise terminate and create.
        story = _get_active_story(conn, symbol, story_timeframe)
        if story and story["story_anchor"] == story_anchor:
            story_id = int(story["id"])
        else:
            conn.execute("UPDATE narrative_stories SET status='TERMINATED', updated_at=? WHERE symbol=? AND timeframe=? AND status='ACTIVE'", (now, symbol, story_timeframe))
            cur = conn.execute(
                """
                INSERT INTO narrative_stories(symbol,timeframe,story_anchor,anchor_class,anchor_price,activated_timestamp,status,created_at,updated_at)
                VALUES(?,?,?,?,?,?,'ACTIVE',?,?)
                """,
                (symbol, story_timeframe, story_anchor, anchor_class, price, timestamp, now, now),
            )
            story_id = int(cur.lastrowid)

        # Chapter: append only when the latest chapter changed.
        chapter = conn.execute(
            "SELECT * FROM story_chapters WHERE story_id=? ORDER BY created_timestamp DESC, id DESC LIMIT 1",
            (story_id,),
        ).fetchone()
        if chapter and chapter["chapter_catalyst"] == chapter_catalyst:
            chapter_id = int(chapter["id"])
        else:
            cur = conn.execute(
                """
                INSERT INTO story_chapters(story_id,symbol,timeframe,chapter_catalyst,trigger_price,created_timestamp,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?)
                """,
                (story_id, symbol, chapter_timeframe, chapter_catalyst, price, timestamp, now, now),
            )
            chapter_id = int(cur.lastrowid)

        # Phase: dedupe exact coordinate, otherwise append a new operational coordinate.
        last_phase = conn.execute(
            "SELECT * FROM market_phases WHERE chapter_id=? ORDER BY established_timestamp DESC, id DESC LIMIT 1",
            (chapter_id,),
        ).fetchone()
        if last_phase and int(last_phase["phase_number"]) == phase_number and last_phase["phase_part"] == phase_part and last_phase["active_objective"] == objective and str(last_phase["current_zone"] or "UNKNOWN") == current_zone:
            phase_id = int(last_phase["id"])
            changed = False
        else:
            cur = conn.execute(
                """
                INSERT INTO market_phases(chapter_id,symbol,timeframe,phase_number,phase_part,direction,active_objective,established_price,established_timestamp,created_at,updated_at,current_zone)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (chapter_id, symbol, chapter_timeframe, phase_number, phase_part, direction, objective, price, timestamp, now, now, current_zone),
            )
            phase_id = int(cur.lastrowid)
            changed = True
        conn.commit()

    return {
        "ok": True, "status": "MOS_STATE_SAVED", "changed": changed,
        "story_id": story_id, "chapter_id": chapter_id, "phase_id": phase_id,
        "coordinates": {
            "story_anchor": story_anchor, "anchor_class": anchor_class, "chapter": chapter_catalyst,
            "phase": f"P{phase_number}", "phase_part": phase_part,
            "objective": objective, "current_zone": current_zone,
        }
    }

def get_active_gps_snapshot(symbol: str = "XAUUSD", timeframe: str = "W1") -> dict[str, Any]:
    init_db()
    symbol = str(symbol or "XAUUSD")
    tf = normalise_timeframe(timeframe or "W1")
    with connect() as conn:
        story = _get_active_story(conn, symbol, tf)
        if not story:
            return {"ok": True, "status": "NO_ACTIVE_STORY", "symbol": symbol, "timeframe": tf, "coordinates": None}
        chapter = conn.execute(
            "SELECT * FROM story_chapters WHERE story_id=? ORDER BY created_timestamp DESC, id DESC LIMIT 1",
            (story["id"],),
        ).fetchone()
        if not chapter:
            return {
                "ok": True, "status": "TRACKING_ACTIVE", "symbol": symbol, "timeframe": tf,
                "coordinates": {
                    "story_anchor": story["story_anchor"], "anchor_class": story["anchor_class"] if "anchor_class" in story.keys() else anchor_class_for(story["story_anchor"]), "chapter": "AWAITING_FORMATION",
                    "phase": "NONE", "phase_part": "NONE", "objective": "NONE", "current_zone": "NONE"
                }
            }
        phase = conn.execute(
            "SELECT * FROM market_phases WHERE chapter_id=? ORDER BY established_timestamp DESC, id DESC LIMIT 1",
            (chapter["id"],),
        ).fetchone()
        return {
            "ok": True, "status": "TRACKING_ACTIVE", "symbol": symbol, "timeframe": tf,
            "coordinates": {
                "story_anchor": story["story_anchor"],
                "anchor_class": story["anchor_class"] if "anchor_class" in story.keys() else anchor_class_for(story["story_anchor"]),
                "chapter": chapter["chapter_catalyst"],
                "phase": f"P{phase['phase_number']}" if phase else "UNKNOWN",
                "phase_part": phase["phase_part"] if phase else "UNKNOWN",
                "objective": phase["active_objective"] if phase else "UNKNOWN",
                "current_zone": phase["current_zone"] if phase and "current_zone" in phase.keys() else "UNKNOWN",
            }
        }

def get_mos_timeline(symbol: str = "XAUUSD", timeframe: str = "W1") -> dict[str, Any]:
    """Return a lightweight narrative timeline for the Electron sidebar.

    V1 intentionally follows the active story only:
    Anchor -> Chapters -> Phase coordinates.
    No automation. No prophecy. Just the memory, displayed neatly.
    """
    init_db()
    symbol = str(symbol or "XAUUSD")
    tf = normalise_timeframe(timeframe or "W1")
    with connect() as conn:
        story = _get_active_story(conn, symbol, tf)
        if not story:
            return {"ok": True, "status": "NO_ACTIVE_STORY", "symbol": symbol, "timeframe": tf, "nodes": []}
        nodes: list[dict[str, Any]] = [{
            "kind": "ANCHOR",
            "label": story["story_anchor"],
            "anchor_class": story["anchor_class"] if "anchor_class" in story.keys() else anchor_class_for(story["story_anchor"]),
            "time": story["activated_timestamp"],
            "price": story["anchor_price"],
            "active": False,
        }]
        chapters = conn.execute(
            "SELECT * FROM story_chapters WHERE story_id=? ORDER BY created_timestamp ASC, id ASC",
            (story["id"],),
        ).fetchall()
        for ci, ch in enumerate(chapters):
            nodes.append({
                "kind": "CHAPTER",
                "label": ch["chapter_catalyst"],
                "timeframe": ch["timeframe"],
                "time": ch["created_timestamp"],
                "price": ch["trigger_price"],
                "active": False,
            })
            phases = conn.execute(
                "SELECT * FROM market_phases WHERE chapter_id=? ORDER BY established_timestamp ASC, id ASC",
                (ch["id"],),
            ).fetchall()
            for pi, ph in enumerate(phases):
                is_latest_ch = ci == len(chapters) - 1
                is_latest_ph = pi == len(phases) - 1
                nodes.append({
                    "kind": "PHASE",
                    "label": f"P{ph['phase_number']}_{ph['phase_part']}",
                    "phase": f"P{ph['phase_number']}",
                    "phase_part": ph["phase_part"],
                    "direction": ph["direction"],
                    "objective": ph["active_objective"],
                    "current_zone": ph["current_zone"] if "current_zone" in ph.keys() else "UNKNOWN",
                    "time": ph["established_timestamp"],
                    "price": ph["established_price"],
                    "active": is_latest_ch and is_latest_ph,
                })
        if nodes and not any(n.get("active") for n in nodes):
            nodes[-1]["active"] = True
        return {"ok": True, "status": "TIMELINE_ACTIVE", "symbol": symbol, "timeframe": tf, "story_id": story["id"], "nodes": nodes}


def _mos_enum(value: Any, allowed: set[str], default: str) -> str:
    txt = str(value or default).strip().upper()
    return txt if txt in allowed else default


def _mos_zone(value: Any, default: str = "DAILY_DISCOUNT") -> str:
    txt = str(value or default).strip().upper()
    aliases = {
        "DISCOUNT": "DAILY_DISCOUNT",
        "D": "DAILY_DISCOUNT",
        "PREMIUM": "DAILY_PREMIUM",
        "P": "DAILY_PREMIUM",
        "FAIR": "DAILY_FAIR_PRICE",
        "FAIR_PRICE": "DAILY_FAIR_PRICE",
        "EXT_H": "WEEKLY_EXTERNAL_HIGH",
        "EXTERNAL_HIGH": "WEEKLY_EXTERNAL_HIGH",
        "EXT_L": "WEEKLY_EXTERNAL_LOW",
        "EXTERNAL_LOW": "WEEKLY_EXTERNAL_LOW",
        "EXTREME_DISCOUNT": "WEEKLY_EXTREME_DISCOUNT",
        "EXTREME_PREMIUM": "WEEKLY_EXTREME_PREMIUM",
    }
    txt = aliases.get(txt, txt)
    return txt if txt in MOS_ZONES else default


def _mos_objective_id(conn: sqlite3.Connection, objective_code: str) -> int:
    code = str(objective_code or "DAILY_PREMIUM").strip().upper()
    row = conn.execute("SELECT id FROM objective_types WHERE code=?", (code,)).fetchone()
    if row:
        return int(row["id"])
    # Flexible enough for manual work, but still normalised into the lookup. Humans invent labels; SQL requires rent.
    conn.execute(
        "INSERT OR IGNORE INTO objective_types(code,name,objective_level,parent_objective_id) VALUES(?,?,?,NULL)",
        (code, code.replace("_", " ").title(), "MANUAL"),
    )
    row = conn.execute("SELECT id FROM objective_types WHERE code=?", (code,)).fetchone()
    return int(row["id"])


def seed_case_03() -> dict[str, Any]:
    """Seed the XAUUSD Case 03 story/chapter scaffold used for MOS calibration."""
    init_db()
    now = now_iso()
    with connect() as conn:
        for code, name, level, parent_id in MOS_OBJECTIVE_SEEDS:
            conn.execute("INSERT OR IGNORE INTO objective_types(code,name,objective_level,parent_objective_id) VALUES(?,?,?,?)", (code, name, level, parent_id))
        conn.execute(
            """
            INSERT OR IGNORE INTO narrative_stories(id,symbol,timeframe,story_anchor,anchor_class,anchor_price,activated_timestamp,status,created_at,updated_at,parent_context_mode,daily_range_status)
            VALUES(3,'XAUUSD','W1','WEEKLY_EXTERNAL_LOW_REJECTION','REJECTION',2280.0,?,'ACTIVE',?,?, 'WEEKLY_ACTIVE_PARENT','DAILY_RANGE_FORMING')
            """,
            (now, now, now),
        )
        rows = [
            (301, 3, "XAUUSD", "D1", "WEEKLY_EXTERNAL_LOW_REJECTION", 2285.0),
            (302, 3, "XAUUSD", "D1", "DAILY_BOS_UP", 2320.0),
            (303, 3, "XAUUSD", "D1", "POLARITY_FLIP_RETEST", 2322.0),
        ]
        for chapter_id, story_id, symbol, timeframe, catalyst, price in rows:
            conn.execute(
                """
                INSERT OR IGNORE INTO story_chapters(id,story_id,symbol,timeframe,chapter_catalyst,trigger_price,created_timestamp,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (chapter_id, story_id, symbol, timeframe, catalyst, price, now, now, now),
            )
        conn.commit()
    return {"ok": True, "seeded": "CASE_03", "story_id": 3, "chapters": [301, 302, 303]}


def seed_case_03_frames() -> dict[str, Any]:
    """Reset and seed Case 03 with its four deterministic playback frames.

    This is a test harness, not trading automation. It gives Electron Replay Mode something real
    to scrub without forcing Josh to hand-post four JSON payloads like a medieval clerk.
    """
    init_db()
    seed_case_03()
    with connect() as conn:
        # Clear only the Case 03 dependent ledger rows so the seed is idempotent.
        conn.execute("DELETE FROM market_coordinates WHERE story_id=3")
        conn.execute("DELETE FROM playback_frames WHERE story_id=3")
        conn.execute("DELETE FROM state_transitions WHERE story_id=3")
        conn.execute("DELETE FROM price_profiles WHERE story_id=3")
        conn.execute("DELETE FROM market_phases WHERE chapter_id IN (301,302,303)")
        conn.commit()

    frames = [
        {
            "symbol": "XAUUSD", "story_id": 3, "chapter_id": 301,
            "story_timeframe": "W1", "chapter_timeframe": "D1",
            "story_anchor": "WEEKLY_EXTERNAL_LOW_REJECTION", "chapter": "WEEKLY_EXTERNAL_LOW_REJECTION",
            "parent_context_mode": "WEEKLY_ACTIVE_PARENT", "daily_range_status": "DAILY_RANGE_FORMING",
            "lifecycle_state": "MITIGATION", "phase_number": 1, "phase_part": "RETEST",
            "objective_code": "WEEKLY_EXTERNAL_LOW", "current_zone": "WEEKLY_EXTERNAL_LOW",
            "established_price": 2282.50, "trigger_event": "WEEKLY_EXTERNAL_LOW_REJECTED_HTF_ZONE",
            "expected_next_event": "DAILY_BOS_UP_RECLAIM",
            "invalidation_condition": "WEEK_OPEN_GAP_LIQUIDATION_DESTRUCTIVE_WEEKLY_LOW_VIOLATION",
            "timeframe": "D1", "bos_direction": "UP", "bos_price": 2282.50,
            "profile_type": "NO_RECLAIM_CONTINUATION_PROFILE", "timestamp": "2026-06-05T07:00:00"
        },
        {
            "symbol": "XAUUSD", "story_id": 3, "chapter_id": 302,
            "story_timeframe": "W1", "chapter_timeframe": "D1",
            "story_anchor": "WEEKLY_EXTERNAL_LOW_REJECTION", "chapter": "DAILY_BOS_UP",
            "parent_context_mode": "WEEKLY_ACTIVE_PARENT", "daily_range_status": "DAILY_RANGE_ACTIVE",
            "lifecycle_state": "EXPANSION", "phase_number": 1, "phase_part": "BOS",
            "objective_code": "DAILY_PREMIUM", "current_zone": "DAILY_PREMIUM",
            "established_price": 2345.00, "trigger_event": "DAILY_BOS_UP_RECLAIM",
            "expected_next_event": "LOCAL_DISCOUNT_TEST_ON_ABANDONED_DAILY_PREMIUM_CEILING",
            "invalidation_condition": "DAILY_LOW_VIOLATION_DESTRUCTIVE",
            "timeframe": "D1", "bos_direction": "UP", "bos_price": 2320.00,
            "profile_type": "SHALLOW_RECLAIM_SR_PROFILE", "timestamp": "2026-06-05T07:05:00"
        },
        {
            "symbol": "XAUUSD", "story_id": 3, "chapter_id": 303,
            "story_timeframe": "W1", "chapter_timeframe": "D1",
            "story_anchor": "WEEKLY_EXTERNAL_LOW_REJECTION", "chapter": "POLARITY_FLIP_RETEST",
            "parent_context_mode": "WEEKLY_ACTIVE_PARENT", "daily_range_status": "DAILY_RANGE_RETESTING",
            "lifecycle_state": "REVERSAL_DEVELOPMENT", "phase_number": 2, "phase_part": "RETEST",
            "objective_code": "DAILY_PREMIUM", "current_zone": "DAILY_DISCOUNT",
            "established_price": 2322.00, "trigger_event": "LOCAL_DISCOUNT_TEST_ON_ABANDONED_DAILY_PREMIUM_CEILING",
            "expected_next_event": "DAILY_MOMENTUM_EXPANSION_TO_WEEKLY_PREMIUM",
            "invalidation_condition": "DAILY_BREAKOUT_BAR_FAILED_RECLAIM_DESTRUCTIVE",
            "timeframe": "D1", "bos_direction": "UP", "broken_range_high": 2345.00, "broken_range_low": 2282.50,
            "bos_price": 2320.00, "profile_type": "DEEP_RECLAIM_SD_PROFILE", "timestamp": "2026-06-05T07:10:00"
        },
        {
            "symbol": "XAUUSD", "story_id": 3, "chapter_id": 303,
            "story_timeframe": "W1", "chapter_timeframe": "D1",
            "story_anchor": "WEEKLY_EXTERNAL_LOW_REJECTION", "chapter": "POLARITY_FLIP_RETEST",
            "parent_context_mode": "WEEKLY_ACTIVE_PARENT", "daily_range_status": "DAILY_RANGE_ABANDONED",
            "lifecycle_state": "OBJECTIVE_COMPLETION", "phase_number": 3, "phase_part": "IMPULSE",
            "objective_code": "WEEKLY_EXTREME_PREMIUM", "current_zone": "WEEKLY_EXTREME_PREMIUM",
            "established_price": 2420.00, "trigger_event": "DAILY_MOMENTUM_EXPANSION_TO_WEEKLY_PREMIUM",
            "expected_next_event": "DAILY_COMPRESSION_FORMING", "invalidation_condition": "TREND_REVERSAL_DESTRUCTIVE",
            "timeframe": "D1", "bos_direction": "UP", "bos_price": 2420.00,
            "profile_type": "DEEP_RECLAIM_SD_PROFILE", "timestamp": "2026-06-05T07:15:00"
        },
    ]
    written = []
    for payload in frames:
        written.append(build_mos_state(payload))
    return {"ok": True, "seeded": "CASE_03_FRAMES", "story_id": 3, "frames": len(written), "results": written}


def build_mos_state(payload: dict[str, Any]) -> dict[str, Any]:
    """MOS v150 manual state writer.

    Writes phase snapshot, transition line, price profile, immutable playback frame, and runtime GPS cache
    inside one transaction. No automation. No prophecy. Just disciplined state capture.
    """
    init_db()
    now = str(payload.get("timestamp") or payload.get("frame_timestamp") or now_iso())
    symbol = str(payload.get("symbol") or "XAUUSD").strip()
    story_tf = normalise_timeframe(payload.get("story_timeframe") or "W1")
    chapter_tf = normalise_timeframe(payload.get("chapter_timeframe") or payload.get("timeframe") or "D1")
    lifecycle = _mos_enum(payload.get("lifecycle_state"), MOS_LIFECYCLE_STATES, "EXPANSION")
    parent_mode = _mos_enum(payload.get("parent_context_mode"), MOS_PARENT_CONTEXT_MODES, "WEEKLY_ACTIVE_PARENT")
    daily_status = _mos_enum(payload.get("daily_range_status"), MOS_DAILY_RANGE_STATUSES, "NO_ACTIVE_DAILY_RANGE")
    phase_number = int(payload.get("phase_number") or _phase_num_from_value(payload.get("phase") or "P1"))
    if phase_number not in {1, 2, 3}:
        raise ValueError("phase_number must be 1, 2, or 3")
    phase_part = _mos_enum(payload.get("phase_part") or payload.get("state"), MOS_PHASE_PARTS, "RETEST")
    profile_type = _mos_enum(payload.get("profile_type"), MOS_PROFILE_TYPES, "NO_RECLAIM_CONTINUATION_PROFILE")
    objective_code = str(payload.get("objective_code") or payload.get("objective") or payload.get("active_objective") or "DAILY_PREMIUM").strip().upper()
    current_zone = _mos_zone(payload.get("current_zone") or payload.get("zone"), "DAILY_DISCOUNT")
    established_price = parse_float(payload.get("established_price", payload.get("price", 0)))
    trigger_event = str(payload.get("trigger_event") or payload.get("event_type") or "MANUAL_STATE_WRITE").strip().upper()
    expected_next_event = str(payload.get("expected_next_event") or "PENDING_MARKET_DELIVERY").strip().upper()
    invalidation_condition = str(payload.get("invalidation_condition") or "MANUAL_INVALIDATION_REQUIRED").strip().upper()
    bos_direction = str(payload.get("bos_direction") or _direction_from_chapter(trigger_event)).strip().upper()
    if bos_direction not in {"UP", "DOWN"}:
        bos_direction = "UP" if bos_direction == "BULLISH" else "DOWN" if bos_direction == "BEARISH" else "UP"
    bos_price = parse_float(payload.get("bos_price", established_price))
    broken_range_high = payload.get("broken_range_high")
    broken_range_low = payload.get("broken_range_low")
    reclaim_price = payload.get("reclaim_price")
    reclaim_depth_percent = payload.get("reclaim_depth_percent")
    story_anchor = str(payload.get("story_anchor") or "WEEKLY_REF_LOW_TAKEN").strip().upper()
    anchor_class = str(payload.get("anchor_class") or anchor_class_for(story_anchor)).strip().upper()
    chapter_catalyst = str(payload.get("chapter_catalyst") or payload.get("chapter") or trigger_event).strip().upper()

    with connect() as conn:
        conn.execute("BEGIN")
        story_id = payload.get("story_id")
        if story_id:
            story = conn.execute("SELECT * FROM narrative_stories WHERE id=?", (int(story_id),)).fetchone()
            if not story:
                conn.execute(
                    """
                    INSERT INTO narrative_stories(id,symbol,timeframe,story_anchor,anchor_class,anchor_price,activated_timestamp,status,created_at,updated_at,parent_context_mode,daily_range_status)
                    VALUES(?,?,?,?,?,?,?,'ACTIVE',?,?,?,?,?)
                    """.replace("?,?,?,?,?,?,?,'ACTIVE',?,?,?,?,?", "?,?,?,?,?,?,?,'ACTIVE',?,?,?,?,?"),
                    (int(story_id), symbol, story_tf, story_anchor, anchor_class, established_price, now, now, now, parent_mode, daily_status),
                )
        else:
            story = _get_active_story(conn, symbol, story_tf)
            if story:
                story_id = int(story["id"])
            else:
                cur = conn.execute(
                    """
                    INSERT INTO narrative_stories(symbol,timeframe,story_anchor,anchor_class,anchor_price,activated_timestamp,status,created_at,updated_at,parent_context_mode,daily_range_status)
                    VALUES(?,?,?,?,?,?,'ACTIVE',?,?,?,?)
                    """,
                    (symbol, story_tf, story_anchor, anchor_class, established_price, now, now, now, parent_mode, daily_status),
                )
                story_id = int(cur.lastrowid)
        story_id = int(story_id)
        conn.execute("UPDATE narrative_stories SET parent_context_mode=?, daily_range_status=?, updated_at=? WHERE id=?", (parent_mode, daily_status, now, story_id))

        chapter_id = payload.get("chapter_id")
        if chapter_id:
            chapter = conn.execute("SELECT * FROM story_chapters WHERE id=?", (int(chapter_id),)).fetchone()
            if not chapter:
                conn.execute(
                    """
                    INSERT INTO story_chapters(id,story_id,symbol,timeframe,chapter_catalyst,trigger_price,created_timestamp,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?)
                    """,
                    (int(chapter_id), story_id, symbol, chapter_tf, chapter_catalyst, established_price, now, now, now),
                )
        else:
            cur = conn.execute(
                """
                INSERT INTO story_chapters(story_id,symbol,timeframe,chapter_catalyst,trigger_price,created_timestamp,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?)
                """,
                (story_id, symbol, chapter_tf, chapter_catalyst, established_price, now, now, now),
            )
            chapter_id = int(cur.lastrowid)
        chapter_id = int(chapter_id)
        objective_id = _mos_objective_id(conn, objective_code)
        prev = conn.execute("SELECT current_lifecycle,current_phase,current_phase_part FROM market_coordinates WHERE symbol=?", (symbol,)).fetchone()
        previous_lifecycle = prev["current_lifecycle"] if prev else "NONE"
        previous_phase = f"P{prev['current_phase']}_{prev['current_phase_part']}" if prev else "NONE"
        new_phase = f"P{phase_number}_{phase_part}"

        cur = conn.execute(
            """
            INSERT INTO market_phases(chapter_id,symbol,timeframe,phase_number,phase_part,direction,active_objective,established_price,established_timestamp,created_at,updated_at,current_zone,lifecycle_state,objective_id)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (chapter_id, symbol, chapter_tf, phase_number, phase_part, _direction_from_chapter(trigger_event), objective_code, established_price, now, now, now, current_zone, lifecycle, objective_id),
        )
        phase_id = int(cur.lastrowid)
        cur = conn.execute(
            """
            INSERT INTO state_transitions(story_id,previous_lifecycle,new_lifecycle,previous_phase,new_phase,trigger_event,transition_timestamp)
            VALUES(?,?,?,?,?,?,?)
            """,
            (story_id, previous_lifecycle, lifecycle, previous_phase, new_phase, trigger_event, now),
        )
        transition_id = int(cur.lastrowid)
        cur = conn.execute(
            """
            INSERT INTO price_profiles(symbol,timeframe,story_id,chapter_id,bos_direction,broken_range_high,broken_range_low,bos_price,reclaim_price,reclaim_depth_percent,profile_type,created_timestamp)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (symbol, chapter_tf, story_id, chapter_id, bos_direction, parse_float(broken_range_high, None) if broken_range_high not in (None, "") else None, parse_float(broken_range_low, None) if broken_range_low not in (None, "") else None, bos_price, parse_float(reclaim_price, None) if reclaim_price not in (None, "") else None, parse_float(reclaim_depth_percent, None) if reclaim_depth_percent not in (None, "") else None, profile_type, now),
        )
        profile_id = int(cur.lastrowid)
        cur = conn.execute(
            """
            INSERT INTO playback_frames(story_id,frame_timestamp,parent_context_mode,daily_range_status,lifecycle_state,phase_number,phase_part,profile_type,objective_code,current_zone,established_price,trigger_event,expected_next_event,invalidation_condition)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (story_id, now, parent_mode, daily_status, lifecycle, phase_number, phase_part, profile_type, objective_code, current_zone, established_price, trigger_event, expected_next_event, invalidation_condition),
        )
        frame_id = int(cur.lastrowid)
        conn.execute(
            """
            INSERT INTO market_coordinates(symbol,story_id,chapter_id,active_objective_id,active_profile_id,parent_context_mode,daily_range_status,current_zone,current_lifecycle,current_phase,current_phase_part,last_updated)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(symbol) DO UPDATE SET
                story_id=excluded.story_id,
                chapter_id=excluded.chapter_id,
                active_objective_id=excluded.active_objective_id,
                active_profile_id=excluded.active_profile_id,
                parent_context_mode=excluded.parent_context_mode,
                daily_range_status=excluded.daily_range_status,
                current_zone=excluded.current_zone,
                current_lifecycle=excluded.current_lifecycle,
                current_phase=excluded.current_phase,
                current_phase_part=excluded.current_phase_part,
                last_updated=excluded.last_updated
            """,
            (symbol, story_id, chapter_id, objective_id, profile_id, parent_mode, daily_status, current_zone, lifecycle, phase_number, phase_part, now),
        )
        conn.commit()
    return {
        "ok": True,
        "status": "MOS_STATE_IMMUTABLY_BUILT",
        "symbol": symbol,
        "story_id": story_id,
        "chapter_id": chapter_id,
        "frame_id": frame_id,
        "phase_id": phase_id,
        "transition_id": transition_id,
        "profile_id": profile_id,
        "coordinates": {
            "parent_context_mode": parent_mode,
            "daily_range_status": daily_status,
            "lifecycle": lifecycle,
            "phase": f"P{phase_number}",
            "phase_part": phase_part,
            "profile": profile_type,
            "zone": current_zone,
            "objective": objective_code,
        },
    }


def get_mos_coordinates(symbol: str = "XAUUSD") -> dict[str, Any]:
    init_db()
    symbol = str(symbol or "XAUUSD")
    with connect() as conn:
        row = conn.execute(
            """
            SELECT mc.*, ns.story_anchor, ns.anchor_class, sc.chapter_catalyst, ot.code AS objective_code, pp.profile_type
            FROM market_coordinates mc
            JOIN narrative_stories ns ON mc.story_id=ns.id
            LEFT JOIN story_chapters sc ON mc.chapter_id=sc.id
            LEFT JOIN objective_types ot ON mc.active_objective_id=ot.id
            LEFT JOIN price_profiles pp ON mc.active_profile_id=pp.id
            WHERE mc.symbol=?
            """,
            (symbol,),
        ).fetchone()
        if not row:
            return {"ok": False, "status": "NO_ACTIVE_COORDINATES", "symbol": symbol, "coordinates": None}
        coords = {
            "story_anchor": row["story_anchor"],
            "anchor_class": row["anchor_class"],
            "chapter": row["chapter_catalyst"],
            "parent_context_mode": row["parent_context_mode"],
            "daily_range_status": row["daily_range_status"],
            "lifecycle_state": row["current_lifecycle"],
            "phase": f"P{row['current_phase']}",
            "phase_part": row["current_phase_part"],
            "profile_type": row["profile_type"],
            "objective": row["objective_code"],
            "current_zone": row["current_zone"],
            "last_updated": row["last_updated"],
        }
        return {"ok": True, "status": "TRACKING_ACTIVE", "symbol": symbol, "coordinates": coords}


def get_mos_playback(story_id: int) -> dict[str, Any]:
    init_db()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM playback_frames WHERE story_id=? ORDER BY frame_timestamp ASC, id ASC
            """,
            (int(story_id),),
        ).fetchall()
    frames = []
    for idx, row in enumerate(rows):
        frames.append({
            "frame_index": idx,
            "id": row["id"],
            "story_id": row["story_id"],
            "frame_timestamp": row["frame_timestamp"],
            "parent_context_mode": row["parent_context_mode"],
            "daily_range_status": row["daily_range_status"],
            "lifecycle_state": row["lifecycle_state"],
            "phase": f"P{row['phase_number']}_{row['phase_part']}",
            "phase_number": row["phase_number"],
            "phase_part": row["phase_part"],
            "profile_type": row["profile_type"],
            "objective_code": row["objective_code"],
            "current_zone": row["current_zone"],
            "established_price": row["established_price"],
            "trigger_event": row["trigger_event"],
            "expected_next_event": row["expected_next_event"],
            "invalidation_condition": row["invalidation_condition"],
        })
    return {"ok": True, "story_id": int(story_id), "frames": frames}


def lookahead_result_for_frames(current: dict[str, Any], next_frame: dict[str, Any] | None) -> str:
    if not next_frame:
        return "PENDING"
    trigger = str(next_frame.get("trigger_event") or "").upper()
    expected = str(current.get("expected_next_event") or "").upper()
    invalidation = str(current.get("invalidation_condition") or "").upper()
    destructive = ("LIQUIDATION", "DESTRUCTIVE", "GAP_BEYOND_INVALIDATION")
    if (invalidation and invalidation in trigger) or any(tok in trigger for tok in destructive):
        return "FAILED"
    if expected and expected in trigger:
        return "VALIDATED"
    if "PHASE_2_SKIPPED" in trigger or "QUANTUM_LEAP" in trigger or "SUPERSEDED" in trigger:
        return "VALIDATED_SUPERSEDED"
    return "DELAYED"


def get_mos_playback_evaluation(story_id: int) -> dict[str, Any]:
    data = get_mos_playback(story_id)
    frames = data.get("frames", [])
    evaluated = []
    for idx, frame in enumerate(frames):
        nxt = frames[idx + 1] if idx + 1 < len(frames) else None
        evaluated.append({**frame, "lookahead_result": lookahead_result_for_frames(frame, nxt)})
    return {"ok": True, "story_id": int(story_id), "frames": evaluated}

def mos_status() -> dict[str, Any]:
    init_db()
    with connect() as conn:
        counts = {}
        for table in [
            "narrative_stories",
            "story_chapters",
            "market_phases",
            "objective_types",
            "price_profiles",
            "state_transitions",
            "market_coordinates",
            "playback_frames",
        ]:
            try:
                counts[table] = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
            except Exception:
                counts[table] = 0
    return {"ok": True, "db": str(DB_PATH), "mos_v150": counts}


def _case_fields_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    replay = payload.get("replay") if isinstance(payload.get("replay"), dict) else {}
    anchors = payload.get("anchors") if isinstance(payload.get("anchors"), dict) else {}
    mos_payload = payload.get("mos_payload") if isinstance(payload.get("mos_payload"), dict) else {}

    def num_or_none(v):
        if v in (None, ""):
            return None
        try:
            return float(v)
        except Exception:
            return None

    return {
        "seed_name": str(payload.get("seed_name") or payload.get("name") or f"Case {now_iso()}").strip(),
        "symbol": str(payload.get("symbol") or "XAUUSD").strip(),
        "replay_timeframe": str(replay.get("timeframe") or payload.get("timeframe") or "D1"),
        "replay_candle_time": replay.get("candle_time"),
        "replay_candle_index": int(replay.get("candle_index") or 0),
        "weekly_high": num_or_none(anchors.get("weekly_high")),
        "weekly_high_time": anchors.get("weekly_high_time"),
        "weekly_low": num_or_none(anchors.get("weekly_low")),
        "weekly_low_time": anchors.get("weekly_low_time"),
        "daily_high": num_or_none(anchors.get("daily_high")),
        "daily_high_time": anchors.get("daily_high_time"),
        "daily_low": num_or_none(anchors.get("daily_low")),
        "daily_low_time": anchors.get("daily_low_time"),
        "case_scope": str(payload.get("case_scope") or anchors.get("case_scope") or mos_payload.get("case_scope") or "").upper() or None,
        "case_timeframe": str(payload.get("case_timeframe") or anchors.get("case_timeframe") or mos_payload.get("case_timeframe") or replay.get("case_timeframe") or "").upper() or None,
        "case_high": num_or_none(anchors.get("case_high")),
        "case_high_time": anchors.get("case_high_time"),
        "case_low": num_or_none(anchors.get("case_low")),
        "case_low_time": anchors.get("case_low_time"),
        "range_start_date": anchors.get("range_start_date"),
        "range_end_date": anchors.get("range_end_date"),
        "event_count": int(anchors.get("event_count") or 0),
        "anchors_json": json.dumps(anchors, ensure_ascii=False, default=str),
        "mos_payload_json": json.dumps(mos_payload, ensure_ascii=False, default=str),
        "notes": str(payload.get("notes") or ""),
    }


def save_mos_seed_idea(payload: dict[str, Any]) -> dict[str, Any]:
    """Persist a case/bookmark container.

    Atomic map events remain the truth. This table is a named wrapper around a mapping
    session, not the market's soul in a shoebox.
    """
    init_db()
    now = now_iso()
    fields = _case_fields_from_payload(payload)
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO mos_seed_ideas(
                seed_name,symbol,replay_timeframe,replay_candle_time,replay_candle_index,
                weekly_high,weekly_high_time,weekly_low,weekly_low_time,
                daily_high,daily_high_time,daily_low,daily_low_time,
                mos_payload_json,notes,created_at,updated_at,
                case_scope,case_timeframe,case_high,case_high_time,case_low,case_low_time,
                range_start_date,range_end_date,event_count,anchors_json
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                fields["seed_name"], fields["symbol"], fields["replay_timeframe"], fields["replay_candle_time"], fields["replay_candle_index"],
                fields["weekly_high"], fields["weekly_high_time"], fields["weekly_low"], fields["weekly_low_time"],
                fields["daily_high"], fields["daily_high_time"], fields["daily_low"], fields["daily_low_time"],
                fields["mos_payload_json"], fields["notes"], now, now,
                fields["case_scope"], fields["case_timeframe"], fields["case_high"], fields["case_high_time"], fields["case_low"], fields["case_low_time"],
                fields["range_start_date"], fields["range_end_date"], fields["event_count"], fields["anchors_json"],
            ),
        )
        conn.commit()
        idea_id = int(cur.lastrowid)
    return {"ok": True, "status": "MOS_CASE_SAVED", "id": idea_id, "seed_name": fields["seed_name"], "symbol": fields["symbol"]}


def update_mos_seed_idea(case_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    init_db()
    now = now_iso()
    fields = _case_fields_from_payload(payload)
    with connect() as conn:
        existing = conn.execute("SELECT id FROM mos_seed_ideas WHERE id=?", (int(case_id),)).fetchone()
        if not existing:
            return {"ok": False, "error": f"Case not found: {case_id}"}
        conn.execute(
            """
            UPDATE mos_seed_ideas SET
                seed_name=?,symbol=?,replay_timeframe=?,replay_candle_time=?,replay_candle_index=?,
                weekly_high=?,weekly_high_time=?,weekly_low=?,weekly_low_time=?,
                daily_high=?,daily_high_time=?,daily_low=?,daily_low_time=?,
                mos_payload_json=?,notes=?,updated_at=?,
                case_scope=?,case_timeframe=?,case_high=?,case_high_time=?,case_low=?,case_low_time=?,
                range_start_date=?,range_end_date=?,event_count=?,anchors_json=?
            WHERE id=?
            """,
            (
                fields["seed_name"], fields["symbol"], fields["replay_timeframe"], fields["replay_candle_time"], fields["replay_candle_index"],
                fields["weekly_high"], fields["weekly_high_time"], fields["weekly_low"], fields["weekly_low_time"],
                fields["daily_high"], fields["daily_high_time"], fields["daily_low"], fields["daily_low_time"],
                fields["mos_payload_json"], fields["notes"], now,
                fields["case_scope"], fields["case_timeframe"], fields["case_high"], fields["case_high_time"], fields["case_low"], fields["case_low_time"],
                fields["range_start_date"], fields["range_end_date"], fields["event_count"], fields["anchors_json"],
                int(case_id),
            ),
        )
        conn.commit()
    return {"ok": True, "status": "MOS_CASE_UPDATED", "id": int(case_id), "seed_name": fields["seed_name"], "symbol": fields["symbol"]}



def get_case_payload(case_id: int) -> dict[str, Any]:
    """Return a saved case workspace payload for Electron reload.

    This is intentionally a container/workspace fetch, not an analyser. It gives Electron
    the case row, linked ranges, linked events, snapshots/objectives and the date camera
    window so a saved case can reopen visually instead of behaving like a filing cabinet
    full of invisible candles. Tiny mercy.
    """
    cid = int(case_id)
    def parse_json(value: Any, default: Any = None) -> Any:
        if default is None:
            default = {}
        if value is None:
            return default
        if isinstance(value, (dict, list)):
            return value
        try:
            return json.loads(value)
        except Exception:
            return default
    with _connect() as conn:
        case_row = conn.execute("SELECT * FROM mos_seed_ideas WHERE id=?", (cid,)).fetchone()
        if not case_row:
            return {"ok": False, "error": f"Case not found: {cid}"}
        case = dict(case_row)
        case["mos_payload"] = parse_json(case.pop("mos_payload_json", "{}"))
        case["anchors"] = parse_json(case.get("anchors_json") or "{}")
        symbol = str(case.get("symbol") or "XAUUSD")
        replay_tf = normalise_timeframe(case.get("replay_timeframe") or case.get("case_timeframe") or "D1")
        case_tf = normalise_timeframe(case.get("case_timeframe") or replay_tf)
        anchors = case.get("anchors") or {}
        start = case.get("range_start_date") or anchors.get("range_start_date") or case.get("case_high_time") or anchors.get("case_high_time") or case.get("replay_candle_time")
        end = case.get("range_end_date") or anchors.get("range_end_date") or case.get("case_low_time") or anchors.get("case_low_time") or case.get("replay_candle_time")
        ranges = [dict(r) for r in conn.execute("SELECT * FROM map_ranges WHERE case_id=? ORDER BY timeframe ASC, active_from_time ASC, id ASC", (cid,)).fetchall()]
        events = [dict(r) for r in conn.execute("SELECT * FROM map_events WHERE case_id=? ORDER BY timeframe ASC, time ASC, id ASC", (cid,)).fetchall()]
        snapshots = [dict(r) for r in conn.execute("SELECT * FROM htf_state_snapshots WHERE case_id=? ORDER BY id ASC", (cid,)).fetchall()]
        objectives = [dict(r) for r in conn.execute("SELECT * FROM range_objectives WHERE case_id=? ORDER BY id ASC", (cid,)).fetchall()]
        for ev in events:
            ev["meta"] = parse_json(ev.get("meta_json") or "{}")
        for r in ranges:
            r["meta"] = parse_json(r.get("meta_json") or "{}")
        return {
            "ok": True,
            "case_id": cid,
            "case": case,
            "symbol": symbol,
            "case_timeframe": case_tf,
            "replay_timeframe": replay_tf,
            "camera": {"start_time": start, "end_time": end, "replay_time": case.get("replay_candle_time")},
            "ranges": ranges,
            "events": events,
            "snapshots": snapshots,
            "objectives": objectives,
            "counts": {"ranges": len(ranges), "events": len(events), "snapshots": len(snapshots), "objectives": len(objectives)},
        }

def get_case_audit(case_id: int, include_fallback: bool = False) -> dict[str, Any]:
    """Return a DB-level audit bundle for one mapping case.

    This is intentionally read-only. It lets Electron verify that accepted/rejected
    candidates, HTF state snapshots, and linked events are actually persisted in SQL
    instead of merely looking alive in the UI. Humanity calls this trust-but-verify;
    software calls it being caught.
    """
    init_db()
    cid = int(case_id)

    def parse_json(v: Any) -> Any:
        try:
            return json.loads(v or "{}") if isinstance(v, str) else (v or {})
        except Exception:
            return {"_raw": v}

    def ev_case_id(ev: dict[str, Any]) -> int | None:
        meta = parse_json(ev.get("meta_json"))
        raw = ev.get("case_id") or meta.get("case_id")
        try:
            return int(raw) if raw is not None and str(raw).strip() != "" else None
        except Exception:
            return None

    def parse_event_time_to_ts(v: Any) -> float | None:
        txt = str(v or "").strip()
        if not txt:
            return None
        candidates = [txt, txt.replace("Z", "+00:00"), txt.replace(".", "-", 2)]
        for c in candidates:
            try:
                return datetime.fromisoformat(c.replace(" ", "T", 1)).timestamp()
            except Exception:
                pass
        for fmt in ("%Y.%m.%d %H:%M", "%Y.%m.%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(txt, fmt).timestamp()
            except Exception:
                pass
        return None

    def is_rejected(ev: dict[str, Any]) -> bool:
        meta = parse_json(ev.get("meta_json"))
        return str(meta.get("candidate_status") or ev.get("candidate_status") or "").upper() == "REJECTED" or "REJECTED" in str(ev.get("event_type") or "").upper()

    def is_accepted(ev: dict[str, Any]) -> bool:
        meta = parse_json(ev.get("meta_json"))
        return bool(meta.get("accepted_from_candidate")) or "HTF" in str(ev.get("engine_source") or "").upper()

    with connect() as conn:
        case_row = conn.execute("SELECT * FROM mos_seed_ideas WHERE id=?", (cid,)).fetchone()
        if not case_row:
            return {"ok": False, "error": f"Case not found: {cid}"}
        case = dict(case_row)
        case["mos_payload"] = parse_json(case.pop("mos_payload_json", "{}"))
        case["anchors"] = parse_json(case.get("anchors_json") or "{}")
        symbol = str(case.get("symbol") or "XAUUSD")
        tf = normalise_timeframe(case.get("case_timeframe") or case.get("replay_timeframe") or "D1")

        all_events = [dict(r) for r in conn.execute(
            "SELECT * FROM map_events WHERE symbol=? AND timeframe=? ORDER BY COALESCE(time, created_at) ASC, id ASC",
            (symbol, tf),
        ).fetchall()]
        for ev in all_events:
            ev["meta"] = parse_json(ev.get("meta_json"))
            if ev.get("client_event_id"):
                ev["id"] = str(ev.get("client_event_id"))
            else:
                ev["id"] = str(ev.get("id"))

        case_events = [ev for ev in all_events if ev_case_id(ev) == cid]

        # If older events did not carry case_id in meta_json, include events inside the saved date window as probable linked rows.
        anchors = case.get("anchors") or {}
        start = case.get("range_start_date") or anchors.get("range_start_date") or case.get("case_high_time") or case.get("weekly_high_time") or case.get("daily_high_time")
        end = case.get("range_end_date") or anchors.get("range_end_date") or case.get("case_low_time") or case.get("weekly_low_time") or case.get("daily_low_time")
        try:
            lo = min(datetime.fromisoformat(str(start).replace("Z", "+00:00")).timestamp(), datetime.fromisoformat(str(end).replace("Z", "+00:00")).timestamp()) if start and end else None
            hi = max(datetime.fromisoformat(str(start).replace("Z", "+00:00")).timestamp(), datetime.fromisoformat(str(end).replace("Z", "+00:00")).timestamp()) if start and end else None
        except Exception:
            lo = hi = None
        # v155: clean mapping mode defaults to STRICT linked events only.
        # Old DATE_WINDOW_FALLBACK recovery was useful during migration, but it pollutes clean research audits.
        # Pass include_fallback=True only when intentionally inspecting legacy/test data.
        if include_fallback and lo is not None and hi is not None:
            seen_ids = {str(ev.get("id")) for ev in case_events}
            for ev in all_events:
                if str(ev.get("id")) in seen_ids:
                    continue
                ms = parse_event_time_to_ts(ev.get("time"))
                if ms is not None and lo <= ms <= hi:
                    ev.setdefault("audit_link_reason", "DATE_WINDOW_FALLBACK")
                    case_events.append(ev)
                    seen_ids.add(str(ev.get("id")))

        states = [dict(r) for r in conn.execute(
            "SELECT * FROM htf_state_snapshots WHERE case_id=? ORDER BY id ASC",
            (cid,),
        ).fetchall()]
        for st in states:
            st["state"] = parse_json(st.get("state_json"))

        objectives = [dict(r) for r in conn.execute(
            "SELECT * FROM range_objectives WHERE case_id=? ORDER BY id ASC",
            (cid,),
        ).fetchall()]

    accepted = [ev for ev in case_events if is_accepted(ev) and not is_rejected(ev)]
    rejected = [ev for ev in case_events if is_rejected(ev)]
    edited = [ev for ev in case_events if bool((ev.get("meta") or {}).get("user_edited_price"))]
    return {
        "ok": True,
        "case_id": cid,
        "case": case,
        "symbol": symbol,
        "timeframe": tf,
        "counts": {
            "events": len(case_events),
            "accepted_candidates": len(accepted),
            "rejected_candidates": len(rejected),
            "edited_candidates": len(edited),
            "htf_state_snapshots": len(states),
            "objectives": len(objectives),
        },
        "events": case_events,
        "candidates": {"accepted": accepted, "rejected": rejected, "edited": edited},
        "htf_state_snapshots": states,
        "objectives": objectives,
    }


def delete_mos_seed_idea(case_id: int, delete_linked_events: bool = False) -> dict[str, Any]:
    """Delete one case container and its case-scoped audit rows.

    Default keeps map_events intact because events are the raw ledger. With delete_linked_events=True,
    events explicitly carrying this case_id are removed too. Old date-window fallback ghosts are not
    removed unless a full research reset is requested. Software gets one broom at a time.
    """
    init_db()
    cid = int(case_id)
    with connect() as conn:
        existing = conn.execute("SELECT id FROM mos_seed_ideas WHERE id=?", (cid,)).fetchone()
        if not existing:
            return {"ok": False, "error": f"Case not found: {cid}"}
        deleted_events = 0
        if delete_linked_events:
            cur = conn.execute("DELETE FROM map_events WHERE case_id=?", (cid,))
            deleted_events = int(cur.rowcount or 0)
        cur_states = conn.execute("DELETE FROM htf_state_snapshots WHERE case_id=?", (cid,))
        cur_obj = conn.execute("DELETE FROM range_objectives WHERE case_id=?", (cid,))
        conn.execute("DELETE FROM mos_seed_ideas WHERE id=?", (cid,))
        conn.commit()
    return {
        "ok": True,
        "status": "MOS_CASE_DELETED",
        "id": cid,
        "deleted_events": deleted_events,
        "deleted_state_snapshots": int(cur_states.rowcount or 0),
        "deleted_objectives": int(cur_obj.rowcount or 0),
    }


def clear_mos_seed_ideas(symbol: str | None = None) -> dict[str, Any]:
    """Clear case containers for a symbol while leaving raw map events untouched."""
    init_db()
    sym = str(symbol or "").strip()
    with connect() as conn:
        if sym:
            ids = [int(r["id"]) for r in conn.execute("SELECT id FROM mos_seed_ideas WHERE symbol=?", (sym,)).fetchall()]
        else:
            ids = [int(r["id"]) for r in conn.execute("SELECT id FROM mos_seed_ideas").fetchall()]
        if ids:
            q = ",".join(["?"] * len(ids))
            conn.execute(f"DELETE FROM htf_state_snapshots WHERE case_id IN ({q})", ids)
            conn.execute(f"DELETE FROM range_objectives WHERE case_id IN ({q})", ids)
            conn.execute(f"DELETE FROM mos_seed_ideas WHERE id IN ({q})", ids)
        conn.commit()
    return {"ok": True, "status": "MOS_CASES_CLEARED", "symbol": sym or "ALL", "deleted_cases": len(ids)}


def reset_research_mapping(symbol: str = "XAUUSD", confirm: str = "") -> dict[str, Any]:
    """Hard reset research mapping rows for a symbol. Candles are preserved.

    This is the clean-slate button for real mapping. It wipes cases, map events, HTF snapshots,
    objectives, ranges, and route memory for the symbol. Raw imported OHLC candles remain intact.
    """
    init_db()
    sym = str(symbol or "XAUUSD").strip()
    if confirm != "RESET":
        return {"ok": False, "error": "CONFIRM_RESET_REQUIRED", "detail": "Pass confirm=RESET to wipe research mapping rows."}
    with connect() as conn:
        counts = {}
        for table in ["mos_seed_ideas", "map_events", "htf_state_snapshots", "range_objectives", "map_ranges", "route_memory"]:
            try:
                row = conn.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE symbol=?", (sym,)).fetchone()
                counts[table] = int(row["n"] if row else 0)
                conn.execute(f"DELETE FROM {table} WHERE symbol=?", (sym,))
            except Exception:
                counts[table] = 0
        conn.commit()
    return {"ok": True, "status": "RESEARCH_MAPPING_RESET", "symbol": sym, "deleted": counts, "candles_preserved": True}

def get_mos_seed_ideas(symbol: str = "XAUUSD", limit: int = 50) -> dict[str, Any]:
    init_db()
    symbol = str(symbol or "XAUUSD").strip()
    limit = max(1, min(200, int(limit or 50)))
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM mos_seed_ideas
            WHERE symbol=?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (symbol, limit),
        ).fetchall()
    ideas = []
    for r in rows:
        d = dict(r)
        try:
            d["mos_payload"] = json.loads(d.pop("mos_payload_json") or "{}")
        except Exception:
            d["mos_payload"] = {}
        try:
            d["anchors"] = json.loads(d.get("anchors_json") or "{}")
        except Exception:
            d["anchors"] = {}
        # Backfill old rows with newer metadata if it only lives in the JSON payload.
        d["case_scope"] = d.get("case_scope") or d.get("anchors", {}).get("case_scope") or d.get("mos_payload", {}).get("case_scope")
        d["case_timeframe"] = d.get("case_timeframe") or d.get("anchors", {}).get("case_timeframe") or d.get("mos_payload", {}).get("case_timeframe")
        d["case_high"] = d.get("case_high") if d.get("case_high") is not None else d.get("anchors", {}).get("case_high")
        d["case_low"] = d.get("case_low") if d.get("case_low") is not None else d.get("anchors", {}).get("case_low")
        ideas.append(d)
    return {"ok": True, "symbol": symbol, "ideas": ideas, "count": len(ideas)}


# =========================
# v159 Raw Mapping Ledger
# =========================
RAW_EVENT_TYPES = {
    'SET_INITIAL_ANCHOR','SET_ANCHOR','ADJUST_ANCHOR','MANUAL_BOS','AUTO_BOS',
    'RECLAIM','ABANDON_RANGE','DELETE_RECORD','NOTE'
}
RAW_EVENT_SIDES = {'HIGH','LOW','NONE'}
RAW_SOURCES = {'manual','auto','system','import'}


def _utc_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _raw_price_scale(symbol: str) -> int:
    sym = str(symbol or '').upper()
    if 'XAUUSD' in sym or 'GOLD' in sym:
        return 100
    if 'JPY' in sym:
        return 1000
    if 'US30' in sym or 'US100' in sym or 'NAS' in sym or 'US500' in sym or 'SPX' in sym:
        return 100
    return 100000


def _raw_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {k: row[k] for k in row.keys()}


def _validate_raw_event(payload: dict[str, Any], require_case: bool = True) -> tuple[bool, str | None]:
    if require_case and not payload.get('case_id'):
        return False, 'Missing case_id'
    for key in ('symbol','timeframe','event_type','event_side'):
        if not payload.get(key):
            return False, f'Missing {key}'
    if payload.get('candle_time_utc_ms') is None:
        return False, 'Missing candle_time_utc_ms'
    if str(payload.get('event_type')) not in RAW_EVENT_TYPES:
        return False, f"Invalid event_type: {payload.get('event_type')}"
    if str(payload.get('event_side')) not in RAW_EVENT_SIDES:
        return False, f"Invalid event_side: {payload.get('event_side')}"
    src = str(payload.get('source') or 'manual').lower()
    if src not in RAW_SOURCES:
        return False, f"Invalid source: {payload.get('source')}"
    return True, None


def ensure_raw_mapping_case(case_id: str, symbol: str = 'XAUUSD', case_name: str | None = None, base_timeframe: str = 'W1', price_scale_default: int | None = None, notes: str = '') -> dict[str, Any]:
    """Create/return a raw mapping case. This is the VPS-owned folder context for the raw ledger."""
    init_db()
    cid = str(case_id or str(uuid.uuid4()))
    sym = str(symbol or 'XAUUSD').upper()
    tf = str(base_timeframe or 'W1').upper()
    scale = int(price_scale_default or _raw_price_scale(sym))
    now = _utc_ms()
    with connect() as conn:
        existing = conn.execute("SELECT * FROM raw_mapping_cases WHERE case_id=?", (cid,)).fetchone()
        if existing:
            return {'ok': True, 'case': _raw_row(existing), 'created': False}
        conn.execute(
            """
            INSERT INTO raw_mapping_cases(case_id,symbol,case_name,base_timeframe,price_scale_default,status,notes,schema_version,created_at_utc_ms,updated_at_utc_ms)
            VALUES(?,?,?,?,?,'ACTIVE',?,'raw_mapping_v1',?,?)
            """,
            (cid, sym, case_name or f'{sym}_{tf}_{cid[:8]}', tf, scale, notes or '', now, now)
        )
        row = conn.execute("SELECT * FROM raw_mapping_cases WHERE case_id=?", (cid,)).fetchone()
        return {'ok': True, 'case': _raw_row(row), 'created': True}


def create_raw_mapping_case(payload: dict[str, Any]) -> dict[str, Any]:
    cid = str(payload.get('case_id') or str(uuid.uuid4()))
    return ensure_raw_mapping_case(
        cid,
        symbol=str(payload.get('symbol') or 'XAUUSD'),
        case_name=str(payload.get('case_name') or payload.get('name') or f"{payload.get('symbol','XAUUSD')}_raw_case"),
        base_timeframe=str(payload.get('base_timeframe') or payload.get('timeframe') or 'W1'),
        price_scale_default=payload.get('price_scale_default'),
        notes=str(payload.get('notes') or '')
    )


def _payload_consistent(existing: sqlite3.Row, incoming: dict[str, Any], scale: int) -> bool:
    price = incoming.get('price')
    price_int = round(float(price) * scale) if price is not None else None
    return (
        str(existing['case_id']) == str(incoming.get('case_id')) and
        str(existing['symbol']).upper() == str(incoming.get('symbol')).upper() and
        str(existing['timeframe']).upper() == str(incoming.get('timeframe')).upper() and
        int(existing['candle_time_utc_ms']) == int(incoming.get('candle_time_utc_ms')) and
        str(existing['event_type']) == str(incoming.get('event_type')) and
        str(existing['event_side']) == str(incoming.get('event_side')) and
        str(existing['source']) == str(incoming.get('source') or 'manual').lower() and
        (existing['price_int'] == price_int or (existing['price'] == price))
    )


def save_raw_mapping_event(payload: dict[str, Any]) -> dict[str, Any]:
    init_db()
    payload = dict(payload or {})
    if payload.get('event_id') is None:
        payload['event_id'] = str(uuid.uuid4())
    payload['source'] = str(payload.get('source') or 'manual').lower()
    payload['event_side'] = str(payload.get('event_side') or 'NONE').upper()
    payload['timeframe'] = str(payload.get('timeframe') or 'W1').upper()
    payload['symbol'] = str(payload.get('symbol') or 'XAUUSD').upper()
    payload['case_id'] = str(payload.get('case_id') or '')
    ok, err = _validate_raw_event(payload)
    if not ok:
        return {'ok': False, 'status': 400, 'error': err}
    now = _utc_ms()
    with connect() as conn:
        try:
            conn.execute('BEGIN IMMEDIATE')
            existing = conn.execute("SELECT * FROM raw_mapping_events WHERE event_id=?", (payload['event_id'],)).fetchone()
            case_row = conn.execute("SELECT * FROM raw_mapping_cases WHERE case_id=?", (payload['case_id'],)).fetchone()
            if case_row is None:
                # Bridge-safe: the VPS still owns the case context; it creates it on first raw write if the old UI passes an existing legacy case id.
                scale0 = _raw_price_scale(payload['symbol'])
                conn.execute(
                    """
                    INSERT INTO raw_mapping_cases(case_id,symbol,case_name,base_timeframe,price_scale_default,status,notes,schema_version,created_at_utc_ms,updated_at_utc_ms)
                    VALUES(?,?,?,?,?,'ACTIVE','','raw_mapping_v1',?,?)
                    """,
                    (payload['case_id'], payload['symbol'], f"{payload['symbol']}_{payload['timeframe']}_{payload['case_id']}", payload['timeframe'], scale0, now, now)
                )
                case_row = conn.execute("SELECT * FROM raw_mapping_cases WHERE case_id=?", (payload['case_id'],)).fetchone()
            scale = int(case_row['price_scale_default'] or _raw_price_scale(payload['symbol']))
            if existing:
                if not _payload_consistent(existing, payload, scale):
                    conn.rollback()
                    return {'ok': False, 'status': 409, 'error': 'Payload conflict identified on duplicate event_id reference'}
                conn.commit()
                return {'ok': True, 'status': 200, 'duplicate': True, 'event': _raw_row(existing)}
            price = payload.get('price')
            price_int = round(float(price) * scale) if price is not None else None
            max_order = conn.execute("SELECT COALESCE(MAX(created_order),0) AS max_order FROM raw_mapping_events WHERE case_id=?", (payload['case_id'],)).fetchone()['max_order']
            next_order = int(max_order or 0) + 1
            raw_json = payload.get('raw_payload_json')
            if isinstance(raw_json, (dict, list)):
                raw_json = json.dumps(raw_json, separators=(',', ':'), default=str)
            conn.execute(
                """
                INSERT INTO raw_mapping_events(event_id,case_id,symbol,timeframe,candle_time_utc_ms,candle_index,price,price_int,price_scale,event_type,event_side,source,created_order,is_deleted,supersedes_event_id,schema_version,notes,created_at_utc_ms,updated_at_utc_ms,raw_payload_json)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,0,?,'raw_mapping_v1',?,?,NULL,?)
                """,
                (payload['event_id'], payload['case_id'], payload['symbol'], payload['timeframe'], int(payload['candle_time_utc_ms']), payload.get('candle_index'), price, price_int, scale, payload['event_type'], payload['event_side'], payload['source'], next_order, payload.get('supersedes_event_id'), str(payload.get('notes') or ''), now, raw_json)
            )
            row = conn.execute("SELECT * FROM raw_mapping_events WHERE event_id=?", (payload['event_id'],)).fetchone()
            conn.commit()
            return {'ok': True, 'status': 201, 'event': _raw_row(row)}
        except sqlite3.IntegrityError as exc:
            try: conn.rollback()
            except Exception: pass
            return {'ok': False, 'status': 400, 'error': str(exc)}
        except Exception as exc:
            try: conn.rollback()
            except Exception: pass
            return {'ok': False, 'status': 500, 'error': str(exc)}


def save_raw_mapping_events_batch(case_id: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    init_db()
    if not case_id or not isinstance(events, list) or not events:
        return {'ok': False, 'status': 400, 'error': 'Invalid batch payload'}
    now = _utc_ms()
    with connect() as conn:
        try:
            conn.execute('BEGIN IMMEDIATE')
            case_row = conn.execute("SELECT * FROM raw_mapping_cases WHERE case_id=?", (str(case_id),)).fetchone()
            if case_row is None:
                first = events[0] if events else {}
                sym = str(first.get('symbol') or 'XAUUSD').upper()
                tf = str(first.get('timeframe') or 'W1').upper()
                scale0 = _raw_price_scale(sym)
                conn.execute("INSERT INTO raw_mapping_cases(case_id,symbol,case_name,base_timeframe,price_scale_default,status,notes,schema_version,created_at_utc_ms,updated_at_utc_ms) VALUES(?,?,?,?,?,'ACTIVE','','raw_mapping_v1',?,?)", (str(case_id), sym, f'{sym}_{tf}_{case_id}', tf, scale0, now, now))
                case_row = conn.execute("SELECT * FROM raw_mapping_cases WHERE case_id=?", (str(case_id),)).fetchone()
            scale = int(case_row['price_scale_default'] or _raw_price_scale(case_row['symbol']))
            current_order = int(conn.execute("SELECT COALESCE(MAX(created_order),0) AS max_order FROM raw_mapping_events WHERE case_id=?", (str(case_id),)).fetchone()['max_order'] or 0)
            saved = []
            for original in events:
                ev = dict(original or {})
                ev['case_id'] = str(case_id)
                ev['event_id'] = str(ev.get('event_id') or str(uuid.uuid4()))
                ev['source'] = str(ev.get('source') or 'manual').lower()
                ev['event_side'] = str(ev.get('event_side') or 'NONE').upper()
                ev['timeframe'] = str(ev.get('timeframe') or case_row['base_timeframe'] or 'W1').upper()
                ev['symbol'] = str(ev.get('symbol') or case_row['symbol'] or 'XAUUSD').upper()
                ok, err = _validate_raw_event(ev)
                if not ok:
                    conn.rollback(); return {'ok': False, 'status': 400, 'error': err, 'event': ev}
                existing = conn.execute("SELECT * FROM raw_mapping_events WHERE event_id=?", (ev['event_id'],)).fetchone()
                if existing:
                    if not _payload_consistent(existing, ev, scale):
                        conn.rollback(); return {'ok': False, 'status': 409, 'error': f"Payload conflict on duplicate event_id {ev['event_id']}"}
                    saved.append(_raw_row(existing)); continue
                current_order += 1
                price = ev.get('price')
                price_int = round(float(price) * scale) if price is not None else None
                raw_json = ev.get('raw_payload_json')
                if isinstance(raw_json, (dict, list)):
                    raw_json = json.dumps(raw_json, separators=(',', ':'), default=str)
                conn.execute("""
                    INSERT INTO raw_mapping_events(event_id,case_id,symbol,timeframe,candle_time_utc_ms,candle_index,price,price_int,price_scale,event_type,event_side,source,created_order,is_deleted,supersedes_event_id,schema_version,notes,created_at_utc_ms,updated_at_utc_ms,raw_payload_json)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,0,?,'raw_mapping_v1',?,?,NULL,?)
                """, (ev['event_id'], ev['case_id'], ev['symbol'], ev['timeframe'], int(ev['candle_time_utc_ms']), ev.get('candle_index'), price, price_int, scale, ev['event_type'], ev['event_side'], ev['source'], current_order, ev.get('supersedes_event_id'), str(ev.get('notes') or ''), now, raw_json))
                saved.append(_raw_row(conn.execute("SELECT * FROM raw_mapping_events WHERE event_id=?", (ev['event_id'],)).fetchone()))
            conn.commit()
            return {'ok': True, 'status': 201, 'count': len(saved), 'events': saved}
        except Exception as exc:
            try: conn.rollback()
            except Exception: pass
            return {'ok': False, 'status': 500, 'error': str(exc)}


def append_raw_delete_event(case_id: str, event_id: str, notes: str = '') -> dict[str, Any]:
    init_db()
    now = _utc_ms()
    with connect() as conn:
        try:
            conn.execute('BEGIN IMMEDIATE')
            target = conn.execute("SELECT * FROM raw_mapping_events WHERE event_id=? AND case_id=?", (str(event_id), str(case_id))).fetchone()
            if target is None:
                conn.rollback(); return {'ok': False, 'status': 404, 'error': 'Target event not found'}
            max_order = conn.execute("SELECT COALESCE(MAX(created_order),0) AS max_order FROM raw_mapping_events WHERE case_id=?", (str(case_id),)).fetchone()['max_order']
            next_order = int(max_order or 0) + 1
            delete_id = str(uuid.uuid4())
            conn.execute("""
                INSERT INTO raw_mapping_events(event_id,case_id,symbol,timeframe,candle_time_utc_ms,candle_index,price,price_int,price_scale,event_type,event_side,source,created_order,is_deleted,supersedes_event_id,schema_version,notes,created_at_utc_ms,updated_at_utc_ms,raw_payload_json)
                VALUES(?,?,?,?,?,?,?,?,?,'DELETE_RECORD','NONE','manual',?,0,?,'raw_mapping_v1',?,?,NULL,NULL)
            """, (delete_id, str(case_id), target['symbol'], target['timeframe'], target['candle_time_utc_ms'], target['candle_index'], target['price'], target['price_int'], target['price_scale'], next_order, str(event_id), notes or 'Delete modifier appended', now))
            row = conn.execute("SELECT * FROM raw_mapping_events WHERE event_id=?", (delete_id,)).fetchone()
            conn.commit()
            return {'ok': True, 'status': 201, 'event': _raw_row(row)}
        except Exception as exc:
            try: conn.rollback()
            except Exception: pass
            return {'ok': False, 'status': 500, 'error': str(exc)}


def get_raw_mapping_events(case_id: str) -> dict[str, Any]:
    init_db()
    with connect() as conn:
        rows = conn.execute("SELECT * FROM raw_mapping_events WHERE case_id=? ORDER BY created_order ASC", (str(case_id),)).fetchall()
        return {'ok': True, 'data': [_raw_row(r) for r in rows]}


def export_raw_mapping_events(case_id: str) -> dict[str, Any]:
    init_db()
    with connect() as conn:
        case = conn.execute("SELECT * FROM raw_mapping_cases WHERE case_id=?", (str(case_id),)).fetchone()
        if case is None:
            return {'ok': False, 'status': 404, 'error': 'Case not found'}
        rows = [_raw_row(r) for r in conn.execute("SELECT * FROM raw_mapping_events WHERE case_id=?", (str(case_id),)).fetchall()]
        sequence_by_intent = sorted(rows, key=lambda r: int(r.get('created_order') or 0))
        sequence_by_timeline = sorted(rows, key=lambda r: (int(r.get('candle_time_utc_ms') or 0), int(r.get('created_order') or 0)))
        fingerprint = '|'.join(f"{r.get('event_id')}:{r.get('created_order')}:{r.get('is_deleted')}:{r.get('supersedes_event_id') or ''}" for r in sequence_by_intent)
        ledger_hash = hashlib.sha256(fingerprint.encode('utf-8')).hexdigest()
        return {
            'ok': True,
            'meta': {'case_id': str(case_id), 'schema_version': 'raw_mapping_v1', 'total_records': len(rows), 'ledger_hash': ledger_hash, 'case': _raw_row(case)},
            'sequence_by_intent': sequence_by_intent,
            'sequence_by_timeline': sequence_by_timeline,
        }
