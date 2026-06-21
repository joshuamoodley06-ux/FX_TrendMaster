"""Unified per-step seed resolution — Review Candidate and historical year scan share this."""

from __future__ import annotations

import sqlite3
from typing import Any

from detector.models import DetectionContext
from dataclasses import dataclass

from detector.range_seed import (
    SEED_POLICY_DEFAULT,
    SEED_POLICY_REVIEWED_TRUTH_ONLY,
    SEED_SOURCE_NONE,
    SEED_SOURCE_PROMOTED_RANGE,
    SEED_SOURCE_TEMP_PREVIOUS_CANDIDATE,
    SeedResolutionResult,
    _electron_chart_seed_from_payload,
    load_latest_promoted_range_seed,
    resolve_detector_seed_context,
    seed_resolution_to_meta,
)
from detector.range_state import RangeSeedContext

# Legacy rolled label for resolve_range_step_seed (non-scan callers).
SEED_SOURCE_ROLLED = "previous_range_candidate"
SEED_SOURCE_BOOTSTRAP = "bootstrap_candidate"
SEED_SOURCE_ELECTRON = "electron_selected_range"


@dataclass(frozen=True)
class HistoricalScanSeedResolution:
    seed: RangeSeedContext | None
    seed_source: str
    meta: dict[str, Any]


def _temp_working_seed_context(
    working_seed: RangeSeedContext,
    *,
    layer: str,
    tf: str,
) -> RangeSeedContext:
    return RangeSeedContext(
        range_high=float(working_seed.range_high),
        range_low=float(working_seed.range_low),
        active_range_id=working_seed.active_range_id,
        is_manual_seed=False,
        seed_source=SEED_SOURCE_TEMP_PREVIOUS_CANDIDATE,
        range_scale=working_seed.range_scale,
        range_role=working_seed.range_role,
        parent_range_id=working_seed.parent_range_id,
        structure_layer=working_seed.structure_layer or layer,
        source_timeframe=working_seed.source_timeframe or tf,
    )


def resolve_historical_scan_step_seed(
    ctx: DetectionContext,
    *,
    conn: sqlite3.Connection | None,
    seed_policy: str,
    temp_working_seed: RangeSeedContext | None,
    period_start_ms: int | None,
    structure_layer: str | None,
    parent_range_id: int | None,
    scan_chain_index: int,
) -> HistoricalScanSeedResolution:
    """
    Per-step seed for historical range scan.

    reviewed_truth_only: promoted map_range before replay time beats in-scan temp roll.
    default: same roll behavior, meta uses TEMP_PREVIOUS_CANDIDATE for raw candidate chain.
    """
    layer = (structure_layer or str(ctx.structure_layer or "")).strip().upper()
    tf = str(ctx.source_timeframe or "W1").upper()
    policy = str(seed_policy or SEED_POLICY_DEFAULT).strip().lower()
    replay_ms = int(ctx.replay_until_time_ms or 0)
    if replay_ms <= 0 and ctx.active_candle is not None:
        replay_ms = int(ctx.active_candle.time_ms)

    if policy == SEED_POLICY_REVIEWED_TRUTH_ONLY and conn is not None and replay_ms > 0:
        promoted = load_latest_promoted_range_seed(
            conn,
            symbol=str(ctx.symbol or "XAUUSD"),
            structure_layer=layer,
            source_timeframe=tf,
            before_replay_time_ms=replay_ms,
            parent_range_id=parent_range_id,
        )
        if promoted.seed is not None:
            meta = seed_resolution_to_meta(promoted)
            meta["scan_chain_index"] = scan_chain_index
            meta["seed_policy"] = policy
            if promoted.seed.active_range_id is not None:
                meta["promoted_range_id"] = promoted.seed.active_range_id
            return HistoricalScanSeedResolution(
                seed=promoted.seed,
                seed_source=SEED_SOURCE_PROMOTED_RANGE,
                meta=meta,
            )

    if temp_working_seed is not None and temp_working_seed.is_valid():
        seed = _temp_working_seed_context(temp_working_seed, layer=layer, tf=tf)
        meta = {
            "seed_source": SEED_SOURCE_TEMP_PREVIOUS_CANDIDATE,
            "no_seed_context": False,
            "seed_rh": seed.range_high,
            "seed_rl": seed.range_low,
            "scan_chain_index": scan_chain_index,
            "seed_policy": policy,
        }
        return HistoricalScanSeedResolution(
            seed=seed,
            seed_source=SEED_SOURCE_TEMP_PREVIOUS_CANDIDATE,
            meta=meta,
        )

    step = resolve_range_step_seed(
        ctx,
        conn=conn,
        period_start_ms=period_start_ms,
        discovery_mode=True,
        allow_map_ranges=False,
        structure_layer=layer,
        parent_range_id=parent_range_id,
    )
    meta = seed_resolution_to_meta(step) if step.seed is not None else {"seed_source": step.seed_source}
    meta["scan_chain_index"] = 0
    meta["seed_policy"] = policy
    return HistoricalScanSeedResolution(
        seed=step.seed,
        seed_source=step.seed_source,
        meta=meta,
    )


