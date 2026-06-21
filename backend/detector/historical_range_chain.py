"""Historical candles-only range chain — bootstrap from OHLC, no map_ranges seed.

EXPERIMENTAL: not the trusted Weekly Research / Review Candidate baseline.
Use Review Candidate → Run Detector (RANGE_V2 replay) for known-good behavior.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Any

from detection_brain_store import new_uuid, utc_now_ms
from detector.context_window import build_detection_window_meta, ms_to_date_label
from detector.models import DetectionContext, NormalizedCandle, SuggestionDraft, SwingPoint
from detector.ohlc_loader import build_context, load_context_from_db, make_conn_candle_loader
from detector.pipeline import run_detector_v1
from detector.range_boundary import derive_boundaries
from detector.range_lifecycle import evaluate_lifecycle
from detector.range_mode import RANGE_MODE_DOCTRINE_V2, resolve_range_mode
from detector.range_scale_mode import (
    CANDIDATE_KIND_RANGE,
    RANGE_SCALE_UNKNOWN,
    resolve_range_scale_mode,
)
from detector.range_scan_runner import (
    HISTORICAL_RANGE_KINDS,
    ConfirmedStructureMutatedError,
    HistoricalRangeScanConfig,
    HistoricalRangeScanResult,
    _apply_candidate_filter,
    _index_bounds,
    _range_drafts_from_result,
    _supersede_pending_for_detection_run,
    _table_count,
)
from detector.range_seed import resolve_detector_seed_context, seed_resolution_to_meta
from detector.range_state import RangeSeedContext
from detector.swing import detect_swings
from detector.break_rules import breaches_high, breaches_low
from detector.writer import write_suggestion

DETECTION_MODE_HISTORICAL_CANDLES_ONLY = "historical_candles_only"
# Weekly replay steps only promote cycles that complete on the active bar (or prior week).
HISTORICAL_CHAIN_MAX_RECLAIM_LAG_BARS = 1
# Replay only recent bars per step — avoids scanning 400+ W1 candles every weekly step.
CHAIN_REPLAY_LOOKBACK_BARS = 104
# Reclaim older than this many bars before active week is an ancient cycle (not first formation).
BOOTSTRAP_MAX_ANCHOR_LAG_BARS = 26
BOOTSTRAP_TRACE_LIMIT = 10
WORKING_SOURCE_BOOTSTRAP = "bootstrap_candidate"
WORKING_SOURCE_PREVIOUS = "previous_range_candidate"
WORKING_SOURCE_MANUAL = "manual_seed_override"
WORKING_SOURCE_NONE = "none"


@dataclass
class HistoricalRangeChainConfig(HistoricalRangeScanConfig):
    """Candles-only historical chain; optional manual seed override for Advanced mode."""

    detection_mode: str = DETECTION_MODE_HISTORICAL_CANDLES_ONLY
    use_manual_seed: bool = False


@dataclass
class WorkingRangeContext:
    range_high: float
    range_low: float
    source: str
    chain_index: int = 0
    previous_suggestion_id: str | None = None


@dataclass
class HistoricalRangeChainResult(HistoricalRangeScanResult):
    chain_id: str = ""
    chain_candidates: int = 0
    bootstrap_step_index: int | None = None
    bootstrap_trace: BootstrapTraceReport | None = None


@dataclass
class ChainStepResult:
    drafts: list[SuggestionDraft]
    working_context: WorkingRangeContext | None = None
    bootstrap_used: bool = False


def _working_to_seed(working: WorkingRangeContext) -> RangeSeedContext:
    return RangeSeedContext(
        range_high=float(working.range_high),
        range_low=float(working.range_low),
        active_range_id=None,
        is_manual_seed=working.source == WORKING_SOURCE_MANUAL,
        seed_source=working.source,
        range_scale=RANGE_SCALE_UNKNOWN,
    )


@dataclass
class BootstrapCandidateRecord:
    """One bootstrap seed box evaluated at the first chain step."""

    candidate_index: int
    seed_rh: float
    seed_rl: float
    seed_rh_time: str | None = None
    seed_rl_time: str | None = None
    suggested_rh: float | None = None
    suggested_rl: float | None = None
    bos_time: str | None = None
    reclaim_time: str | None = None
    active_week: str | None = None
    freshness_score: float = 0.0
    price_coherence_score: float = 0.0
    anchor_score: float = 0.0
    composite_score: float = 0.0
    status: str = "REJECTED"
    selection_reason: str | None = None
    rejection_reason: str | None = None


@dataclass
class BootstrapTraceReport:
    active_week: str | None = None
    active_close: float | None = None
    period_start: str | None = None
    candidates_considered: int = 0
    candidates_traced: list[BootstrapCandidateRecord] = field(default_factory=list)
    selected: BootstrapCandidateRecord | None = None
    no_selection_reason: str | None = None


@dataclass
class BootstrapEvaluationResult:
    seed: RangeSeedContext | None = None
    trace: BootstrapTraceReport | None = None


def _candle_label(candles: list[NormalizedCandle], index: int | None) -> str | None:
    if index is None or index < 0 or index >= len(candles):
        return None
    c = candles[index]
    return c.time_raw or ms_to_date_label(c.time_ms)


def _freshness_score(active_index: int, reclaim_index: int, max_lag: int) -> float:
    lag = active_index - reclaim_index
    if lag < 0 or lag > max_lag:
        return 0.0
    if max_lag <= 0:
        return 1.0 if lag == 0 else 0.0
    return round(1.0 - (lag / max_lag), 4)


def _price_coherence_score(active_close: float, rh: float, rl: float, *, span_tolerance: float = 0.5) -> float:
    span = rh - rl
    if span <= 0:
        return 0.0
    pad = span * span_tolerance
    low_bound = rl - pad
    high_bound = rh + pad
    if low_bound <= active_close <= high_bound:
        return 1.0
    if active_close < low_bound:
        dist = low_bound - active_close
    else:
        dist = active_close - high_bound
    return round(max(0.0, 1.0 - (dist / span)), 4)


def _anchor_score(reclaim_index: int, active_index: int, *, max_anchor_lag_bars: int) -> float:
    """Reject reclaim cycles that completed long before the active replay week."""
    lag = active_index - reclaim_index
    if lag < 0:
        return 0.0
    if lag > max_anchor_lag_bars:
        return 0.0
    if max_anchor_lag_bars <= 0:
        return 1.0 if lag == 0 else 0.0
    return round(1.0 - (lag / max_anchor_lag_bars), 4)


def _composite_bootstrap_score(
    *,
    freshness: float,
    price_coherence: float,
    anchor: float,
) -> float:
    if freshness <= 0.0 or anchor <= 0.0:
        return 0.0
    return round((freshness * 0.45) + (price_coherence * 0.35) + (anchor * 0.20), 4)


def evaluate_bootstrap_candidates(
    candles: list[NormalizedCandle],
    active_index: int,
    *,
    break_rule: str,
    period_start_ms: int | None = None,
    trace_limit: int = BOOTSTRAP_TRACE_LIMIT,
) -> BootstrapEvaluationResult:
    """
    Evaluate bootstrap seed boxes; select by freshness + price coherence + anchor.
    Returns trace for the first `trace_limit` candidates considered.
    """
    window = candles[: active_index + 1]
    active = window[active_index] if window else None
    trace = BootstrapTraceReport(
        active_week=_candle_label(window, active_index),
        active_close=float(active.close) if active else None,
        period_start=ms_to_date_label(period_start_ms) if period_start_ms else None,
    )

    if active_index < 3 or not window:
        trace.no_selection_reason = "insufficient replay window"
        return BootstrapEvaluationResult(seed=None, trace=trace)

    swings = detect_swings(window)
    if not swings:
        trace.no_selection_reason = "no swings in replay window"
        return BootstrapEvaluationResult(seed=None, trace=trace)

    highs = [s for s in swings if s.kind == "SWING_HIGH"]
    lows = [s for s in swings if s.kind == "SWING_LOW"]
    if not highs or not lows:
        trace.no_selection_reason = "missing swing highs or lows"
        return BootstrapEvaluationResult(seed=None, trace=trace)

    eligible: list[tuple[float, BootstrapCandidateRecord, RangeSeedContext]] = []
    candidate_idx = 0

    for bos_idx in range(1, active_index + 1):
        candle = window[bos_idx]
        for sh in reversed([s for s in highs if s.index < bos_idx]):
            candidate_idx += 1
            prior_lows = [low for low in lows if low.index < sh.index and low.price < sh.price]
            record = BootstrapCandidateRecord(
                candidate_index=candidate_idx,
                seed_rh=float(sh.price),
                seed_rl=0.0,
                seed_rh_time=_candle_label(window, sh.index),
                active_week=trace.active_week,
            )

            if not breaches_high(candle.high, candle.close, float(sh.price), break_rule):
                record.rejection_reason = "no BOS break above swing high"
                if len(trace.candidates_traced) < trace_limit:
                    trace.candidates_traced.append(record)
                continue

            if not prior_lows:
                record.rejection_reason = "no prior swing low under swing high"
                if len(trace.candidates_traced) < trace_limit:
                    trace.candidates_traced.append(record)
                continue

            low = max(prior_lows, key=lambda item: item.index)
            record.seed_rl = float(low.price)
            record.seed_rl_time = _candle_label(window, low.index)

            seed = RangeSeedContext(
                range_high=float(sh.price),
                range_low=float(low.price),
                active_range_id=None,
                is_manual_seed=False,
                seed_source=WORKING_SOURCE_BOOTSTRAP,
            )

            lifecycle = evaluate_lifecycle(window, active_index, seed, break_rule=break_rule)
            if not lifecycle.can_suggest_range or lifecycle.chain is None:
                record.rejection_reason = lifecycle.reason_text or "lifecycle incomplete"
                if len(trace.candidates_traced) < trace_limit:
                    trace.candidates_traced.append(record)
                continue

            chain = lifecycle.chain
            if chain.bos_index < sh.index or chain.bos_index < low.index:
                record.rejection_reason = "BOS before seed swings formed"
                if len(trace.candidates_traced) < trace_limit:
                    trace.candidates_traced.append(record)
                continue

            reclaim_idx = int(chain.reclaim_index)
            record.bos_time = _candle_label(window, chain.bos_index)
            record.reclaim_time = _candle_label(window, reclaim_idx)

            freshness = _freshness_score(
                active_index,
                reclaim_idx,
                HISTORICAL_CHAIN_MAX_RECLAIM_LAG_BARS,
            )
            anchor = _anchor_score(
                reclaim_idx,
                active_index,
                max_anchor_lag_bars=BOOTSTRAP_MAX_ANCHOR_LAG_BARS,
            )
            record.freshness_score = freshness
            record.anchor_score = anchor

            if freshness <= 0.0:
                record.rejection_reason = (
                    f"stale reclaim: completed {active_index - reclaim_idx} bars before active week "
                    f"(max lag {HISTORICAL_CHAIN_MAX_RECLAIM_LAG_BARS})"
                )
                if len(trace.candidates_traced) < trace_limit:
                    trace.candidates_traced.append(record)
                continue

            if anchor <= 0.0:
                record.rejection_reason = (
                    f"ancient cycle: reclaim {active_index - reclaim_idx} bars before active week "
                    f"(max anchor {BOOTSTRAP_MAX_ANCHOR_LAG_BARS})"
                )
                if len(trace.candidates_traced) < trace_limit:
                    trace.candidates_traced.append(record)
                continue

            boundaries = derive_boundaries(lifecycle, swings, candles=window)
            if not boundaries.is_valid:
                record.rejection_reason = boundaries.reason_text or "unclear opposite swing"
                if len(trace.candidates_traced) < trace_limit:
                    trace.candidates_traced.append(record)
                continue

            record.suggested_rh = boundaries.suggested_rh
            record.suggested_rl = boundaries.suggested_rl
            active_close = float(active.close) if active else 0.0
            coherence_rh = float(boundaries.suggested_rh)  # type: ignore[arg-type]
            coherence_rl = float(boundaries.suggested_rl)  # type: ignore[arg-type]
            record.price_coherence_score = _price_coherence_score(
                active_close,
                coherence_rh,
                coherence_rl,
            )
            record.composite_score = _composite_bootstrap_score(
                freshness=freshness,
                price_coherence=record.price_coherence_score,
                anchor=anchor,
            )

            if record.composite_score <= 0.0:
                record.rejection_reason = "composite score zero after scoring"
                if len(trace.candidates_traced) < trace_limit:
                    trace.candidates_traced.append(record)
                continue

            record.status = "ELIGIBLE"
            eligible.append((record.composite_score, record, seed))
            if len(trace.candidates_traced) < trace_limit:
                trace.candidates_traced.append(record)

    trace.candidates_considered = candidate_idx

    if not eligible:
        trace.no_selection_reason = (
            "no bootstrap seed completed a fresh BOS→reclaim cycle near the active week"
        )
        return BootstrapEvaluationResult(seed=None, trace=trace)

    eligible.sort(key=lambda item: item[0], reverse=True)
    best_score, best_record, best_seed = eligible[0]
    best_record.status = "SELECTED"
    best_record.selection_reason = (
        f"highest composite score {best_score} "
        f"(freshness={best_record.freshness_score}, "
        f"price_coherence={best_record.price_coherence_score}, "
        f"anchor={best_record.anchor_score})"
    )
    trace.selected = best_record

    for score, record, _seed in eligible[1:]:
        record.rejection_reason = (
            f"lower composite score {record.composite_score} vs selected {best_score}"
        )

    return BootstrapEvaluationResult(seed=best_seed, trace=trace)


def format_bootstrap_trace_report(report: BootstrapTraceReport) -> str:
    lines = [
        "Historical Bootstrap Trace",
        f"  period_start:        {report.period_start or '—'}",
        f"  active_week:           {report.active_week or '—'}",
        f"  active_close:          {report.active_close if report.active_close is not None else '—'}",
        f"  candidates_considered: {report.candidates_considered}",
        "",
    ]
    if not report.candidates_traced:
        lines.append("  (no candidate boxes evaluated)")
    for rec in report.candidates_traced:
        lines.append(f"  --- candidate #{rec.candidate_index} [{rec.status}] ---")
        lines.append(f"    seed RH/RL:          {rec.seed_rh} / {rec.seed_rl}")
        lines.append(f"    seed RH time:        {rec.seed_rh_time or '—'}")
        lines.append(f"    seed RL time:        {rec.seed_rl_time or '—'}")
        if rec.suggested_rh is not None:
            lines.append(f"    suggested RH/RL:     {rec.suggested_rh} / {rec.suggested_rl}")
        lines.append(f"    BOS time:              {rec.bos_time or '—'}")
        lines.append(f"    reclaim time:          {rec.reclaim_time or '—'}")
        lines.append(f"    active week:           {rec.active_week or '—'}")
        lines.append(f"    freshness_score:       {rec.freshness_score}")
        lines.append(f"    price_coherence_score: {rec.price_coherence_score}")
        lines.append(f"    anchor_score:          {rec.anchor_score}")
        lines.append(f"    composite_score:       {rec.composite_score}")
        if rec.selection_reason:
            lines.append(f"    selection_reason:      {rec.selection_reason}")
        if rec.rejection_reason:
            lines.append(f"    rejection_reason:      {rec.rejection_reason}")
        lines.append("")
    lines.append("  --- final selection ---")
    if report.selected:
        sel = report.selected
        lines.append(f"    SELECTED candidate #{sel.candidate_index}")
        lines.append(f"    seed RH/RL:          {sel.seed_rh} / {sel.seed_rl}")
        if sel.suggested_rh is not None:
            lines.append(f"    suggested RH/RL:     {sel.suggested_rh} / {sel.suggested_rl}")
        lines.append(f"    reclaim time:        {sel.reclaim_time or '—'}")
        lines.append(f"    reason:              {sel.selection_reason or '—'}")
    else:
        lines.append(f"    NO SELECTION: {report.no_selection_reason or 'unknown'}")
    return "\n".join(lines)


def try_bootstrap_seed(
    candles: list[NormalizedCandle],
    active_index: int,
    *,
    break_rule: str,
    period_start_ms: int | None = None,
) -> RangeSeedContext | None:
    """Derive the first seed box from swing/break/reclaim sequence."""
    result = evaluate_bootstrap_candidates(
        candles,
        active_index,
        break_rule=break_rule,
        period_start_ms=period_start_ms,
    )
    return result.seed


def try_bootstrap_working_context(
    candles: list[NormalizedCandle],
    active_index: int,
    *,
    break_rule: str,
) -> WorkingRangeContext | None:
    """Backward-compatible alias — returns None; use try_bootstrap_seed + detector pass."""
    seed = try_bootstrap_seed(candles, active_index, break_rule=break_rule)
    if seed is None:
        return None
    return WorkingRangeContext(
        range_high=float(seed.range_high),
        range_low=float(seed.range_low),
        source=WORKING_SOURCE_BOOTSTRAP,
        chain_index=0,
    )


def _attach_chain_meta(
    draft: SuggestionDraft,
    *,
    chain_id: str,
    chain_index: int,
    detection_mode: str,
    bootstrap_used: bool,
    working_context_source: str,
    previous_chain_index: int | None,
    previous_candidate_id: str | None,
    first_candle_time_ms: int | None,
    last_candle_time_ms: int | None,
    candle_count_used: int,
    scan_step_index: int,
    scan_step_offset: int,
    detection_run_id: str,
    date_from_ms: int | None,
    date_to_ms: int | None,
) -> None:
    meta = dict(draft.meta_json or {})
    meta["historical_scan"] = True
    meta["historical_chain"] = True
    meta["chain_id"] = chain_id
    meta["chain_index"] = chain_index
    meta["detection_mode"] = detection_mode
    meta["bootstrap_used"] = bootstrap_used
    meta["working_context_source"] = working_context_source
    if previous_chain_index is not None:
        meta["previous_chain_index"] = previous_chain_index
    if previous_candidate_id:
        meta["previous_candidate_id"] = previous_candidate_id
    meta["detection_run_id"] = detection_run_id
    meta["scan_step_index"] = scan_step_index
    meta["scan_step_offset"] = scan_step_offset
    meta["date_from_ms"] = date_from_ms
    meta["date_to_ms"] = date_to_ms
    meta["first_candle_time_ms"] = first_candle_time_ms
    meta["last_candle_time_ms"] = last_candle_time_ms
    meta["candle_count_used"] = candle_count_used
    if first_candle_time_ms:
        meta["first_candle_time"] = ms_to_date_label(first_candle_time_ms)
    if last_candle_time_ms:
        meta["last_candle_time"] = ms_to_date_label(last_candle_time_ms)
    draft.meta_json = meta
    draft.candidate_index = scan_step_offset


def _inject_seed_into_ctx(
    ctx: DetectionContext,
    seed: RangeSeedContext,
    *,
    seed_meta: dict[str, Any] | None = None,
) -> None:
    ctx.range_seed = seed
    ctx.range_high = seed.range_high
    ctx.range_low = seed.range_low
    ctx.active_range_id = None
    meta = dict(seed_meta or {})
    meta["seed_source"] = seed.seed_source or WORKING_SOURCE_PREVIOUS
    meta["no_seed_context"] = False
    meta["seed_rh"] = seed.range_high
    meta["seed_rl"] = seed.range_low
    ctx.range_seed_meta = meta


def detect_historical_range_chain(
    candles: list[NormalizedCandle],
    *,
    symbol: str,
    source_timeframe: str,
    structure_layer: str,
    date_from_ms: int | None,
    date_to_ms: int | None,
    detection_run_id: str | None = None,
    range_mode: str = RANGE_MODE_DOCTRINE_V2,
    range_scale_mode: str = "generic",
    use_manual_seed: bool = False,
    manual_seed_resolver: Any | None = None,
    parent_range_id: int | None = None,
    candidate_kind_filter: str | None = None,
    max_steps: int | None = None,
) -> tuple[list[tuple[DetectionContext, list[SuggestionDraft], dict[str, Any]]], HistoricalRangeChainResult]:
    """
    Walk candles and build a self-feeding RANGE_V2 chain without map_ranges.
    Returns per-step (ctx, drafts, step_meta) and aggregate result stats.
    """
    symbol_u = str(symbol).upper()
    tf = str(source_timeframe).upper()
    layer = str(structure_layer).upper()
    run_id = detection_run_id or new_uuid()
    chain_id = new_uuid()
    range_mode_resolved = resolve_range_mode(range_mode)
    scale_mode = resolve_range_scale_mode(range_scale_mode)

    start_idx, end_idx = _index_bounds(candles, date_from_ms=date_from_ms, date_to_ms=date_to_ms)
    if max_steps is not None:
        end_idx = min(end_idx, start_idx + max(0, int(max_steps) - 1))

    working: WorkingRangeContext | None = None
    manual_seed: RangeSeedContext | None = None
    manual_seed_meta: dict[str, Any] | None = None
    if use_manual_seed and manual_seed_resolver is not None:
        resolution = manual_seed_resolver()
        if resolution is not None and getattr(resolution, "seed", None) is not None:
            manual_seed = resolution.seed
            manual_seed_meta = seed_resolution_to_meta(resolution)

    steps: list[tuple[DetectionContext, list[SuggestionDraft], dict[str, Any]]] = []
    range_candidate_count = 0
    no_valid_range_count = 0
    chain_candidates = 0
    bootstrap_step_index: int | None = None
    bootstrap_trace: BootstrapTraceReport | None = None
    previous_candidate_id: str | None = None
    first_ms = candles[start_idx].time_ms if candles and start_idx < len(candles) else None
    last_ms = candles[end_idx].time_ms if candles and end_idx >= 0 else None
    slice_start = max(0, start_idx - CHAIN_REPLAY_LOOKBACK_BARS)

    for idx in range(start_idx, end_idx + 1):
        window = candles[slice_start : idx + 1]
        if not window:
            continue
        active_index = len(window) - 1
        replay_ms = candles[idx].time_ms
        ctx = build_context(
            symbol=symbol_u,
            source_timeframe=tf,
            structure_layer=layer,
            candles=window,
            active_index=active_index,
            replay_until_time_ms=replay_ms,
            visible_from_time_ms=None,
            detection_run_id=run_id,
            parent_range_id=parent_range_id,
            range_scale=RANGE_SCALE_UNKNOWN,
        )

        bootstrap_used = False
        working_source = WORKING_SOURCE_NONE
        seed_for_step: RangeSeedContext | None = None
        seed_meta_for_step: dict[str, Any] | None = None

        if working is not None:
            seed_for_step = _working_to_seed(working)
            working_source = working.source
            seed_meta_for_step = {
                "seed_source": working.source,
                "no_seed_context": False,
                "seed_rh": working.range_high,
                "seed_rl": working.range_low,
            }
        elif use_manual_seed and manual_seed is not None:
            seed_for_step = manual_seed
            seed_meta_for_step = manual_seed_meta
            working_source = WORKING_SOURCE_MANUAL
            working = WorkingRangeContext(
                range_high=float(manual_seed.range_high),
                range_low=float(manual_seed.range_low),
                source=WORKING_SOURCE_MANUAL,
                chain_index=0,
            )
        else:
            boot_eval = evaluate_bootstrap_candidates(
                window,
                active_index,
                break_rule=ctx.break_rule,
                period_start_ms=date_from_ms,
            )
            if bootstrap_trace is None:
                bootstrap_trace = boot_eval.trace
            boot_seed = boot_eval.seed
            if boot_seed is not None:
                bootstrap_used = True
                bootstrap_step_index = idx if bootstrap_step_index is None else bootstrap_step_index
                seed_for_step = boot_seed
                working_source = WORKING_SOURCE_BOOTSTRAP
                seed_meta_for_step = {
                    "seed_source": WORKING_SOURCE_BOOTSTRAP,
                    "no_seed_context": False,
                    "seed_rh": boot_seed.range_high,
                    "seed_rl": boot_seed.range_low,
                }

        if seed_for_step is not None:
            _inject_seed_into_ctx(ctx, seed_for_step, seed_meta=seed_meta_for_step)
        else:
            ctx.range_seed_meta = {
                "seed_source": "none",
                "no_seed_context": True,
            }

        ctx.detection_window_meta = build_detection_window_meta(ctx, detection_run_id=run_id)
        ctx.detection_window_meta["historical_scan"] = True
        ctx.detection_window_meta["historical_chain"] = True
        ctx.detection_window_meta["detection_mode"] = DETECTION_MODE_HISTORICAL_CANDLES_ONLY
        ctx.detection_window_meta["max_reclaim_lag_bars"] = HISTORICAL_CHAIN_MAX_RECLAIM_LAG_BARS

        result = run_detector_v1(ctx, range_mode=range_mode_resolved, scale_mode=scale_mode)
        range_drafts = _apply_candidate_filter(
            _range_drafts_from_result(result.drafts),
            candidate_kind_filter=candidate_kind_filter,
        )
        if not range_drafts:
            continue

        step_offset = idx - start_idx
        chain_index = working.chain_index if working else 0
        prev_chain_index = chain_index - 1 if chain_index > 0 else None

        for draft in range_drafts:
            kind = str(draft.candidate_kind or "").upper()
            if kind == "RANGE_CANDIDATE":
                range_candidate_count += 1
                if draft.suggested_rh is not None and draft.suggested_rl is not None:
                    new_rh = float(draft.suggested_rh)
                    new_rl = float(draft.suggested_rl)
                    if working is None or (
                        abs(new_rh - working.range_high) > 1e-9
                        or abs(new_rl - working.range_low) > 1e-9
                    ):
                        prev_idx = working.chain_index if working else 0
                        working = WorkingRangeContext(
                            range_high=new_rh,
                            range_low=new_rl,
                            source=WORKING_SOURCE_PREVIOUS,
                            chain_index=prev_idx + 1,
                            previous_suggestion_id=previous_candidate_id,
                        )
                        chain_index = working.chain_index
                        chain_candidates += 1
            elif kind == "NO_VALID_RANGE":
                no_valid_range_count += 1

            _attach_chain_meta(
                draft,
                chain_id=chain_id,
                chain_index=chain_index,
                detection_mode=DETECTION_MODE_HISTORICAL_CANDLES_ONLY,
                bootstrap_used=bootstrap_used,
                working_context_source=working_source,
                previous_chain_index=prev_chain_index,
                previous_candidate_id=previous_candidate_id,
                first_candle_time_ms=first_ms,
                last_candle_time_ms=last_ms,
                candle_count_used=len(window),
                scan_step_index=idx,
                scan_step_offset=step_offset,
                detection_run_id=run_id,
                date_from_ms=date_from_ms,
                date_to_ms=date_to_ms,
            )

        step_meta = {
            "bootstrap_used": bootstrap_used,
            "working_context_source": working_source,
            "chain_index": chain_index,
        }
        steps.append((ctx, range_drafts, step_meta))

        for draft in range_drafts:
            if str(draft.candidate_kind or "").upper() == "RANGE_CANDIDATE":
                meta = draft.meta_json or {}
                sid = meta.get("suggestion_id")
                if sid:
                    previous_candidate_id = str(sid)

    aggregate = HistoricalRangeChainResult(
        symbol=symbol_u,
        source_timeframe=tf,
        structure_layer=layer,
        date_from_ms=date_from_ms,
        date_to_ms=date_to_ms,
        detection_run_id=run_id,
        candles_scanned=len(steps),
        suggestions_created=0,
        range_candidate_count=range_candidate_count,
        no_valid_range_count=no_valid_range_count,
        chain_id=chain_id,
        chain_candidates=chain_candidates,
        bootstrap_step_index=bootstrap_step_index,
        bootstrap_trace=bootstrap_trace,
    )
    return steps, aggregate


def run_historical_range_chain(
    conn: sqlite3.Connection,
    config: HistoricalRangeChainConfig,
    *,
    candles: list[NormalizedCandle] | None = None,
) -> HistoricalRangeChainResult:
    """Persist candles-only historical chain suggestions; never mutates map_ranges."""
    symbol = str(config.symbol).upper()
    tf = str(config.source_timeframe).upper()
    layer = str(config.structure_layer).upper()
    run_id = config.detection_run_id or new_uuid()

    map_ranges_before = _table_count(conn, "map_ranges")
    map_events_before = _table_count(conn, "map_events")

    if candles is None:
        ctx_boot = load_context_from_db(
            symbol=symbol,
            source_timeframe=tf,
            structure_layer=layer,
            replay_until_time_ms=config.date_to_ms,
            visible_from_time_ms=None,
            limit=config.candle_limit,
            parent_range_id=config.parent_range_id,
            range_scale=RANGE_SCALE_UNKNOWN,
            detection_run_id=run_id,
            loader=make_conn_candle_loader(conn),
        )
        candles = ctx_boot.candles

    def _manual_resolver():
        if not config.use_manual_seed:
            return None
        return resolve_detector_seed_context(
            conn,
            {},
            symbol=symbol,
            structure_layer=layer,
            source_timeframe=tf,
            parent_range_id=config.parent_range_id,
        )

    steps, aggregate = detect_historical_range_chain(
        candles,
        symbol=symbol,
        source_timeframe=tf,
        structure_layer=layer,
        date_from_ms=config.date_from_ms,
        date_to_ms=config.date_to_ms,
        detection_run_id=run_id,
        range_mode=config.range_mode,
        range_scale_mode=config.range_scale_mode,
        use_manual_seed=config.use_manual_seed,
        manual_seed_resolver=_manual_resolver,
        parent_range_id=config.parent_range_id,
        candidate_kind_filter=config.candidate_kind_filter,
        max_steps=config.max_steps,
    )

    superseded_count = 0
    if not config.dry_run:
        superseded_count = _supersede_pending_for_detection_run(
            conn,
            detection_run_id=run_id,
            symbol=symbol,
            structure_layer=layer,
            source_timeframe=tf,
        )

    saved_rows: list[dict[str, Any]] = []
    first_suggestion_ms: int | None = None
    last_suggestion_ms: int | None = None
    previous_candidate_id: str | None = None

    for ctx, drafts, _step_meta in steps:
        for draft in drafts:
            if config.dry_run:
                continue
            saved = write_suggestion(conn, draft, ctx, supersede_on_conflict=True)
            saved_rows.append(saved)
            sid = str(saved.get("suggestion_id") or "")
            if sid and str(draft.candidate_kind or "").upper() == "RANGE_CANDIDATE":
                meta = dict(draft.meta_json or {})
                meta["suggestion_id"] = sid
                if previous_candidate_id:
                    meta["previous_candidate_id"] = previous_candidate_id
                draft.meta_json = meta
                previous_candidate_id = sid
            t_ms = int(saved.get("candle_time_utc_ms") or ctx.active_candle.time_ms if ctx.active_candle else 0)
            if first_suggestion_ms is None or t_ms < first_suggestion_ms:
                first_suggestion_ms = t_ms
            if last_suggestion_ms is None or t_ms > last_suggestion_ms:
                last_suggestion_ms = t_ms

    if not config.dry_run:
        conn.commit()

    map_ranges_after = _table_count(conn, "map_ranges")
    map_events_after = _table_count(conn, "map_events")
    if map_ranges_before != map_ranges_after or map_events_before != map_events_after:
        raise ConfirmedStructureMutatedError(
            f"confirmed structure mutated: map_ranges {map_ranges_before}->{map_ranges_after}, "
            f"map_events {map_events_before}->{map_events_after}"
        )

    aggregate.detection_run_id = run_id
    aggregate.dry_run = config.dry_run
    aggregate.superseded_count = superseded_count
    aggregate.suggestions_created = len(saved_rows)
    aggregate.saved_rows = saved_rows
    aggregate.first_suggestion_time_ms = first_suggestion_ms
    aggregate.last_suggestion_time_ms = last_suggestion_ms
    aggregate.map_ranges_before = map_ranges_before
    aggregate.map_ranges_after = map_ranges_after
    aggregate.map_events_before = map_events_before
    aggregate.map_events_after = map_events_after
    return aggregate


def format_chain_summary(result: HistoricalRangeChainResult) -> str:
    lines = [
        "Historical Range Chain Summary",
        f"  symbol:              {result.symbol}",
        f"  timeframe:           {result.source_timeframe}",
        f"  layer:               {result.structure_layer}",
        f"  date_from:           {ms_to_date_label(result.date_from_ms) or '—'}",
        f"  date_to:             {ms_to_date_label(result.date_to_ms) or '—'}",
        f"  detection_run_id:    {result.detection_run_id}",
        f"  chain_id:            {result.chain_id}",
        f"  dry_run:             {result.dry_run}",
        f"  candles_scanned:     {result.candles_scanned}",
        f"  suggestions_created: {result.suggestions_created}",
        f"  RANGE_CANDIDATE:     {result.range_candidate_count}",
        f"  chain_candidates:    {result.chain_candidates}",
        f"  NO_VALID_RANGE:      {result.no_valid_range_count}",
        f"  bootstrap_step:      {result.bootstrap_step_index if result.bootstrap_step_index is not None else '—'}",
        f"  map_ranges:          {result.map_ranges_before} (unchanged)",
        f"  map_events:          {result.map_events_before} (unchanged)",
    ]
    if result.bootstrap_trace is not None:
        lines.append("")
        lines.append(format_bootstrap_trace_report(result.bootstrap_trace))
    return "\n".join(lines)
