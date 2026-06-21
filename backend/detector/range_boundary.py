"""RANGE_V2 leg-based HTF boundary selection — expansion leg + opposite anchor."""

from __future__ import annotations

from typing import Any

from detector.models import NormalizedCandle, SwingPoint
from detector.range_state import (
    BOUNDARY_SOURCE_BOS_BAR,
    BOUNDARY_SOURCE_LEG_EXPANSION,
    BOUNDARY_SOURCE_RETRACEMENT_POINT,
    BOUNDARY_SOURCE_SEED_ANCHORED,
    BOUNDARY_SOURCE_STRUCTURAL_SWING,
    BosDirection,
    BosReclaimChain,
    BoundarySelection,
    EXPANSION_OWNER_BOS_CANDLE,
    EXPANSION_OWNER_IMPULSE_SWING,
    EXPANSION_OWNER_REF_CANDLE,
    LEG_STATE_RECLAIM,
    LifecycleEvaluation,
    NoRangeReason,
    OppositeSwingReason,
    POST_BOS_RETRACEMENT_POINT_NOT_BOUNDARY,
    RELATION_BEFORE_BOS,
    RELATION_BETWEEN_BOS_RECLAIM,
    RELATION_BOS_BAR,
    RangeLifecycleState,
)


LOOKBACK_BEFORE_BOS = 50


def _opposite_kind(direction: BosDirection) -> str:
    return "SWING_LOW" if direction == BosDirection.UP else "SWING_HIGH"


def _is_between_bos_reclaim(index: int, bos_index: int, reclaim_index: int) -> bool:
    return bos_index < index < reclaim_index


def _candidate_record(
    *,
    side: str,
    price: float,
    time_ms: int | None,
    swing_index: int | None,
    source: str,
    relation_to_bos: str,
) -> dict[str, Any]:
    return {
        "side": side,
        "price": price,
        "time_ms": time_ms,
        "swing_index": swing_index,
        "source": source,
        "relation_to_bos": relation_to_bos,
    }


def _rejection_record(
    *,
    side: str,
    price: float,
    time_ms: int | None,
    swing_index: int | None,
    source: str,
    relation_to_bos: str,
    rejection_reason: str,
) -> dict[str, Any]:
    row = _candidate_record(
        side=side,
        price=price,
        time_ms=time_ms,
        swing_index=swing_index,
        source=source,
        relation_to_bos=relation_to_bos,
    )
    row["rejection_reason"] = rejection_reason
    return row


def _swing_time_ms(swing: SwingPoint) -> int | None:
    try:
        return int(swing.candle.time_ms)
    except (AttributeError, TypeError, ValueError):
        return None


def _candle_time_ms(candles: list[NormalizedCandle], index: int) -> int | None:
    if index < 0 or index >= len(candles):
        return None
    return int(candles[index].time_ms)


def _collect_retracement_rejections(
    swings: list[SwingPoint],
    chain: BosReclaimChain,
) -> list[dict[str, Any]]:
    """Post-BOS retracement-zone swings must not become range boundaries."""
    rejected: list[dict[str, Any]] = []
    bos = int(chain.bos_index)
    reclaim = int(chain.reclaim_index)

    if chain.direction == BosDirection.UP:
        for swing in swings:
            if swing.kind != "SWING_LOW":
                continue
            if not _is_between_bos_reclaim(swing.index, bos, reclaim):
                continue
            rejected.append(
                _rejection_record(
                    side="RL",
                    price=float(swing.price),
                    time_ms=_swing_time_ms(swing),
                    swing_index=swing.index,
                    source=BOUNDARY_SOURCE_RETRACEMENT_POINT,
                    relation_to_bos=RELATION_BETWEEN_BOS_RECLAIM,
                    rejection_reason=POST_BOS_RETRACEMENT_POINT_NOT_BOUNDARY,
                )
            )
    else:
        for swing in swings:
            if swing.kind != "SWING_HIGH":
                continue
            if not _is_between_bos_reclaim(swing.index, bos, reclaim):
                continue
            rejected.append(
                _rejection_record(
                    side="RH",
                    price=float(swing.price),
                    time_ms=_swing_time_ms(swing),
                    swing_index=swing.index,
                    source=BOUNDARY_SOURCE_RETRACEMENT_POINT,
                    relation_to_bos=RELATION_BETWEEN_BOS_RECLAIM,
                    rejection_reason=POST_BOS_RETRACEMENT_POINT_NOT_BOUNDARY,
                )
            )
    return rejected


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
    """Legacy helper — retained for tests; boundary selection uses leg rules."""
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


