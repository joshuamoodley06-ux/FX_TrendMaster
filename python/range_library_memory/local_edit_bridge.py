"""Process only backend-confirmed durable mapping edits into Range Library raw memory."""

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

BRIDGE_SCHEMA_VERSION = "local_mapping_bridge_v2"
PROCESSOR_VERSION = "range_library_backend_confirmed_v2"
BACKEND_CONFIRMED = "CONFIRMED"
PYTHON_PENDING = "PYTHON_PENDING"
PYTHON_PROCESSING = "PYTHON_PROCESSING"
PYTHON_FAILED = "PYTHON_FAILED"
PROCESSED = "PROCESSED"

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
    python_database_path TEXT,
    backend_status TEXT NOT NULL DEFAULT 'UNCONFIRMED',
    backend_attempt_count INTEGER NOT NULL DEFAULT 0,
    backend_response_json TEXT,
    backend_confirmed_payload_json TEXT,
    backend_confirmed_payload_sha256 TEXT,
    backend_http_status INTEGER,
    backend_error TEXT,
    backend_confirmed_at_utc TEXT,
    backend_range_id TEXT,
    backend_event_id TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_local_mapping_edits_payload
    ON local_mapping_edits(payload_sha256);
CREATE INDEX IF NOT EXISTS idx_local_mapping_edits_status
    ON local_mapping_edits(status, updated_at_utc);
CREATE INDEX IF NOT EXISTS idx_local_mapping_edits_backend
    ON local_mapping_edits(backend_status, status, updated_at_utc);
