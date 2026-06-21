"""Split persistence context from week-local range discovery (historical scan)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from detector.historical_range_chain import evaluate_bootstrap_candidates
from detector.models import DetectionContext, SuggestionDraft, SwingPoint
from detector.range_boundary import derive_boundaries
from detector.range_lifecycle import evaluate_lifecycle
from detector.range_seed import (
    DISCOVERY_SOURCE_LOCAL_ACTIVE_REPLAY,
    DISCOVERY_SOURCE_PROMOTED_SEED_LIFECYCLE,
    SEED_SOURCE_PROMOTED_RANGE,
)
from detector.range_state import RangeSeedContext
from detector.range_v2 import (
    _boundaries_coherent_with_active,
    _min_reclaim_time_ms,
    _reclaim_cycle_is_fresh,
    _valid_range_draft,
    _no_valid_range_draft,
    _range_kind_for_scale,
    _internal_structure_status,
)
from detector.range_scale_mode import is_generic_scale_mode, RANGE_SCALE_UNKNOWN


@dataclass(frozen=True)
class PersistenceDiscoveryTrace:
    context_seed_source: str
    discovery_source: str
    stale_context_rejected: bool
    local_discovery_attempted: bool
    local_discovery_result: str

    def to_meta(self) -> dict[str, Any]:
        return {
            "context_seed_source": self.context_seed_source,
            "discovery_source": self.discovery_source,
            "stale_context_rejected": self.stale_context_rejected,
            "local_discovery_attempted": self.local_discovery_attempted,
            "local_discovery_result": self.local_discovery_result,
        }


def context_seed_source_label(
    seed: RangeSeedContext | None,
    ctx: DetectionContext,
) -> str:
    if seed is not None and seed.seed_source:
        return str(seed.seed_source)
    return str((ctx.range_seed_meta or {}).get("seed_source") or "")


def uses_persistence_context(seed: RangeSeedContext | None, ctx: DetectionContext) -> bool:
    return context_seed_source_label(seed, ctx) == SEED_SOURCE_PROMOTED_RANGE


def promoted_lifecycle_trace() -> PersistenceDiscoveryTrace:
    return PersistenceDiscoveryTrace(
        context_seed_source=SEED_SOURCE_PROMOTED_RANGE,
        discovery_source=DISCOVERY_SOURCE_PROMOTED_SEED_LIFECYCLE,
        stale_context_rejected=False,
        local_discovery_attempted=False,
        local_discovery_result="PROMOTED_SEED_LIFECYCLE_EMITTED",
    )


def attach_persistence_context_meta(
    meta: dict[str, Any],
    *,
    persistence_seed: RangeSeedContext | None,
    trace: PersistenceDiscoveryTrace,
) -> None:
    meta.update(trace.to_meta())
    if persistence_seed is not None and persistence_seed.is_valid():
        meta["context_seed_rh"] = persistence_seed.range_high
        meta["context_seed_rl"] = persistence_seed.range_low
        if persistence_seed.active_range_id is not None:
            meta["context_promoted_range_id"] = persistence_seed.active_range_id


def attempt_local_active_discovery(
    ctx: DetectionContext,
    *,
    persistence_seed: RangeSeedContext,
    swings: list[SwingPoint],
    bos_candidates: list[SuggestionDraft],
    reclaim_candidates: list[SuggestionDraft],
    scale_mode: str | None,
) -> tuple[list[SuggestionDraft] | None, PersistenceDiscoveryTrace]:
    period_start_ms = _min_reclaim_time_ms(ctx)
    boot = evaluate_bootstrap_candidates(
        ctx.candles,
        ctx.active_index,
        break_rule=ctx.break_rule,
        period_start_ms=period_start_ms,
    )
    base_trace = PersistenceDiscoveryTrace(
        context_seed_source=SEED_SOURCE_PROMOTED_RANGE,
        discovery_source="",
        stale_context_rejected=True,
        local_discovery_attempted=True,
        local_discovery_result="",
    )

    if boot.seed is None:
        reason = (
            boot.trace.no_selection_reason
            if boot.trace is not None
            else None
        ) or "no fresh local BOS→reclaim cycle near active week"
        return None, PersistenceDiscoveryTrace(
            context_seed_source=base_trace.context_seed_source,
            discovery_source="",
            stale_context_rejected=True,
            local_discovery_attempted=True,
            local_discovery_result=reason,
        )

    discovery_seed = boot.seed
    lifecycle = evaluate_lifecycle(
        ctx.candles,
        ctx.active_index,
        discovery_seed,
        break_rule=ctx.break_rule,
        min_reclaim_time_ms=period_start_ms,
    )
    swings_used = swings or ctx.swings or []

    if not lifecycle.can_suggest_range:
        reason = lifecycle.reason_text or "local lifecycle incomplete"
        return None, PersistenceDiscoveryTrace(
            context_seed_source=base_trace.context_seed_source,
            discovery_source="",
            stale_context_rejected=True,
            local_discovery_attempted=True,
            local_discovery_result=reason,
        )

    boundaries = derive_boundaries(lifecycle, swings_used, candles=ctx.candles)
    if not boundaries.is_valid:
        reason = boundaries.reason_text or "local boundary selection failed"
        return None, PersistenceDiscoveryTrace(
            context_seed_source=base_trace.context_seed_source,
            discovery_source="",
            stale_context_rejected=True,
            local_discovery_attempted=True,
            local_discovery_result=reason,
        )

    if not _reclaim_cycle_is_fresh(ctx, lifecycle):
        return None, PersistenceDiscoveryTrace(
            context_seed_source=base_trace.context_seed_source,
            discovery_source="",
            stale_context_rejected=True,
            local_discovery_attempted=True,
            local_discovery_result="local reclaim not fresh at active week",
        )

    if not _boundaries_coherent_with_active(ctx, boundaries):
        return None, PersistenceDiscoveryTrace(
            context_seed_source=base_trace.context_seed_source,
            discovery_source="",
            stale_context_rejected=True,
            local_discovery_attempted=True,
            local_discovery_result="local boundaries incoherent with active-week price",
        )

    if _internal_structure_status(ctx) == "NO_MINOR_STRUCTURE" and not is_generic_scale_mode(scale_mode):
        draft = _valid_range_draft(
            ctx,
            seed=discovery_seed,
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
        trace = PersistenceDiscoveryTrace(
            context_seed_source=SEED_SOURCE_PROMOTED_RANGE,
            discovery_source=DISCOVERY_SOURCE_LOCAL_ACTIVE_REPLAY,
            stale_context_rejected=True,
            local_discovery_attempted=True,
            local_discovery_result="NO_MINOR_STRUCTURE",
        )
        attach_persistence_context_meta(
            draft.meta_json,
            persistence_seed=persistence_seed,
            trace=trace,
        )
        return [draft], trace

    candidate_kind, range_scale, range_role = _range_kind_for_scale(
        str(ctx.range_scale or RANGE_SCALE_UNKNOWN).upper(),
        scale_mode=scale_mode,
    )
    draft = _valid_range_draft(
        ctx,
        seed=discovery_seed,
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
    trace = PersistenceDiscoveryTrace(
        context_seed_source=SEED_SOURCE_PROMOTED_RANGE,
        discovery_source=DISCOVERY_SOURCE_LOCAL_ACTIVE_REPLAY,
        stale_context_rejected=True,
        local_discovery_attempted=True,
        local_discovery_result="RANGE_CANDIDATE",
    )
    attach_persistence_context_meta(
        draft.meta_json,
        persistence_seed=persistence_seed,
        trace=trace,
    )
    draft.meta_json["bootstrap_retry"] = True
    return [draft], trace


def stale_persistence_no_valid_draft(
    ctx: DetectionContext,
    *,
    persistence_seed: RangeSeedContext,
    lifecycle,
    boundaries,
    bos_candidates: list[SuggestionDraft],
    reclaim_candidates: list[SuggestionDraft],
    trace: PersistenceDiscoveryTrace,
) -> SuggestionDraft:
    reason = (
        f"Promoted context reclaim stale; {trace.local_discovery_result}"
        if trace.local_discovery_result
        else "Promoted context reclaim stale; no fresh local BOS→reclaim cycle"
    )
    draft = _no_valid_range_draft(
        ctx,
        seed=persistence_seed,
        lifecycle=lifecycle,
        boundaries=boundaries,
        bos_candidates=bos_candidates,
        reclaim_candidates=reclaim_candidates,
        reason_text=reason,
    )
    attach_persistence_context_meta(
        draft.meta_json,
        persistence_seed=persistence_seed,
        trace=trace,
    )
    return draft