def _expansion_owner(bos_index: int, extreme_index: int) -> str:
    if extreme_index == bos_index:
        return EXPANSION_OWNER_BOS_CANDLE
    if extreme_index == bos_index + 1:
        return EXPANSION_OWNER_REF_CANDLE
    return EXPANSION_OWNER_IMPULSE_SWING


def _source_for_expansion_owner(owner: str) -> str:
    if owner == EXPANSION_OWNER_BOS_CANDLE:
        return BOUNDARY_SOURCE_BOS_BAR
    if owner == EXPANSION_OWNER_REF_CANDLE:
        return BOUNDARY_SOURCE_STRUCTURAL_SWING
    return BOUNDARY_SOURCE_LEG_EXPANSION


def _pick_expansion_extreme(
    chain: BosReclaimChain,
    candles: list[NormalizedCandle],
    swings: list[SwingPoint],
    *,
    broken_side: str,
) -> tuple[float | None, int | None, int | None, str, list[dict[str, Any]]]:
    """
    Highest/lowest valid price in expansion leg [bos, reclaim) before reclaim freezes the leg.

    broken_side: 'HIGH' for bullish RH, 'LOW' for bearish RL.
    """
    bos = int(chain.bos_index)
    reclaim = int(chain.reclaim_index)
    considered: list[dict[str, Any]] = []

    if reclaim <= bos:
        return None, None, None, "", considered

    best_price: float | None = None
    best_index: int | None = None

    for idx in range(bos, reclaim):
        if idx >= len(candles):
            continue
        candle = candles[idx]
        price = float(candle.high if broken_side == "HIGH" else candle.low)
        relation = (
            RELATION_BETWEEN_BOS_RECLAIM
            if _is_between_bos_reclaim(idx, bos, reclaim)
            else RELATION_BOS_BAR
            if idx == bos
            else RELATION_BEFORE_BOS
        )
        considered.append(
            _candidate_record(
                side="RH" if broken_side == "HIGH" else "RL",
                price=price,
                time_ms=int(candle.time_ms),
                swing_index=idx,
                source=BOUNDARY_SOURCE_LEG_EXPANSION,
                relation_to_bos=relation,
            )
        )
        if best_price is None:
            best_price, best_index = price, idx
        elif broken_side == "HIGH" and price > best_price:
            best_price, best_index = price, idx
        elif broken_side == "LOW" and price < best_price:
            best_price, best_index = price, idx

    swing_kind = "SWING_HIGH" if broken_side == "HIGH" else "SWING_LOW"
    for swing in swings:
        if swing.kind != swing_kind:
            continue
        if not (bos <= swing.index < reclaim):
            continue
        price = float(swing.price)
        considered.append(
            _candidate_record(
                side="RH" if broken_side == "HIGH" else "RL",
                price=price,
                time_ms=_swing_time_ms(swing),
                swing_index=swing.index,
                source=BOUNDARY_SOURCE_STRUCTURAL_SWING,
                relation_to_bos=(
                    RELATION_BETWEEN_BOS_RECLAIM
                    if _is_between_bos_reclaim(swing.index, bos, reclaim)
                    else RELATION_BOS_BAR
                ),
            )
        )
        if best_price is None:
            best_price, best_index = price, swing.index
        elif broken_side == "HIGH" and price > best_price:
            best_price, best_index = price, swing.index
        elif broken_side == "LOW" and price < best_price:
            best_price, best_index = price, swing.index

    if best_price is None or best_index is None:
        return None, None, None, "", considered

    owner = _expansion_owner(bos, best_index)
    time_ms = _candle_time_ms(candles, best_index)
    return best_price, best_index, time_ms, owner, considered


