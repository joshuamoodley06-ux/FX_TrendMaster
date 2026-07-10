"""Advisory duplicate candidate detection for Range Library Memory imports."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import Any


def record_duplicate_candidates(
    connection: sqlite3.Connection,
    import_run_id: int,
    *,
    raw_range_ids: list[int],
    raw_event_ids: list[int],
) -> int:
    """Record duplicate candidates for raw rows touched by one import run."""
    count = 0
    for raw_range in rows_by_ids(connection, "raw_ranges", raw_range_ids):
        count += record_range_candidates(connection, import_run_id, raw_range)
    for raw_event in rows_by_ids(connection, "raw_events", raw_event_ids):
        count += record_event_candidates(connection, import_run_id, raw_event)
    return count


def record_range_candidates(
    connection: sqlite3.Connection,
    import_run_id: int,
    raw_range: sqlite3.Row,
) -> int:
    count = 0
    seen_pairs: set[tuple[str, int, int]] = set()

    count += record_range_matches(
        connection,
        import_run_id,
        raw_range,
        rule_code="exact_payload_hash",
        confidence="exact",
        reason="Range has the same raw payload hash as another stored range.",
        where_clause="payload_sha256 = ?",
        params=(raw_range["payload_sha256"],),
        seen_pairs=seen_pairs,
    )

    if raw_range["source_record_id"]:
        count += record_range_matches(
            connection,
            import_run_id,
            raw_range,
            rule_code="same_source_record_id",
            confidence="exact",
            reason="Range has the same source_record_id as another stored range.",
            where_clause="source_record_id = ?",
            params=(raw_range["source_record_id"],),
            seen_pairs=seen_pairs,
        )

    has_window = all(
        raw_range[column] is not None
        for column in ("symbol", "timeframe", "start_time_utc", "end_time_utc", "high", "low")
    )
    if has_window:
        count += record_range_matches(
            connection,
            import_run_id,
            raw_range,
            rule_code="same_range_window",
            confidence="high",
            reason="Range has the same symbol, timeframe, time window, high, and low.",
            where_clause="""
                symbol = ?
                AND timeframe = ?
                AND start_time_utc = ?
                AND end_time_utc = ?
                AND high = ?
                AND low = ?
            """,
            params=(
                raw_range["symbol"],
                raw_range["timeframe"],
                raw_range["start_time_utc"],
                raw_range["end_time_utc"],
                raw_range["high"],
                raw_range["low"],
            ),
            seen_pairs=seen_pairs,
        )
        count += record_range_matches(
            connection,
            import_run_id,
            raw_range,
            rule_code="same_window_different_payload",
            confidence="medium",
            reason="Range has the same symbol, timeframe, and time window but a different payload.",
            where_clause="""
                symbol = ?
                AND timeframe = ?
                AND start_time_utc = ?
                AND end_time_utc = ?
                AND payload_sha256 != ?
            """,
            params=(
                raw_range["symbol"],
                raw_range["timeframe"],
                raw_range["start_time_utc"],
                raw_range["end_time_utc"],
                raw_range["payload_sha256"],
            ),
            seen_pairs=seen_pairs,
        )

    if raw_range["symbol"] and raw_range["timeframe"] and raw_range["start_time_utc"] and raw_range["end_time_utc"]:
        count += record_range_matches(
            connection,
            import_run_id,
            raw_range,
            rule_code="overlapping_range_window",
            confidence="low",
            reason="Range has a simple overlapping time window for the same symbol and timeframe.",
            where_clause="""
                symbol = ?
                AND timeframe = ?
                AND start_time_utc <= ?
                AND end_time_utc >= ?
            """,
            params=(
                raw_range["symbol"],
                raw_range["timeframe"],
                raw_range["end_time_utc"],
                raw_range["start_time_utc"],
            ),
            seen_pairs=seen_pairs,
        )

    return count


def record_event_candidates(
    connection: sqlite3.Connection,
    import_run_id: int,
    raw_event: sqlite3.Row,
) -> int:
    count = 0
    seen_pairs: set[tuple[str, int, int]] = set()

    count += record_event_matches(
        connection,
        import_run_id,
        raw_event,
        rule_code="exact_payload_hash",
        confidence="exact",
        reason="Event has the same raw payload hash as another stored event.",
        where_clause="payload_sha256 = ?",
        params=(raw_event["payload_sha256"],),
        seen_pairs=seen_pairs,
    )

    if raw_event["source_record_id"]:
        count += record_event_matches(
            connection,
            import_run_id,
            raw_event,
            rule_code="same_source_record_id",
            confidence="exact",
            reason="Event has the same source_record_id as another stored event.",
            where_clause="source_record_id = ?",
            params=(raw_event["source_record_id"],),
            seen_pairs=seen_pairs,
        )

    if raw_event["event_type"] and raw_event["event_time_utc"] and raw_event["price"] is not None:
        count += record_event_matches(
            connection,
            import_run_id,
            raw_event,
            rule_code="same_event_signature",
            confidence="high",
            reason="Event has the same type, timestamp, and price as another stored event.",
            where_clause="event_type = ? AND event_time_utc = ? AND price = ?",
            params=(raw_event["event_type"], raw_event["event_time_utc"], raw_event["price"]),
            seen_pairs=seen_pairs,
        )

    return count


def record_range_matches(
    connection: sqlite3.Connection,
    import_run_id: int,
    raw_range: sqlite3.Row,
    *,
    rule_code: str,
    confidence: str,
    reason: str,
    where_clause: str,
    params: tuple[Any, ...],
    seen_pairs: set[tuple[str, int, int]],
) -> int:
    count = 0
    for candidate in matching_rows(connection, "raw_ranges", where_clause, params):
        pair = ordered_pair(raw_range["id"], candidate["id"])
        if pair is None or (rule_code, *pair) in seen_pairs:
            continue
        seen_pairs.add((rule_code, *pair))
        count += insert_candidate(
            connection=connection,
            import_run_id=import_run_id,
            candidate_type="range",
            rule_code=rule_code,
            confidence=confidence,
            reason=reason,
            left_raw_range_id=pair[0],
            right_raw_range_id=pair[1],
            left_raw_event_id=None,
            right_raw_event_id=None,
        )
    return count


def record_event_matches(
    connection: sqlite3.Connection,
    import_run_id: int,
    raw_event: sqlite3.Row,
    *,
    rule_code: str,
    confidence: str,
    reason: str,
    where_clause: str,
    params: tuple[Any, ...],
    seen_pairs: set[tuple[str, int, int]],
) -> int:
    count = 0
    for candidate in matching_rows(connection, "raw_events", where_clause, params):
        pair = ordered_pair(raw_event["id"], candidate["id"])
        if pair is None or (rule_code, *pair) in seen_pairs:
            continue
        seen_pairs.add((rule_code, *pair))
        count += insert_candidate(
            connection=connection,
            import_run_id=import_run_id,
            candidate_type="event",
            rule_code=rule_code,
            confidence=confidence,
            reason=reason,
            left_raw_range_id=None,
            right_raw_range_id=None,
            left_raw_event_id=pair[0],
            right_raw_event_id=pair[1],
        )
    return count


def insert_candidate(
    *,
    connection: sqlite3.Connection,
    import_run_id: int,
    candidate_type: str,
    rule_code: str,
    confidence: str,
    reason: str,
    left_raw_range_id: int | None,
    right_raw_range_id: int | None,
    left_raw_event_id: int | None,
    right_raw_event_id: int | None,
) -> int:
    if candidate_exists(
        connection=connection,
        import_run_id=import_run_id,
        rule_code=rule_code,
        left_raw_range_id=left_raw_range_id,
        right_raw_range_id=right_raw_range_id,
        left_raw_event_id=left_raw_event_id,
        right_raw_event_id=right_raw_event_id,
    ):
        return 0
    connection.execute(
        """
        INSERT INTO duplicate_candidates (
            import_run_id,
            candidate_type,
            left_raw_range_id,
            right_raw_range_id,
            left_raw_event_id,
            right_raw_event_id,
            rule_code,
            confidence,
            reason,
            created_at_utc,
            review_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            import_run_id,
            candidate_type,
            left_raw_range_id,
            right_raw_range_id,
            left_raw_event_id,
            right_raw_event_id,
            rule_code,
            confidence,
            reason,
            utc_now(),
            "open",
        ),
    )
    return 1


