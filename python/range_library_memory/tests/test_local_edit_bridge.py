import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from range_library_memory.local_edit_bridge import (
    BRIDGE_SCHEMA_VERSION,
    ensure_database,
    process_edit,
)


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def confirmed_envelope(edit_id: str, kind: str, payload: dict, response: dict) -> dict:
    confirmed_payload = dict(payload)
    final_id = response["range_id"] if kind == "structural_range" else response["event_id"]
    confirmed_payload.update(
        {
            "backend_confirmed": True,
            "local_edit_id": edit_id,
            "source_record_id": str(final_id),
            "backend_response": response,
        }
    )
    if kind == "structural_range":
        confirmed_payload.update({"backend_range_id": str(final_id), "range_id": str(final_id)})
    else:
        confirmed_payload.update({"backend_event_id": str(final_id), "event_id": str(final_id)})
    return {
        "schema_version": BRIDGE_SCHEMA_VERSION,
        "kind": kind,
        "source": "test",
        "payload": confirmed_payload,
        "original_payload": payload,
        "backend_response": response,
    }


def insert_edit(
    db_path: Path,
    *,
    edit_id: str,
    kind: str,
    payload: dict,
    status: str,
    backend_status: str,
    backend_response: dict | None = None,
    confirmed: dict | None = None,
) -> None:
    ensure_database(db_path)
    instruction = {
        "schema_version": BRIDGE_SCHEMA_VERSION,
        "kind": kind,
        "source": "test",
        "payload": payload,
        "path_params": {},
    }
    instruction_json = canonical(instruction)
    confirmed_json = canonical(confirmed) if confirmed else None
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO local_mapping_edits (
                edit_id, schema_version, edit_kind, edit_source,
                payload_json, payload_sha256, status, attempt_count,
                created_at_utc, updated_at_utc,
                backend_status, backend_attempt_count,
                backend_response_json, backend_confirmed_payload_json,
                backend_confirmed_payload_sha256, backend_range_id, backend_event_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, 1, ?, ?, ?, ?, ?)
            """,
            (
                edit_id,
                BRIDGE_SCHEMA_VERSION,
                kind,
                "test",
                instruction_json,
                hashlib.sha256(instruction_json.encode()).hexdigest(),
                status,
                "2026-07-13T00:00:00Z",
                "2026-07-13T00:00:00Z",
                backend_status,
                canonical(backend_response) if backend_response else None,
                confirmed_json,
                hashlib.sha256(confirmed_json.encode()).hexdigest() if confirmed_json else None,
                (confirmed or {}).get("payload", {}).get("backend_range_id"),
                (confirmed or {}).get("payload", {}).get("backend_event_id"),
            ),
        )


def test_backend_rejection_preserves_edit_but_creates_no_raw_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "range_library.sqlite3"
    insert_edit(
        db_path,
        edit_id="rejected-range",
        kind="structural_range",
        payload={"case_ref": "case-A", "symbol": "XAUUSD"},
        status="BACKEND_REJECTED",
        backend_status="REJECTED",
        backend_response={"ok": False, "error": "parent mismatch"},
    )

    with pytest.raises(ValueError, match="not been confirmed"):
        process_edit(db_path, "rejected-range")

    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM local_mapping_edits").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM raw_ranges").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM raw_events").fetchone()[0] == 0


def test_backend_assigned_range_id_is_stored_in_python_raw_range(tmp_path: Path) -> None:
    db_path = tmp_path / "range_library.sqlite3"
    payload = {
        "case_ref": "case-A",
        "symbol": "XAUUSD",
        "source_timeframe": "D1",
        "structure_layer": "DAILY",
        "range_high": 2400,
        "range_low": 2300,
    }
    response = {"ok": True, "range_id": 42}
    insert_edit(
        db_path,
        edit_id="confirmed-range",
        kind="structural_range",
        payload=payload,
        status="PYTHON_PENDING",
        backend_status="CONFIRMED",
        backend_response=response,
        confirmed=confirmed_envelope("confirmed-range", "structural_range", payload, response),
    )

    result = process_edit(db_path, "confirmed-range")

    assert result["state"] == "SUCCESS"
    with sqlite3.connect(db_path) as connection:
        source_id, raw_json = connection.execute(
            "SELECT source_record_id, raw_payload_json FROM raw_ranges"
        ).fetchone()
    assert source_id == "42"
    assert json.loads(raw_json)["backend_range_id"] == "42"


def test_later_bos_links_to_exact_backend_confirmed_range(tmp_path: Path) -> None:
    db_path = tmp_path / "range_library.sqlite3"
    range_payload = {"case_ref": "case-A", "symbol": "XAUUSD"}
    range_response = {"ok": True, "range_id": 42}
    insert_edit(
        db_path,
        edit_id="range-edit",
        kind="structural_range",
        payload=range_payload,
        status="PYTHON_PENDING",
        backend_status="CONFIRMED",
        backend_response=range_response,
        confirmed=confirmed_envelope("range-edit", "structural_range", range_payload, range_response),
    )
    process_edit(db_path, "range-edit")

    event_payload = {
        "case_ref": "case-A",
        "symbol": "XAUUSD",
        "active_range_id": "42",
        "event_type": "BOS_UP",
    }
    event_response = {"ok": True, "event_id": 99}
    insert_edit(
        db_path,
        edit_id="event-edit",
        kind="structural_event",
        payload=event_payload,
        status="PYTHON_PENDING",
        backend_status="CONFIRMED",
        backend_response=event_response,
        confirmed=confirmed_envelope("event-edit", "structural_event", event_payload, event_response),
    )
    process_edit(db_path, "event-edit")

    with sqlite3.connect(db_path) as connection:
        range_row_id = connection.execute(
            "SELECT id FROM raw_ranges WHERE source_record_id='42'"
        ).fetchone()[0]
        linked_row_id = connection.execute(
            "SELECT raw_range_id FROM raw_events WHERE source_record_id='99'"
        ).fetchone()[0]
    assert linked_row_id == range_row_id


def test_duplicate_legacy_source_ids_cannot_cross_case_identity(tmp_path: Path) -> None:
    db_path = tmp_path / "range_library.sqlite3"
    ensure_database(db_path)
    with sqlite3.connect(db_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO import_runs (run_uuid, source_path, source_kind, started_at_utc, status)
            VALUES ('legacy-run', 'legacy', 'legacy', '2026-01-01T00:00:00Z', 'completed')
            """
        )
        import_run_id = cursor.lastrowid
        range_ids = {}
        for case_ref in ("case-A", "case-B"):
            raw = canonical({"case_ref": case_ref, "symbol": "XAUUSD"})
            cursor = connection.execute(
                """
                INSERT INTO raw_ranges (
                    import_run_id, source_record_id, symbol,
                    raw_payload_json, payload_sha256, created_at_utc
                ) VALUES (?, '777', 'XAUUSD', ?, ?, '2026-01-01T00:00:00Z')
                """,
                (import_run_id, raw, hashlib.sha256(f"{raw}:{case_ref}".encode()).hexdigest()),
            )
            range_ids[case_ref] = cursor.lastrowid

    event_payload = {
        "case_ref": "case-B",
        "symbol": "XAUUSD",
        "active_range_id": "777",
        "event_type": "BOS_DOWN",
    }
    response = {"ok": True, "event_id": 100}
    insert_edit(
        db_path,
        edit_id="case-b-event",
        kind="structural_event",
        payload=event_payload,
        status="PYTHON_PENDING",
        backend_status="CONFIRMED",
        backend_response=response,
        confirmed=confirmed_envelope("case-b-event", "structural_event", event_payload, response),
    )
    process_edit(db_path, "case-b-event")

    with sqlite3.connect(db_path) as connection:
        linked = connection.execute(
            "SELECT raw_range_id FROM raw_events WHERE source_record_id='100'"
        ).fetchone()[0]
    assert linked == range_ids["case-B"]
    assert linked != range_ids["case-A"]


