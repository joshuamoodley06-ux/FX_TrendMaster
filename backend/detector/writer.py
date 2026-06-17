"""Persist detector drafts as PENDING suggestions only."""

from __future__ import annotations

import sqlite3
from typing import Any

from detection_brain_store import (
    DetectorSuggestion,
    DuplicateOpenSuggestionError,
    insert_suggestion,
    list_suggestions,
    new_uuid,
    supersede_pending_suggestion,
    utc_now_ms,
)
from detector.models import DetectionContext, SuggestionDraft
from detector.versions import ENGINE_SOURCE


def draft_to_suggestion(draft: SuggestionDraft, ctx: DetectionContext) -> DetectorSuggestion:
    candle = ctx.candles[draft.candle_index]
    return DetectorSuggestion(
        suggestion_id=new_uuid(),
        detector_version=draft.detector_version,
        engine_source=ENGINE_SOURCE,
        candidate_kind=draft.candidate_kind,
        candidate_index=draft.candidate_index,
        symbol=ctx.symbol,
        structure_layer=ctx.structure_layer or "WEEKLY",
        source_timeframe=ctx.source_timeframe,
        chart_timeframe=ctx.chart_timeframe or ctx.source_timeframe,
        candle_time_utc_ms=draft.candle_time_utc_ms or candle.time_ms,
        candle_index=draft.candle_index,
        created_at_utc_ms=utc_now_ms(),
        case_ref=ctx.case_ref,
        parent_range_id=ctx.parent_range_id,
        active_range_id=ctx.active_range_id,
        session_id=ctx.session_id,
        suggested_rh=draft.suggested_rh,
        suggested_rl=draft.suggested_rl,
        suggested_rh_time_ms=draft.suggested_rh_time_ms,
        suggested_rl_time_ms=draft.suggested_rl_time_ms,
        range_scale=draft.range_scale or ctx.range_scale,
        range_role=draft.range_role,
        event_side=draft.event_side,
        event_price=draft.event_price,
        break_rule=draft.break_rule,
        movement_rule=draft.movement_rule,
        primitive=draft.primitive,
        derived_event_code=draft.derived_event_code,
        confidence=draft.confidence,
        reason_text=draft.reason_text,
        meta_json=draft.meta_json or None,
    )


def _find_open_slot_duplicate(
    conn: sqlite3.Connection,
    record: DetectorSuggestion,
) -> str | None:
    rows = list_suggestions(
        conn,
        status="PENDING",
        symbol=record.symbol,
        limit=500,
    )
    parent_key = record.parent_range_id if record.parent_range_id is not None else -1
    for row in rows:
        if (
            row.get("source_timeframe") == record.source_timeframe
            and row.get("structure_layer") == record.structure_layer
            and (row.get("parent_range_id") if row.get("parent_range_id") is not None else -1) == parent_key
            and row.get("candidate_kind") == record.candidate_kind
            and int(row.get("candidate_index") or 0) == int(record.candidate_index or 0)
        ):
            return str(row.get("suggestion_id"))
    return None


def write_suggestion(
    conn: sqlite3.Connection,
    draft: SuggestionDraft,
    ctx: DetectionContext,
    *,
    supersede_on_conflict: bool = True,
) -> dict[str, Any]:
    """Write one suggestion. Never touches map_ranges or map_events."""
    record = draft_to_suggestion(draft, ctx)
    try:
        return insert_suggestion(conn, record)
    except DuplicateOpenSuggestionError:
        if not supersede_on_conflict:
            raise
        existing_id = _find_open_slot_duplicate(conn, record)
        if existing_id:
            supersede_pending_suggestion(conn, existing_id)
            record = draft_to_suggestion(draft, ctx)
            record.supersedes_suggestion_id = existing_id
            return insert_suggestion(conn, record)
        raise


def write_suggestions(
    conn: sqlite3.Connection,
    drafts: list[SuggestionDraft],
    ctx: DetectionContext,
    *,
    supersede_on_conflict: bool = True,
) -> list[dict[str, Any]]:
    saved: list[dict[str, Any]] = []
    for draft in drafts:
        saved.append(
            write_suggestion(
                conn,
                draft,
                ctx,
                supersede_on_conflict=supersede_on_conflict,
            )
        )
    return saved