def candidate_exists(
    *,
    connection: sqlite3.Connection,
    import_run_id: int,
    rule_code: str,
    left_raw_range_id: int | None,
    right_raw_range_id: int | None,
    left_raw_event_id: int | None,
    right_raw_event_id: int | None,
) -> bool:
    row = connection.execute(
        """
        SELECT 1
        FROM duplicate_candidates
        WHERE import_run_id = ?
          AND rule_code = ?
          AND COALESCE(left_raw_range_id, -1) = COALESCE(?, -1)
          AND COALESCE(right_raw_range_id, -1) = COALESCE(?, -1)
          AND COALESCE(left_raw_event_id, -1) = COALESCE(?, -1)
          AND COALESCE(right_raw_event_id, -1) = COALESCE(?, -1)
        LIMIT 1
        """,
        (
            import_run_id,
            rule_code,
            left_raw_range_id,
            right_raw_range_id,
            left_raw_event_id,
            right_raw_event_id,
        ),
    ).fetchone()
    return row is not None


def rows_by_ids(connection: sqlite3.Connection, table: str, row_ids: list[int]) -> list[sqlite3.Row]:
    if not row_ids:
        return []
    placeholders = ",".join("?" for _ in row_ids)
    return connection.execute(
        f"SELECT * FROM {table} WHERE id IN ({placeholders}) ORDER BY id",
        tuple(row_ids),
    ).fetchall()


def matching_rows(
    connection: sqlite3.Connection,
    table: str,
    where_clause: str,
    params: tuple[Any, ...],
) -> list[sqlite3.Row]:
    return connection.execute(
        f"SELECT * FROM {table} WHERE {where_clause} ORDER BY id",
        params,
    ).fetchall()


def ordered_pair(left_id: int, right_id: int) -> tuple[int, int] | None:
    if left_id == right_id:
        return None
    return (left_id, right_id) if left_id < right_id else (right_id, left_id)


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
