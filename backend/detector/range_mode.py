"""DETECTOR_RANGE_MODE flag parsing and pipeline seed context (Phase D)."""

from __future__ import annotations

import os
import warnings

from detector.models import DetectionContext
from detector.range_state import RangeSeedContext

RANGE_MODE_SMOKE_V1 = "smoke_v1"
RANGE_MODE_DOCTRINE_V2 = "doctrine_v2"
DEFAULT_RANGE_MODE = RANGE_MODE_SMOKE_V1
VALID_RANGE_MODES = frozenset({RANGE_MODE_SMOKE_V1, RANGE_MODE_DOCTRINE_V2})


def resolve_range_mode(override: str | None = None) -> str:
    """
    Resolve detector range mode from explicit override or DETECTOR_RANGE_MODE env.

    Unknown values default to smoke_v1 with a RuntimeWarning (safe default).
    """
    raw = (override or os.environ.get("DETECTOR_RANGE_MODE") or DEFAULT_RANGE_MODE).strip().lower()
    if raw in VALID_RANGE_MODES:
        return raw
    warnings.warn(
        f"Unknown DETECTOR_RANGE_MODE={raw!r}; defaulting to {DEFAULT_RANGE_MODE!r}",
        RuntimeWarning,
        stacklevel=2,
    )
    return DEFAULT_RANGE_MODE


def build_pipeline_seed_context(ctx: DetectionContext) -> RangeSeedContext | None:
    """
    Build RANGE_V2 seed from pipeline context only — never invent anchors.

    Phase D requires confirmed active range id plus RH/RL on context.
    """
    if not ctx.has_range():
        return None
    active_id = ctx.active_range_id
    if active_id in (None, "", 0):
        return None
    return RangeSeedContext(
        range_high=float(ctx.range_high),  # type: ignore[arg-type]
        range_low=float(ctx.range_low),  # type: ignore[arg-type]
        active_range_id=int(active_id),
        is_manual_seed=False,
    )