def test_restart_after_backend_success_processes_once(tmp_path: Path) -> None:
    db_path = tmp_path / "range_library.sqlite3"
    payload = {"case_ref": "case-A", "symbol": "XAUUSD"}
    response = {"ok": True, "range_id": 55}
    insert_edit(
        db_path,
        edit_id="restart-edit",
        kind="structural_range",
        payload=payload,
        status="PYTHON_PENDING",
        backend_status="CONFIRMED",
        backend_response=response,
        confirmed=confirmed_envelope("restart-edit", "structural_range", payload, response),
    )

    first = process_edit(db_path, "restart-edit")
    second = process_edit(db_path, "restart-edit")

    assert first["state"] == "SUCCESS"
    assert second["duplicate"] is True
    with sqlite3.connect(db_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM raw_ranges WHERE source_record_id='55'"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT attempt_count FROM local_mapping_edits WHERE edit_id='restart-edit'"
        ).fetchone()[0] == 1


def test_identical_python_retries_remain_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "range_library.sqlite3"
    payload = {"case_ref": "case-A", "symbol": "XAUUSD", "event_type": "BOS_UP"}
    response = {"ok": True, "event_id": 501}
    insert_edit(
        db_path,
        edit_id="idempotent-event",
        kind="structural_event",
        payload=payload,
        status="PYTHON_PENDING",
        backend_status="CONFIRMED",
        backend_response=response,
        confirmed=confirmed_envelope("idempotent-event", "structural_event", payload, response),
    )

    process_edit(db_path, "idempotent-event")
    process_edit(db_path, "idempotent-event")
    process_edit(db_path, "idempotent-event")

    with sqlite3.connect(db_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM raw_events WHERE source_record_id='501'"
        ).fetchone()[0] == 1
