"""Typed records for the analyst pipeline.

Rules (mirrors the processor contract):
- Core logic only ever sees these dataclasses, never loose dicts.
- Parsers ignore unknown JSON fields and preserve the original payload
  on the ``raw`` attribute.
- All id-like fields are normalized to strings so parent/child joins are
  type-stable regardless of int/str storage in the backend.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from analyst.util.timeparse import parse_time_to_ms


def opt_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def opt_upper(value: Any) -> str | None:
    text = opt_str(value)
    return text.upper() if text else None


def opt_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    return num


def _first(d: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in d and d[key] is not None and d[key] != "":
            return d[key]
    return None


@dataclass(frozen=True)
class RangeRecord:
    range_id: str | None
    case_ref: str | None
    symbol: str | None
    structure_layer: str | None
    source_timeframe: str | None
    chart_timeframe: str | None
    parent_range_id: str | None
    old_range_id: str | None
    new_range_id: str | None
    status: str | None
    direction_of_break: str | None
    broken_by_event_id: str | None
    created_by_event_id: str | None
    range_high_price: float | None
    range_low_price: float | None
    range_high_time_ms: int | None
    range_low_time_ms: int | None
    range_start_time_ms: int | None
    range_end_time_ms: int | None
    active_from_time_ms: int | None
    inactive_from_time_ms: int | None
    range_scope: str = "MAJOR"
    raw: dict[str, Any] = field(repr=False, default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RangeRecord":
        return cls(
            range_id=opt_str(_first(d, "range_id", "id")),
            case_ref=opt_str(d.get("case_ref")),
            symbol=opt_str(d.get("symbol")),
            structure_layer=opt_upper(_first(d, "structure_layer", "layer")),
            source_timeframe=opt_str(d.get("source_timeframe")),
            chart_timeframe=opt_str(_first(d, "chart_timeframe", "timeframe")),
            parent_range_id=opt_str(d.get("parent_range_id")),
            old_range_id=opt_str(d.get("old_range_id")),
            new_range_id=opt_str(d.get("new_range_id")),
            status=opt_upper(d.get("status")),
            direction_of_break=opt_upper(d.get("direction_of_break")),
            broken_by_event_id=opt_str(d.get("broken_by_event_id")),
            created_by_event_id=opt_str(d.get("created_by_event_id")),
            range_high_price=opt_float(_first(d, "range_high_price", "range_high")),
            range_low_price=opt_float(_first(d, "range_low_price", "range_low")),
            range_high_time_ms=parse_time_to_ms(d.get("range_high_time")),
            range_low_time_ms=parse_time_to_ms(d.get("range_low_time")),
            range_start_time_ms=parse_time_to_ms(d.get("range_start_time")),
            range_end_time_ms=parse_time_to_ms(d.get("range_end_time")),
            active_from_time_ms=parse_time_to_ms(d.get("active_from_time")),
            inactive_from_time_ms=parse_time_to_ms(d.get("inactive_from_time")),
            range_scope=opt_upper(d.get("range_scope")) or "MAJOR",
            raw=d,
        )


@dataclass(frozen=True)
class EventRecord:
    event_id: str | None
    case_ref: str | None
    symbol: str | None
    timeframe: str | None
    event_type: str | None
    structure_layer: str | None
    source_timeframe: str | None
    active_range_id: str | None
    parent_range_id: str | None
    event_time_ms: int | None
    event_price: float | None
    direction: str | None
    candle_open: float | None
    candle_high: float | None
    candle_low: float | None
    candle_close: float | None
    raw: dict[str, Any] = field(repr=False, default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "EventRecord":
        return cls(
            # VPS range rows reference events by the numeric map row id
            # (broken_by_event_id / created_by_event_id), not the UUID
            # event_id, so the row id must win for join stability.
            event_id=opt_str(_first(d, "id", "event_id", "client_event_id")),
            case_ref=opt_str(d.get("case_ref")),
            symbol=opt_str(d.get("symbol")),
            timeframe=opt_str(d.get("timeframe")),
            event_type=opt_upper(_first(d, "event_type", "structural_event", "event_name")),
            structure_layer=opt_upper(d.get("structure_layer")),
            source_timeframe=opt_str(d.get("source_timeframe")),
            active_range_id=opt_str(_first(d, "active_range_id", "range_id")),
            parent_range_id=opt_str(d.get("parent_range_id")),
            event_time_ms=parse_time_to_ms(_first(d, "event_time", "time", "candle_time")),
            event_price=opt_float(_first(d, "event_price", "price")),
            direction=opt_upper(d.get("direction")),
            candle_open=opt_float(d.get("candle_open")),
            candle_high=opt_float(d.get("candle_high")),
            candle_low=opt_float(d.get("candle_low")),
            candle_close=opt_float(d.get("candle_close")),
            raw=d,
        )


@dataclass(frozen=True)
class Candle:
    symbol: str | None
    timeframe: str | None
    time_ms: int | None
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: float | None

    @classmethod
    def from_dict(cls, d: dict[str, Any], timeframe: str | None = None) -> "Candle":
        return cls(
            symbol=opt_str(d.get("symbol")),
            timeframe=opt_str(d.get("timeframe")) or opt_str(timeframe),
            time_ms=parse_time_to_ms(d.get("time")),
            open=opt_float(d.get("open")),
            high=opt_float(d.get("high")),
            low=opt_float(d.get("low")),
            close=opt_float(d.get("close")),
            volume=opt_float(d.get("volume")),
        )


@dataclass
class InputPackage:
    schema_version: str | None
    symbol: str
    year: int | None
    label: str
    case_refs: list[str]
    generated_at_utc_ms: int | None
    source: dict[str, Any]
    ranges: list[RangeRecord]
    events: list[EventRecord]
    candles: dict[str, list[Candle]]
    raw_ledgers: dict[str, dict[str, Any]]
    raw: dict[str, Any] = field(repr=False, default_factory=dict)

    @property
    def candle_count_total(self) -> int:
        return sum(len(rows) for rows in self.candles.values())