def _pick_opposite_anchor(
    chain: BosReclaimChain,
    swings: list[SwingPoint],
    candles: list[NormalizedCandle],
) -> tuple[float | None, int | None, int | None, str, SwingPoint | None, list[dict[str, Any]]]:
    """Opposite-side anchor before BOS — exclude BOS-predecessor retrace week."""
    bos = int(chain.bos_index)
    min_index = max(0, bos - LOOKBACK_BEFORE_BOS)
    # Structural anchor lives before the BOS-predecessor bar (audit: not retrace low week).
    anchor_cutoff = max(min_index, bos - 1)
    considered: list[dict[str, Any]] = []

    if chain.direction == BosDirection.UP:
        pool = [
            s
            for s in swings
            if s.kind == "SWING_LOW" and min_index <= s.index < anchor_cutoff
        ]
        if not pool:
            pool = [
                s
                for s in swings
                if s.kind == "SWING_LOW" and min_index <= s.index < bos
            ]
        for swing in pool:
            considered.append(
                _candidate_record(
                    side="RL",
                    price=float(swing.price),
                    time_ms=_swing_time_ms(swing),
                    swing_index=swing.index,
                    source=BOUNDARY_SOURCE_STRUCTURAL_SWING,
                    relation_to_bos=RELATION_BEFORE_BOS,
                )
            )
        anchor_swing: SwingPoint | None = None
        if pool:
            anchor_swing = min(pool, key=lambda s: s.price)
        elif chain.old_range_low is not None:
            considered.append(
                _candidate_record(
                    side="RL",
                    price=float(chain.old_range_low),
                    time_ms=None,
                    swing_index=None,
                    source=BOUNDARY_SOURCE_SEED_ANCHORED,
                    relation_to_bos=RELATION_BEFORE_BOS,
                )
            )
            return (
                float(chain.old_range_low),
                None,
                None,
                BOUNDARY_SOURCE_SEED_ANCHORED,
                None,
                considered,
            )
        else:
            return None, None, None, "", None, considered

        idx = anchor_swing.index
        return (
            float(anchor_swing.price),
            idx,
            _candle_time_ms(candles, idx),
            BOUNDARY_SOURCE_STRUCTURAL_SWING,
            anchor_swing,
            considered,
        )

    pool = [
        s
        for s in swings
        if s.kind == "SWING_HIGH" and min_index <= s.index < anchor_cutoff
    ]
    if not pool:
        pool = [
            s
            for s in swings
            if s.kind == "SWING_HIGH" and min_index <= s.index < bos
        ]
    for swing in pool:
        considered.append(
            _candidate_record(
                side="RH",
                price=float(swing.price),
                time_ms=_swing_time_ms(swing),
                swing_index=swing.index,
                source=BOUNDARY_SOURCE_STRUCTURAL_SWING,
                relation_to_bos=RELATION_BEFORE_BOS,
            )
        )
    anchor_swing = None
    if pool:
        anchor_swing = max(pool, key=lambda s: s.price)
    elif chain.old_range_high is not None:
        considered.append(
            _candidate_record(
                side="RH",
                price=float(chain.old_range_high),
                time_ms=None,
                swing_index=None,
                source=BOUNDARY_SOURCE_SEED_ANCHORED,
                relation_to_bos=RELATION_BEFORE_BOS,
            )
        )
        return (
            float(chain.old_range_high),
            None,
            None,
            BOUNDARY_SOURCE_SEED_ANCHORED,
            None,
            considered,
        )
    else:
        return None, None, None, "", None, considered

    idx = anchor_swing.index
    return (
        float(anchor_swing.price),
        idx,
        _candle_time_ms(candles, idx),
        BOUNDARY_SOURCE_STRUCTURAL_SWING,
        anchor_swing,
        considered,
    )


def _build_htf_leg_trace(
    chain: BosReclaimChain,
    candles: list[NormalizedCandle],
    *,
    expansion_price: float,
    expansion_index: int,
    expansion_time_ms: int | None,
    expansion_owner: str,
    opposite_price: float,
    opposite_time_ms: int | None,
) -> dict[str, Any]:
    bos = int(chain.bos_index)
    reclaim = int(chain.reclaim_index)
    return {
        "schema_version": "htf_leg_trace_v1",
        "broken_boundary": chain.broken_boundary.value,
        "bos_direction": chain.direction.value,
        "expansion_leg_start_time_ms": _candle_time_ms(candles, bos),
        "expansion_leg_end_time_ms": _candle_time_ms(candles, reclaim),
        "expansion_extreme_price": expansion_price,
        "expansion_extreme_time_ms": expansion_time_ms,
        "expansion_extreme_owner": expansion_owner,
        "expansion_extreme_candle_index": expansion_index,
        "reclaim_leg_start_time_ms": _candle_time_ms(candles, reclaim),
        "reclaim_leg_extreme_price": None,
        "reclaim_leg_extreme_time_ms": None,
        "current_leg_state": LEG_STATE_RECLAIM,
        "opposite_anchor_price": opposite_price,
        "opposite_anchor_time_ms": opposite_time_ms,
    }


