"""HTTP-facing Detection Brain operations."""

from __future__ import annotations

from typing import Any

import candle_store
from detection_brain_promotion import PromotionError, review_suggestion
from detection_brain_schema import init_detection_brain_schema
from detection_brain_store import get_suggestion, list_suggestions, new_uuid
from detector.break_rules import structure_layer_for_timeframe
from detector.context_window import meta_matches_context_filter, parse_window_from_payload
from detector.ohlc_loader import build_context, load_context_from_db
from detector.debug_run_summary import build_run_debug_summary
from detector.period_scan import run_detector_period_scan
from detector.pipeline import run_detector_v1
from detector.range_mode import RANGE_MODE_SMOKE_V1, resolve_range_mode
from detector.range_scale_mode import RANGE_SCALE_UNKNOWN, resolve_range_scale_mode
from detector.range_seed import resolve_detector_seed_context, seed_resolution_to_meta
from detector.writer import write_suggestions


def _connect():
    candle_store.init_db()
    return candle_store.connect()


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def list_pending_suggestions(
    *,
    symbol: str,
    structure_layer: str | None = None,
    source_timeframe: str | None = None,
    parent_range_id: int | None = None,
    status: str = "PENDING",
    limit: int = 100,
    detection_run_id: str | None = None,
    replay_until_time_ms: int | None = None,
) -> dict[str, Any]:
    with _connect() as conn:
        init_detection_brain_schema(conn)
        rows = list_suggestions(
            conn,
            status=status,
            symbol=symbol,
            structure_layer=structure_layer,
            source_timeframe=source_timeframe,
            parent_range_id=parent_range_id,
            limit=limit,
        )
    if detection_run_id or replay_until_time_ms is not None:
        rows = [
            row
            for row in rows
            if meta_matches_context_filter(
                row.get("meta_json"),
                detection_run_id=detection_run_id,
                replay_until_time_ms=replay_until_time_ms,
            )
        ]
    return {"ok": True, "count": len(rows), "suggestions": rows}


def get_suggestion_by_id(suggestion_id: str) -> dict[str, Any]:
    with _connect() as conn:
        init_detection_brain_schema(conn)
        row = get_suggestion(conn, suggestion_id)
    if not row:
        return {"ok": False, "status": 404, "error": "suggestion not found"}
    return {"ok": True, "suggestion": row}


