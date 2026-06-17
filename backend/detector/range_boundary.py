"""RANGE_V2 opposite-swing boundary selection (Phase B)."""

from __future__ import annotations

from detector.models import SwingPoint
from detector.range_state import (
    BosDirection,
    BosReclaimChain,
    BoundarySelection,
    LifecycleEvaluation,
    NoRangeReason,
    OppositeSwingReason,
    RangeLifecycleState,
)


LOOKBACK_BEFORE_BOS = 50


def _opposite_kind(direction: BosDirection) -> str:
    return "SWING_LOW" if direction == BosDirection.UP else "SWING_HIGH"


def _pick_between_swings(
    swings: list[SwingPoint],
    *,
    kind: str,
    bos_index: int,
    reclaim_index: int,
) -> SwingPoint | None:
    pool = [
        s
        for s in swings
        if s.kind == kind and bos_index < s.index < reclaim_index
    ]
    if not pool:
        return None
    if len(pool) == 1:
        return pool[0]
    if kind == "SWING_LOW":
        return min(pool, key=lambda s: s.price)
    return max(pool, key=lambda s: s.price)


def _pick_before_bos_swing(
    swings: list[SwingPoint],
    *,
    kind: str,
    bos_index: int,
) -> SwingPoint | None:
    pool = [s for s in swings if s.kind == kind and s.index < bos_index]
    if not pool:
        return None
    min_index = max(0, bos_index - LOOKBACK_BEFORE_BOS)
    pool = [s for s in pool if s.index >= min_index]
    if not pool:
        return None
    return pool[-1]


def select_opposite_swing(
    swings: list[SwingPoint],
    chain: BosReclaimChain,
) -> tuple[SwingPoint | None, OppositeSwingReason | None]:
    kind = _opposite_kind(chain.direction)

    between = _pick_between_swings(
        swings,
        kind=kind,
        bos_index=chain.bos_index,
        reclaim_index=chain.reclaim_index,
    )
    if between is not None:
        return between, OppositeSwingReason.OPPOSITE_SWING_BETWEEN_BOS_RECLAIM

    before = _pick_before_bos_swing(swings, kind=kind, bos_index=chain.bos_index)
    if before is not None:
        return before, OppositeSwingReason.LAST_OPPOSITE_SWING_BEFORE_BOS

    return None, OppositeSwingReason.UNCLEAR_OPPOSITE_SWING


def derive_boundaries(
    lifecycle: LifecycleEvaluation,
    swings: list[SwingPoint],
) -> BoundarySelection:
    """
    Derive RH/RL per Josh doctrine:
    - Bullish: RH = BOS high; RL = linked opposite swing low
    - Bearish: RL = BOS low; RH = linked opposite swing high
    """
    if not lifecycle.can_suggest_range or lifecycle.chain is None:
        return BoundarySelection(
            no_range_reason=lifecycle.no_range_reason or NoRangeReason.BOS_WITHOUT_RECLAIM,
            reason_text=lifecycle.reason_text or "Lifecycle not ready for boundary selection",
            boundary_selection_reason=OppositeSwingReason.UNCLEAR_OPPOSITE_SWING.value,
        )

    chain = lifecycle.chain
    opposite, swing_reason = select_opposite_swing(swings, chain)

    if opposite is None or swing_reason == OppositeSwingReason.UNCLEAR_OPPOSITE_SWING:
        return BoundarySelection(
            no_range_reason=NoRangeReason.UNCLEAR_OPPOSITE_SWING,
            reason_text="Reclaim confirmed; no linked opposite swing",
            boundary_selection_reason=OppositeSwingReason.UNCLEAR_OPPOSITE_SWING.value,
            confidence="LOW",
        )

    reason_code = swing_reason.value

    if chain.direction == BosDirection.UP:
        suggested_rh = chain.bos_boundary_price
        suggested_rl = opposite.price
    else:
        suggested_rl = chain.bos_boundary_price
        suggested_rh = opposite.price

    if suggested_rh <= suggested_rl:
        return BoundarySelection(
            no_range_reason=NoRangeReason.UNCLEAR_OPPOSITE_SWING,
            reason_text="Boundary prices invalid after selection",
            boundary_selection_reason=OppositeSwingReason.UNCLEAR_OPPOSITE_SWING.value,
            confidence="LOW",
        )

    return BoundarySelection(
        suggested_rh=suggested_rh,
        suggested_rl=suggested_rl,
        opposite_swing_index=opposite.index,
        opposite_swing_kind=opposite.kind,
        opposite_swing_price=opposite.price,
        boundary_selection_reason=reason_code,
        confidence="HIGH" if swing_reason == OppositeSwingReason.OPPOSITE_SWING_BETWEEN_BOS_RECLAIM else "MEDIUM",
        reason_text=(
            f"BOS {chain.direction.value} @{chain.bos_index}; reclaim @{chain.reclaim_index}; "
            f"{reason_code}; opposite @{opposite.index}"
        ),
    )


def evaluate_range_v2_boundaries(
    lifecycle: LifecycleEvaluation,
    swings: list[SwingPoint],
) -> BoundarySelection:
    """Convenience: lifecycle must already be RECLAIMED_* or REBASED."""
    if lifecycle.state not in {
        RangeLifecycleState.RECLAIMED_UP,
        RangeLifecycleState.RECLAIMED_DOWN,
        RangeLifecycleState.REBASED,
    }:
        return BoundarySelection(
            no_range_reason=lifecycle.no_range_reason or NoRangeReason.BOS_WITHOUT_RECLAIM,
            reason_text=lifecycle.reason_text,
        )
    return derive_boundaries(lifecycle, swings)
