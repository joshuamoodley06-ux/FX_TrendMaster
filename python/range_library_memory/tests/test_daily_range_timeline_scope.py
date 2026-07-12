from __future__ import annotations

import sqlite3
from pathlib import Path

from range_library_memory.daily_range_timeline import clear_scope
from range_library_memory.schema import init_schema


INSERT_SQL = """
INSERT INTO daily_range_timelines (
    built_at_utc, import_run_id, case_ref, symbol, source_timeframe,
    daily_range_source_id, raw_range_id, raw_status, current_daily_state,
    parent_weekly_source_id, parent_membership_state, observation_status,
    resolution_status, resolution_confidence, reason_codes_json, as_of_time,
    created_at_utc, updated_at_utc
) VALUES (
    '2026-01-01T00:00:00Z', 1, 'case', 'XAUUSD', 'D1', ?, 1, 'ACTIVE',
    'ACTIVE_PRE_BREAK', ?, 'VALID', 'CENSORED', 'PENDING', 'medium', '[]',
    '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z'
)
"""


def test_weekly_scope_replaces_selected_daily_with_stale_old_parent(tmp_path: Path) -> None:
    db_path = tmp_path / "memory.sqlite3"
    init_schema(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute(INSERT_SQL, ("10", "100"))
        connection.execute(INSERT_SQL, ("20", "200"))
        connection.execute(INSERT_SQL, ("30", "300"))
        clear_scope(
            connection,
            {
                "case_ref": None,
                "symbol": None,
                "daily_source_id": None,
                "weekly_source_id": "200",
            },
            {"10", "20"},
        )
        remaining = {
            row[0]
            for row in connection.execute(
                "SELECT daily_range_source_id FROM daily_range_timelines"
            ).fetchall()
        }
    assert remaining == {"30"}
