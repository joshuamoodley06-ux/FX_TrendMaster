"""Ref candle candidate detector (post-BOS search on active candle)."""

from __future__ import annotations

from detector.break_rules import breaches_high
from detector.models import DetectionContext, SuggestionDraft
from detector.versions import REF_CANDLE_V1


def _bearish_engulf(curr, prev) -> bool:
    return (
        curr.is_bearish
        and prev.is_bullish
        and curr.open >= prev.close
        and curr.close <= prev.open
    )


def _ohcl_manipulation(candle) -> bool:
    """Open-high-close-low style bearish manipulation (no lower wick extension)."""
    upper_wick = candle.high - max(candle.open, candle.close)
    lower_wick = min(candle.open, candle.close) - candle.low
    return candle.is_bearish and upper_wick > candle.body and lower_wick <= candle.body * 0.25


def detect_ref_candle_suggestions(ctx: DetectionContext) -> list[SuggestionDraft]:
    """Emit ref candle candidate when active candle shows post-BOS manipulation."""
    if not ctx.has_range() or len(ctx.candles) < 2:
        return []
    active = ctx.active_candle
    if active is None:
        return []

    rh = float(ctx.range_high)  # type: ignore[arg-type]
    prev = ctx.candles[active.index - 1]
    tf = ctx.tf_prefix

    # Context: prior candle broke up (BOS up) — look for bearish ref on active bar.
    bos_up = breaches_high(prev.high, prev.close, rh, ctx.break_rule)
    if not bos_up:
        return []

    ref_type = None
    if prev.high > rh and _bearish_engulf(active, prev):
        ref_type = "SWEEP_BEARISH_ENGULF"
    elif _bearish_engulf(active, prev):
        ref_type = "BEARISH_ENGULF_ONLY"
    elif prev.high > rh and _ohcl_manipulation(active):
        ref_type = "SWEEP_OHCL"
    elif _ohcl_manipulation(active):
        ref_type = "OHCL_MANIPULATION_ONLY"

    if ref_type is None:
        return []

    return [
        SuggestionDraft(
            candidate_kind="REF_CANDLE",
            detector_version=REF_CANDLE_V1,
            candle_index=active.index,
            candle_time_utc_ms=active.time_ms,
            candidate_index=0,
            movement_rule="STRUCTURE_REF_CANDLE",
            derived_event_code=f"{tf}_REF_CANDLE",
            primitive="REF",
            event_side="REF",
            event_price=active.close,
            confidence="MEDIUM",
            reason_text=f"Ref candle candidate: {ref_type}",
            meta_json={
                "ref_candle_type": ref_type,
                "ref_role": "REF_CANDLE_CANDIDATE",
                "bos_event_context": "BOS_UP",
                "sweep_level_price": rh,
            },
        )
    ]