"""

MIGRATION_COLUMNS = {
    "backend_status": "TEXT NOT NULL DEFAULT 'UNCONFIRMED'",
    "backend_attempt_count": "INTEGER NOT NULL DEFAULT 0",
    "backend_response_json": "TEXT",
    "backend_confirmed_payload_json": "TEXT",
    "backend_confirmed_payload_sha256": "TEXT",
    "backend_http_status": "INTEGER",
    "backend_error": "TEXT",
    "backend_confirmed_at_utc": "TEXT",
    "backend_range_id": "TEXT",
    "backend_event_id": "TEXT",
}


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def ensure_bridge_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(BRIDGE_SCHEMA_SQL)
    names = {str(row[1]) for row in connection.execute("PRAGMA table_info(local_mapping_edits)")}
    for name, definition in MIGRATION_COLUMNS.items():
        if name not in names:
            connection.execute(f"ALTER TABLE local_mapping_edits ADD COLUMN {name} {definition}")
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_local_mapping_edits_backend "
        "ON local_mapping_edits(backend_status, status, updated_at_utc)"
    )


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
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT * FROM local_mapping_edits WHERE edit_id = ?", (str(edit_id),)
        ).fetchone()
        if row is None:
            connection.rollback()
            raise KeyError(f"local mapping edit not found: {edit_id}")
        if str(row["status"]).upper() == PROCESSED:
            connection.rollback()
            return public_result(row, path, duplicate=True)
        if str(row["backend_status"] or "").upper() != BACKEND_CONFIRMED:
            connection.rollback()
            raise ValueError("local mapping edit has not been confirmed by the backend")
        if not row["backend_confirmed_payload_json"]:
            connection.rollback()
            raise ValueError("backend-confirmed payload is missing")

        claimed_at = utc_now()
        connection.execute(
            """
            UPDATE local_mapping_edits
            SET status=?, attempt_count=attempt_count+1,
                processing_started_at_utc=?, updated_at_utc=?, last_error=NULL,
                processor_version=?, python_database_path=?
            WHERE edit_id=? AND status!=?
            """,
            (
                PYTHON_PROCESSING, claimed_at, claimed_at, PROCESSOR_VERSION,
                str(path), str(edit_id), PROCESSED,
            ),
        )
        connection.commit()

        try:
            fresh = connection.execute(
                "SELECT * FROM local_mapping_edits WHERE edit_id = ?", (str(edit_id),)
            ).fetchone()
            envelope = json.loads(str(fresh["backend_confirmed_payload_json"]))
            result = process_confirmed_envelope(connection, path, str(edit_id), envelope)
            completed_at = utc_now()
            connection.execute(
                """
                UPDATE local_mapping_edits
                SET status=?, result_json=?, last_error=NULL,
                    processed_at_utc=?, updated_at_utc=?, processor_version=?,
                    python_database_path=?
                WHERE edit_id=?
                """,
                (
                    PROCESSED, canonical_json(result), completed_at, completed_at,
                    PROCESSOR_VERSION, str(path), str(edit_id),
                ),
            )
            connection.commit()
        except Exception as exc:
            connection.rollback()
            failed_at = utc_now()
            connection.execute(
                """
                UPDATE local_mapping_edits
                SET status=?, last_error=?, updated_at_utc=?,
                    processor_version=?, python_database_path=?
                WHERE edit_id=? AND backend_status=?
                """,
                (PYTHON_FAILED, str(exc), failed_at, PROCESSOR_VERSION, str(path), str(edit_id), BACKEND_CONFIRMED),
            )
            connection.commit()

        final = connection.execute(
            "SELECT * FROM local_mapping_edits WHERE edit_id = ?", (str(edit_id),)
        ).fetchone()
        return public_result(final, path)


def process_confirmed_envelope(
    connection: sqlite3.Connection,
    db_path: Path,
    edit_id: str,
    envelope: dict[str, Any],
) -> dict[str, Any]:
    if envelope.get("schema_version") != BRIDGE_SCHEMA_VERSION:
        raise ValueError(f"unsupported bridge schema: {envelope.get('schema_version')}")
    kind = str(envelope.get("kind") or "")
    payload = envelope.get("payload")
    if not isinstance(payload, dict) or payload.get("backend_confirmed") is not True:
        raise ValueError("Python only accepts a backend-confirmed mapping payload")
    if str(payload.get("local_edit_id") or "") != edit_id:
        raise ValueError("backend-confirmed payload edit identity mismatch")

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
    row = connection.execute("SELECT id FROM import_runs WHERE run_uuid = ?", (run_uuid,)).fetchone()
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
            run_uuid, f"electron://local-mapping/{edit_id}", f"electron_backend_confirmed_{kind}",
            utc_now(), "started", "electron_local_mapping_bridge", PROCESSOR_VERSION,
            "Backend-confirmed local durability copy. Backend remains structural truth.",
        ),
    )
    return int(cursor.lastrowid)


def finish_import_run(connection: sqlite3.Connection, import_run_id: int) -> None:
    connection.execute(
        "UPDATE import_runs SET finished_at_utc=?, status='completed', tool_version=? WHERE id=?",
        (utc_now(), PROCESSOR_VERSION, import_run_id),
    )


def append_raw_range(
    connection: sqlite3.Connection, import_run_id: int, payload: dict[str, Any]
) -> tuple[int, bool]:
    source_record_id = text_value(payload, "backend_range_id", "source_record_id", "range_id")
    if not source_record_id:
        raise ValueError("backend-confirmed range_id is missing")
    raw_json = canonical_json(payload)
    digest = hashlib.sha256(raw_json.encode("utf-8")).hexdigest()
    existing = connection.execute(
        "SELECT id FROM raw_ranges WHERE payload_sha256=? ORDER BY id LIMIT 1", (digest,)
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
            import_run_id, source_record_id, text_value(payload, "symbol"),
            text_value(payload, "source_timeframe", "timeframe", "chart_timeframe"),
            text_value(payload, "structure_layer", "range_type", "layer", "type"),
            text_value(payload, "range_start_time", "start_time", "active_from_time", "range_high_time"),
            text_value(payload, "range_end_time", "end_time", "inactive_from_time", "range_low_time"),
            number_value(payload, "range_high_price", "range_high", "high", "rh"),
            number_value(payload, "range_low_price", "range_low", "low", "rl"),
            raw_json, digest, utc_now(),
        ),
    )
    return int(cursor.lastrowid), False


def append_raw_event(
    connection: sqlite3.Connection, import_run_id: int, payload: dict[str, Any]
) -> tuple[int, bool]:
    source_record_id = text_value(payload, "backend_event_id", "source_record_id", "event_id")
    if not source_record_id:
        raise ValueError("backend-confirmed event_id is missing")
    raw_json = canonical_json(payload)
    digest = hashlib.sha256(raw_json.encode("utf-8")).hexdigest()
    existing = connection.execute(
        "SELECT id FROM raw_events WHERE payload_sha256=? ORDER BY id LIMIT 1", (digest,)
    ).fetchone()
    if existing:
        return int(existing[0]), True

    raw_range_id = resolve_exact_raw_range(connection, payload)
    cursor = connection.execute(
        """
        INSERT INTO raw_events (
            import_run_id, raw_range_id, source_record_id, event_type,
            event_time_utc, price, raw_payload_json, payload_sha256, created_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            import_run_id, raw_range_id, source_record_id,
            text_value(payload, "event_type", "type", "direction"),
            text_value(payload, "event_time", "event_time_utc", "time", "candle_time"),
            number_value(payload, "price", "event_price", "break_price", "break_level_price"),
            raw_json, digest, utc_now(),
        ),
    )
    return int(cursor.lastrowid), False


