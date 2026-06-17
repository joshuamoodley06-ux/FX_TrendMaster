"""Detector V1 pipeline — runs all current-TF detectors."""

from __future__ import annotations

from dataclasses import dataclass, field

from detector.bos import detect_bos_suggestions
from detector.models import DetectionContext, SuggestionDraft
from detector.range_candidate import detect_range_suggestions
from detector.reclaim import detect_reclaim_suggestions
from detector.ref_candle import detect_ref_candle_suggestions
from detector.swing import detect_swing_suggestions
from detector.sweep import detect_sweep_suggestions
from detector.versions import DEFAULT_VERSIONS


@dataclass
class DetectionResult:
    context: DetectionContext
    drafts: list[SuggestionDraft] = field(default_factory=list)
    detector_versions: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_VERSIONS))

    def by_kind(self, kind: str) -> list[SuggestionDraft]:
        return [d for d in self.drafts if d.candidate_kind == kind]


def run_detector_v1(ctx: DetectionContext) -> DetectionResult:
    """Run deterministic detectors for the active candle on one timeframe."""
    drafts: list[SuggestionDraft] = []
    drafts.extend(detect_swing_suggestions(ctx))
    drafts.extend(detect_range_suggestions(ctx))
    drafts.extend(detect_bos_suggestions(ctx))
    drafts.extend(detect_sweep_suggestions(ctx))
    drafts.extend(detect_reclaim_suggestions(ctx))
    drafts.extend(detect_ref_candle_suggestions(ctx))
    return DetectionResult(context=ctx, drafts=drafts)
