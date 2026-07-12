"""Conservative second-pass resolution for Daily to Weekly parent conflicts."""

from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .db import connect
from .inspection import deterministic_json
from .parent_child import (
    CONFLICT,
    NEEDS_REVIEW,
    ORPHAN,
    RELATIONSHIP_TYPE,
    VALID,
    RangeRow,
    relationship_payload,
)
from .schema import init_schema

FACTUAL_LIFECYCLE_STATUSES = {"MAPPED_CONFIRMED", "OHLC_DERIVED", "UNBROKEN_THROUGH_AS_OF"}
INACTIVE_STATUSES = {"BROKEN", "ABANDONED", "ARCHIVED"}

COMPATIBLE = "COMPATIBLE"
AMBIGUOUS = "AMBIGUOUS"
INCOMPATIBLE = "INCOMPATIBLE"


@dataclass(frozen=True)
class RangeSnapshot:
    row: RangeRow
    formation_time: str | None


@dataclass(frozen=True)
class LifecycleSnapshot:
    range_source_id: str
    effective_status: str
    effective_active_from_time: str | None
    effective_inactive_from_time: str | None
    resolution_status: str
    resolution_confidence: str


@dataclass(frozen=True)
class CandidateAssessment:
    parent: RangeSnapshot
    effective_parent: RangeRow
    status: str
    reasons: tuple[str, ...]
    lifecycle_source: str


class ParentConflictResolverError(RuntimeError):
    """Raised when parent conflicts cannot be resolved safely."""


def resolve_parent_conflicts(
    db_path: str | Path,
    *,
    case_ref: str | None = None,
    daily_source_id: str | None = None,
) -> dict[str, Any]:
    """Rebuild Daily to Weekly relationships using derived Weekly lifecycle truth.

    Raw mapping remains untouched. A raw explicit parent or the currently selected
    relationship is treated as preferred chart context. It is confirmed only when
    case, symbol, price, range-span chronology, and the best available Weekly
    lifecycle agree. A preferred parent is never silently replaced.
    """

    path = init_schema(db_path)
    filters = {
        "case_ref": case_ref,
        "daily_source_id": str(daily_source_id) if daily_source_id else None,
    }
    timestamp = utc_now()
    with connect(path) as connection:
        dailies = load_latest_ranges(connection, "DAILY")
        weeklies = load_latest_ranges(connection, "WEEKLY")
        lifecycles = load_latest_weekly_lifecycles(connection)
        existing = load_latest_relationships(connection)
        selected = [
            daily
            for daily in dailies
            if (case_ref is None or daily.row.case_ref == case_ref)
            and (daily_source_id is None or daily.row.source_record_id == str(daily_source_id))
        ]
        selected_ids = {daily.row.source_record_id for daily in selected}
        rows = [
            resolve_daily(
                daily,
                weeklies,
                lifecycles,
                existing.get(daily.row.source_record_id),
                timestamp=timestamp,
            )
            for daily in selected
        ]
        clear_selected_relationships(connection, selected_ids)
        for row in rows:
            insert_relationship(connection, row)
        connection.commit()
    return build_summary(filters, rows)


def summarize_parent_conflicts(
    db_path: str | Path,
    *,
    case_ref: str | None = None,
    daily_source_id: str | None = None,
) -> dict[str, Any]:
    path = init_schema(db_path)
    clauses = ["relationship_type = ?"]
    params: list[Any] = [RELATIONSHIP_TYPE]
    if case_ref is not None:
        clauses.append("case_ref = ?")
        params.append(case_ref)
    if daily_source_id is not None:
        clauses.append("child_range_id = ?")
        params.append(str(daily_source_id))
    where = " AND ".join(clauses)
    with connect(path) as connection:
        groups = connection.execute(
            f"""
            SELECT link_status,
                   link_source,
                   link_confidence,
                   COUNT(*) AS count
            FROM parent_child_relationships
            WHERE {where}
            GROUP BY link_status, link_source, link_confidence
            ORDER BY link_status, link_source, link_confidence
            """,
            tuple(params),
        ).fetchall()
    rows = [dict(row) for row in groups]
    return {
        "filters": {
            "case_ref": case_ref,
            "daily_source_id": str(daily_source_id) if daily_source_id else None,
        },
        "total": sum(int(row["count"]) for row in rows),
        "groups": rows,
    }


def format_summary(summary: dict[str, Any], *, as_json: bool = False) -> str:
    if as_json:
        return deterministic_json(summary)
    if "groups" in summary:
        lines = [f"total: {summary['total']}", "status | source | confidence | count"]
        lines.extend(
            f"{row['link_status']} | {row['link_source']} | "
            f"{row['link_confidence']} | {row['count']}"
            for row in summary["groups"]
        )
        return "\n".join(lines)
    return "\n".join(f"{key}: {value}" for key, value in summary.items() if key != "filters")