def _leg_bullish_boundaries(
    chain: BosReclaimChain,
    swings: list[SwingPoint],
    candles: list[NormalizedCandle],
) -> BoundarySelection | None:
    rejected = _collect_retracement_rejections(swings, chain)
    considered: list[dict[str, Any]] = []

    exp_price, exp_idx, exp_ms, exp_owner, exp_considered = _pick_expansion_extreme(
        chain, candles, swings, broken_side="HIGH"
    )
    considered.extend(exp_considered)
    if exp_price is None or exp_idx is None:
        return None

    rl_price, rl_idx, rl_ms, rl_source, rl_swing, opp_considered = _pick_opposite_anchor(
        chain, swings, candles
    )
    considered.extend(opp_considered)
    if rl_price is None:
        return None

    suggested_rh = float(exp_price)
    suggested_rl = float(rl_price)
    if suggested_rh <= suggested_rl:
        return None

    rh_source = _source_for_expansion_owner(exp_owner)
    confidence = "MEDIUM" if exp_owner != EXPANSION_OWNER_BOS_CANDLE else "MEDIUM"

    selected_rh = _candidate_record(
        side="RH",
        price=suggested_rh,
        time_ms=exp_ms,
        swing_index=exp_idx,
        source=rh_source,
        relation_to_bos=(
            RELATION_BETWEEN_BOS_RECLAIM
            if _is_between_bos_reclaim(exp_idx, chain.bos_index, chain.reclaim_index)
            else RELATION_BOS_BAR
        ),
    )
    selected_rl = _candidate_record(
        side="RL",
        price=suggested_rl,
        time_ms=rl_ms,
        swing_index=rl_idx,
        source=rl_source,
        relation_to_bos=RELATION_BEFORE_BOS,
    )

    leg_trace = _build_htf_leg_trace(
        chain,
        candles,
        expansion_price=suggested_rh,
        expansion_index=exp_idx,
        expansion_time_ms=exp_ms,
        expansion_owner=exp_owner,
        opposite_price=suggested_rl,
        opposite_time_ms=rl_ms,
    )

    rl_reason = OppositeSwingReason.STRUCTURAL_SWING_FLOOR_BEFORE_BOS
    return BoundarySelection(
        suggested_rh=suggested_rh,
        suggested_rl=suggested_rl,
        opposite_swing_index=rl_swing.index if rl_swing else rl_idx,
        opposite_swing_kind="SWING_LOW" if rl_swing else None,
        opposite_swing_price=suggested_rl,
        rh_swing_index=exp_idx,
        rl_swing_index=rl_swing.index if rl_swing else rl_idx,
        selected_rh_source=rh_source,
        selected_rl_source=rl_source,
        boundary_selection_reason=rl_reason.value,
        confidence=confidence,
        reason_text=(
            f"BOS {chain.direction.value} @{chain.bos_index}; reclaim @{chain.reclaim_index}; "
            f"leg RH {exp_owner} RL opposite_anchor"
        ),
        boundary_trace={
            "boundary_candidates_considered": considered,
            "rejected_boundary_candidates": rejected,
            "selected_boundary_candidate": {"RH": selected_rh, "RL": selected_rl},
            "selected_rh_source": rh_source,
            "selected_rl_source": rl_source,
            "htf_leg_trace": leg_trace,
        },
    )


