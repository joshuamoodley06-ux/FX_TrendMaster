"""Durable local mapping edit processor for the Electron Range Library bridge."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import resolve_db_path
from .db import connect
from .schema import init_schema

BRIDGE_SCHEMA_VERSION = "local_mapping_bridge_v1"
PROCESSOR_VERSION = "range_library_local_edit_v1"
PENDING = "PENDING"
PROCESSING = "PROCESSING"
PROCESSED = "PROCESSED"
FAILED = "FAILED"

BRIDGE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS local_mapping_edits (
    edit_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    edit_kind TEXT NOT NULL,
    edit_source TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    status TEXT NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL,
    processing_started_at_utc TEXT,
    processed_at_utc TEXT,
    last_error TEXT,
    result_json TEXT,
    processor_version TEXT,
    python_database_path TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_local_mapping_edits_payload
    ON local_mapping_edits(payload_sha256);
CREATE INDEX IF NOT EXISTS idx_local_mapping_edits_status
    ON local_mapping_edits(status, updated_at_utc);
"""


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def payload_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def ensure_bridge_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(BRIDGE_SCHEMA_SQL)


def absolute_db_path(db_path: str | Path) -> Path:
    return Path(db_path).expanduser().resolve()


def ensure_database(db_path: str | Path) -> Path:
    path = absolute_db_path(db_path)
    init_schema(path)
    with connect(path, initialize=True) as connection:
        ensure_bridge_schema(connection)
        connection.commit()
    return path


def process_edit(db_path: str | Path, edit_id: str) -> dict[str, Any]:
    path = ensure_database(db_path)
    with connect(path, initialize=True) as connection:
        ensure_bridge_schema(connection)
        row = connection.execute(
            "SELECT * FROM local_mapping_edits WHERE edit_id = ?", (str(edit_id),)
        ).fetchone()
        if row is None:
            raise KeyError(f"local mapping edit not found: {edit_id}")
        if str(row["status"]).upper() == PROCESSED:
            return public_result(row, path, duplicate=True)

        claimed_at = utc_now()
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """
            UPDATE local_mapping_edits
            SET status = ?,
                attempt_count = attempt_count + 1,
                processing_started_at_utc = ?,
                updated_at_utc = ?,
                last_error = NULL,
                processor_version = ?,
                python_database_path = ?
            WHERE edit_id = ?
              AND status != ?
            """,
            (
                PROCESSING,
                claimed_at,
                claimed_at,
                PROCESSOR_VERSION,
                str(path),
                str(edit_id),
                PROCESSED,
            ),
        )
        connection.commit()

        try:
            fresh = connection.execute(
                "SELECT * FROM local_mapping_edits WHERE edit_id = ?", (str(edit_id),)
            ).fetchone()
            envelope = json.loads(str(fresh["payload_json"]))
            result = process_envelope(connection, path, str(edit_id), envelope)
            completed_at = utc_now()
            connection.execute(
                """
                UPDATE local_mapping_edits
                SET status = ?,
                    result_json = ?,
                    last_error = NULL,
                    processed_at_utc = ?,
                    updated_at_utc = ?,
                    processor_version = ?,
                    python_database_path = ?
                WHERE edit_id = ?
                """,
                (
                    PROCESSED,
                    canonical_json(result),
                    completed_at,
                    completed_at,
                    PROCESSOR_VERSION,
                    str(path),
                    str(edit_id),
                ),
            )
            connection.commit()
        except Exception as exc:
            connection.rollback()
            failed_at = utc_now()
            connection.execute(
                """
                UPDATE local_mapping_edits
                SET status = ?,
                    last_error = ?,
                    updated_at_utc = ?,
                    processor_version = ?,
                    python_database_path = ?
                WHERE edit_id = ?
                """,
                (FAILED, str(exc), failed_at, PROCESSOR_VERSION, str(path), str(edit_id)),
            )
            connection.commit()

        final = connection.execute(
            "SELECT * FROM local_mapping_edits WHERE edit_id = ?", (str(edit_id),)
        ).fetchone()
        return public_result(final, path)


def process_envelope(
    connection: sqlite3.Connection,
    db_path: Path,
    edit_id: str,
    envelope: dict[str, Any],
) -> dict[str, Any]:
    if envelope.get("schema_version") != BRIDGE_SCHEMA_VERSION:
        raise ValueError(f"unsupported bridge schema: {envelope.get('schema_version')}")
    kind = str(envelope.get("kind") or "")
    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("mapping edit payload must be a JSON object")

    import_run_id = ensure_import_run(connection, edit_id, kind)
    if kind == "structural_range":
        raw_row_id, reused = append_raw_range(connection, import_run_id, payload)
        table = "raw_ranges"
    elif kind == "structural_event":
        raw_row_id, reused = append_raw_event(connection, import_run_id, payload)
        table = "raw_events"
    else:
        raise ValueError(f"unsupported local mapping edit kind: {kind}")

    finish_import_run(connection, import_run_id)
    connection.commit()
    return {
        "ok": True,
        "state": "SUCCESS",
        "edit_id": edit_id,
        "edit_kind": kind,
        "database_path": str(db_path),
        "raw_table": table,
        "raw_row_id": raw_row_id,
        "raw_row_reused": reused,
        "import_run_id": import_run_id,
        "processor_version": PROCESSOR_VERSION,
    }


