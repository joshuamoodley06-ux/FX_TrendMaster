"""RANGE_V2 draft suggestion emitter (Phase C — no pipeline hook)."""

from __future__ import annotations

from typing import Any

from detector.context_window import build_detection_window_meta
from detector.models import DetectionContext, SuggestionDraft, SwingPoint
from detector.range_boundary import derive_boundaries
from detector.range_lifecycle import evaluate_lifecycle
from detector.range_state import (
    BosDirection,
    BosReclaimChain,
    BoundarySelection,
    LifecycleEvaluation,
    NoRangeReason,
    OppositeSwingReason,
    RangeLifecycleState,
    RangeSeedContext,
)
from detector.range_seed import SEED_SOURCE_NONE
from detector.range_scale_mode import (
    CANDIDATE_KIND_RANGE,
    RANGE_SCALE_UNKNOWN,
    is_generic_scale_mode,
)
from detector.versions import ENGINE_SOURCE, RANGE_V2


def _resolve_seed(
    seed_context: RangeSeedContext | None,
    ctx: DetectionContext,
    *,
    strict: bool = False,
) -> RangeSeedContext | None:
    if seed_context is not None and seed_context.is_valid():
        return seed_context
    if strict:
        return None
    if ctx.has_range():
        return RangeSeedContext(
            range_high=float(ctx.range_high),  # type: ignore[arg-type]
            range_low=float(ctx.range_low),  # type: ignore[arg-type]
            active_range_id=ctx.active_range_id,
            is_manual_seed=False,
        )
    return None


def _window_meta(ctx: DetectionContext) -> dict[str, Any]:
    if ctx.detection_window_meta:
        return dict(ctx.detection_window_meta)
    return build_detection_window_meta(ctx)


def _suggestion_id_from_draft(draft: SuggestionDraft) -> str | None:
    meta = draft.meta_json or {}
    for key in ("suggestion_id", "bos_suggestion_id", "reclaim_suggestion_id"):
        raw = meta.get(key)
        if raw:
            return str(raw)
    return None


def _match_bos_draft(
    candidates: list[SuggestionDraft],
    *,
    direction: BosDirection,
    candle_index: int,
) -> SuggestionDraft | None:
    kind = "BOS_UP" if direction == BosDirection.UP else "BOS_DOWN"
    for draft in candidates:
        if draft.candidate_kind == kind and draft.candle_index == candle_index:
            return draft
    return None


def _match_reclaim_draft(
    candidates: list[SuggestionDraft],
    *,
    lifecycle_state: RangeLifecycleState,
    candle_index: int,
) -> SuggestionDraft | None:
    kind = (
        "RECLAIM_DOWN"
        if lifecycle_state == RangeLifecycleState.RECLAIMED_DOWN
        else "RECLAIM_UP"
    )
    for draft in candidates:
        if draft.candidate_kind == kind and draft.candle_index == candle_index:
            return draft
    return None


def _broken_boundary_for_state(state: RangeLifecycleState) -> str | None:
    if state == RangeLifecycleState.BREACHED_UP:
        return "HIGH"
    if state == RangeLifecycleState.BREACHED_DOWN:
        return "LOW"
    return None


def _internal_structure_status(ctx: DetectionContext, *, explicit: str | None = None) -> str:
    if explicit:
        return explicit
    raw = ctx.detection_window_meta.get("internal_structure_status")
    if raw:
        return str(raw)
    return "UNKNOWN"


def _apply_seed_trace_meta(
    meta: dict[str, Any],
    ctx: DetectionContext,
    seed: RangeSeedContext | None,
    *,
    no_seed_context: bool,
) -> None:
    seed_meta = dict(ctx.range_seed_meta or {})
    if seed is not None:
        seed_meta.setdefault("seed_source", seed.seed_source or SEED_SOURCE_NONE)
        seed_meta["no_seed_context"] = False
        seed_meta["active_range_id"] = seed.active_range_id
        seed_meta["seed_rh"] = seed.range_high
        seed_meta["seed_rl"] = seed.range_low
        seed_meta["seed_status"] = seed.status
    else:
        seed_meta.setdefault("seed_source", SEED_SOURCE_NONE)
        seed_meta["no_seed_context"] = no_seed_context
    meta.update(seed_meta)


