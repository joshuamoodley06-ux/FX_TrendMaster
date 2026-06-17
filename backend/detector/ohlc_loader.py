"""OHLC loading adapter — current timeframe only."""

from __future__ import annotations

from typing import Any, Callable

from detector.break_rules import normalise_timeframe
from detector.models import DetectionContext, NormalizedCandle
from detector.normalize import normalize_candles, parse_time_to_ms, truncate_candles_at_or_before


CandleLoader = Callable[[str, str, int], list[dict[str, Any]]]


def default_db_candle_loader(symbol: str, timeframe: str, limit: int) -> list[dict[str, Any]]:
    """Load candles from backend candle_store (optional dependency)."""
    import candle_store

    payload = candle_store.get_candles(symbol=symbol, timeframe=timeframe, limit=limit)
    return list(payload.get("candles") or [])


def build_context(
    *,
    symbol: str,
    source_timeframe: str,
    candles: list[dict[str, Any]] | list[NormalizedCandle],
    active_index: int,
    range_high: float | None = None,
    range_low: float | None = None,
    range_scale: str = "MAJOR",
    parent_range_id: int | None = None,
    active_range_id: int | None = None,
    case_ref: str | None = None,
    session_id: str | None = None,
    active_candle_time_ms: int | None = None,
) -> DetectionContext:
    tf = normalise_timeframe(source_timeframe)
    if candles and isinstance(candles[0], NormalizedCandle):
        normalized = list(candles)  # type: ignore[arg-type]
    else:
        normalized = normalize_candles(list(candles), tf)
    normalized = truncate_candles_at_or_before(normalized, active_candle_time_ms)
    if not normalized:
        normalized = normalize_candles(list(candles), tf) if candles and not isinstance(candles[0], NormalizedCandle) else list(candles)  # type: ignore[arg-type]
    idx = max(0, min(int(active_index), len(normalized) - 1)) if normalized else 0
    if active_candle_time_ms is not None and active_candle_time_ms > 0 and normalized:
        idx = len(normalized) - 1
    return DetectionContext(
        symbol=str(symbol).upper(),
        source_timeframe=tf,
        candles=normalized,
        active_index=idx,
        range_high=range_high,
        range_low=range_low,
        range_scale=range_scale,
        parent_range_id=parent_range_id,
        active_range_id=active_range_id,
        case_ref=case_ref,
        session_id=session_id,
    )


def load_context_from_db(
    *,
    symbol: str,
    source_timeframe: str,
    active_index: int | None = None,
    active_candle_time_ms: int | None = None,
    limit: int = 500,
    loader: CandleLoader | None = None,
    range_high: float | None = None,
    range_low: float | None = None,
    range_scale: str = "MAJOR",
    parent_range_id: int | None = None,
    active_range_id: int | None = None,
    case_ref: str | None = None,
    session_id: str | None = None,
) -> DetectionContext:
    load = loader or default_db_candle_loader
    tf = normalise_timeframe(source_timeframe)
    rows = load(str(symbol).upper(), tf, limit)
    normalized = normalize_candles(rows, tf)
    normalized = truncate_candles_at_or_before(normalized, active_candle_time_ms)
    if active_candle_time_ms is not None and active_candle_time_ms > 0 and normalized:
        idx = len(normalized) - 1
    elif active_index is not None:
        idx = max(0, min(int(active_index), len(normalized) - 1)) if normalized else 0
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
        parent_range_id=parent_range_id,
        active_range_id=active_range_id,
        case_ref=case_ref,
        session_id=session_id,
        active_candle_time_ms=active_candle_time_ms,
    )
