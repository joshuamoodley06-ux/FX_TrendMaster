"""Normalized candle and detection context models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from detector.break_rules import break_rule_for_timeframe, normalise_timeframe, structure_layer_for_timeframe


@dataclass(frozen=True)
class NormalizedCandle:
    index: int
    time_ms: int
    time_raw: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    body: float
    range: float
    direction: str  # BULLISH | BEARISH | DOJI

    @property
    def is_bullish(self) -> bool:
        return self.direction == "BULLISH"

    @property
    def is_bearish(self) -> bool:
        return self.direction == "BEARISH"


@dataclass
class SwingPoint:
    index: int
    kind: str  # SWING_HIGH | SWING_LOW
    price: float
    candle: NormalizedCandle


@dataclass
class SuggestionDraft:
    """In-memory detector output before persistence."""

    candidate_kind: str
    detector_version: str
    candle_index: int
    candle_time_utc_ms: int
    candidate_index: int = 0
    movement_rule: str | None = None
    derived_event_code: str | None = None
    primitive: str | None = None
    break_rule: str | None = None
    event_side: str | None = None
    event_price: float | None = None
    confidence: str = "MEDIUM"
    reason_text: str = ""
    suggested_rh: float | None = None
    suggested_rl: float | None = None
    suggested_rh_time_ms: int | None = None
    suggested_rl_time_ms: int | None = None
    range_scale: str | None = None
    range_role: str | None = None
    meta_json: dict[str, Any] = field(default_factory=dict)


@dataclass
class DetectionContext:
    """Single-timeframe detector input. No multi-TF inference."""

    symbol: str
    source_timeframe: str
    candles: list[NormalizedCandle]
    active_index: int
    range_high: float | None = None
    range_low: float | None = None
    range_scale: str = "MAJOR"
    structure_layer: str | None = None
    chart_timeframe: str | None = None
    parent_range_id: int | None = None
    active_range_id: int | None = None
    case_ref: str | None = None
    session_id: str | None = None
    swings: list[SwingPoint] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.source_timeframe = normalise_timeframe(self.source_timeframe)
        if self.chart_timeframe is None:
            self.chart_timeframe = self.source_timeframe
        else:
            self.chart_timeframe = normalise_timeframe(self.chart_timeframe)
        if self.structure_layer is None:
            self.structure_layer = structure_layer_for_timeframe(self.source_timeframe)
        self.range_scale = str(self.range_scale or "MAJOR").upper()
        if self.active_index < 0:
            self.active_index = 0
        if self.candles and self.active_index >= len(self.candles):
            self.active_index = len(self.candles) - 1

    @property
    def active_candle(self) -> NormalizedCandle | None:
        if not self.candles or self.active_index < 0:
            return None
        return self.candles[self.active_index]

    @property
    def break_rule(self) -> str:
        return break_rule_for_timeframe(self.source_timeframe)

    @property
    def tf_prefix(self) -> str:
        return self.source_timeframe

    def has_range(self) -> bool:
        return (
            self.range_high is not None
            and self.range_low is not None
            and self.range_high > self.range_low
        )