def run_detector_and_store(payload: dict[str, Any]) -> dict[str, Any]:
    symbol = str(payload.get("symbol") or "XAUUSD").upper()
    timeframe = str(payload.get("source_timeframe") or payload.get("timeframe") or "D1").upper()
    structure_layer = str(payload.get("structure_layer") or "").strip().upper() or None
    active_index = payload.get("active_index")
    limit = int(payload.get("limit") or 500)
    range_mode = resolve_range_mode(payload.get("range_mode"))
    scale_mode = resolve_range_scale_mode(payload.get("range_scale_mode"))

    replay_until_ms, visible_from_ms, detection_run_id = parse_window_from_payload(payload)
    detection_run_id = detection_run_id or new_uuid()

    period_scan = bool(
        payload.get("period_scan")
        or payload.get("date_from")
        or payload.get("date_from_ms")
        or payload.get("date_to")
        or payload.get("date_to_ms")
    )
    date_from_ms = visible_from_ms
    date_to_ms = replay_until_ms

    if replay_until_ms:
        limit = max(limit, 2000)

    range_high = _optional_float(payload.get("range_high") or payload.get("range_high_price"))
    range_low = _optional_float(payload.get("range_low") or payload.get("range_low_price"))
    parent_range_id = _optional_int(payload.get("parent_range_id"))
    active_range_id = _optional_int(payload.get("active_range_id"))
    range_scale = str(payload.get("range_scale") or RANGE_SCALE_UNKNOWN).upper()
    range_role = str(payload.get("range_role") or "").strip() or None

    seed_resolution = None
    if range_mode != RANGE_MODE_SMOKE_V1:
        with _connect() as conn:
            seed_resolution = resolve_detector_seed_context(
                conn,
                payload,
                symbol=symbol,
                structure_layer=structure_layer or structure_layer_for_timeframe(timeframe),
                source_timeframe=timeframe,
                parent_range_id=parent_range_id,
            )
        if seed_resolution and seed_resolution.seed:
            seed = seed_resolution.seed
            range_high = seed.range_high
            range_low = seed.range_low
            active_range_id = seed.active_range_id
            range_scale = str(seed.range_scale or range_scale).upper()
            range_role = seed.range_role or range_role
            if seed.parent_range_id is not None:
                parent_range_id = seed.parent_range_id
        else:
            range_high = None
            range_low = None
            active_range_id = None
    elif active_range_id in (None, 0) and not payload.get("include_active_range"):
        range_high = None
        range_low = None

    common = dict(
        symbol=symbol,
        source_timeframe=timeframe,
        structure_layer=structure_layer,
        range_high=range_high,
        range_low=range_low,
        range_scale=range_scale,
        range_role=range_role,
        parent_range_id=parent_range_id,
        active_range_id=active_range_id,
        case_ref=payload.get("case_ref"),
        session_id=payload.get("session_id"),
        replay_until_time_ms=replay_until_ms,
        visible_from_time_ms=visible_from_ms,
        detection_run_id=detection_run_id,
    )

    if payload.get("candles"):
        candles = list(payload.get("candles") or [])
        idx = int(active_index if active_index is not None else max(0, len(candles) - 1))
        ctx = build_context(candles=candles, active_index=idx, **common)
    else:
        ctx = load_context_from_db(
            active_index=int(active_index) if active_index is not None else None,
            limit=limit,
            **common,
        )

    if seed_resolution is not None:
        ctx.range_seed = seed_resolution.seed
        ctx.range_seed_meta = seed_resolution_to_meta(seed_resolution)

    result = (
        run_detector_period_scan(
            ctx,
            date_from_ms=date_from_ms,
            date_to_ms=date_to_ms,
            range_mode=range_mode,
            scale_mode=scale_mode,
        )
        if period_scan
        else run_detector_v1(ctx, range_mode=range_mode, scale_mode=scale_mode)
    )
    with _connect() as conn:
        init_detection_brain_schema(conn)
        saved = write_suggestions(conn, result.drafts, ctx)
        conn.commit()
    window_meta = dict(ctx.detection_window_meta or {})
    if ctx.range_seed_meta:
        window_meta.update(ctx.range_seed_meta)
    debug_summary = build_run_debug_summary(
        result,
        ctx,
        detection_run_id=detection_run_id,
        seed_resolution=seed_resolution,
        saved_suggestions=saved,
    )
    return {
        "ok": True,
        "draft_count": len(result.drafts),
        "written_count": len(saved),
        "suggestions": saved,
        "detector_versions": result.detector_versions,
        "detection_run_id": detection_run_id,
        "replay_until_time_ms": replay_until_ms,
        "visible_from_time_ms": visible_from_ms,
        "detection_context": window_meta,
        "range_mode": result.range_mode,
        "range_scale_mode": result.range_scale_mode,
        "period_scan": result.period_scan,
        "debug_summary": debug_summary,
    }


def review_suggestion_action(payload: dict[str, Any]) -> dict[str, Any]:
    suggestion_id = str(payload.get("suggestion_id") or "").strip()
    if not suggestion_id:
        return {"ok": False, "status": 400, "error": "suggestion_id is required"}

    try:
        with _connect() as conn:
            init_detection_brain_schema(conn)
            return review_suggestion(
                conn,
                suggestion_id,
                action=str(payload.get("action") or ""),
                edits=payload.get("edits") if isinstance(payload.get("edits"), dict) else None,
                error_category=payload.get("error_category"),
                notes=str(payload.get("notes") or ""),
            )
    except PromotionError as exc:
        return {"ok": False, "status": exc.status, "error": str(exc)}
