"""Detector V1 pipeline — runs all current-TF detectors."""

from __future__ import annotations

from dataclasses import dataclass, field

from detector.bos import detect_bos_suggestions
from detector.models import DetectionContext, SuggestionDraft
from detector.range_candidate import detect_range_suggestions
from detector.range_mode import (
    RANGE_MODE_DOCTRINE_V2,
    RANGE_MODE_SMOKE_V1,
    build_pipeline_seed_context,
    resolve_range_mode,
)
from detector.range_state import RangeSeedContext
from detector.range_v2 import detect_range_v2_suggestions
from detector.reclaim import detect_reclaim_suggestions
from detector.ref_candle import detect_ref_candle_suggestions
from detector.swing import detect_swing_suggestions
from detector.sweep import detect_sweep_suggestions
from detector.versions import DEFAULT_VERSIONS, RANGE_V1, RANGE_V2


@dataclass
class DetectionResult:
    context: DetectionContext
    drafts: list[SuggestionDraft] = field(default_factory=list)
    detector_versions: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_VERSIONS))
    range_mode: str = RANGE_MODE_SMOKE_V1

    def by_kind(self, kind: str) -> list[SuggestionDraft]:
        return [d for d in self.drafts if d.candidate_kind == kind]


def _resolve_pipeline_seed(ctx: DetectionContext) -> RangeSeedContext | None:
    if ctx.range_seed is not None and ctx.range_seed.is_valid():
        return ctx.range_seed
    return build_pipeline_seed_context(ctx)


def _range_drafts_for_mode(
    ctx: DetectionContext,
    *,
    mode: str,
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
        )
    return detect_range_suggestions(ctx)


def run_detector_v1(
    ctx: DetectionContext,
    *,
    range_mode: str | None = None,
) -> DetectionResult:
    """Run deterministic detectors for the active candle on one timeframe."""
    mode = resolve_range_mode(range_mode)
    versions = dict(DEFAULT_VERSIONS)
    if mode == RANGE_MODE_DOCTRINE_V2:
        versions["RANGE"] = RANGE_V2
    else:
        versions["RANGE"] = RANGE_V1

    drafts: list[SuggestionDraft] = []
    drafts.extend(detect_swing_suggestions(ctx))

    bos_drafts = detect_bos_suggestions(ctx)
    sweep_drafts = detect_sweep_suggestions(ctx)
    reclaim_drafts = detect_reclaim_suggestions(ctx)

    drafts.extend(_range_drafts_for_mode(ctx, mode=mode, bos_drafts=bos_drafts, reclaim_drafts=reclaim_drafts))
    drafts.extend(bos_drafts)
    drafts.extend(sweep_drafts)
    drafts.extend(reclaim_drafts)
    drafts.extend(detect_ref_candle_suggestions(ctx))

    return DetectionResult(
        context=ctx,
        drafts=drafts,
        detector_versions=versions,
        range_mode=mode,
    )