def resolve_daily(
    daily: RangeSnapshot,
    weeklies: list[RangeSnapshot],
    lifecycles: dict[str, LifecycleSnapshot],
    existing: sqlite3.Row | None,
    *,
    timestamp: str,
) -> dict[str, Any]:
    compatible: list[CandidateAssessment] = []
    ambiguous: list[CandidateAssessment] = []
    assessments: dict[str, CandidateAssessment] = {}

    for weekly in weeklies:
        assessment = assess_candidate(daily, weekly, lifecycles.get(weekly.row.source_record_id))
        assessments[weekly.row.source_record_id] = assessment
        if assessment.status == COMPATIBLE:
            compatible.append(assessment)
        elif assessment.status == AMBIGUOUS:
            ambiguous.append(assessment)

    raw_explicit_id = daily.row.explicit_parent_id
    existing_parent_id = None
    if (
        not raw_explicit_id
        and existing is not None
        and str(existing["link_status"] or "").upper() in {VALID, NEEDS_REVIEW}
        and existing["parent_range_id"] is not None
    ):
        existing_parent_id = str(existing["parent_range_id"])

    preferred_id = str(raw_explicit_id or existing_parent_id or "")
    if preferred_id:
        preferred_daily = daily
        if not raw_explicit_id:
            preferred_daily = RangeSnapshot(
                replace(daily.row, explicit_parent_id=preferred_id),
                daily.formation_time,
            )
        result = resolve_explicit(
            preferred_daily,
            assessments.get(preferred_id),
            compatible,
            ambiguous,
            timestamp=timestamp,
        )
        if existing_parent_id and not raw_explicit_id:
            source = str(result["link_source"])
            if source == "resolver_explicit":
                result["link_source"] = "resolver_existing"
            elif source == "resolver_explicit_lifecycle":
                result["link_source"] = "resolver_existing_lifecycle"
            result["notes"] = str(result["notes"]).replace(
                "Explicit Weekly parent",
                "Existing Weekly parent",
            ).replace(
                "Explicit parent",
                "Existing parent",
            )
        return result

    return resolve_inferred(
        daily,
        compatible,
        ambiguous,
        timestamp=timestamp,
    )


def resolve_explicit(
    daily: RangeSnapshot,
    explicit: CandidateAssessment | None,
    compatible: list[CandidateAssessment],
    ambiguous: list[CandidateAssessment],
    *,
    timestamp: str,
) -> dict[str, Any]:
    explicit_id = str(daily.row.explicit_parent_id)
    alternatives = [
        candidate
        for candidate in compatible
        if candidate.parent.row.source_record_id != explicit_id
    ]

    if explicit is None:
        return review_payload(
            daily,
            None,
            CONFLICT if len(alternatives) > 1 else NEEDS_REVIEW,
            candidate_note(
                f"Explicit parent {explicit_id} is missing from mapped Weekly history.",
                alternatives,
            ),
            timestamp,
        )

    if explicit.status == COMPATIBLE:
        source = (
            "resolver_explicit_lifecycle"
            if explicit.lifecycle_source == "derived"
            else "resolver_explicit"
        )
        confidence = "high"
        return relationship_payload(
            daily.row,
            explicit.effective_parent,
            link_source=source,
            link_status=VALID,
            confidence=confidence,
            notes=(
                "Explicit Weekly parent confirmed by case, symbol, formation chronology, "
                f"price overlap, and {explicit.lifecycle_source} lifecycle."
            ),
            timestamp=timestamp,
        )

    reason = ", ".join(explicit.reasons) if explicit.reasons else "parent facts are incomplete"
    status = CONFLICT if len(alternatives) > 1 else NEEDS_REVIEW
    return review_payload(
        daily,
        explicit.effective_parent,
        status,
        candidate_note(
            f"Explicit parent {explicit_id} was not confirmed: {reason}.",
            alternatives,
        ),
        timestamp,
    )


