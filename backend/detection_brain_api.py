"""HTTP-facing Detection Brain operations."""

from __future__ import annotations

from typing import Any

import candle_store
from detection_brain_promotion import PromotionError, review_suggestion
from detection_brain_schema import init_detection_brain_schema
from detection_brain_store import get_suggestion, list_suggestions
from detector.ohlc_loader import build_context, load_context_from_db
from detector.pipeline import run_detector_v1
from detector.writer import write_suggestions


def _connect():
    candle_store.init_db()
    return candle_store.connect()


def list_pending_suggestions(
    *,
    symbol: str,
    structure_layer: str | None = None,
    source_timeframe: str | None = None,
    parent_range_id: int | None = None,
    status: str = "PENDING",
    limit: int = 100,
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
    return {"ok": True, "count": len(rows), "suggestions": rows}


def get_suggestion_by_id(suggestion_id: str) -> dict[str, Any]:
    with _connect() as conn:
        init_detection_brain_schema(conn)
        row = get_suggestion(conn, suggestion_id)
    if not row:
        return {"ok": False, "status": 404, "error": "suggestion not found"}
    return {"ok": True, "suggestion": row}


def run_detector_and_store(payload: dict[str, Any]) -> dict[str, Any]:
    from detector.normalize import parse_time_to_ms

    symbol = str(payload.get("symbol") or "XAUUSD").upper()
    timeframe = str(payload.get("source_timeframe") or payload.get("timeframe") or "D1").upper()
    active_index = payload.get("active_index")
    limit = int(payload.get("limit") or 500)

    active_candle_time_ms: int | None = None
    for key in ("active_candle_time_ms", "candle_time_utc_ms"):
        raw = payload.get(key)
        if raw not in (None, ""):
            n = int(raw)
            active_candle_time_ms = n if n > 1_000_000_000_000 else n * 1000
            break
    if active_candle_time_ms is None and payload.get("active_candle_time"):
        active_candle_time_ms = parse_time_to_ms(payload.get("active_candle_time"))
    if active_candle_time_ms:
        limit = max(limit, 2000)

    if payload.get("candles"):
        ctx = build_context(
            symbol=symbol,
            source_timeframe=timeframe,
            candles=list(payload.get("candles") or []),
            active_index=int(active_index if active_index is not None else max(0, len(payload["candles"]) - 1)),
            range_high=payload.get("range_high"),
            range_low=payload.get("range_low"),
            range_scale=str(payload.get("range_scale") or "MAJOR"),
            parent_range_id=payload.get("parent_range_id"),
            active_range_id=payload.get("active_range_id"),
            case_ref=payload.get("case_ref"),
            session_id=payload.get("session_id"),
            active_candle_time_ms=active_candle_time_ms,
        )
    else:
        ctx = load_context_from_db(
            symbol=symbol,
            source_timeframe=timeframe,
            active_index=int(active_index) if active_index is not None else None,
            active_candle_time_ms=active_candle_time_ms,
            limit=limit,
            range_high=payload.get("range_high"),
            range_low=payload.get("range_low"),
            range_scale=str(payload.get("range_scale") or "MAJOR"),
            parent_range_id=payload.get("parent_range_id"),
            active_range_id=payload.get("active_range_id"),
            case_ref=payload.get("case_ref"),
            session_id=payload.get("session_id"),
        )

    result = run_detector_v1(ctx)
    with _connect() as conn:
        init_detection_brain_schema(conn)
        saved = write_suggestions(conn, result.drafts, ctx)
        conn.commit()
    return {
        "ok": True,
        "draft_count": len(result.drafts),
        "written_count": len(saved),
        "suggestions": saved,
        "detector_versions": result.detector_versions,
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