def _build_meta_json(
    ctx: DetectionContext,
    *,
    seed: RangeSeedContext | None,
    lifecycle: LifecycleEvaluation,
    boundaries: BoundarySelection | None,
    bos_candidates: list[SuggestionDraft],
    reclaim_candidates: list[SuggestionDraft],
    range_scale: str | None = None,
    range_role: str | None = None,
    internal_structure_status: str | None = None,
) -> dict[str, Any]:
    meta = _window_meta(ctx)
    meta["engine_source"] = ENGINE_SOURCE
    meta["lifecycle_state"] = lifecycle.state.value
    meta["old_range_id"] = (
        seed.active_range_id if seed and seed.active_range_id is not None else ctx.active_range_id
    )
    meta["parent_range_id"] = ctx.parent_range_id

    if range_scale:
        meta["range_scale"] = range_scale
    if range_role:
        meta["range_role"] = range_role
    meta["internal_structure_status"] = _internal_structure_status(
        ctx,
        explicit=internal_structure_status,
    )

    chain = lifecycle.chain
    if chain is not None:
        meta["broken_boundary"] = chain.broken_boundary.value
        meta["bos_candle_index"] = chain.bos_index
        meta["reclaim_candle_index"] = chain.reclaim_index

        bos_draft = _match_bos_draft(
            bos_candidates,
            direction=chain.direction,
            candle_index=chain.bos_index,
        )
        if bos_draft:
            bos_id = _suggestion_id_from_draft(bos_draft)
            if bos_id:
                meta["bos_suggestion_id"] = bos_id
            bos_event_id = (bos_draft.meta_json or {}).get("bos_event_id")
            if bos_event_id:
                meta["bos_event_id"] = bos_event_id

        reclaim_draft = _match_reclaim_draft(
            reclaim_candidates,
            lifecycle_state=lifecycle.state,
            candle_index=chain.reclaim_index,
        )
        if reclaim_draft:
            reclaim_id = _suggestion_id_from_draft(reclaim_draft)
            if reclaim_id:
                meta["reclaim_suggestion_id"] = reclaim_id
            reclaim_event_id = (reclaim_draft.meta_json or {}).get("reclaim_event_id")
            if reclaim_event_id:
                meta["reclaim_event_id"] = reclaim_event_id
    else:
        broken = _broken_boundary_for_state(lifecycle.state)
        if broken:
            meta["broken_boundary"] = broken
        direction = (
            BosDirection.UP
            if lifecycle.state == RangeLifecycleState.BREACHED_UP
            else BosDirection.DOWN
            if lifecycle.state == RangeLifecycleState.BREACHED_DOWN
            else None
        )
        if direction is not None:
            for draft in reversed(bos_candidates):
                kind = "BOS_UP" if direction == BosDirection.UP else "BOS_DOWN"
                if draft.candidate_kind == kind and draft.candle_index <= ctx.active_index:
                    meta["bos_candle_index"] = draft.candle_index
                    bos_id = _suggestion_id_from_draft(draft)
                    if bos_id:
                        meta["bos_suggestion_id"] = bos_id
                    break

    if boundaries is not None:
        meta["boundary_selection_reason"] = boundaries.boundary_selection_reason or ""
        if boundaries.opposite_swing_index is not None:
            meta["opposite_swing_index"] = boundaries.opposite_swing_index
        if boundaries.opposite_swing_kind:
            meta["opposite_swing_kind"] = boundaries.opposite_swing_kind
    elif lifecycle.no_range_reason == NoRangeReason.UNCLEAR_OPPOSITE_SWING:
        meta["boundary_selection_reason"] = OppositeSwingReason.UNCLEAR_OPPOSITE_SWING.value
    elif boundaries is None and lifecycle.state == RangeLifecycleState.NO_VALID_RANGE:
        meta["boundary_selection_reason"] = OppositeSwingReason.UNCLEAR_OPPOSITE_SWING.value

    _apply_seed_trace_meta(
        meta,
        ctx,
        seed,
        no_seed_context=seed is None,
    )
    return meta


def _active_draft_anchor(ctx: DetectionContext) -> tuple[int, int]:
    active = ctx.active_candle
    if active is None:
        return 0, 0
    return active.index, active.time_ms


