"""Unified read-only review queue for FX TrendMaster analytical uncertainty."""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

from .db import connect
from .inspection import deterministic_json, require_existing_db
from .parent_conflict_resolver import (
    AMBIGUOUS,
    COMPATIBLE,
    assess_candidate,
    load_latest_ranges,
    load_latest_weekly_lifecycles,
)
from .schema import init_schema

ACTION_REQUIRED = "ACTION_REQUIRED"
REFERENCE_ONLY = "REFERENCE_ONLY"

QUEUE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS structure_review_queue (
    id INTEGER PRIMARY KEY,
    review_key TEXT NOT NULL UNIQUE,
    built_at_utc TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    actionability TEXT NOT NULL,
    priority INTEGER NOT NULL,
    severity TEXT NOT NULL,
    item_type TEXT NOT NULL,
    root_cause_code TEXT NOT NULL,
    source_table TEXT NOT NULL,
    source_row_id INTEGER,
    case_ref TEXT,
    symbol TEXT,
    structure_layer TEXT,
    source_timeframe TEXT,
    range_source_id TEXT,
    event_source_id TEXT,
    parent_range_id TEXT,
    candidate_range_ids_json TEXT NOT NULL,
    reason_codes_json TEXT NOT NULL,
    chart_time TEXT,
    chart_start_time TEXT,
    chart_end_time TEXT,
    title TEXT NOT NULL,
    trader_summary TEXT NOT NULL,
    suggested_action TEXT NOT NULL,
    first_seen_at_utc TEXT NOT NULL,
    last_seen_at_utc TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_structure_review_queue_active
    ON structure_review_queue(is_active, actionability, priority);
CREATE INDEX IF NOT EXISTS idx_structure_review_queue_type
    ON structure_review_queue(item_type, is_active);
CREATE INDEX IF NOT EXISTS idx_structure_review_queue_scope
    ON structure_review_queue(case_ref, symbol, structure_layer, is_active);
CREATE INDEX IF NOT EXISTS idx_structure_review_queue_range
    ON structure_review_queue(range_source_id, is_active);
"""


def build_structure_review_queue(db_path: str | Path) -> dict[str, Any]:
    """Rebuild active review items from root analytical causes only.

    Raw ranges, raw events, hierarchy truth, and analytical source tables are never
    changed. Stable review keys preserve first-seen timestamps while active items
    are refreshed and stale items are marked inactive.
    """

    path = init_schema(db_path)
    now = utc_now()
    with connect(path) as connection:
        ensure_queue_schema(connection)
        connection.execute(
            "UPDATE structure_review_queue SET is_active=0, last_seen_at_utc=? WHERE is_active=1",
            (now,),
        )

        items: list[dict[str, Any]] = []
        parent_items, parent_daily_ids = collect_parent_items(connection, now)
        items.extend(parent_items)

        weekly_items, weekly_issue_ids = collect_weekly_items(connection, now)
        items.extend(weekly_items)

        items.extend(collect_event_items(connection, now))
        items.extend(collect_validation_items(connection, now))
        items.extend(collect_duplicate_items(connection, now))
        items.extend(
            collect_daily_fallback_items(
                connection,
                now,
                covered_daily_ids=parent_daily_ids,
                covered_weekly_ids=weekly_issue_ids,
            )
        )

        for item in items:
            upsert_item(connection, item)
        connection.commit()

    return build_result(items)


def summarize_structure_review_queue(
    db_path: str | Path,
    *,
    actionability: str | None = None,
    item_type: str | None = None,
    severity: str | None = None,
    case_ref: str | None = None,
    symbol: str | None = None,
    structure_layer: str | None = None,
) -> dict[str, Any]:
    path = require_existing_db(db_path)
    filters = normalize_filters(
        actionability=actionability,
        item_type=item_type,
        severity=severity,
        case_ref=case_ref,
        symbol=symbol,
        structure_layer=structure_layer,
    )
    with connect(path) as connection:
        ensure_queue_schema(connection)
        where, params = queue_where(filters, active_only=True)
        total = int(
            connection.execute(
                f"SELECT COUNT(*) FROM structure_review_queue {where}",
                tuple(params),
            ).fetchone()[0]
        )
        action_required = int(
            connection.execute(
                f"SELECT COUNT(*) FROM structure_review_queue {where} "
                + ("AND" if where else "WHERE")
                + " actionability = ?",
                (*params, ACTION_REQUIRED),
            ).fetchone()[0]
        )
        reference_only = int(
            connection.execute(
                f"SELECT COUNT(*) FROM structure_review_queue {where} "
                + ("AND" if where else "WHERE")
                + " actionability = ?",
                (*params, REFERENCE_ONLY),
            ).fetchone()[0]
        )
        by_type = grouped_count(connection, "item_type", where, params)
        by_severity = grouped_count(connection, "severity", where, params)
        by_layer = grouped_count(connection, "structure_layer", where, params)
        by_actionability = grouped_count(connection, "actionability", where, params)

    return {
        "filters": filters,
        "totals": {
            "active": total,
            "action_required": action_required,
            "reference_only": reference_only,
        },
        "by_type": by_type,
        "by_severity": by_severity,
        "by_layer": by_layer,
        "by_actionability": by_actionability,
    }


def list_structure_review_queue(
    db_path: str | Path,
    *,
    actionability: str | None = None,
    item_type: str | None = None,
    severity: str | None = None,
    case_ref: str | None = None,
    symbol: str | None = None,
    structure_layer: str | None = None,
    range_source_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    path = require_existing_db(db_path)
    filters = normalize_filters(
        actionability=actionability,
        item_type=item_type,
        severity=severity,
        case_ref=case_ref,
        symbol=symbol,
        structure_layer=structure_layer,
        range_source_id=range_source_id,
    )
    with connect(path) as connection:
        ensure_queue_schema(connection)
        where, params = queue_where(filters, active_only=True)
        rows = connection.execute(
            f"""
            SELECT *
            FROM structure_review_queue
            {where}
            ORDER BY
                CASE actionability WHEN '{ACTION_REQUIRED}' THEN 0 ELSE 1 END,
                priority ASC,
                CASE severity
                    WHEN 'CRITICAL' THEN 0
                    WHEN 'HIGH' THEN 1
                    WHEN 'MEDIUM' THEN 2
                    WHEN 'LOW' THEN 3
                    ELSE 4
                END,
                item_type ASC,
                CASE WHEN range_source_id GLOB '[0-9]*' THEN CAST(range_source_id AS INTEGER) END,
                range_source_id ASC,
                id ASC
            LIMIT ?
            """,
            (*params, max(1, int(limit))),
        ).fetchall()
    return [queue_row(dict(row)) for row in rows]


def format_summary(summary: dict[str, Any], *, as_json: bool = False) -> str:
    if as_json:
        return deterministic_json(summary)
    totals = summary["totals"]
    lines = [
        f"active: {totals['active']}",
        f"action_required: {totals['action_required']}",
        f"reference_only: {totals['reference_only']}",
        "",
        "item_type | count",
    ]
    lines.extend(f"{row['value']} | {row['count']}" for row in summary["by_type"])
    return "\n".join(lines)


def format_items(items: list[dict[str, Any]], *, as_json: bool = False) -> str:
    if as_json:
        return deterministic_json({"items": items})
    if not items:
        return "No active structure review items found."
    lines = [
        "priority | actionability | severity | item_type | layer | range | event | title | action"
    ]
    for item in items:
        lines.append(
            " | ".join(
                str(item.get(key) if item.get(key) is not None else "")
                for key in (
                    "priority",
                    "actionability",
                    "severity",
                    "item_type",
                    "structure_layer",
                    "range_source_id",
                    "event_source_id",
                    "title",
                    "suggested_action",
                )
            )
        )
    return "\n".join(lines)


def collect_parent_items(
    connection: sqlite3.Connection,
    now: str,
) -> tuple[list[dict[str, Any]], set[str]]:
    rows = connection.execute(
        """
        SELECT relationship.*
        FROM parent_child_relationships AS relationship
        JOIN (
            SELECT child_range_id, MAX(id) AS max_id
            FROM parent_child_relationships
            WHERE relationship_type = 'weekly_daily'
            GROUP BY child_range_id
        ) AS latest ON latest.max_id = relationship.id
        WHERE relationship.relationship_type = 'weekly_daily'
          AND relationship.link_status IN ('CONFLICT', 'NEEDS_REVIEW', 'ORPHAN')
        ORDER BY relationship.id
        """
    ).fetchall()
    dailies = {item.row.source_record_id: item for item in load_latest_ranges(connection, "DAILY")}
    weeklies = load_latest_ranges(connection, "WEEKLY")
    lifecycles = load_latest_weekly_lifecycles(connection)

    items: list[dict[str, Any]] = []
    covered: set[str] = set()
    for relationship in rows:
        daily_id = str(relationship["child_range_id"] or "")
        if not daily_id:
            continue
        daily = dailies.get(daily_id)
        candidates: list[str] = []
        if daily is not None:
            for weekly in weeklies:
                assessment = assess_candidate(
                    daily,
                    weekly,
                    lifecycles.get(weekly.row.source_record_id),
                )
                if assessment.status in {COMPATIBLE, AMBIGUOUS}:
                    candidates.append(weekly.row.source_record_id)
        candidates = sorted(set(candidates), key=source_sort_key)

        status = str(relationship["link_status"]).upper()
        if status == "CONFLICT":
            actionability = ACTION_REQUIRED
            severity = "HIGH"
            priority = 10
            item_type = "PARENT_CONFLICT"
            root_code = "MULTIPLE_WEEKLY_PARENTS"
            candidate_text = ", ".join(candidates) if candidates else "multiple Weeklies"
            summary = (
                f"Daily {daily_id} can belong to {candidate_text}. "
                "Python cannot confirm one Weekly parent."
            )
            action = "Open the Daily with the candidate Weeklies visible and confirm the correct parent."
        elif status == "NEEDS_REVIEW":
            actionability = ACTION_REQUIRED
            severity = "HIGH"
            priority = 20
            item_type = "PARENT_NEEDS_REVIEW"
            root_code = "WEEKLY_PARENT_NOT_CONFIRMED"
            summary = (
                f"Daily {daily_id} has a Weekly parent link that factual price or lifecycle evidence "
                "cannot confirm."
            )
            action = "Review the Daily against its current and alternative Weekly parent candidates."
        else:
            actionability = REFERENCE_ONLY
            severity = "LOW"
            priority = 90
            item_type = "TRUE_ORPHAN"
            root_code = "NO_COMPATIBLE_WEEKLY_PARENT"
            summary = f"Daily {daily_id} has no compatible Weekly parent in the mapped case."
            action = "No action unless this Daily was expected to belong to a mapped Weekly."

        covered.add(daily_id)
        items.append(
            item_payload(
                review_key=f"parent:{daily_id}",
                now=now,
                actionability=actionability,
                priority=priority,
                severity=severity,
                item_type=item_type,
                root_cause_code=root_code,
                source_table="parent_child_relationships",
                source_row_id=relationship["id"],
                case_ref=relationship["case_ref"],
                symbol=relationship["symbol"],
                structure_layer="DAILY",
                source_timeframe=relationship["child_timeframe"] or "D1",
                range_source_id=daily_id,
                parent_range_id=relationship["parent_range_id"],
                candidate_range_ids=candidates,
                reason_codes=[status],
                chart_time=daily.formation_time if daily else None,
                chart_start_time=daily.row.start_time if daily else None,
                chart_end_time=daily.row.end_time if daily else None,
                title=f"Daily {daily_id}: Weekly parent {status.replace('_', ' ').title()}",
                trader_summary=summary,
                suggested_action=action,
            )
        )
    return items, covered


def collect_weekly_items(
    connection: sqlite3.Connection,
    now: str,
) -> tuple[list[dict[str, Any]], set[str]]:
    rows = connection.execute(
        """
        SELECT *
        FROM weekly_direction_contexts
        WHERE current_direction_state IN ('UNRESOLVED', 'NEEDS_REVIEW')
        ORDER BY id
        """
    ).fetchall()
    weeklies = {item.row.source_record_id: item for item in load_latest_ranges(connection, "WEEKLY")}
    items: list[dict[str, Any]] = []
    covered: set[str] = set()
    for row in rows:
        weekly_id = str(row["weekly_range_source_id"])
        reasons = parse_codes(row["reason_codes_json"])
        weekly = weeklies.get(weekly_id)
        covered.add(weekly_id)

        if str(row["current_direction_state"]).upper() == "UNRESOLVED":
            actionability = REFERENCE_ONLY
            severity = "LOW"
            priority = 80
            item_type = "WEEKLY_CREATION_CONTEXT_UNAVAILABLE"
            root_code = reasons[0] if reasons else "NO_CREATION_LINK"
            summary = (
                f"Weekly {weekly_id} has no confirmed creation chain in mapped history. "
                "This may be an intentionally fragmented historical case."
            )
            action = "No action unless this case is needed for Weekly-direction analysis."
        else:
            actionability = ACTION_REQUIRED
            severity = "HIGH"
            priority = 25
            item_type = "WEEKLY_CREATION_REVIEW"
            root_code = reasons[0] if reasons else "WEEKLY_CREATION_NEEDS_REVIEW"
            summary = (
                f"Weekly {weekly_id} has creation evidence, but the old Weekly, creating BOS, "
                "or reclaim chain is not trustworthy enough to confirm."
            )
            action = "Open the Weekly creation area and confirm the old Weekly and creating BOS chain."

        items.append(
            item_payload(
                review_key=f"weekly-creation:{weekly_id}",
                now=now,
                actionability=actionability,
                priority=priority,
                severity=severity,
                item_type=item_type,
                root_cause_code=root_code,
                source_table="weekly_direction_contexts",
                source_row_id=row["id"],
                case_ref=row["case_ref"],
                symbol=row["symbol"],
                structure_layer="WEEKLY",
                source_timeframe=row["source_timeframe"] or "W1",
                range_source_id=weekly_id,
                event_source_id=row["creation_event_source_id"],
                parent_range_id=row["creation_old_weekly_source_id"],
                candidate_range_ids=[row["creation_old_weekly_source_id"]]
                if row["creation_old_weekly_source_id"]
                else [],
                reason_codes=reasons,
                chart_time=row["creation_break_time"] or (weekly.formation_time if weekly else None),
                chart_start_time=weekly.row.start_time if weekly else None,
                chart_end_time=weekly.row.end_time if weekly else None,
                title=f"Weekly {weekly_id}: Creation Context {str(row['current_direction_state']).title()}",
                trader_summary=summary,
                suggested_action=action,
            )
        )
    return items, covered


def collect_event_items(connection: sqlite3.Connection, now: str) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT evidence.*
        FROM event_ohlc_evidence AS evidence
        JOIN (
            SELECT COALESCE(event_source_id, CAST(id AS TEXT)) AS event_key, MAX(id) AS max_id
            FROM event_ohlc_evidence
            GROUP BY COALESCE(event_source_id, CAST(id AS TEXT))
        ) AS latest ON latest.max_id = evidence.id
        WHERE evidence.resolution_status IN ('NEEDS_REVIEW', 'MISSING_DATA', 'UNRESOLVED')
           OR evidence.transition_status = 'INVALID'
           OR evidence.evidence_status IN (
                'INVALID_CHRONOLOGY',
                'TIME_MISMATCH',
                'BOUNDARY_NOT_BREACHED',
                'INCOMPLETE_RANGE',
                'MISSING_RANGE',
                'NEEDS_REVIEW'
           )
        ORDER BY evidence.id
        """
    ).fetchall()
    items: list[dict[str, Any]] = []
    for row in rows:
        event_key = str(row["event_source_id"] or row["id"])
        reasons = sorted(
            set(parse_codes(row["reason_codes_json"]))
            | set(parse_codes(row["transition_reason_codes_json"]))
        )
        if row["resolution_status"] == "MISSING_DATA":
            item_type = "MISSING_CANDLE_EVIDENCE"
            root_code = "MISSING_CANDLES"
            severity = "HIGH"
            priority = 12
            summary = (
                f"BOS event {event_key} cannot be checked because the required "
                f"{row['source_timeframe']} candles are missing."
            )
            action = "Import or sync the missing candles, then rebuild BOS evidence."
        elif row["transition_status"] == "INVALID":
            item_type = "INVALID_RANGE_TRANSITION"
            root_code = reasons[0] if reasons else "INVALID_RANGE_TRANSITION"
            severity = "HIGH"
            priority = 15
            summary = (
                f"BOS event {event_key} does not form a valid old-range to new-range transition."
            )
            action = "Review the old range, new range, and creating BOS links on the chart."
        elif row["evidence_status"] in {
            "INVALID_CHRONOLOGY",
            "TIME_MISMATCH",
            "BOUNDARY_NOT_BREACHED",
            "INCOMPLETE_RANGE",
            "MISSING_RANGE",
        }:
            item_type = "BOS_EVIDENCE_MISMATCH"
            root_code = str(row["evidence_status"])
            severity = "MEDIUM"
            priority = 30
            summary = (
                f"Mapped BOS event {event_key} disagrees with the factual candle or range evidence "
                f"({row['evidence_status']})."
            )
            action = "Open the BOS candle and boundary, then confirm or correct the mapped event."
        else:
            item_type = "BOS_EVIDENCE_REVIEW"
            root_code = reasons[0] if reasons else "BOS_EVIDENCE_NEEDS_REVIEW"
            severity = "MEDIUM"
            priority = 35
            summary = f"BOS event {event_key} does not yet have trustworthy factual evidence."
            action = "Review the event candle and broken boundary before using it in statistics."

        items.append(
            item_payload(
                review_key=f"event-evidence:{event_key}",
                now=now,
                actionability=ACTION_REQUIRED,
                priority=priority,
                severity=severity,
                item_type=item_type,
                root_cause_code=root_code,
                source_table="event_ohlc_evidence",
                source_row_id=row["id"],
                case_ref=row["case_ref"],
                symbol=row["symbol"],
                structure_layer=row["structure_layer"],
                source_timeframe=row["source_timeframe"],
                range_source_id=row["range_source_id"],
                event_source_id=row["event_source_id"],
                candidate_range_ids=[row["mapped_new_range_id"]]
                if row["mapped_new_range_id"]
                else [],
                reason_codes=reasons or [str(row["evidence_status"])],
                chart_time=row["effective_break_time"]
                or row["mapped_event_time"]
                or row["first_wick_breach_time"],
                chart_start_time=row["range_formation_time"],
                chart_end_time=row["as_of_time"],
                title=f"{row['structure_layer'].title()} BOS {event_key}: Evidence Review",
                trader_summary=summary,
                suggested_action=action,
            )
        )
    return items


