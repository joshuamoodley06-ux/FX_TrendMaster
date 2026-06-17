"""Candle normalization from raw OHLC rows."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from detector.break_rules import normalise_timeframe
from detector.models import NormalizedCandle


def parse_time_to_ms(value: Any) -> int:
    if value is None or value == "":
        return 0
    if isinstance(value, (int, float)):
        n = int(value)
        return n if n > 1_000_000_000_000 else n * 1000
    text = str(value).strip().replace("T", " ")
    if text.isdigit():
        n = int(text)
        return n if n > 1_000_000_000_000 else n * 1000
    for fmt in ("%Y.%m.%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            dt = datetime.strptime(text[:19], fmt).replace(tzinfo=timezone.utc)
            return int(dt.timestamp() * 1000)
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    except ValueError:
        return 0


def _direction(open_: float, close: float, body: float, range_: float) -> str:
    if range_ <= 0:
        return "DOJI"
    if body <= range_ * 0.05:
        return "DOJI"
    return "BULLISH" if close >= open_ else "BEARISH"


def normalize_candle_row(row: dict[str, Any], index: int, timeframe: str | None = None) -> NormalizedCandle | None:
    try:
        o = float(row["open"])
        h = float(row["high"])
        l = float(row["low"])
        c = float(row["close"])
    except (KeyError, TypeError, ValueError):
        return None
    if h < l:
        h, l = l, h
    time_raw = str(row.get("time") or row.get("candle_time") or "")
    time_ms = parse_time_to_ms(row.get("time_ms") or row.get("candle_time_utc_ms") or time_raw)
    body = abs(c - o)
    range_ = max(h - l, 0.0)
    vol = float(row.get("volume") or 0)
    return NormalizedCandle(
        index=index,
        time_ms=time_ms,
        time_raw=time_raw,
        open=o,
        high=h,
        low=l,
        close=c,
        volume=vol,
        body=body,
        range=range_,
        direction=_direction(o, c, body, range_),
    )


def normalize_candles(rows: list[dict[str, Any]], timeframe: str) -> list[NormalizedCandle]:
    tf = normalise_timeframe(timeframe)
    out: list[NormalizedCandle] = []
    for i, row in enumerate(rows):
        candle = normalize_candle_row(row, i, tf)
        if candle is not None:
            out.append(candle)
    return out


def truncate_candles_at_or_before(
    candles: list[NormalizedCandle],
    active_candle_time_ms: int | None,
) -> list[NormalizedCandle]:
    """Keep only candles visible at replay/market-time cut (no future leakage)."""
    if active_candle_time_ms is None or active_candle_time_ms <= 0:
        return candles
    trimmed = [c for c in candles if c.time_ms <= active_candle_time_ms]
    if not trimmed:
        return candles
    return [replace(c, index=i) for i, c in enumerate(trimmed)]