def seed_coherent_with_active(
    ctx: DetectionContext,
    rh: float,
    rl: float,
    *,
    span_tolerance: float = 0.5,
) -> bool:
    """Reject stale map_ranges / chart boxes far from current replay price."""
    from detector.historical_range_chain import _price_coherence_score

    active = ctx.active_candle
    if active is None:
        return True
    score = _price_coherence_score(
        float(active.close),
        float(rh),
        float(rl),
        span_tolerance=span_tolerance,
    )
    return score > 0.0


def resolve_range_step_seed(
    ctx: DetectionContext,
    *,
    working_seed: RangeSeedContext | None = None,
    payload: dict[str, Any] | None = None,
    conn: sqlite3.Connection | None = None,
    period_start_ms: int | None = None,
    discovery_mode: bool = True,
    allow_map_ranges: bool = False,
    structure_layer: str | None = None,
    parent_range_id: int | None = None,
) -> SeedResolutionResult:
    """
    One seed rule for every replay step (single week or full-year weekly walk):

    1. Rolled seed from prior accepted RANGE_CANDIDATE (historical walk)
    2. map_ranges ACTIVE when allow_map_ranges (advanced / explicit id)
    3. Coherent chart RH/RL from Electron (manual override)
    4. Bootstrap from swings — BOS→reclaim near active bar (discovery_mode)
    """
    layer = (structure_layer or str(ctx.structure_layer or "")).strip().upper()
    tf = str(ctx.source_timeframe or "W1").upper()
    sym = str(ctx.symbol or "XAUUSD").upper()
    payload = payload or {}

    if working_seed is not None and working_seed.is_valid():
        rolled = RangeSeedContext(
            range_high=float(working_seed.range_high),
            range_low=float(working_seed.range_low),
            active_range_id=working_seed.active_range_id,
            is_manual_seed=False,
            seed_source=SEED_SOURCE_ROLLED,
            range_scale=working_seed.range_scale,
            range_role=working_seed.range_role,
            parent_range_id=working_seed.parent_range_id,
            structure_layer=working_seed.structure_layer or layer,
            source_timeframe=working_seed.source_timeframe or tf,
        )
        return SeedResolutionResult(seed=rolled, seed_source=SEED_SOURCE_ROLLED)

    if allow_map_ranges and conn is not None:
        backend = resolve_detector_seed_context(
            conn,
            payload,
            symbol=sym,
            structure_layer=layer,
            source_timeframe=tf,
            parent_range_id=parent_range_id,
        )
        if backend.seed is not None:
            return backend

    chart = _electron_chart_seed_from_payload(
        payload,
        structure_layer=layer,
        source_timeframe=tf,
        parent_range_id=parent_range_id,
    )
    if chart is not None and seed_coherent_with_active(ctx, chart.range_high, chart.range_low):
        return SeedResolutionResult(seed=chart, seed_source=SEED_SOURCE_ELECTRON)

    if discovery_mode:
        from detector.historical_range_chain import evaluate_bootstrap_candidates

        boot = evaluate_bootstrap_candidates(
            ctx.candles,
            ctx.active_index,
            break_rule=ctx.break_rule,
            period_start_ms=period_start_ms,
        )
        if boot.seed is not None:
            discovered = RangeSeedContext(
                range_high=float(boot.seed.range_high),
                range_low=float(boot.seed.range_low),
                active_range_id=None,
                is_manual_seed=False,
                seed_source=SEED_SOURCE_BOOTSTRAP,
                structure_layer=layer,
                source_timeframe=tf,
            )
            return SeedResolutionResult(seed=discovered, seed_source=SEED_SOURCE_BOOTSTRAP)

    return SeedResolutionResult(seed=None, seed_source=SEED_SOURCE_NONE)
