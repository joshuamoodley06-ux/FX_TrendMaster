"""RANGE_V2 BOS → reclaim lifecycle evaluation (Phase B)."""

from __future__ import annotations

from detector.break_rules import (
    BODY_CLOSE,
    RECLAIM_CLOSE,
    RECLAIM_TOUCH,
    breaches_high,
    breaches_low,
    reclaim_close_after_bos_down,
    reclaim_close_after_bos_up,
    reclaim_confirmed_after_bos_down,
    reclaim_confirmed_after_bos_up,
    reclaim_touch_after_bos_down,
    reclaim_touch_after_bos_up,
)
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


def _is_reclaim_touch_after_bos_up(candle: NormalizedCandle, old_rh: float, break_rule: str) -> bool:
    return reclaim_touch_after_bos_up(candle.low, candle.close, old_rh, break_rule)


def _is_reclaim_touch_after_bos_down(candle: NormalizedCandle, old_rl: float, break_rule: str) -> bool:
    return reclaim_touch_after_bos_down(candle.high, candle.close, old_rl, break_rule)


def _is_reclaim_close_after_bos_up(candle: NormalizedCandle, old_rh: float) -> bool:
    return reclaim_close_after_bos_up(candle.close, old_rh)


def _is_reclaim_close_after_bos_down(candle: NormalizedCandle, old_rl: float) -> bool:
    return reclaim_close_after_bos_down(candle.close, old_rl)


def evaluate_lifecycle(
    candles: list[NormalizedCandle],
    active_index: int,
    seed: RangeSeedContext | None,
    *,
    break_rule: str,
    min_reclaim_time_ms: int | None = None,
) -> LifecycleEvaluation:
    """
    Evaluate range lifecycle at active_index using Josh doctrine:
    BOS must precede reclaim in same cycle.
    HTF (W1/D1/H4/H1): wick tag of old boundary completes reclaim.
    LTF (M15 and below): body close back inside old boundary required.
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
    reclaim_touch_index: int | None = None
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
            if _is_reclaim_touch_after_bos_up(candle, rh, break_rule):
                if reclaim_touch_index is None:
                    reclaim_touch_index = i

            if _is_bos_down(candle, rl, break_rule):
                if reclaim_touch_index is None:
                    return LifecycleEvaluation(
                        state=RangeLifecycleState.NO_VALID_RANGE,
                        no_range_reason=NoRangeReason.UNRESOLVED_TRANSITION,
                        reason_text="Opposite BOS DOWN before RECLAIM_CLOSE after BOS UP",
                        reclaim_touch_index=reclaim_touch_index,
                        reclaim_touch_kind=RECLAIM_TOUCH if reclaim_touch_index is not None else None,
                    )

            if reclaim_confirmed_after_bos_up(candle.low, candle.close, rh, break_rule):
                if min_reclaim_time_ms is not None and candle.time_ms < min_reclaim_time_ms:
                    breach_dir = None
                    bos_index = None
                    bos_price = None
                    reclaim_touch_index = None
                    continue
                touch_only = (
                    break_rule != BODY_CLOSE
                    and reclaim_touch_after_bos_up(candle.low, candle.close, rh, break_rule)
                    and not reclaim_close_after_bos_up(candle.close, rh)
                )
                completed_chain = BosReclaimChain(
                    direction=BosDirection.UP,
                    bos_index=int(bos_index),
                    bos_boundary_price=float(bos_price),
                    reclaim_index=i,
                    broken_boundary=BrokenBoundary.HIGH,
                    old_range_high=rh,
                    old_range_low=rl,
                    reclaim_touch_index=reclaim_touch_index,
                    reclaim_confirmation=RECLAIM_TOUCH if touch_only else RECLAIM_CLOSE,
                )
                breach_dir = None
                bos_index = None
                bos_price = None
                reclaim_touch_index = None
                continue

            if _is_bos_up(candle, rh, break_rule):
                new_price = _bos_boundary_price(candle, BosDirection.UP, break_rule)
                if bos_price is None or new_price > float(bos_price):
                    bos_index = i
                    bos_price = new_price
            continue

        if breach_dir == BosDirection.DOWN:
            if _is_reclaim_touch_after_bos_down(candle, rl, break_rule):
                if reclaim_touch_index is None:
                    reclaim_touch_index = i

            if _is_bos_up(candle, rh, break_rule):
                if reclaim_touch_index is None:
                    return LifecycleEvaluation(
                        state=RangeLifecycleState.NO_VALID_RANGE,
                        no_range_reason=NoRangeReason.UNRESOLVED_TRANSITION,
                        reason_text="Opposite BOS UP before RECLAIM_CLOSE after BOS DOWN",
                        reclaim_touch_index=reclaim_touch_index,
                        reclaim_touch_kind=RECLAIM_TOUCH if reclaim_touch_index is not None else None,
                    )

            if reclaim_confirmed_after_bos_down(candle.high, candle.close, rl, break_rule):
                if min_reclaim_time_ms is not None and candle.time_ms < min_reclaim_time_ms:
                    breach_dir = None
                    bos_index = None
                    bos_price = None
                    reclaim_touch_index = None
                    continue
                touch_only = (
                    break_rule != BODY_CLOSE
                    and reclaim_touch_after_bos_down(candle.high, candle.close, rl, break_rule)
                    and not reclaim_close_after_bos_down(candle.close, rl)
                )
                completed_chain = BosReclaimChain(
                    direction=BosDirection.DOWN,
                    bos_index=int(bos_index),
                    bos_boundary_price=float(bos_price),
                    reclaim_index=i,
                    broken_boundary=BrokenBoundary.LOW,
                    old_range_high=rh,
                    old_range_low=rl,
                    reclaim_touch_index=reclaim_touch_index,
                    reclaim_confirmation=RECLAIM_TOUCH if touch_only else RECLAIM_CLOSE,
                )
                breach_dir = None
                bos_index = None
                bos_price = None
                reclaim_touch_index = None
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
            reclaim_touch_index=completed_chain.reclaim_touch_index,
            reclaim_touch_kind=RECLAIM_TOUCH if completed_chain.reclaim_touch_index is not None else None,
        )

    if breach_dir == BosDirection.UP:
        return LifecycleEvaluation(
            state=RangeLifecycleState.BREACHED_UP,
            no_range_reason=NoRangeReason.BOS_WITHOUT_RECLAIM,
            reason_text="BOS UP detected; reclaim not yet confirmed",
            reclaim_touch_index=reclaim_touch_index,
            reclaim_touch_kind=RECLAIM_TOUCH if reclaim_touch_index is not None else None,
        )

    if breach_dir == BosDirection.DOWN:
        return LifecycleEvaluation(
            state=RangeLifecycleState.BREACHED_DOWN,
            no_range_reason=NoRangeReason.BOS_WITHOUT_RECLAIM,
            reason_text="BOS DOWN detected; reclaim not yet confirmed",
            reclaim_touch_index=reclaim_touch_index,
            reclaim_touch_kind=RECLAIM_TOUCH if reclaim_touch_index is not None else None,
        )

    start_state = RangeLifecycleState.SEEDED if seed.is_manual_seed else RangeLifecycleState.ACTIVE_RANGE
    return LifecycleEvaluation(
        state=start_state,
        no_range_reason=NoRangeReason.SEED_ONLY_NO_BOS,
        reason_text="Seed anchors only; no BOS cycle in replay window",
    )