def _no_valid_range_draft(
    ctx: DetectionContext,
    *,
    seed: RangeSeedContext | None,
    lifecycle: LifecycleEvaluation,
    boundaries: BoundarySelection | None,
    bos_candidates: list[SuggestionDraft],
    reclaim_candidates: list[SuggestionDraft],
    reason_text: str,
    no_seed_context: bool = False,
) -> SuggestionDraft:
    idx, time_ms = _active_draft_anchor(ctx)
    meta = _build_meta_json(
        ctx,
        seed=seed,
        lifecycle=lifecycle,
        boundaries=boundaries,
        bos_candidates=bos_candidates,
        reclaim_candidates=reclaim_candidates,
    )
    if no_seed_context:
        meta["no_seed_context"] = True
    return SuggestionDraft(
        candidate_kind="NO_VALID_RANGE",
        detector_version=RANGE_V2,
        candle_index=idx,
        candle_time_utc_ms=time_ms,
        candidate_index=0,
        movement_rule="STRUCTURE_NO_VALID_RANGE",
        derived_event_code=f"{ctx.tf_prefix}_NO_VALID_RANGE",
        primitive="RANGE",
        break_rule=ctx.break_rule,
        confidence="LOW",
        reason_text=reason_text,
        meta_json=meta,
    )


def _range_kind_for_scale(scale: str, *, scale_mode: str | None = None) -> tuple[str, str | None, str | None]:
    if is_generic_scale_mode(scale_mode):
        return CANDIDATE_KIND_RANGE, RANGE_SCALE_UNKNOWN, None
    if scale == "MINOR":
        return "RANGE_MINOR", "MINOR", "INTERNAL_LEG"
    return "RANGE_MAJOR", "MAJOR", "ACTIVE_CONTAINER"


def _boundary_times(
    ctx: DetectionContext,
    chain: BosReclaimChain,
    boundaries: BoundarySelection,
) -> tuple[int | None, int | None]:
    rh_ms: int | None = None
    rl_ms: int | None = None
    if chain.direction == BosDirection.UP:
        rh_ms = ctx.candles[chain.bos_index].time_ms
        if boundaries.opposite_swing_index is not None:
            rl_ms = ctx.candles[boundaries.opposite_swing_index].time_ms
    else:
        rl_ms = ctx.candles[chain.bos_index].time_ms
        if boundaries.opposite_swing_index is not None:
            rh_ms = ctx.candles[boundaries.opposite_swing_index].time_ms
    return rh_ms, rl_ms


def _valid_range_draft(
    ctx: DetectionContext,
    *,
    seed: RangeSeedContext,
    lifecycle: LifecycleEvaluation,
    boundaries: BoundarySelection,
    bos_candidates: list[SuggestionDraft],
    reclaim_candidates: list[SuggestionDraft],
    candidate_kind: str,
    range_role: str | None,
    range_scale: str | None,
    internal_structure_status: str,
    scale_mode: str | None = None,
) -> SuggestionDraft:
    assert lifecycle.chain is not None
    chain = lifecycle.chain
    idx, time_ms = _active_draft_anchor(ctx)
    rh_ms, rl_ms = _boundary_times(ctx, chain, boundaries)
    scale = range_scale or str(ctx.range_scale or RANGE_SCALE_UNKNOWN).upper()
    if is_generic_scale_mode(scale_mode):
        scale = RANGE_SCALE_UNKNOWN

    meta = _build_meta_json(
        ctx,
        seed=seed,
        lifecycle=lifecycle,
        boundaries=boundaries,
        bos_candidates=bos_candidates,
        reclaim_candidates=reclaim_candidates,
        range_scale=scale,
        range_role=range_role,
        internal_structure_status=internal_structure_status,
    )
    if candidate_kind == CANDIDATE_KIND_RANGE:
        meta["classification_deferred"] = True

    return SuggestionDraft(
        candidate_kind=candidate_kind,
        detector_version=RANGE_V2,
        candle_index=idx,
        candle_time_utc_ms=time_ms,
        candidate_index=0,
        movement_rule=f"STRUCTURE_{candidate_kind}",
        derived_event_code=f"{ctx.tf_prefix}_{candidate_kind}",
        primitive="RANGE",
        break_rule=ctx.break_rule,
        suggested_rh=boundaries.suggested_rh,
        suggested_rl=boundaries.suggested_rl,
        suggested_rh_time_ms=rh_ms,
        suggested_rl_time_ms=rl_ms,
        range_scale=scale,
        range_role=range_role,
        confidence=boundaries.confidence,
        reason_text=boundaries.reason_text,
        meta_json=meta,
    )