def ensure_import_run(connection: sqlite3.Connection, edit_id: str, kind: str) -> int:
    run_uuid = f"local-edit:{edit_id}"
    row = connection.execute(
        "SELECT id FROM import_runs WHERE run_uuid = ?", (run_uuid,)
    ).fetchone()
    if row:
        return int(row[0])
    cursor = connection.execute(
        """
        INSERT INTO import_runs (
            run_uuid, source_path, source_kind, started_at_utc, status,
            requested_by, tool_version, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_uuid,
            f"electron://local-mapping/{edit_id}",
            f"electron_{kind}",
            utc_now(),
            "started",
            "electron_local_mapping_bridge",
            PROCESSOR_VERSION,
            "Durable local outbox copy. Backend remains structural truth.",
        ),
    )
    return int(cursor.lastrowid)


def finish_import_run(connection: sqlite3.Connection, import_run_id: int) -> None:
    connection.execute(
        """
        UPDATE import_runs
        SET finished_at_utc = ?, status = ?, tool_version = ?
        WHERE id = ?
        """,
        (utc_now(), "completed", PROCESSOR_VERSION, import_run_id),
    )


def append_raw_range(
    connection: sqlite3.Connection, import_run_id: int, payload: dict[str, Any]
) -> tuple[int, bool]:
    raw_json = canonical_json(payload)
    digest = hashlib.sha256(raw_json.encode("utf-8")).hexdigest()
    existing = connection.execute(
        "SELECT id FROM raw_ranges WHERE payload_sha256 = ? ORDER BY id LIMIT 1", (digest,)
    ).fetchone()
    if existing:
        return int(existing[0]), True
    cursor = connection.execute(
        """
        INSERT INTO raw_ranges (
            import_run_id, source_record_id, symbol, timeframe, range_type,
            start_time_utc, end_time_utc, high, low,
            raw_payload_json, payload_sha256, created_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            import_run_id,
            text_value(payload, "id", "range_id", "source_record_id", "range_key"),
            text_value(payload, "symbol"),
            text_value(payload, "source_timeframe", "timeframe", "chart_timeframe"),
            text_value(payload, "structure_layer", "range_type", "layer", "type"),
            text_value(payload, "range_start_time", "start_time", "active_from_time", "range_high_time"),
            text_value(payload, "range_end_time", "end_time", "inactive_from_time", "range_low_time"),
            number_value(payload, "range_high_price", "range_high", "high", "rh"),
            number_value(payload, "range_low_price", "range_low", "low", "rl"),
            raw_json,
            digest,
            utc_now(),
        ),
    )
    return int(cursor.lastrowid), False


def append_raw_event(
    connection: sqlite3.Connection, import_run_id: int, payload: dict[str, Any]
) -> tuple[int, bool]:
    raw_json = canonical_json(payload)
    digest = hashlib.sha256(raw_json.encode("utf-8")).hexdigest()
    existing = connection.execute(
        "SELECT id FROM raw_events WHERE payload_sha256 = ? ORDER BY id LIMIT 1", (digest,)
    ).fetchone()
    if existing:
        return int(existing[0]), True

    range_source_id = text_value(
        payload, "active_range_id", "range_id", "range_source_record_id", "parent_range_id"
    )
    raw_range_id = None
    if range_source_id:
        linked = connection.execute(
            "SELECT id FROM raw_ranges WHERE source_record_id = ? ORDER BY id DESC LIMIT 1",
            (range_source_id,),
        ).fetchone()
        raw_range_id = int(linked[0]) if linked else None

    cursor = connection.execute(
        """
        INSERT INTO raw_events (
            import_run_id, raw_range_id, source_record_id, event_type,
            event_time_utc, price, raw_payload_json, payload_sha256, created_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            import_run_id,
            raw_range_id,
            text_value(payload, "id", "event_id", "source_record_id"),
            text_value(payload, "event_type", "type", "direction"),
            text_value(payload, "event_time", "event_time_utc", "time", "candle_time"),
            number_value(payload, "price", "event_price", "break_price", "break_level_price"),
            raw_json,
            digest,
            utc_now(),
        ),
    )
    return int(cursor.lastrowid), False


def text_value(payload: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if value is not None and value != "":
            return str(value)
    return None


def number_value(payload: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = payload.get(key)
        if value is None or value == "":
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    return None


def public_result(row: sqlite3.Row, db_path: Path, *, duplicate: bool = False) -> dict[str, Any]:
    status = str(row["status"]).upper()
    state = "SUCCESS" if status == PROCESSED else "FAILED" if status == FAILED else "PENDING"
    result = json.loads(row["result_json"]) if row["result_json"] else None
    return {
        "ok": state != "FAILED",
        "saved": True,
        "state": state,
        "edit_id": str(row["edit_id"]),
        "duplicate": duplicate,
        "attempt_count": int(row["attempt_count"] or 0),
        "database_path": str(db_path),
        "electron_database_path": str(db_path),
        "python_database_path": str(db_path),
        "same_database_path": True,
        "processor_version": row["processor_version"] or PROCESSOR_VERSION,
        "error": row["last_error"],
        "result": result,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="range_library_memory.local_edit_bridge")
    subparsers = parser.add_subparsers(dest="command", required=True)
    process_parser = subparsers.add_parser("process", help="Process one durable local mapping edit.")
    process_parser.add_argument("--db-path", type=Path, default=None)
    process_parser.add_argument("--edit-id", required=True)
    process_parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    db_path = resolve_db_path(args.db_path)
    if args.command == "process":
        result = process_edit(db_path, args.edit_id)
        print(canonical_json(result) if args.json else result)
        return 0 if result["state"] != "FAILED" else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
