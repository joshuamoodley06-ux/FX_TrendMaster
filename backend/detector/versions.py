"""Detector version constants (Phase 0 contract §3)."""

from __future__ import annotations

ENGINE_SOURCE = "python_detector"

SWING_V1 = "SWING_V1"
RANGE_V1 = "RANGE_V1"
BOS_V1 = "BOS_V1"
SWEEP_V1 = "SWEEP_V1"
RECLAIM_V1 = "RECLAIM_V1"
REF_CANDLE_V1 = "REF_CANDLE_V1"

DEFAULT_VERSIONS: dict[str, str] = {
    "SWING": SWING_V1,
    "RANGE": RANGE_V1,
    "BOS": BOS_V1,
    "SWEEP": SWEEP_V1,
    "RECLAIM": RECLAIM_V1,
    "REF_CANDLE": REF_CANDLE_V1,
}
