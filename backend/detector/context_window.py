"""Replay / detection window parsing and meta for detector runs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from detector.models import DetectionContext, NormalizedCandle
from detector.normalize import parse_time_to_ms


def _coerce_ms(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        n = int(value)
        return n if n > 1_000_000_000_000 else n * 1000
    ms = parse_time_to_ms(value)
    return ms if ms > 0 else None


def parse_window_from_payload(payload: dict[str, Any]) -> tuple[int | None, int | None, str | None]:
    """Return (replay_until_ms, visible_from_ms, detection_run_id)."""
    replay_until_ms: int | None = None
    for key in (
        "replay_until_time_ms",
        "visible_until_time_ms",
        "active_candle_time_ms",
        "candle_time_utc_ms",
    ):
        raw = payload.get(key)
        if raw not in (None, ""):
            replay_until_ms = _coerce_ms(raw)
            break
    if replay_until_ms is None:
        for key in (
            "replay_until_time",
            "visible_until_time",
            "active_candle_time",
        ):
            raw = payload.get(key)
            if raw not in (None, ""):
                replay_until_ms = _coerce_ms(raw)
                break

    visible_from_ms: int | None = None
    for key in ("visible_from_time_ms",):
        raw = payload.get(key)
        if raw not in (None, ""):
            visible_from_ms = _coerce_ms(raw)
            break
    if visible_from_ms is None and payload.get("visible_from_time"):
        visible_from_ms = _coerce_ms(payload.get("visible_from_time"))
    if visible_from_ms is None:
        for key in ("date_from_ms", "date_from"):
            raw = payload.get(key)
            if raw not in (None, ""):
                visible_from_ms = _coerce_ms(raw)
                break

    if replay_until_ms is None:
        for key in ("date_to_ms", "date_to"):
            raw = payload.get(key)
            if raw not in (None, ""):
                replay_until_ms = _coerce_ms(raw)
                break

    detection_run_id = str(payload.get("detection_run_id") or "").strip() or None
    return replay_until_ms, visible_from_ms, detection_run_id


def ms_to_date_label(ms: int | None) -> str | None:
    if ms is None or ms <= 0:
        return None
    dt = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d")


def build_detection_window_meta(
    ctx: DetectionContext,
    *,
    detection_run_id: str | None = None,
) -> dict[str, Any]:
    candles = ctx.candles
    first: NormalizedCandle | None = candles[0] if candles else None
    last: NormalizedCandle | None = candles[-1] if candles else None
    replay_ms = ctx.replay_until_time_ms
    from_ms = ctx.visible_from_time_ms
    return {
        "detection_run_id": detection_run_id or ctx.detection_run_id,
        "replay_until_time_ms": replay_ms,
        "replay_until_time": ms_to_date_label(replay_ms),
        "visible_from_time_ms": from_ms,
        "visible_from_time": ms_to_date_label(from_ms) if from_ms else None,
        "candle_count_used": len(candles),
        "first_candle_time": first.time_raw if first else None,
        "first_candle_time_ms": first.time_ms if first else None,
        "last_candle_time": last.time_raw if last else None,
        "last_candle_time_ms": last.time_ms if last else None,
    }


def meta_matches_context_filter(
    meta: dict[str, Any] | None,
    *,
    detection_run_id: str | None = None,
    replay_until_time_ms: int | None = None,
) -> bool:
    if not detection_run_id and replay_until_time_ms is None:
        return True
    m = meta or {}
    if detection_run_id:
        return str(m.get("detection_run_id") or "") == detection_run_id
    if replay_until_time_ms is not None:
        stored = m.get("replay_until_time_ms")
        return stored is not None and int(stored) == int(replay_until_time_ms)
    return True