def resolve_inferred(
    daily: RangeSnapshot,
    compatible: list[CandidateAssessment],
    ambiguous: list[CandidateAssessment],
    *,
    timestamp: str,
) -> dict[str, Any]:
    if len(compatible) == 1:
        candidate = compatible[0]
        return relationship_payload(
            daily.row,
            candidate.effective_parent,
            link_source="resolver_inferred",
            link_status=VALID,
            confidence="medium",
            notes=(
                "One Weekly parent matched case, symbol, formation chronology, "
                f"price overlap, and {candidate.lifecycle_source} lifecycle."
            ),
            timestamp=timestamp,
        )

    if len(compatible) > 1:
        ids = ", ".join(sorted(candidate.parent.row.source_record_id for candidate in compatible))
        return review_payload(
            daily,
            None,
            CONFLICT,
            f"Multiple compatible Weekly parents remain: {ids}.",
            timestamp,
        )

    if ambiguous:
        ids = ", ".join(sorted(candidate.parent.row.source_record_id for candidate in ambiguous))
        return review_payload(
            daily,
            None,
            NEEDS_REVIEW,
            f"Weekly candidates exist but lifecycle evidence is incomplete: {ids}.",
            timestamp,
        )

    return relationship_payload(
        daily.row,
        None,
        link_source="resolver_orphan",
        link_status=ORPHAN,
        confidence="low",
        notes="No explicit parent and no compatible Weekly parent found.",
        timestamp=timestamp,
    )


def assess_candidate(
    daily: RangeSnapshot,
    weekly: RangeSnapshot,
    lifecycle: LifecycleSnapshot | None,
) -> CandidateAssessment:
    reasons: list[str] = []
    if weekly.row.case_ref != daily.row.case_ref:
        reasons.append("case mismatch")
    if weekly.row.symbol != daily.row.symbol:
        reasons.append("symbol mismatch")
    if reasons:
        return CandidateAssessment(
            weekly,
            effective_parent_row(weekly.row, lifecycle),
            INCOMPATIBLE,
            tuple(reasons),
            lifecycle_source(lifecycle),
        )

    if not prices_overlap(weekly.row, daily.row):
        reasons.append("price does not overlap")

    parent_effective = effective_parent_row(weekly.row, lifecycle)
    parent_start = parse_time(parent_effective.start_time)
    parent_cutoff = parse_time(parent_effective.inactive_from_time)
    child_start = parse_time(daily.row.start_time or daily.formation_time)
    child_end = parse_time(daily.row.end_time or daily.formation_time)

    if child_start is None or child_end is None:
        reasons.append("Daily range span is incomplete")
    if parent_start is None:
        reasons.append("Weekly formation time missing")
    if child_end is not None and parent_start is not None and child_end < parent_start:
        reasons.append("Daily ended before Weekly formed")
    if child_start is not None and parent_cutoff is not None and child_start > parent_cutoff:
        reasons.append("Daily started after Weekly became inactive")

    if reasons:
        return CandidateAssessment(
            weekly,
            parent_effective,
            INCOMPATIBLE,
            tuple(reasons),
            lifecycle_source(lifecycle),
        )

    if inactive_lifecycle_is_ambiguous(parent_effective, lifecycle):
        return CandidateAssessment(
            weekly,
            parent_effective,
            AMBIGUOUS,
            ("inactive Weekly has no trustworthy lifecycle cutoff",),
            lifecycle_source(lifecycle),
        )

    return CandidateAssessment(
        weekly,
        parent_effective,
        COMPATIBLE,
        (),
        lifecycle_source(lifecycle),
    )


def effective_parent_row(
    parent: RangeRow,
    lifecycle: LifecycleSnapshot | None,
) -> RangeRow:
    if lifecycle is None:
        return parent
    start = lifecycle.effective_active_from_time or parent.start_time
    status = lifecycle.effective_status or parent.status
    inactive = lifecycle.effective_inactive_from_time
    if inactive is None and lifecycle.resolution_status not in FACTUAL_LIFECYCLE_STATUSES:
        inactive = parent.inactive_from_time
    return replace(
        parent,
        start_time=start,
        status=status,
        inactive_from_time=inactive,
    )


def inactive_lifecycle_is_ambiguous(
    parent: RangeRow,
    lifecycle: LifecycleSnapshot | None,
) -> bool:
    if parent.status not in INACTIVE_STATUSES:
        return False
    if parent.inactive_from_time:
        return False
    if lifecycle and lifecycle.resolution_status == "UNBROKEN_THROUGH_AS_OF":
        return False
    return True


def lifecycle_source(lifecycle: LifecycleSnapshot | None) -> str:
    if lifecycle and lifecycle.resolution_status in FACTUAL_LIFECYCLE_STATUSES:
        return "derived"
    return "raw"


def prices_overlap(parent: RangeRow, child: RangeRow) -> bool:
    if None in (parent.high, parent.low, child.high, child.low):
        return False
    parent_low, parent_high = sorted((float(parent.low), float(parent.high)))
    child_low, child_high = sorted((float(child.low), float(child.high)))
    return child_low <= parent_high and child_high >= parent_low


