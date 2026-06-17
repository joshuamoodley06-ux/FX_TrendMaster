"""Range candidate detector from adaptive swings."""

from __future__ import annotations

from detector.models import DetectionContext, SuggestionDraft, SwingPoint
from detector.swing import detect_swings
from detector.versions import RANGE_V1


def _latest_pair(swings: list[SwingPoint], before_index: int) -> tuple[SwingPoint | None, SwingPoint | None]:
    highs = [s for s in swings if s.kind == "SWING_HIGH" and s.index <= before_index]
    lows = [s for s in swings if s.kind == "SWING_LOW" and s.index <= before_index]
    if not highs or not lows:
        return None, None
    return highs[-1], lows[-1]


def detect_range_suggestions(ctx: DetectionContext) -> list[SuggestionDraft]:
    swings = ctx.swings or detect_swings(ctx.candles)
    ctx.swings = swings
    if len(swings) < 2:
        return []

    active = ctx.active_index
    swing_high, swing_low = _latest_pair(swings, active)
    if swing_high is None or swing_low is None:
        return []
    if swing_high.price <= swing_low.price:
        return []

    # Suggest range when active candle is the later of the two swing anchors.
    latest_anchor_index = max(swing_high.index, swing_low.index)
    if active < latest_anchor_index:
        return []

    scale = ctx.range_scale
    candidate_kind = "RANGE_MAJOR" if scale == "MAJOR" else "RANGE_MINOR"
    tf = ctx.tf_prefix
    movement = f"STRUCTURE_{candidate_kind}"
    derived = f"{tf}_{candidate_kind}"

    return [
        SuggestionDraft(
            candidate_kind=candidate_kind,
            detector_version=RANGE_V1,
            candle_index=active,
            candle_time_utc_ms=ctx.candles[active].time_ms,
            candidate_index=0,
            movement_rule=movement,
            derived_event_code=derived,
            primitive="RANGE",
            suggested_rh=swing_high.price,
            suggested_rl=swing_low.price,
            suggested_rh_time_ms=swing_high.candle.time_ms,
            suggested_rl_time_ms=swing_low.candle.time_ms,
            range_scale=scale,
            range_role="ACTIVE_CONTAINER" if scale == "MAJOR" else "INTERNAL_LEG",
            confidence="MEDIUM",
            reason_text=(
                f"Range candidate from swing high {swing_high.price:.2f} "
                f"and swing low {swing_low.price:.2f}"
            ),
            meta_json={
                "swing_high_index": swing_high.index,
                "swing_low_index": swing_low.index,
            },
        )
    ]
