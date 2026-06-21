"""OHLC loading adapter — current timeframe only."""

from __future__ import annotations

import sqlite3
from typing import Any, Callable

from detector.break_rules import normalise_timeframe
from detector.context_window import build_detection_window_meta
from detector.models import DetectionContext, NormalizedCandle
from detector.normalize import filter_candles_by_window, normalize_candles


CandleLoader = Callable[[str, str, int], list[dict[str, Any]]]


def default_db_candle_loader(symbol: str, timeframe: str, limit: int) -> list[dict[str, Any]]:
    """Load candles from backend candle_store (optional dependency)."""
    import candle_store

    payload = candle_store.get_candles(symbol=symbol, timeframe=timeframe, limit=limit)
    return list(payload.get("candles") or [])


def make_conn_candle_loader(conn: sqlite3.Connection) -> CandleLoader:
    """Load candles on the scan connection to avoid SQLite lock from a second connect()."""

    def _load(symbol: str, timeframe: str, limit: int) -> list[dict[str, Any]]:
        import candle_store

        return candle_store.fetch_candles(conn, symbol=symbol, timeframe=timeframe, limit=limit)

    return _load


def _apply_window(
    normalized: list[NormalizedCandle],
    *,
    replay_until_time_ms: int | None,
    visible_from_time_ms: int | None,
) -> list[NormalizedCandle]:
    return filter_candles_by_window(
        normalized,
        visible_from_time_ms=visible_from_time_ms,
        replay_until_time_ms=replay_until_time_ms,
    )


def _resolve_active_index(
    normalized: list[NormalizedCandle],
    active_index: int,
    replay_until_time_ms: int | None,
) -> int:
    if not normalized:
        return 0
    if replay_until_time_ms is not None and replay_until_time_ms > 0:
        return len(normalized) - 1
    return max(0, min(int(active_index), len(normalized) - 1))


def build_context(
    *,
    symbol: str,
    source_timeframe: str,
    candles: list[dict[str, Any]] | list[NormalizedCandle],
    active_index: int,
    range_high: float | None = None,
    range_low: float | None = None,
    range_scale: str = "MAJOR",
    range_role: str | None = None,
    structure_layer: str | None = None,
    parent_range_id: int | None = None,
    active_range_id: int | None = None,
    case_ref: str | None = None,
    session_id: str | None = None,
    active_candle_time_ms: int | None = None,
    replay_until_time_ms: int | None = None,
    visible_from_time_ms: int | None = None,
    detection_run_id: str | None = None,
) -> DetectionContext:
    tf = normalise_timeframe(source_timeframe)
    until_ms = replay_until_time_ms if replay_until_time_ms is not None else active_candle_time_ms
    if candles and isinstance(candles[0], NormalizedCandle):
        normalized = list(candles)  # type: ignore[arg-type]
    else:
        normalized = normalize_candles(list(candles), tf)
    normalized = _apply_window(
        normalized,
        replay_until_time_ms=until_ms,
        visible_from_time_ms=visible_from_time_ms,
    )
    idx = _resolve_active_index(normalized, active_index, until_ms) if normalized else 0
    ctx = DetectionContext(
        symbol=str(symbol).upper(),
        source_timeframe=tf,
        candles=normalized,
        active_index=idx,
        range_high=range_high,
        range_low=range_low,
        range_scale=range_scale,
        range_role=range_role,
        structure_layer=structure_layer,
        parent_range_id=parent_range_id,
        active_range_id=active_range_id,
        case_ref=case_ref,
        session_id=session_id,
        detection_run_id=detection_run_id,
        replay_until_time_ms=until_ms,
        visible_from_time_ms=visible_from_time_ms,
    )
    ctx.detection_window_meta = build_detection_window_meta(ctx, detection_run_id=detection_run_id)
    return ctx


def load_context_from_db(
    *,
    symbol: str,
    source_timeframe: str,
    active_index: int | None = None,
    active_candle_time_ms: int | None = None,
    replay_until_time_ms: int | None = None,
    visible_from_time_ms: int | None = None,
    limit: int = 500,
    loader: CandleLoader | None = None,
    range_high: float | None = None,
    range_low: float | None = None,
    range_scale: str = "MAJOR",
    range_role: str | None = None,
    structure_layer: str | None = None,
    parent_range_id: int | None = None,
    active_range_id: int | None = None,
    case_ref: str | None = None,
    session_id: str | None = None,
    detection_run_id: str | None = None,
) -> DetectionContext:
    load = loader or default_db_candle_loader
    tf = normalise_timeframe(source_timeframe)
    until_ms = replay_until_time_ms if replay_until_time_ms is not None else active_candle_time_ms
    rows = load(str(symbol).upper(), tf, max(limit, 2000) if until_ms else limit)
    normalized = normalize_candles(rows, tf)
    normalized = _apply_window(
        normalized,
        replay_until_time_ms=until_ms,
        visible_from_time_ms=visible_from_time_ms,
    )
    if active_index is not None:
        idx = _resolve_active_index(normalized, active_index, until_ms)
    else:
        idx = len(normalized) - 1 if normalized else 0
    return build_context(
        symbol=symbol,
        source_timeframe=tf,
        candles=normalized,
        active_index=idx,
        range_high=range_high,
        range_low=range_low,
        range_scale=range_scale,
        range_role=range_role,
        structure_layer=structure_layer,
        parent_range_id=parent_range_id,
        active_range_id=active_range_id,
        case_ref=case_ref,
        session_id=session_id,
        replay_until_time_ms=until_ms,
        visible_from_time_ms=visible_from_time_ms,
        detection_run_id=detection_run_id,
    )