def _leg_bearish_boundaries(
    chain: BosReclaimChain,
    swings: list[SwingPoint],
    candles: list[NormalizedCandle],
) -> BoundarySelection | None:
    rejected = _collect_retracement_rejections(swings, chain)
    considered: list[dict[str, Any]] = []

    exp_price, exp_idx, exp_ms, exp_owner, exp_considered = _pick_expansion_extreme(
        chain, candles, swings, broken_side="LOW"
    )
    considered.extend(exp_considered)
    if exp_price is None or exp_idx is None:
        return None

    rh_price, rh_idx, rh_ms, rh_source, rh_swing, opp_considered = _pick_opposite_anchor(
        chain, swings, candles
    )
    considered.extend(opp_considered)
    if rh_price is None:
        return None

    suggested_rh = float(rh_price)
    suggested_rl = float(exp_price)
    if suggested_rh <= suggested_rl:
        return None

    rl_source = _source_for_expansion_owner(exp_owner)
    confidence = "MEDIUM"

    selected_rh = _candidate_record(
        side="RH",
        price=suggested_rh,
        time_ms=rh_ms,
        swing_index=rh_idx,
        source=rh_source,
        relation_to_bos=RELATION_BEFORE_BOS,
    )
    selected_rl = _candidate_record(
        side="RL",
        price=suggested_rl,
        time_ms=exp_ms,
        swing_index=exp_idx,
        source=rl_source,
        relation_to_bos=(
            RELATION_BETWEEN_BOS_RECLAIM
            if _is_between_bos_reclaim(exp_idx, chain.bos_index, chain.reclaim_index)
            else RELATION_BOS_BAR
        ),
    )

    leg_trace = _build_htf_leg_trace(
        chain,
        candles,
        expansion_price=suggested_rl,
        expansion_index=exp_idx,
        expansion_time_ms=exp_ms,
        expansion_owner=exp_owner,
        opposite_price=suggested_rh,
        opposite_time_ms=rh_ms,
    )

    rl_reason = OppositeSwingReason.STRUCTURAL_SWING_IMPULSE_LEG
    return BoundarySelection(
        suggested_rh=suggested_rh,
        suggested_rl=suggested_rl,
        opposite_swing_index=rh_swing.index if rh_swing else rh_idx,
        opposite_swing_kind="SWING_HIGH" if rh_swing else None,
        opposite_swing_price=suggested_rh,
        rh_swing_index=rh_swing.index if rh_swing else rh_idx,
        rl_swing_index=exp_idx,
        selected_rh_source=rh_source,
        selected_rl_source=rl_source,
        boundary_selection_reason=rl_reason.value,
        confidence=confidence,
        reason_text=(
            f"BOS {chain.direction.value} @{chain.bos_index}; reclaim @{chain.reclaim_index}; "
            f"leg RL {exp_owner} RH opposite_anchor"
        ),
        boundary_trace={
            "boundary_candidates_considered": considered,
            "rejected_boundary_candidates": rejected,
            "selected_boundary_candidate": {"RH": selected_rh, "RL": selected_rl},
            "selected_rh_source": rh_source,
            "selected_rl_source": rl_source,
            "htf_leg_trace": leg_trace,
        },
    )


def derive_boundaries(
    lifecycle: LifecycleEvaluation,
    swings: list[SwingPoint],
    candles: list[NormalizedCandle] | None = None,
) -> BoundarySelection:
    """
    Derive RH/RL from HTF leg doctrine:

    Bullish: RH = expansion-leg extreme before reclaim; RL = opposite anchor before BOS.
    Bearish: RL = expansion-leg extreme before reclaim; RH = opposite anchor before BOS.
    """
    if not lifecycle.can_suggest_range or lifecycle.chain is None:
        return BoundarySelection(
            no_range_reason=lifecycle.no_range_reason or NoRangeReason.BOS_WITHOUT_RECLAIM,
            reason_text=lifecycle.reason_text or "Lifecycle not ready for boundary selection",
            boundary_selection_reason=OppositeSwingReason.UNCLEAR_OPPOSITE_SWING.value,
        )

    chain = lifecycle.chain
    candle_list: list[NormalizedCandle] = list(candles or [])
    if not candle_list and swings:
        candle_list = [s.candle for s in swings]

    if not candle_list:
        return BoundarySelection(
            no_range_reason=NoRangeReason.UNCLEAR_OPPOSITE_SWING,
            reason_text="Reclaim confirmed; no candle context for leg boundaries",
            boundary_selection_reason=OppositeSwingReason.UNCLEAR_OPPOSITE_SWING.value,
            confidence="LOW",
        )

    if chain.direction == BosDirection.UP:
        result = _leg_bullish_boundaries(chain, swings, candle_list)
    else:
        result = _leg_bearish_boundaries(chain, swings, candle_list)

    if result is None:
        return BoundarySelection(
            no_range_reason=NoRangeReason.UNCLEAR_OPPOSITE_SWING,
            reason_text="Reclaim confirmed; no leg boundary candidates",
            boundary_selection_reason=OppositeSwingReason.UNCLEAR_OPPOSITE_SWING.value,
            confidence="LOW",
        )

    return result


def evaluate_range_v2_boundaries(
    lifecycle: LifecycleEvaluation,
    swings: list[SwingPoint],
    candles: list[NormalizedCandle] | None = None,
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
    return derive_boundaries(lifecycle, swings, candles=candles)