def review_payload(
    daily: RangeSnapshot,
    parent: RangeRow | None,
    status: str,
    notes: str,
    timestamp: str,
) -> dict[str, Any]:
    return relationship_payload(
        daily.row,
        parent,
        link_source="resolver_review",
        link_status=status,
        confidence="low",
        notes=notes,
        timestamp=timestamp,
    )


def candidate_note(prefix: str, alternatives: list[CandidateAssessment]) -> str:
    if not alternatives:
        return prefix + " No compatible alternative Weekly was found."
    ids = ", ".join(sorted(candidate.parent.row.source_record_id for candidate in alternatives))
    if len(alternatives) == 1:
        return prefix + f" One compatible alternative Weekly exists: {ids}."
    return prefix + f" Multiple compatible alternative Weeklies exist: {ids}."


def load_latest_ranges(
    connection: sqlite3.Connection,
    layer: str,
) -> list[RangeSnapshot]:
    rows = connection.execute(
        """
        SELECT *
        FROM raw_ranges
        WHERE UPPER(COALESCE(json_extract(raw_payload_json, '$.structure_layer'), range_type, '')) = ?
          AND id IN (
              SELECT MAX(id)
              FROM raw_ranges
              GROUP BY source_record_id
          )
        ORDER BY source_record_id
        """,
        (layer.upper(),),
    ).fetchall()
    return [snapshot_from_row(dict(row)) for row in rows]


def snapshot_from_row(row: dict[str, Any]) -> RangeSnapshot:
    payload = parse_payload(row.get("raw_payload_json"))
    source_id = str(row.get("source_record_id") or row["id"])
    case_ref = first_text(payload, "case_ref", "raw_case_id", "case_id")
    symbol = str(row.get("symbol") or first_text(payload, "symbol") or "UNKNOWN").upper()
    layer = str(
        first_text(payload, "structure_layer", "layer", "range_type", "type")
        or row.get("range_type")
        or ""
    ).upper()
    timeframe = row.get("timeframe") or first_text(
        payload,
        "timeframe",
        "source_timeframe",
        "chart_timeframe",
    )
    active = first_text(payload, "active_from_time")
    high_time = first_text(payload, "range_high_time")
    low_time = first_text(payload, "range_low_time")
    raw_start = (
        first_text(payload, "range_start_time", "start_time_utc", "start_time", "start")
        or row.get("start_time_utc")
    )
    raw_end = (
        first_text(payload, "range_end_time", "end_time_utc", "end_time", "end")
        or row.get("end_time_utc")
    )
    formation = latest_time([high_time, low_time, active, raw_start])
    span_start = earliest_time([high_time, low_time, active, raw_start])
    span_end = latest_time([high_time, low_time, active, raw_start, raw_end])
    effective_start = formation if layer == "WEEKLY" else span_start or formation

    raw_range = RangeRow(
        raw_id=int(row["id"]),
        import_run_id=int(row["import_run_id"]),
        source_record_id=source_id,
        case_ref=case_ref,
        symbol=symbol,
        layer=layer,
        timeframe=str(timeframe) if timeframe else None,
        start_time=effective_start or active or raw_start,
        end_time=span_end or raw_end,
        high=number(
            row.get("high"),
            first_number(payload, "high", "range_high_price", "range_high", "rh"),
        ),
        low=number(
            row.get("low"),
            first_number(payload, "low", "range_low_price", "range_low", "rl"),
        ),
        status=(first_text(payload, "status", "range_status") or "ACTIVE").upper(),
        inactive_from_time=first_text(payload, "inactive_from_time"),
        explicit_parent_id=first_text(
            payload,
            "parent_range_id",
            "parent_id",
            "parent_source_record_id",
        ),
    )
    return RangeSnapshot(raw_range, formation)


def load_latest_weekly_lifecycles(
    connection: sqlite3.Connection,
) -> dict[str, LifecycleSnapshot]:
    rows = connection.execute(
        """
        SELECT lifecycle.*
        FROM resolved_range_lifecycles AS lifecycle
        JOIN (
            SELECT range_source_id, MAX(id) AS max_id
            FROM resolved_range_lifecycles
            WHERE structure_layer = 'WEEKLY'
            GROUP BY range_source_id
        ) AS latest ON latest.max_id = lifecycle.id
        WHERE lifecycle.structure_layer = 'WEEKLY'
        """
    ).fetchall()
    return {
        str(row["range_source_id"]): LifecycleSnapshot(
            range_source_id=str(row["range_source_id"]),
            effective_status=str(row["effective_status"] or "UNKNOWN").upper(),
            effective_active_from_time=optional_text(row["effective_active_from_time"]),
            effective_inactive_from_time=optional_text(row["effective_inactive_from_time"]),
            resolution_status=str(row["resolution_status"] or "UNRESOLVED").upper(),
            resolution_confidence=str(row["resolution_confidence"] or "low"),
        )
        for row in rows
    }

