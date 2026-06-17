"""RANGE_V2 BOS → reclaim lifecycle evaluation (Phase B)."""

from __future__ import annotations

from detector.break_rules import breaches_high, breaches_low
from detector.models import NormalizedCandle
from detector.range_state import (
    BosDirection,
    BosReclaimChain,
    BrokenBoundary,
    LifecycleEvaluation,
    NoRangeReason,
    RangeLifecycleState,
    RangeSeedContext,
)


def _bos_boundary_price(candle: NormalizedCandle, direction: BosDirection, break_rule: str) -> float:
    if direction == BosDirection.UP:
        return candle.close if break_rule == "BODY_CLOSE" else candle.high
    return candle.close if break_rule == "BODY_CLOSE" else candle.low


def _is_bos_up(candle: NormalizedCandle, rh: float, break_rule: str) -> bool:
    return breaches_high(candle.high, candle.close, rh, break_rule)


def _is_bos_down(candle: NormalizedCandle, rl: float, break_rule: str) -> bool:
    return breaches_low(candle.low, candle.close, rl, break_rule)


def _is_reclaim_after_bos_up(candle: NormalizedCandle, old_rh: float) -> bool:
    return candle.close <= old_rh


def _is_reclaim_after_bos_down(candle: NormalizedCandle, old_rl: float) -> bool:
    return candle.close >= old_rl


def evaluate_lifecycle(
    candles: list[NormalizedCandle],
    active_index: int,
    seed: RangeSeedContext | None,
    *,
    break_rule: str,
) -> LifecycleEvaluation:
    """
    Evaluate range lifecycle at active_index using Josh doctrine:
    BOS must precede reclaim in same cycle; close back inside old boundary.
    """
    if not seed or not seed.is_valid():
        return LifecycleEvaluation(
            state=RangeLifecycleState.NO_VALID_RANGE,
            no_range_reason=NoRangeReason.NO_SEED_OR_ACTIVE_RANGE,
            reason_text="No seed or active range context",
        )

    if not candles:
        return LifecycleEvaluation(
            state=RangeLifecycleState.NO_VALID_RANGE,
            no_range_reason=NoRangeReason.NO_SEED_OR_ACTIVE_RANGE,
            reason_text="No candles in replay window",
        )

    idx = max(0, min(int(active_index), len(candles) - 1))
    rh = float(seed.range_high)
    rl = float(seed.range_low)

    breach_dir: BosDirection | None = None
    bos_index: int | None = None
    bos_price: float | None = None
    reclaim_index: int | None = None
    completed_chain: BosReclaimChain | None = None

    for i in range(idx + 1):
        candle = candles[i]

        if breach_dir is None:
            if _is_bos_up(candle, rh, break_rule):
                breach_dir = BosDirection.UP
                bos_index = i
                bos_price = _bos_boundary_price(candle, BosDirection.UP, break_rule)
                continue
            if _is_bos_down(candle, rl, break_rule):
                breach_dir = BosDirection.DOWN
                bos_index = i
                bos_price = _bos_boundary_price(candle, BosDirection.DOWN, break_rule)
                continue
            continue

        if breach_dir == BosDirection.UP:
            if _is_bos_down(candle, rl, break_rule):
                return LifecycleEvaluation(
                    state=RangeLifecycleState.NO_VALID_RANGE,
                    no_range_reason=NoRangeReason.UNRESOLVED_TRANSITION,
                    reason_text="Opposite BOS DOWN before reclaim after BOS UP",
                )
            if _is_reclaim_after_bos_up(candle, rh):
                reclaim_index = i
                completed_chain = BosReclaimChain(
                    direction=BosDirection.UP,
                    bos_index=int(bos_index),
                    bos_boundary_price=float(bos_price),
                    reclaim_index=i,
                    broken_boundary=BrokenBoundary.HIGH,
                    old_range_high=rh,
                    old_range_low=rl,
                )
                breach_dir = None
                bos_index = None
                bos_price = None
                continue
            if _is_bos_up(candle, rh, break_rule):
                new_price = _bos_boundary_price(candle, BosDirection.UP, break_rule)
                if bos_price is None or new_price > float(bos_price):
                    bos_index = i
                    bos_price = new_price
            continue

        if breach_dir == BosDirection.DOWN:
            if _is_bos_up(candle, rh, break_rule):
                return LifecycleEvaluation(
                    state=RangeLifecycleState.NO_VALID_RANGE,
                    no_range_reason=NoRangeReason.UNRESOLVED_TRANSITION,
                    reason_text="Opposite BOS UP before reclaim after BOS DOWN",
                )
            if _is_reclaim_after_bos_down(candle, rl):
                reclaim_index = i
                completed_chain = BosReclaimChain(
                    direction=BosDirection.DOWN,
                    bos_index=int(bos_index),
                    bos_boundary_price=float(bos_price),
                    reclaim_index=i,
                    broken_boundary=BrokenBoundary.LOW,
                    old_range_high=rh,
                    old_range_low=rl,
                )
                breach_dir = None
                bos_index = None
                bos_price = None
                continue
            if _is_bos_down(candle, rl, break_rule):
                new_price = _bos_boundary_price(candle, BosDirection.DOWN, break_rule)
                if bos_price is None or new_price < float(bos_price):
                    bos_index = i
                    bos_price = new_price
            continue

    if completed_chain is not None:
        state = (
            RangeLifecycleState.RECLAIMED_DOWN
            if completed_chain.direction == BosDirection.UP
            else RangeLifecycleState.RECLAIMED_UP
        )
        return LifecycleEvaluation(
            state=state,
            chain=completed_chain,
            reason_text="BOS and reclaim completed in same cycle",
        )

    if breach_dir == BosDirection.UP:
        return LifecycleEvaluation(
            state=RangeLifecycleState.BREACHED_UP,
            no_range_reason=NoRangeReason.BOS_WITHOUT_RECLAIM,
            reason_text="BOS UP detected; reclaim not yet confirmed",
        )

    if breach_dir == BosDirection.DOWN:
        return LifecycleEvaluation(
            state=RangeLifecycleState.BREACHED_DOWN,
            no_range_reason=NoRangeReason.BOS_WITHOUT_RECLAIM,
            reason_text="BOS DOWN detected; reclaim not yet confirmed",
        )

    start_state = RangeLifecycleState.SEEDED if seed.is_manual_seed else RangeLifecycleState.ACTIVE_RANGE
    return LifecycleEvaluation(
        state=start_state,
        no_range_reason=NoRangeReason.SEED_ONLY_NO_BOS,
        reason_text="Seed anchors only; no BOS cycle in replay window",
    )
