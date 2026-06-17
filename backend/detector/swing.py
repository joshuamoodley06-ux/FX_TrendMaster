"""Adaptive swing candidate detector (no fixed candle counts)."""

from __future__ import annotations

from statistics import mean

from detector.models import DetectionContext, NormalizedCandle, SuggestionDraft, SwingPoint
from detector.versions import SWING_V1


def _avg_range(candles: list[NormalizedCandle]) -> float:
    if not candles:
        return 0.0
    return mean(c.range for c in candles)


def detect_swings(
    candles: list[NormalizedCandle],
    *,
    displacement_factor: float = 0.35,
    lookback: int | None = None,
) -> list[SwingPoint]:
    """Find swing highs/lows using local extrema + adaptive displacement threshold."""
    if len(candles) < 3:
        return []
    window = candles if lookback is None else candles[-lookback:]
    offset = len(candles) - len(window)
    avg_rng = _avg_range(window)
    threshold = max(avg_rng * displacement_factor, 1e-9)
    swings: list[SwingPoint] = []

    for i in range(1, len(window) - 1):
        c = window[i]
        prev_c = window[i - 1]
        next_c = window[i + 1]
        gi = offset + i

        if c.high >= prev_c.high and c.high >= next_c.high:
            left = min(prev_c.low, c.low, next_c.low)
            if c.high - left >= threshold:
                swings.append(SwingPoint(index=gi, kind="SWING_HIGH", price=c.high, candle=c))

        if c.low <= prev_c.low and c.low <= next_c.low:
            right = max(prev_c.high, c.high, next_c.high)
            if right - c.low >= threshold:
                swings.append(SwingPoint(index=gi, kind="SWING_LOW", price=c.low, candle=c))

    return swings


def detect_swing_suggestions(ctx: DetectionContext) -> list[SuggestionDraft]:
    swings = detect_swings(ctx.candles)
    ctx.swings = swings
    if not swings:
        return []

    active = ctx.active_index
    drafts: list[SuggestionDraft] = []
    idx_counter = {"SWING_HIGH": 0, "SWING_LOW": 0}

    for sp in swings:
        if sp.index != active:
            continue
        kind = sp.kind
        candidate_kind = kind  # SWING_HIGH | SWING_LOW
        tf = ctx.tf_prefix
        movement = f"STRUCTURE_{kind}"
        derived = f"{tf}_{kind}"
        side = "HIGH" if kind == "SWING_HIGH" else "LOW"
        ci = idx_counter[kind]
        idx_counter[kind] += 1
        drafts.append(
            SuggestionDraft(
                candidate_kind=candidate_kind,
                detector_version=SWING_V1,
                candle_index=sp.index,
                candle_time_utc_ms=sp.candle.time_ms,
                candidate_index=ci,
                movement_rule=movement,
                derived_event_code=derived,
                primitive="SWING",
                event_side=side,
                event_price=sp.price,
                confidence="MEDIUM",
                reason_text=f"Adaptive swing {kind.replace('_', ' ').lower()} at {sp.price:.2f}",
                meta_json={"swing_kind": kind, "displacement_factor": 0.35},
            )
        )
    return drafts