def resolve_exact_raw_range(connection: sqlite3.Connection, payload: dict[str, Any]) -> int | None:
    range_source_id = text_value(
        payload, "active_range_id", "range_source_record_id", "parent_range_id", "range_id"
    )
    if not range_source_id:
        return None
    case_ref = text_value(payload, "case_ref", "raw_case_id", "case_id")
    symbol = text_value(payload, "symbol")
    rows = connection.execute(
        """
        SELECT id,
               COALESCE(json_extract(raw_payload_json, '$.backend_confirmed'), 0) AS is_confirmed
        FROM raw_ranges
        WHERE source_record_id = ?
          AND (? IS NULL OR symbol = ?)
          AND (
            ? IS NULL OR
            COALESCE(
              json_extract(raw_payload_json, '$.case_ref'),
              json_extract(raw_payload_json, '$.raw_case_id'),
              json_extract(raw_payload_json, '$.case_id')
            ) = ?
          )
        ORDER BY is_confirmed DESC, id DESC
        """,
        (range_source_id, symbol, symbol, case_ref, case_ref),
    ).fetchall()
    if not rows:
        return None
    confirmed = [row for row in rows if int(row["is_confirmed"] or 0) == 1]
    if len(confirmed) == 1:
        return int(confirmed[0]["id"])
    if len(confirmed) > 1:
        raise ValueError(
            f"ambiguous confirmed range identity: source_record_id={range_source_id} "
            f"case_ref={case_ref} symbol={symbol}"
        )
    if len(rows) == 1:
        return int(rows[0]["id"])
    raise ValueError(
        f"ambiguous legacy range identity: source_record_id={range_source_id} "
        f"case_ref={case_ref} symbol={symbol}"
    )


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
    state = "SUCCESS" if status == PROCESSED else "FAILED" if status in {"BACKEND_REJECTED", PYTHON_FAILED} else "PENDING"
    return {
        "ok": state != "FAILED",
        "saved": True,
        "state": state,
        "status": status,
        "edit_id": str(row["edit_id"]),
        "duplicate": duplicate,
        "backend_status": str(row["backend_status"] or "UNCONFIRMED"),
        "backend_range_id": row["backend_range_id"],
        "backend_event_id": row["backend_event_id"],
        "attempt_count": int(row["attempt_count"] or 0),
        "database_path": str(db_path),
        "electron_database_path": str(db_path),
        "python_database_path": str(db_path),
        "same_database_path": True,
        "processor_version": row["processor_version"] or PROCESSOR_VERSION,
        "error": row["last_error"] or row["backend_error"],
        "result": json.loads(row["result_json"]) if row["result_json"] else None,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="range_library_memory.local_edit_bridge")
    subparsers = parser.add_subparsers(dest="command", required=True)
    process_parser = subparsers.add_parser("process", help="Process one backend-confirmed durable mapping edit.")
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