def load_latest_relationships(
    connection: sqlite3.Connection,
) -> dict[str, sqlite3.Row]:
    rows = connection.execute(
        """
        SELECT relationship.*
        FROM parent_child_relationships AS relationship
        JOIN (
            SELECT child_range_id, MAX(id) AS max_id
            FROM parent_child_relationships
            WHERE relationship_type = ?
            GROUP BY child_range_id
        ) AS latest ON latest.max_id = relationship.id
        WHERE relationship.relationship_type = ?
        """,
        (RELATIONSHIP_TYPE, RELATIONSHIP_TYPE),
    ).fetchall()
    return {
        str(row["child_range_id"]): row
        for row in rows
        if row["child_range_id"] is not None
    }


def clear_selected_relationships(
    connection: sqlite3.Connection,
    child_ids: set[str],
) -> None:
    if not child_ids:
        return
    ordered = sorted(child_ids, key=source_sort_key)
    placeholders = ",".join("?" for _ in ordered)
    connection.execute(
        f"""
        DELETE FROM parent_child_relationships
        WHERE relationship_type = ?
          AND child_range_id IN ({placeholders})
        """,
        (RELATIONSHIP_TYPE, *ordered),
    )


def insert_relationship(
    connection: sqlite3.Connection,
    row: dict[str, Any],
) -> None:
    keys = tuple(row)
    connection.execute(
        f"INSERT INTO parent_child_relationships ({','.join(keys)}) "
        f"VALUES ({','.join('?' for _ in keys)})",
        tuple(row[key] for key in keys),
    )


def build_summary(
    filters: dict[str, str | None],
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    count = lambda status: sum(row["link_status"] == status for row in rows)
    return {
        "filters": filters,
        "daily_ranges_selected": len(rows),
        "rows_built": len(rows),
        "valid_count": count(VALID),
        "orphan_count": count(ORPHAN),
        "conflict_count": count(CONFLICT),
        "needs_review_count": count(NEEDS_REVIEW),
        "explicit_confirmed_count": sum(
            str(row["link_source"]).startswith("resolver_explicit")
            and row["link_status"] == VALID
            for row in rows
        ),
        "inferred_confirmed_count": sum(
            row["link_source"] == "resolver_inferred"
            and row["link_status"] == VALID
            for row in rows
        ),
        "derived_lifecycle_confirmed_count": sum(
            row["link_source"] == "resolver_explicit_lifecycle"
            and row["link_status"] == VALID
            for row in rows
        ),
    }


def parse_payload(value: Any) -> dict[str, Any]:
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def first_text(payload: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def first_number(payload: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def number(primary: Any, fallback: float | None) -> float | None:
    if primary is not None:
        try:
            return float(primary)
        except (TypeError, ValueError):
            pass
    return fallback


def optional_text(value: Any) -> str | None:
    return None if value in (None, "") else str(value)


def latest_time(values: list[str | None]) -> str | None:
    parsed = [parse_time(value) for value in values if value]
    parsed = [value for value in parsed if value is not None]
    if not parsed:
        return None
    return canonical_time(max(parsed))

def earliest_time(values: list[str | None]) -> str | None:
    parsed = [parse_time(value) for value in values if value]
    parsed = [value for value in parsed if value is not None]
    if not parsed:
        return None
    return canonical_time(min(parsed))


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def canonical_time(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def utc_now() -> str:
    return canonical_time(datetime.now(UTC))


def source_sort_key(value: str) -> tuple[int, int | str]:
    text = str(value)
    return (0, int(text)) if text.isdigit() else (1, text)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="parent_conflict_resolver")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("resolve")
    build.add_argument("--db-path", required=True)
    build.add_argument("--case-ref")
    build.add_argument("--daily-source-id")
    build.add_argument("--json", action="store_true")

    summary = subparsers.add_parser("summary")
    summary.add_argument("--db-path", required=True)
    summary.add_argument("--case-ref")
    summary.add_argument("--daily-source-id")
    summary.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "resolve":
        result = resolve_parent_conflicts(
            args.db_path,
            case_ref=args.case_ref,
            daily_source_id=args.daily_source_id,
        )
    else:
        result = summarize_parent_conflicts(
            args.db_path,
            case_ref=args.case_ref,
            daily_source_id=args.daily_source_id,
        )
    print(format_summary(result, as_json=args.json))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
