"""Range candidate detector from adaptive swings."""

from __future__ import annotations

from detector.models import DetectionContext, SuggestionDraft, SwingPoint
from detector.range_scale_mode import (
    CANDIDATE_KIND_RANGE,
    RANGE_SCALE_UNKNOWN,
    is_generic_scale_mode,
)
from detector.range_selection import (
    SwingRangeCandidate,
    enumerate_swing_range_candidates,
    select_major_candidate,
    select_minor_candidate,
)
from detector.swing import detect_swings
from detector.versions import RANGE_V1


def _latest_pair(swings: list[SwingPoint], before_index: int) -> tuple[SwingPoint | None, SwingPoint | None]:
    highs = [s for s in swings if s.kind == "SWING_HIGH" and s.index <= before_index]
    lows = [s for s in swings if s.kind == "SWING_LOW" and s.index <= before_index]
    if not highs or not lows:
        return None, None
    return highs[-1], lows[-1]


def _dedupe_candidates(candidates: list[SwingRangeCandidate]) -> list[SwingRangeCandidate]:
    seen: set[tuple[float, float]] = set()
    out: list[SwingRangeCandidate] = []
    for c in sorted(candidates, key=lambda x: (x.anchor_index, -x.span)):
        key = (round(c.rh, 4), round(c.rl, 4))
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def _structure_draft(
    ctx: DetectionContext,
    *,
    candidate: SwingRangeCandidate | None,
    candidate_kind: str,
    range_scale: str | None,
    range_role: str | None,
    confidence: str,
    reason_text: str,
    selection_meta: dict,
    candidate_index: int = 0,
    candle_index: int | None = None,
) -> SuggestionDraft:
    active = candle_index if candle_index is not None else ctx.active_index
    tf = ctx.tf_prefix
    meta = {
        "swing_high_index": candidate.swing_high.index if candidate else None,
        "swing_low_index": candidate.swing_low.index if candidate else None,
        "range_selection": selection_meta,
        "classification_deferred": candidate_kind == CANDIDATE_KIND_RANGE,
    }
    return SuggestionDraft(
        candidate_kind=candidate_kind,
        detector_version=RANGE_V1,
        candle_index=active,
        candle_time_utc_ms=ctx.candles[active].time_ms,
        candidate_index=candidate_index,
        movement_rule=f"STRUCTURE_{candidate_kind}",
        derived_event_code=f"{tf}_{candidate_kind}",
        primitive="RANGE",
        suggested_rh=candidate.rh if candidate else None,
        suggested_rl=candidate.rl if candidate else None,
        suggested_rh_time_ms=candidate.swing_high.candle.time_ms if candidate else None,
        suggested_rl_time_ms=candidate.swing_low.candle.time_ms if candidate else None,
        range_scale=range_scale,
        range_role=range_role,
        confidence=confidence,
        reason_text=reason_text,
        meta_json=meta,
    )


def _detect_generic_range_candidates(
    ctx: DetectionContext,
    *,
    swings: list[SwingPoint],
    active: int,
) -> list[SuggestionDraft]:
    """Emit all valid swing-pair ranges without major/minor classification."""
    candidates = enumerate_swing_range_candidates(swings, active_index=active)
    if not candidates:
        swing_high, swing_low = _latest_pair(swings, active)
        if swing_high is None or swing_low is None or swing_high.price <= swing_low.price:
            return []
        if active < max(swing_high.index, swing_low.index):
            return []
        candidates = [SwingRangeCandidate(swing_high=swing_high, swing_low=swing_low)]

    deduped = _dedupe_candidates(candidates)
    if not deduped:
        return []

    selection_meta = {
        "mode": "generic",
        "candidates_considered": len(candidates),
        "candidates_emitted": len(deduped),
        "selection_reason": "all_valid_swing_pairs_no_classification",
    }
    drafts: list[SuggestionDraft] = []
    for idx, candidate in enumerate(deduped):
        anchor = candidate.anchor_index
        if active < anchor:
            continue
        drafts.append(
            _structure_draft(
                ctx,
                candidate=candidate,
                candidate_kind=CANDIDATE_KIND_RANGE,
                range_scale=RANGE_SCALE_UNKNOWN,
                range_role=None,
                confidence="MEDIUM",
                reason_text=(
                    f"Range candidate RH {candidate.rh:.2f} / RL {candidate.rl:.2f} "
                    f"(classification deferred)"
                ),
                selection_meta=selection_meta,
                candidate_index=idx,
                candle_index=anchor,
            )
        )
    return drafts


