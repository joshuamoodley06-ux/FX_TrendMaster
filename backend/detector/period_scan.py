"""Date-period detector scan — multiple generic range candidates, no auto-promotion."""

from __future__ import annotations

from dataclasses import replace

from detector.bos import detect_bos_suggestions
from detector.models import DetectionContext, SuggestionDraft
from detector.range_candidate import detect_range_suggestions
from detector.range_mode import RANGE_MODE_DOCTRINE_V2, resolve_range_mode, build_pipeline_seed_context
from detector.range_scale_mode import CANDIDATE_KIND_RANGE, GENERIC_RANGE_KINDS, resolve_range_scale_mode
from detector.range_v2 import detect_range_v2_suggestions
from detector.reclaim import detect_reclaim_suggestions
from detector.swing import detect_swing_suggestions
from detector.versions import DEFAULT_VERSIONS, RANGE_V1, RANGE_V2


def _resolve_pipeline_seed(ctx: DetectionContext):
    if ctx.range_seed is not None and ctx.range_seed.is_valid():
        return ctx.range_seed
    return build_pipeline_seed_context(ctx)


def _range_drafts_at_index(
    ctx: DetectionContext,
    *,
    mode: str,
    scale: str,
    bos_drafts: list[SuggestionDraft],
    reclaim_drafts: list[SuggestionDraft],
) -> list[SuggestionDraft]:
    if mode == RANGE_MODE_DOCTRINE_V2:
        seed = _resolve_pipeline_seed(ctx)
        return detect_range_v2_suggestions(
            ctx,
            seed,
            bos_drafts,
            reclaim_drafts,
            ctx.swings or [],
            strict_seed=True,
            scale_mode=scale,
        )
    return detect_range_suggestions(ctx, scale_mode=scale)


def _index_bounds(
    ctx: DetectionContext,
    *,
    date_from_ms: int | None,
    date_to_ms: int | None,
) -> tuple[int, int]:
    candles = ctx.candles
    if not candles:
        return 0, 0
    start = 0
    end = len(candles) - 1
    if date_from_ms is not None and date_from_ms > 0:
        for i, c in enumerate(candles):
            if c.time_ms >= date_from_ms:
                start = i
                break
    if date_to_ms is not None and date_to_ms > 0:
        for i in range(len(candles) - 1, -1, -1):
            if candles[i].time_ms <= date_to_ms:
                end = i
                break
    if start > end:
        return end, end
    return start, end


def _range_dedupe_key(draft: SuggestionDraft) -> tuple[float | None, float | None, int]:
    return (
        round(float(draft.suggested_rh), 4) if draft.suggested_rh is not None else None,
        round(float(draft.suggested_rl), 4) if draft.suggested_rl is not None else None,
        int(draft.candle_index),
    )


def collect_period_range_candidates(
    base_ctx: DetectionContext,
    *,
    date_from_ms: int | None,
    date_to_ms: int | None,
    range_mode: str | None = None,
    scale_mode: str | None = None,
) -> list[SuggestionDraft]:
    """
    Scan active_index from date_from → date_to and collect unique range suggestions.
    Suggestions only — no promotion.
    """
    mode = resolve_range_mode(range_mode)
    scale = resolve_range_scale_mode(scale_mode)
    start, end = _index_bounds(base_ctx, date_from_ms=date_from_ms, date_to_ms=date_to_ms)

    collected: list[SuggestionDraft] = []
    seen: set[tuple[float | None, float | None, int]] = set()
    candidate_index = 0

    for idx in range(start, end + 1):
        sub = replace(
            base_ctx,
            active_index=idx,
            replay_until_time_ms=base_ctx.candles[idx].time_ms,
        )
        bos_drafts = detect_bos_suggestions(sub)
        reclaim_drafts = detect_reclaim_suggestions(sub)
        range_drafts = _range_drafts_at_index(
            sub,
            mode=mode,
            scale=scale,
            bos_drafts=bos_drafts,
            reclaim_drafts=reclaim_drafts,
        )
        for draft in range_drafts:
            if draft.candidate_kind not in GENERIC_RANGE_KINDS and draft.candidate_kind != CANDIDATE_KIND_RANGE:
                if draft.candidate_kind not in {"RANGE_MAJOR", "RANGE_MINOR"}:
                    continue
            key = _range_dedupe_key(draft)
            if key in seen:
                continue
            seen.add(key)
            draft.candidate_index = candidate_index
            candidate_index += 1
            meta = dict(draft.meta_json or {})
            meta["period_scan_index"] = idx
            meta["period_scan_from_ms"] = date_from_ms
            meta["period_scan_to_ms"] = date_to_ms
            draft.meta_json = meta
            collected.append(draft)

    return collected


def run_detector_period_scan(
    ctx: DetectionContext,
    *,
    date_from_ms: int | None,
    date_to_ms: int | None,
    range_mode: str | None = None,
    scale_mode: str | None = None,
):
    """Run non-range detectors at period end; collect range candidates across window."""
    from detector.pipeline import DetectionResult
    from detector.ref_candle import detect_ref_candle_suggestions
    from detector.sweep import detect_sweep_suggestions
    mode = resolve_range_mode(range_mode)
    scale = resolve_range_scale_mode(scale_mode)
    versions = dict(DEFAULT_VERSIONS)
    versions["RANGE"] = RANGE_V2 if mode == "doctrine_v2" else RANGE_V1

    start, end = _index_bounds(ctx, date_from_ms=date_from_ms, date_to_ms=date_to_ms)
    end_ctx = replace(
        ctx,
        active_index=end,
        replay_until_time_ms=ctx.candles[end].time_ms if ctx.candles else ctx.replay_until_time_ms,
    )

    drafts: list[SuggestionDraft] = []
    drafts.extend(detect_swing_suggestions(end_ctx))

    bos_drafts = detect_bos_suggestions(end_ctx)
    reclaim_drafts = detect_reclaim_suggestions(end_ctx)

    range_drafts = collect_period_range_candidates(
        ctx,
        date_from_ms=date_from_ms,
        date_to_ms=date_to_ms,
        range_mode=mode,
        scale_mode=scale,
    )
    drafts.extend(range_drafts)
    drafts.extend(bos_drafts)
    drafts.extend(reclaim_drafts)
    drafts.extend(detect_sweep_suggestions(end_ctx))
    drafts.extend(detect_ref_candle_suggestions(end_ctx))

    return DetectionResult(
        context=end_ctx,
        drafts=drafts,
        detector_versions=versions,
        range_mode=mode,
        range_scale_mode=scale,
        period_scan=True,
    )
