import hashlib
import json
import sqlite3
from pathlib import Path

from range_library_memory.local_edit_bridge import (
    BRIDGE_SCHEMA_SQL,
    BRIDGE_SCHEMA_VERSION,
    ensure_database,
    process_edit,
)


def insert_edit(db_path: Path, *, edit_id: str, kind: str, payload: dict) -> None:
    ensure_database(db_path)
    envelope = {
        "schema_version": BRIDGE_SCHEMA_VERSION,
        "kind": kind,
        "source": "test",
        "payload": payload,
        "path_params": {},
    }
    raw = json.dumps(envelope, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(raw.encode()).hexdigest()
    with sqlite3.connect(db_path) as connection:
        connection.executescript(BRIDGE_SCHEMA_SQL)
        connection.execute(
            """
            INSERT INTO local_mapping_edits (
                edit_id, schema_version, edit_kind, edit_source, payload_json,
                payload_sha256, status, attempt_count, created_at_utc, updated_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, 'PENDING', 0, ?, ?)
            """,
            (edit_id, BRIDGE_SCHEMA_VERSION, kind, "test", raw, digest, "2026-07-13T00:00:00Z", "2026-07-13T00:00:00Z"),
        )


def test_range_edit_processes_once_and_survives_reopen(tmp_path: Path):
    db_path = tmp_path / "range_library_memory.sqlite3"
    insert_edit(
        db_path,
        edit_id="edit-range-1",
        kind="structural_range",
        payload={
            "id": "range-1",
            "symbol": "XAUUSD",
            "source_timeframe": "D1",
            "structure_layer": "DAILY",
            "range_high": 2400,
            "range_low": 2300,
        },
    )

    first = process_edit(db_path, "edit-range-1")
    second = process_edit(db_path, "edit-range-1")

    assert first["state"] == "SUCCESS"
    assert first["same_database_path"] is True
    assert second["state"] == "SUCCESS"
    assert second["duplicate"] is True
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM local_mapping_edits").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM raw_ranges").fetchone()[0] == 1
        status = connection.execute(
            "SELECT status, attempt_count FROM local_mapping_edits WHERE edit_id='edit-range-1'"
        ).fetchone()
    assert status == ("PROCESSED", 1)


def test_failed_processing_preserves_original_edit_for_retry(tmp_path: Path):
    db_path = tmp_path / "range_library_memory.sqlite3"
    insert_edit(db_path, edit_id="edit-fail-1", kind="unsupported", payload={"id": "x"})

    result = process_edit(db_path, "edit-fail-1")

    assert result["state"] == "FAILED"
    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "SELECT status, payload_json, attempt_count, last_error FROM local_mapping_edits WHERE edit_id=?",
            ("edit-fail-1",),
        ).fetchone()
    assert row[0] == "FAILED"
    assert '"id":"x"' in row[1]
    assert row[2] == 1
    assert "unsupported" in row[3]
