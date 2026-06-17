"""Liquidity sweep detector."""

from __future__ import annotations

from detector.models import DetectionContext, SuggestionDraft
from detector.versions import SWEEP_V1


def _swept_high(candle_high: float, candle_close: float, level: float) -> bool:
    return candle_high > level and candle_close < level


def _swept_low(candle_low: float, candle_close: float, level: float) -> bool:
    return candle_low < level and candle_close > level


def detect_sweep_suggestions(ctx: DetectionContext) -> list[SuggestionDraft]:
    if not ctx.has_range():
        return []
    active = ctx.active_candle
    if active is None:
        return []

    rh = float(ctx.range_high)  # type: ignore[arg-type]
    rl = float(ctx.range_low)  # type: ignore[arg-type]
    tf = ctx.tf_prefix
    drafts: list[SuggestionDraft] = []
    idx = 0

    if _swept_high(active.high, active.close, rh):
        drafts.append(
            SuggestionDraft(
                candidate_kind="SWEEP_HIGH",
                detector_version=SWEEP_V1,
                candle_index=active.index,
                candle_time_utc_ms=active.time_ms,
                candidate_index=idx,
                movement_rule="STRUCTURE_SWEEP_HIGH",
                derived_event_code=f"{tf}_SWEEP_HIGH",
                primitive="SWEEP",
                event_side="HIGH",
                event_price=active.high,
                confidence="HIGH",
                reason_text=f"Sweep above range high {rh:.2f} with close back inside",
                meta_json={"sweep_level": rh, "close": active.close},
            )
        )
        idx += 1

    if _swept_low(active.low, active.close, rl):
        drafts.append(
            SuggestionDraft(
                candidate_kind="SWEEP_LOW",
                detector_version=SWEEP_V1,
                candle_index=active.index,
                candle_time_utc_ms=active.time_ms,
                candidate_index=idx,
                movement_rule="STRUCTURE_SWEEP_LOW",
                derived_event_code=f"{tf}_SWEEP_LOW",
                primitive="SWEEP",
                event_side="LOW",
                event_price=active.low,
                confidence="HIGH",
                reason_text=f"Sweep below range low {rl:.2f} with close back inside",
                meta_json={"sweep_level": rl, "close": active.close},
            )
        )

    return drafts