def detect_range_v2_suggestions(
    ctx: DetectionContext,
    seed_context: RangeSeedContext | None,
    bos_candidates: list[SuggestionDraft],
    reclaim_candidates: list[SuggestionDraft],
    swings: list[SwingPoint],
    *,
    strict_seed: bool = False,
    scale_mode: str | None = None,
) -> list[SuggestionDraft]:
    """
    Emit RANGE_V2 SuggestionDraft rows only — no DB writes, no pipeline hook.
    """
    seed = _resolve_seed(seed_context, ctx, strict=strict_seed)
    if seed is None:
        lifecycle = LifecycleEvaluation(
            state=RangeLifecycleState.NO_VALID_RANGE,
            no_range_reason=NoRangeReason.NO_SEED_OR_ACTIVE_RANGE,
            reason_text="No seed or active range context",
        )
        return [
            _no_valid_range_draft(
                ctx,
                seed=None,
                lifecycle=lifecycle,
                boundaries=None,
                bos_candidates=bos_candidates,
                reclaim_candidates=reclaim_candidates,
                reason_text=lifecycle.reason_text,
                no_seed_context=strict_seed,
            )
        ]

    lifecycle = evaluate_lifecycle(
        ctx.candles,
        ctx.active_index,
        seed,
        break_rule=ctx.break_rule,
    )
    swings_used = swings or ctx.swings or []

    if lifecycle.can_suggest_range:
        boundaries = derive_boundaries(lifecycle, swings_used)
        if not boundaries.is_valid:
            reason = boundaries.reason_text or "Reclaim confirmed; no linked opposite swing"
            return [
                _no_valid_range_draft(
                    ctx,
                    seed=seed,
                    lifecycle=lifecycle,
                    boundaries=boundaries,
                    bos_candidates=bos_candidates,
                    reclaim_candidates=reclaim_candidates,
                    reason_text=reason,
                )
            ]

        if _internal_structure_status(ctx) == "NO_MINOR_STRUCTURE" and not is_generic_scale_mode(scale_mode):
            return [
                _valid_range_draft(
                    ctx,
                    seed=seed,
                    lifecycle=lifecycle,
                    boundaries=boundaries,
                    bos_candidates=bos_candidates,
                    reclaim_candidates=reclaim_candidates,
                    candidate_kind="NO_MINOR_STRUCTURE",
                    range_role="EXPANSION_LEG",
                    range_scale="MAJOR",
                    internal_structure_status="NO_MINOR_STRUCTURE",
                    scale_mode=scale_mode,
                )
            ]

        candidate_kind, range_scale, range_role = _range_kind_for_scale(
            str(ctx.range_scale or RANGE_SCALE_UNKNOWN).upper(),
            scale_mode=scale_mode,
        )
        return [
            _valid_range_draft(
                ctx,
                seed=seed,
                lifecycle=lifecycle,
                boundaries=boundaries,
                bos_candidates=bos_candidates,
                reclaim_candidates=reclaim_candidates,
                candidate_kind=candidate_kind,
                range_role=range_role,
                range_scale=range_scale,
                internal_structure_status="HAS_MINORS",
                scale_mode=scale_mode,
            )
        ]

    reason_text = lifecycle.reason_text or "No valid RANGE_V2 container"
    if lifecycle.no_range_reason == NoRangeReason.BOS_WITHOUT_RECLAIM:
        reason_text = "BOS detected; reclaim not yet confirmed"

    return [
        _no_valid_range_draft(
            ctx,
            seed=seed,
            lifecycle=lifecycle,
            boundaries=None,
            bos_candidates=bos_candidates,
            reclaim_candidates=reclaim_candidates,
            reason_text=reason_text,
        )
    ]