def collect_validation_items(connection: sqlite3.Connection, now: str) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT *
        FROM validation_issues
        WHERE resolved_at_utc IS NULL
        ORDER BY id
        """
    ).fetchall()
    items: list[dict[str, Any]] = []
    for row in rows:
        ref = raw_reference(
            connection,
            raw_range_id=row["raw_range_id"],
            raw_event_id=row["raw_event_id"],
        )
        severity = normalize_severity(row["severity"])
        items.append(
            item_payload(
                review_key=f"validation:{row['id']}",
                now=now,
                actionability=ACTION_REQUIRED,
                priority=8 if severity in {"CRITICAL", "HIGH"} else 28,
                severity=severity,
                item_type="VALIDATION_ISSUE",
                root_cause_code=str(row["issue_code"]),
                source_table="validation_issues",
                source_row_id=row["id"],
                case_ref=ref.get("case_ref"),
                symbol=ref.get("symbol"),
                structure_layer=ref.get("structure_layer"),
                source_timeframe=ref.get("source_timeframe"),
                range_source_id=ref.get("range_source_id"),
                event_source_id=ref.get("event_source_id"),
                candidate_range_ids=[],
                reason_codes=[str(row["issue_code"])],
                chart_time=ref.get("event_time") or ref.get("range_time"),
                chart_start_time=ref.get("range_start_time"),
                chart_end_time=ref.get("range_end_time"),
                title=f"Validation: {str(row['issue_code']).replace('_', ' ').title()}",
                trader_summary=str(row["message"]),
                suggested_action="Open the linked range or event and confirm or correct the flagged fact.",
            )
        )
    return items


def collect_duplicate_items(connection: sqlite3.Connection, now: str) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT *
        FROM duplicate_candidates
        WHERE review_status = 'open'
        ORDER BY id
        """
    ).fetchall()
    items: list[dict[str, Any]] = []
    for row in rows:
        left = raw_reference(
            connection,
            raw_range_id=row["left_raw_range_id"],
            raw_event_id=row["left_raw_event_id"],
        )
        right = raw_reference(
            connection,
            raw_range_id=row["right_raw_range_id"],
            raw_event_id=row["right_raw_event_id"],
        )
        candidate_ranges = [
            value
            for value in (left.get("range_source_id"), right.get("range_source_id"))
            if value
        ]
        severity = "HIGH" if str(row["confidence"]).lower() == "high" else "MEDIUM"
        items.append(
            item_payload(
                review_key=f"duplicate:{row['id']}",
                now=now,
                actionability=ACTION_REQUIRED,
                priority=18 if severity == "HIGH" else 40,
                severity=severity,
                item_type="DUPLICATE_CANDIDATE",
                root_cause_code=str(row["rule_code"]),
                source_table="duplicate_candidates",
                source_row_id=row["id"],
                case_ref=left.get("case_ref") or right.get("case_ref"),
                symbol=left.get("symbol") or right.get("symbol"),
                structure_layer=left.get("structure_layer") or right.get("structure_layer"),
                source_timeframe=left.get("source_timeframe") or right.get("source_timeframe"),
                range_source_id=left.get("range_source_id") or right.get("range_source_id"),
                event_source_id=left.get("event_source_id") or right.get("event_source_id"),
                candidate_range_ids=candidate_ranges,
                reason_codes=[str(row["rule_code"])],
                chart_time=left.get("event_time") or right.get("event_time"),
                chart_start_time=left.get("range_start_time") or right.get("range_start_time"),
                chart_end_time=left.get("range_end_time") or right.get("range_end_time"),
                title=f"Possible Duplicate: {str(row['candidate_type']).replace('_', ' ').title()}",
                trader_summary=str(row["reason"]),
                suggested_action="Compare both mapped records and mark duplicate or not duplicate.",
            )
        )
    return items