def _detect_legacy_range_suggestions(
    ctx: DetectionContext,
    *,
    swings: list[SwingPoint],
    active: int,
    active_price: float,
) -> list[SuggestionDraft]:
    """Legacy major/minor classification — deprecated; use generic mode."""
    candidates = enumerate_swing_range_candidates(swings, active_index=active)
    if not candidates:
        swing_high, swing_low = _latest_pair(swings, active)
        if swing_high is None or swing_low is None or swing_high.price <= swing_low.price:
            return []
        latest_anchor_index = max(swing_high.index, swing_low.index)
        if active < latest_anchor_index:
            return []
        candidates = [SwingRangeCandidate(swing_high=swing_high, swing_low=swing_low)]

    latest_anchor_index = max(c.anchor_index for c in candidates)
    if active < latest_anchor_index:
        return []

    scale = ctx.range_scale

    if scale == "MINOR":
        chosen, _code, selection_meta = select_minor_candidate(
            candidates,
            active_price=active_price,
        )
        if chosen is None:
            return [
                _structure_draft(
                    ctx,
                    candidate=None,
                    candidate_kind="NO_MINOR_STRUCTURE",
                    range_scale="MINOR",
                    range_role="INTERNAL_LEG",
                    confidence="LOW",
                    reason_text="No engulfing minor range for current price",
                    selection_meta={**selection_meta, "mode": "legacy"},
                )
            ]
        return [
            _structure_draft(
                ctx,
                candidate=chosen,
                candidate_kind="RANGE_MINOR",
                range_scale="MINOR",
                range_role="INTERNAL_LEG",
                confidence="MEDIUM",
                reason_text=(
                    f"Minor range engulfs price {active_price:.2f}: "
                    f"RH {chosen.rh:.2f} / RL {chosen.rl:.2f}"
                ),
                selection_meta={**selection_meta, "mode": "legacy"},
            )
        ]

    chosen, _code, selection_meta = select_major_candidate(
        candidates,
        active_price=active_price,
    )
    if chosen is None:
        return [
            _structure_draft(
                ctx,
                candidate=None,
                candidate_kind="NO_MAJOR_STRUCTURE",
                range_scale="MAJOR",
                range_role="ACTIVE_CONTAINER",
                confidence="LOW",
                reason_text="No major-eligible range with contained minor structure",
                selection_meta={**selection_meta, "mode": "legacy"},
            )
        ]

    reason = selection_meta.get("selection_reason", "major_selected")
    if reason == "outermost_engulfing_major":
        detail = (
            f"Major engulfs price {active_price:.2f} and contains valid minor inside: "
            f"RH {chosen.rh:.2f} / RL {chosen.rl:.2f}"
        )
    elif reason == "outermost_major_no_engulf":
        detail = (
            f"Outermost major (price {active_price:.2f} outside bounds): "
            f"RH {chosen.rh:.2f} / RL {chosen.rl:.2f}"
        )
    else:
        detail = (
            f"Range candidate from swing high {chosen.rh:.2f} "
            f"and swing low {chosen.rl:.2f}"
        )

    return [
        _structure_draft(
            ctx,
            candidate=chosen,
            candidate_kind="RANGE_MAJOR",
            range_scale="MAJOR",
            range_role="ACTIVE_CONTAINER",
            confidence="MEDIUM" if reason == "outermost_engulfing_major" else "LOW",
            reason_text=detail,
            selection_meta={**selection_meta, "mode": "legacy"},
        )
    ]


def detect_range_suggestions(
    ctx: DetectionContext,
    *,
    scale_mode: str | None = None,
) -> list[SuggestionDraft]:
    swings = ctx.swings or detect_swings(ctx.candles)
    ctx.swings = swings
    if len(swings) < 2:
        return []

    active = ctx.active_index

    if is_generic_scale_mode(scale_mode):
        return _detect_generic_range_candidates(ctx, swings=swings, active=active)

    active_candle = ctx.candles[active]
    return _detect_legacy_range_suggestions(
        ctx,
        swings=swings,
        active=active,
        active_price=active_candle.close,
    )
