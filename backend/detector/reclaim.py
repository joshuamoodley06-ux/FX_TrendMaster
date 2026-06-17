"""Reclaim detector — close back beyond swept level."""

from __future__ import annotations

from detector.models import DetectionContext, SuggestionDraft
from detector.sweep import _swept_high, _swept_low
from detector.versions import RECLAIM_V1


def detect_reclaim_suggestions(ctx: DetectionContext) -> list[SuggestionDraft]:
    if not ctx.has_range() or len(ctx.candles) < 2:
        return []
    active = ctx.active_candle
    if active is None:
        return []

    rh = float(ctx.range_high)  # type: ignore[arg-type]
    rl = float(ctx.range_low)  # type: ignore[arg-type]
    prev = ctx.candles[active.index - 1]
    tf = ctx.tf_prefix
    drafts: list[SuggestionDraft] = []

    if _swept_low(prev.low, prev.close, rl) and active.close > rl:
        drafts.append(
            SuggestionDraft(
                candidate_kind="RECLAIM_UP",
                detector_version=RECLAIM_V1,
                candle_index=active.index,
                candle_time_utc_ms=active.time_ms,
                candidate_index=0,
                movement_rule="STRUCTURE_RECLAIM_UP",
                derived_event_code=f"{tf}_RECLAIM_UP",
                primitive="RECLAIM",
                event_side="UP",
                event_price=active.close,
                confidence="HIGH",
                reason_text=f"Reclaim UP after sweep below {rl:.2f}",
                meta_json={"reclaimed_level": rl, "prior_sweep_index": prev.index},
            )
        )

    if _swept_high(prev.high, prev.close, rh) and active.close < rh:
        drafts.append(
            SuggestionDraft(
                candidate_kind="RECLAIM_DOWN",
                detector_version=RECLAIM_V1,
                candle_index=active.index,
                candle_time_utc_ms=active.time_ms,
                candidate_index=0,
                movement_rule="STRUCTURE_RECLAIM_DOWN",
                derived_event_code=f"{tf}_RECLAIM_DOWN",
                primitive="RECLAIM",
                event_side="DOWN",
                event_price=active.close,
                confidence="HIGH",
                reason_text=f"Reclaim DOWN after sweep above {rh:.2f}",
                meta_json={"reclaimed_level": rh, "prior_sweep_index": prev.index},
            )
        )

    return drafts