def collect_daily_fallback_items(
    connection: sqlite3.Connection,
    now: str,
    *,
    covered_daily_ids: set[str],
    covered_weekly_ids: set[str],
) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT relationship.*, timeline.t0_formation_time, timeline.t1_break_time,
               timeline.range_high, timeline.range_low
        FROM daily_trend_relationships AS relationship
        LEFT JOIN daily_range_timelines AS timeline
          ON timeline.daily_range_source_id = relationship.daily_range_source_id
        WHERE relationship.trend_relationship = 'NEEDS_REVIEW'
        ORDER BY relationship.id
        """
    ).fetchall()
    items: list[dict[str, Any]] = []
    for row in rows:
        daily_id = str(row["daily_range_source_id"])
        weekly_id = str(row["parent_weekly_source_id"] or "")
        if daily_id in covered_daily_ids or (weekly_id and weekly_id in covered_weekly_ids):
            continue
        reasons = parse_codes(row["reason_codes_json"])
        items.append(
            item_payload(
                review_key=f"daily-trend:{daily_id}",
                now=now,
                actionability=ACTION_REQUIRED,
                priority=45,
                severity="MEDIUM",
                item_type="DAILY_TREND_REVIEW",
                root_cause_code=reasons[0] if reasons else "DAILY_TREND_NEEDS_REVIEW",
                source_table="daily_trend_relationships",
                source_row_id=row["id"],
                case_ref=row["case_ref"],
                symbol=row["symbol"],
                structure_layer="DAILY",
                source_timeframe="D1",
                range_source_id=daily_id,
                parent_range_id=row["parent_weekly_source_id"],
                candidate_range_ids=[weekly_id] if weekly_id else [],
                reason_codes=reasons,
                chart_time=row["daily_t1_break_time"] or row["daily_t0_formation_time"],
                chart_start_time=row["daily_t0_formation_time"],
                chart_end_time=row["as_of_time"],
                title=f"Daily {daily_id}: Trend Relationship Review",
                trader_summary=(
                    f"Daily {daily_id} cannot yet be classified as ProTrend, CounterTrend, "
                    "Transition, or Pending from the available Weekly context."
                ),
                suggested_action="Review the Daily BOS and its Weekly context on the chart.",
            )
        )
    return items


def raw_reference(
    connection: sqlite3.Connection,
    *,
    raw_range_id: int | None,
    raw_event_id: int | None,
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if raw_range_id is not None:
        row = connection.execute("SELECT * FROM raw_ranges WHERE id=?", (raw_range_id,)).fetchone()
        if row is not None:
            payload = parse_payload(row["raw_payload_json"])
            result.update(
                range_source_id=str(row["source_record_id"] or row["id"]),
                case_ref=first_value(payload, "case_ref", "raw_case_id", "case_id"),
                symbol=str(row["symbol"] or payload.get("symbol") or "").upper() or None,
                structure_layer=upper_or_none(
                    first_value(payload, "structure_layer", "layer", "range_type", "type")
                    or row["range_type"]
                ),
                source_timeframe=upper_or_none(
                    row["timeframe"]
                    or first_value(payload, "source_timeframe", "timeframe", "chart_timeframe")
                ),
                range_time=first_value(payload, "active_from_time", "range_start_time")
                or row["start_time_utc"],
                range_start_time=first_value(payload, "range_start_time", "active_from_time")
                or row["start_time_utc"],
                range_end_time=first_value(payload, "range_end_time", "inactive_from_time")
                or row["end_time_utc"],
            )
    if raw_event_id is not None:
        row = connection.execute("SELECT * FROM raw_events WHERE id=?", (raw_event_id,)).fetchone()
        if row is not None:
            payload = parse_payload(row["raw_payload_json"])
            result.update(
                event_source_id=str(row["source_record_id"] or row["id"]),
                case_ref=result.get("case_ref")
                or first_value(payload, "case_ref", "raw_case_id", "case_id"),
                structure_layer=result.get("structure_layer")
                or upper_or_none(first_value(payload, "structure_layer", "layer")),
                source_timeframe=result.get("source_timeframe")
                or upper_or_none(first_value(payload, "source_timeframe", "timeframe")),
                event_time=row["event_time_utc"]
                or first_value(payload, "event_time", "candle_time", "time"),
            )
            if not result.get("range_source_id") and row["raw_range_id"] is not None:
                linked = raw_reference(
                    connection,
                    raw_range_id=row["raw_range_id"],
                    raw_event_id=None,
                )
                for key, value in linked.items():
                    result.setdefault(key, value)
    return result


def item_payload(
    *,
    review_key: str,
    now: str,
    actionability: str,
    priority: int,
    severity: str,
    item_type: str,
    root_cause_code: str,
    source_table: str,
    source_row_id: int | None,
    case_ref: str | None,
    symbol: str | None,
    structure_layer: str | None,
    source_timeframe: str | None,
    range_source_id: str | None,
    event_source_id: str | None = None,
    parent_range_id: str | None = None,
    candidate_range_ids: Iterable[Any] = (),
    reason_codes: Iterable[Any] = (),
    chart_time: str | None = None,
    chart_start_time: str | None = None,
    chart_end_time: str | None = None,
    title: str,
    trader_summary: str,
    suggested_action: str,
) -> dict[str, Any]:
    candidates = sorted(
        {str(value) for value in candidate_range_ids if value not in (None, "")},
        key=source_sort_key,
    )
    reasons = sorted({str(value) for value in reason_codes if value not in (None, "")})
    return {
        "review_key": review_key,
        "built_at_utc": now,
        "is_active": 1,
        "actionability": actionability,
        "priority": int(priority),
        "severity": normalize_severity(severity),
        "item_type": str(item_type).upper(),
        "root_cause_code": str(root_cause_code),
        "source_table": source_table,
        "source_row_id": source_row_id,
        "case_ref": case_ref,
        "symbol": upper_or_none(symbol),
        "structure_layer": upper_or_none(structure_layer),
        "source_timeframe": upper_or_none(source_timeframe),
        "range_source_id": str(range_source_id) if range_source_id not in (None, "") else None,
        "event_source_id": str(event_source_id) if event_source_id not in (None, "") else None,
        "parent_range_id": str(parent_range_id) if parent_range_id not in (None, "") else None,
        "candidate_range_ids_json": json.dumps(candidates, separators=(",", ":")),
        "reason_codes_json": json.dumps(reasons, separators=(",", ":")),
        "chart_time": chart_time,
        "chart_start_time": chart_start_time,
        "chart_end_time": chart_end_time,
        "title": title,
        "trader_summary": trader_summary,
        "suggested_action": suggested_action,
        "first_seen_at_utc": now,
        "last_seen_at_utc": now,
    }


def upsert_item(connection: sqlite3.Connection, item: dict[str, Any]) -> None:
    keys = tuple(item)
    update_keys = [key for key in keys if key not in {"review_key", "first_seen_at_utc"}]
    connection.execute(
        f"""
        INSERT INTO structure_review_queue ({','.join(keys)})
        VALUES ({','.join('?' for _ in keys)})
        ON CONFLICT(review_key) DO UPDATE SET
            {','.join(f'{key}=excluded.{key}' for key in update_keys)}
        """,
        tuple(item[key] for key in keys),
    )


def build_result(items: list[dict[str, Any]]) -> dict[str, Any]:
    count = lambda value: sum(item["actionability"] == value for item in items)
    by_type: dict[str, int] = {}
    for item in items:
        by_type[item["item_type"]] = by_type.get(item["item_type"], 0) + 1
    return {
        "rows_built": len(items),
        "action_required_count": count(ACTION_REQUIRED),
        "reference_only_count": count(REFERENCE_ONLY),
        "item_type_counts": dict(sorted(by_type.items())),
    }


def grouped_count(
    connection: sqlite3.Connection,
    field: str,
    where: str,
    params: list[Any],
) -> list[dict[str, Any]]:
    rows = connection.execute(
        f"""
        SELECT COALESCE({field}, 'UNKNOWN') AS value, COUNT(*) AS count
        FROM structure_review_queue
        {where}
        GROUP BY COALESCE({field}, 'UNKNOWN')
        ORDER BY value
        """,
        tuple(params),
    ).fetchall()
    return [dict(row) for row in rows]


def queue_where(
    filters: dict[str, str | None],
    *,
    active_only: bool,
) -> tuple[str, list[Any]]:
    columns = {
        "actionability": "actionability",
        "item_type": "item_type",
        "severity": "severity",
        "case_ref": "case_ref",
        "symbol": "symbol",
        "structure_layer": "structure_layer",
        "range_source_id": "range_source_id",
    }
    clauses: list[str] = []
    params: list[Any] = []
    if active_only:
        clauses.append("is_active = 1")
    for key, value in filters.items():
        if value is not None:
            clauses.append(f"{columns[key]} = ?")
            params.append(value)
    return ("WHERE " + " AND ".join(clauses) if clauses else ""), params


def normalize_filters(**values: str | None) -> dict[str, str | None]:
    upper_fields = {"actionability", "item_type", "severity", "symbol", "structure_layer"}
    return {
        key: (str(value).upper() if key in upper_fields and value is not None else value)
        for key, value in values.items()
    }


def ensure_queue_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(QUEUE_SCHEMA_SQL)


def queue_row(row: dict[str, Any]) -> dict[str, Any]:
    row["candidate_range_ids"] = parse_codes(row.pop("candidate_range_ids_json"))
    row["reason_codes"] = parse_codes(row.pop("reason_codes_json"))
    row["is_active"] = bool(row["is_active"])
    return row


def parse_codes(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
    except (TypeError, json.JSONDecodeError):
        return [str(value)]
    if isinstance(parsed, list):
        return [str(item) for item in parsed]
    return [str(parsed)]


def parse_payload(value: Any) -> dict[str, Any]:
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def first_value(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return value
    return None


def normalize_severity(value: Any) -> str:
    text = str(value or "MEDIUM").upper()
    if text in {"CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"}:
        return text
    if text in {"ERROR", "FAIL"}:
        return "HIGH"
    if text in {"WARNING", "WARN"}:
        return "MEDIUM"
    return "LOW"


def upper_or_none(value: Any) -> str | None:
    return str(value).upper() if value not in (None, "") else None


def source_sort_key(value: str) -> tuple[int, int | str]:
    text = str(value)
    return (0, int(text)) if text.isdigit() else (1, text)


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="structure_review_queue")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="Build the unified structure review queue.")
    build.add_argument("--db-path", required=True)
    build.add_argument("--json", action="store_true")

    summary = subparsers.add_parser("summary", help="Summarize active review items.")
    add_filter_arguments(summary)
    summary.add_argument("--json", action="store_true")

    listing = subparsers.add_parser("list", help="List active review items.")
    add_filter_arguments(listing)
    listing.add_argument("--range-source-id")
    listing.add_argument("--limit", type=int, default=100)
    listing.add_argument("--json", action="store_true")
    return parser


def add_filter_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--db-path", required=True)
    parser.add_argument("--actionability", choices=(ACTION_REQUIRED, REFERENCE_ONLY))
    parser.add_argument("--item-type")
    parser.add_argument("--severity")
    parser.add_argument("--case-ref")
    parser.add_argument("--symbol")
    parser.add_argument("--structure-layer")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "build":
        result = build_structure_review_queue(args.db_path)
        print(deterministic_json(result) if args.json else format_build_result(result))
        return 0

    common = {
        "actionability": args.actionability,
        "item_type": args.item_type,
        "severity": args.severity,
        "case_ref": args.case_ref,
        "symbol": args.symbol,
        "structure_layer": args.structure_layer,
    }
    if args.command == "summary":
        result = summarize_structure_review_queue(args.db_path, **common)
        print(format_summary(result, as_json=args.json))
        return 0

    items = list_structure_review_queue(
        args.db_path,
        **common,
        range_source_id=args.range_source_id,
        limit=args.limit,
    )
    print(format_items(items, as_json=args.json))
    return 0


def format_build_result(result: dict[str, Any]) -> str:
    lines = [
        f"rows_built: {result['rows_built']}",
        f"action_required_count: {result['action_required_count']}",
        f"reference_only_count: {result['reference_only_count']}",
        "item_type | count",
    ]
    lines.extend(f"{key} | {value}" for key, value in result["item_type_counts"].items())
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
