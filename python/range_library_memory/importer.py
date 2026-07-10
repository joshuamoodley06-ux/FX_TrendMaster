"""Safe raw import storage for Range Library Memory v1."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .db import connect
from .models import ImportSummary
from .schema import init_schema

RangeRecord = dict[str, Any]
EventRecord = dict[str, Any]


def import_source(db_path: str | Path, source_path: str | Path, source_kind: str) -> ImportSummary:
    """Import raw range/event records into SQLite without rewriting existing rows."""
    db = init_schema(db_path)
    source = Path(source_path)
    run_uuid = str(uuid.uuid4())
    started_at = utc_now()
    import_run_id: int | None = None
    source_sha256: str | None = None

    with connect(db, initialize=True) as connection:
        import_run_id = create_import_run(
            connection=connection,
            run_uuid=run_uuid,
            source_path=source,
            source_kind=source_kind,
            started_at_utc=started_at,
        )
        connection.commit()

        try:
            source_bytes = source.read_bytes()
            source_sha256 = sha256_bytes(source_bytes)
            payload = json.loads(source_bytes.decode("utf-8"))
            ranges, events = split_payload(payload)

            range_stats, range_id_by_source_id = store_ranges(connection, import_run_id, ranges)
            event_stats = store_events(
                connection,
                import_run_id,
                events,
                range_id_by_source_id=range_id_by_source_id,
            )
            insert_import_results(
                connection=connection,
                import_run_id=import_run_id,
                ranges_seen=range_stats["seen"],
                ranges_inserted=range_stats["inserted"],
                ranges_reused=range_stats["reused"],
                events_seen=event_stats["seen"],
                events_inserted=event_stats["inserted"],
                events_reused=event_stats["reused"],
            )
            finish_import_run(
                connection=connection,
                import_run_id=import_run_id,
                status="completed",
                source_sha256=source_sha256,
            )
            connection.commit()
        except Exception as exc:
            connection.rollback()
            mark_import_failed(
                connection,
                import_run_id,
                notes=str(exc),
                source_sha256=source_sha256,
            )
            connection.commit()
            raise

    return ImportSummary(
        import_run_id=import_run_id,
        run_uuid=run_uuid,
        db_path=db,
        ranges_seen=range_stats["seen"],
        ranges_inserted=range_stats["inserted"],
        ranges_reused=range_stats["reused"],
        events_seen=event_stats["seen"],
        events_inserted=event_stats["inserted"],
        events_reused=event_stats["reused"],
    )


def create_import_run(
    *,
    connection: sqlite3.Connection,
    run_uuid: str,
    source_path: Path,
    source_kind: str,
    started_at_utc: str,
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO import_runs (
            run_uuid,
            source_path,
            source_kind,
            started_at_utc,
            status
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (run_uuid, str(source_path), source_kind, started_at_utc, "started"),
    )
    return int(cursor.lastrowid)


def finish_import_run(
    *,
    connection: sqlite3.Connection,
    import_run_id: int,
    status: str,
    source_sha256: str,
) -> None:
    connection.execute(
        """
        UPDATE import_runs
        SET source_sha256 = ?,
            finished_at_utc = ?,
            status = ?
        WHERE id = ?
        """,
        (source_sha256, utc_now(), status, import_run_id),
    )


def mark_import_failed(
    connection: sqlite3.Connection,
    import_run_id: int,
    notes: str,
    source_sha256: str | None = None,
) -> None:
    connection.execute(
        """
        UPDATE import_runs
        SET source_sha256 = ?,
            finished_at_utc = ?,
            status = ?,
            notes = ?
        WHERE id = ?
        """,
        (source_sha256, utc_now(), "failed", notes, import_run_id),
    )


def split_payload(payload: Any) -> tuple[list[RangeRecord], list[EventRecord]]:
    """Accept a simple JSON fixture shape while preserving each record unchanged."""
    if isinstance(payload, list):
        return ensure_records(payload, "root"), []

    if not isinstance(payload, dict):
        raise ValueError("Import source must be a JSON object or list.")

    ranges = ensure_records(payload.get("ranges", []), "ranges")
    events = ensure_records(payload.get("events", []), "events")

    for range_record in ranges:
        nested_events = range_record.get("events")
        if nested_events is not None:
            for event in ensure_records(nested_events, "range.events"):
                linked_event = dict(event)
                linked_event.setdefault("range_source_record_id", obvious_value(range_record, SOURCE_ID_KEYS))
                events.append(linked_event)

    return ranges, events


def ensure_records(value: Any, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list.")
    if not all(isinstance(item, dict) for item in value):
        raise ValueError(f"{label} must contain JSON objects.")
    return value


def store_ranges(
    connection: sqlite3.Connection,
    import_run_id: int,
    ranges: list[RangeRecord],
) -> tuple[dict[str, int], dict[str, int]]:
    stats = {"seen": len(ranges), "inserted": 0, "reused": 0}
    range_id_by_source_id: dict[str, int] = {}

    for record in ranges:
        raw_json = raw_payload_json(record)
        payload_hash = sha256_text(raw_json)
        existing_id = find_existing_id(connection, "raw_ranges", payload_hash)
        if existing_id is not None:
            stats["reused"] += 1
            raw_range_id = existing_id
        else:
            raw_range_id = insert_raw_range(connection, import_run_id, record, raw_json, payload_hash)
            stats["inserted"] += 1

        source_record_id = obvious_value(record, SOURCE_ID_KEYS)
        if source_record_id is not None:
            range_id_by_source_id[str(source_record_id)] = raw_range_id

    return stats, range_id_by_source_id


def store_events(
    connection: sqlite3.Connection,
    import_run_id: int,
    events: list[EventRecord],
    *,
    range_id_by_source_id: dict[str, int],
) -> dict[str, int]:
    stats = {"seen": len(events), "inserted": 0, "reused": 0}

    for record in events:
        raw_json = raw_payload_json(record)
        payload_hash = sha256_text(raw_json)
        existing_id = find_existing_id(connection, "raw_events", payload_hash)
        if existing_id is not None:
            stats["reused"] += 1
            continue

        insert_raw_event(
            connection=connection,
            import_run_id=import_run_id,
            record=record,
            raw_json=raw_json,
            payload_hash=payload_hash,
            raw_range_id=raw_range_id_for_event(record, range_id_by_source_id),
        )
        stats["inserted"] += 1

    return stats


def find_existing_id(connection: sqlite3.Connection, table: str, payload_hash: str) -> int | None:
    row = connection.execute(
        f"SELECT id FROM {table} WHERE payload_sha256 = ? ORDER BY id LIMIT 1",
        (payload_hash,),
    ).fetchone()
    return int(row[0]) if row else None


def insert_raw_range(
    connection: sqlite3.Connection,
    import_run_id: int,
    record: RangeRecord,
    raw_json: str,
    payload_hash: str,
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO raw_ranges (
            import_run_id,
            source_record_id,
            symbol,
            timeframe,
            range_type,
            start_time_utc,
            end_time_utc,
            high,
            low,
            raw_payload_json,
            payload_sha256,
            created_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            import_run_id,
            text_or_none(obvious_value(record, SOURCE_ID_KEYS)),
            text_or_none(obvious_value(record, ("symbol",))),
            text_or_none(obvious_value(record, ("timeframe",))),
            text_or_none(obvious_value(record, ("range_type", "type"))),
            text_or_none(obvious_value(record, ("start_time_utc", "start_time", "start"))),
            text_or_none(obvious_value(record, ("end_time_utc", "end_time", "end"))),
            numeric_or_none(obvious_value(record, ("high",))),
            numeric_or_none(obvious_value(record, ("low",))),
            raw_json,
            payload_hash,
            utc_now(),
        ),
    )
    return int(cursor.lastrowid)


def insert_raw_event(
    *,
    connection: sqlite3.Connection,
    import_run_id: int,
    record: EventRecord,
    raw_json: str,
    payload_hash: str,
    raw_range_id: int | None,
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO raw_events (
            import_run_id,
            raw_range_id,
            source_record_id,
            event_type,
            event_time_utc,
            price,
            raw_payload_json,
            payload_sha256,
            created_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            import_run_id,
            raw_range_id,
            text_or_none(obvious_value(record, SOURCE_ID_KEYS)),
            text_or_none(obvious_value(record, ("event_type", "type"))),
            text_or_none(obvious_value(record, ("event_time_utc", "event_time", "time", "timestamp"))),
            numeric_or_none(obvious_value(record, ("price",))),
            raw_json,
            payload_hash,
            utc_now(),
        ),
    )
    return int(cursor.lastrowid)


def insert_import_results(
    *,
    connection: sqlite3.Connection,
    import_run_id: int,
    ranges_seen: int,
    ranges_inserted: int,
    ranges_reused: int,
    events_seen: int,
    events_inserted: int,
    events_reused: int,
) -> None:
    summary = {
        "ranges_seen": ranges_seen,
        "ranges_inserted": ranges_inserted,
        "ranges_reused": ranges_reused,
        "events_seen": events_seen,
        "events_inserted": events_inserted,
        "events_reused": events_reused,
        "validation_issue_count": 0,
        "duplicate_candidate_count": 0,
    }
    connection.execute(
        """
        INSERT INTO range_import_results (
            import_run_id,
            ranges_seen,
            ranges_inserted,
            ranges_reused,
            events_seen,
            events_inserted,
            events_reused,
            validation_issue_count,
            duplicate_candidate_count,
            summary_json,
            created_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            import_run_id,
            ranges_seen,
            ranges_inserted,
            ranges_reused,
            events_seen,
            events_inserted,
            events_reused,
            0,
            0,
            json.dumps(summary, sort_keys=True, separators=(",", ":")),
            utc_now(),
        ),
    )


def raw_range_id_for_event(record: EventRecord, range_id_by_source_id: dict[str, int]) -> int | None:
    source_id = obvious_value(record, ("range_source_record_id", "raw_range_source_record_id", "range_id"))
    if source_id is None:
        return None
    return range_id_by_source_id.get(str(source_id))


def raw_payload_json(record: dict[str, Any]) -> str:
    return json.dumps(record, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


SOURCE_ID_KEYS = ("source_record_id", "id")


def obvious_value(record: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in record:
            return record[key]
    return None


def text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def numeric_or_none(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
