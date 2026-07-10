"""Non-mutating validation issue logging for Range Library Memory imports."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class ValidationIssue:
    severity: str
    issue_code: str
    message: str
    field_name: str | None = None
    observed_value: str | None = None


def record_range_issues(
    *,
    connection: sqlite3.Connection,
    import_run_id: int,
    raw_range_id: int,
    record: dict[str, Any],
) -> int:
    issues = validate_range(record)
    insert_issues(
        connection=connection,
        import_run_id=import_run_id,
        issues=issues,
        raw_range_id=raw_range_id,
        raw_event_id=None,
    )
    return len(issues)


def record_event_issues(
    *,
    connection: sqlite3.Connection,
    import_run_id: int,
    raw_event_id: int,
    record: dict[str, Any],
    known_range_source_ids: set[str],
) -> int:
    issues = validate_event(record, known_range_source_ids)
    insert_issues(
        connection=connection,
        import_run_id=import_run_id,
        issues=issues,
        raw_range_id=None,
        raw_event_id=raw_event_id,
    )
    return len(issues)


def validate_range(record: dict[str, Any]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    source_record_id = first_present(record, ("source_record_id", "range_id", "id"))
    symbol = first_present(record, ("symbol",))
    timeframe = first_present(record, ("timeframe", "source_timeframe", "chart_timeframe"))
    start_time = first_present(record, ("start_time_utc", "start_time", "start", "range_start_time", "active_from_time", "range_high_time"))
    end_time = first_present(record, ("end_time_utc", "end_time", "end", "range_end_time", "inactive_from_time", "range_low_time"))
    high = first_present(record, ("high", "range_high_price", "range_high", "rh"))
    low = first_present(record, ("low", "range_low_price", "range_low", "rl"))

    if is_missing(source_record_id):
        issues.append(issue("warning", "missing_source_record_id", "Range is missing source_record_id.", "source_record_id"))
    if is_missing(symbol):
        issues.append(issue("warning", "missing_symbol", "Range is missing symbol.", "symbol"))
    if is_missing(timeframe):
        issues.append(issue("warning", "missing_timeframe", "Range is missing timeframe.", "timeframe"))
    if is_missing(start_time):
        issues.append(issue("warning", "missing_start_time", "Range is missing start timestamp.", "start_time_utc"))
    if is_missing(end_time):
        issues.append(issue("warning", "missing_end_time", "Range is missing end timestamp.", "end_time_utc"))

    start_dt = parse_utc(start_time)
    end_dt = parse_utc(end_time)
    if start_dt is not None and end_dt is not None and end_dt < start_dt:
        issues.append(
            issue(
                "error",
                "invalid_range_time_order",
                "Range end timestamp is earlier than start timestamp.",
                "end_time_utc",
                end_time,
            )
        )

    high_number = parse_number(high)
    low_number = parse_number(low)
    if is_missing(high):
        issues.append(issue("warning", "missing_high", "Range is missing high boundary.", "high"))
    elif high_number is None:
        issues.append(issue("error", "non_numeric_high", "Range high is not numeric.", "high", high))
    if is_missing(low):
        issues.append(issue("warning", "missing_low", "Range is missing low boundary.", "low"))
    elif low_number is None:
        issues.append(issue("error", "non_numeric_low", "Range low is not numeric.", "low", low))

    if high_number is not None and low_number is not None and high_number < low_number:
        issues.append(
            issue(
                "error",
                "invalid_range_price_order",
                "Range high is lower than range low.",
                "high",
                high,
            )
        )

    return issues


def validate_event(record: dict[str, Any], known_range_source_ids: set[str]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    event_type = first_present(record, ("event_type", "type", "legacy_event_type"))
    event_time = first_present(record, ("event_time_utc", "event_time", "time", "timestamp", "candle_time", "candle_time_utc_ms"))
    price = first_present(record, ("price",))

    if is_missing(event_type):
        issues.append(issue("warning", "missing_event_type", "Event is missing event_type.", "event_type"))
    if is_missing(event_time):
        issues.append(issue("warning", "missing_event_time", "Event is missing timestamp.", "event_time_utc"))

    if price is not None and parse_number(price) is None:
        issues.append(issue("error", "non_numeric_event_price", "Event price is not numeric.", "price", price))

    range_links = present_values(record, ("range_source_record_id", "raw_range_source_record_id", "active_range_id", "range_id"))
    unique_links = {str(value) for value in range_links}
    if len(unique_links) > 1:
        issues.append(
            issue(
                "error",
                "contradictory_event_range_linkage",
                "Event has contradictory range linkage fields.",
                "range_source_record_id",
                ",".join(sorted(unique_links)),
            )
        )
    elif len(unique_links) == 1 and next(iter(unique_links)) not in known_range_source_ids:
        issues.append(
            issue(
                "warning",
                "missing_event_range_reference",
                "Event references a range source id absent from this import.",
                "range_source_record_id",
                next(iter(unique_links)),
            )
        )

    return issues


def insert_issues(
    *,
    connection: sqlite3.Connection,
    import_run_id: int,
    issues: list[ValidationIssue],
    raw_range_id: int | None,
    raw_event_id: int | None,
) -> None:
    connection.executemany(
        """
        INSERT INTO validation_issues (
            import_run_id,
            raw_range_id,
            raw_event_id,
            severity,
            issue_code,
            message,
            field_name,
            observed_value,
            created_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                import_run_id,
                raw_range_id,
                raw_event_id,
                validation_issue.severity,
                validation_issue.issue_code,
                validation_issue.message,
                validation_issue.field_name,
                validation_issue.observed_value,
                utc_now(),
            )
            for validation_issue in issues
        ],
    )


def issue(
    severity: str,
    issue_code: str,
    message: str,
    field_name: str | None,
    observed_value: Any = None,
) -> ValidationIssue:
    return ValidationIssue(
        severity=severity,
        issue_code=issue_code,
        message=message,
        field_name=field_name,
        observed_value=None if observed_value is None else str(observed_value),
    )


def first_present(record: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in record:
            return record[key]
    nested_payload = raw_payload(record)
    if nested_payload:
        for key in keys:
            if key in nested_payload:
                return nested_payload[key]
    return None


def present_values(record: dict[str, Any], keys: tuple[str, ...]) -> list[Any]:
    values = [record[key] for key in keys if key in record and not is_missing(record[key])]
    nested_payload = raw_payload(record)
    if nested_payload:
        values.extend(nested_payload[key] for key in keys if key in nested_payload and not is_missing(nested_payload[key]))
    return values


def raw_payload(record: dict[str, Any]) -> dict[str, Any]:
    payload = record.get("raw_payload_json")
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, str):
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def is_missing(value: Any) -> bool:
    return value is None or value == ""


def parse_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_utc(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
