"""DETECTOR_RANGE_SCALE_MODE — generic vs legacy major/minor classification."""

from __future__ import annotations

import os
import warnings

RANGE_SCALE_MODE_GENERIC = "generic"
RANGE_SCALE_MODE_LEGACY = "legacy"
DEFAULT_RANGE_SCALE_MODE = RANGE_SCALE_MODE_GENERIC
VALID_RANGE_SCALE_MODES = frozenset({RANGE_SCALE_MODE_GENERIC, RANGE_SCALE_MODE_LEGACY})

CANDIDATE_KIND_RANGE = "RANGE_CANDIDATE"
RANGE_SCALE_UNKNOWN = "UNKNOWN"

LEGACY_RANGE_KINDS = frozenset({"RANGE_MAJOR", "RANGE_MINOR"})
GENERIC_RANGE_KINDS = frozenset({CANDIDATE_KIND_RANGE})
ALL_RANGE_KINDS = LEGACY_RANGE_KINDS | GENERIC_RANGE_KINDS | frozenset(
    {"NO_VALID_RANGE", "NO_MINOR_STRUCTURE", "NO_MAJOR_STRUCTURE"}
)


def resolve_range_scale_mode(override: str | None = None) -> str:
    """
    Resolve scale mode from override or DETECTOR_RANGE_SCALE_MODE env.

    generic (default): emit RANGE_CANDIDATE with range_scale UNKNOWN.
    legacy: preserve RANGE_MAJOR / RANGE_MINOR classification (deprecated).
    """
    raw = (
        override
        or os.environ.get("DETECTOR_RANGE_SCALE_MODE")
        or DEFAULT_RANGE_SCALE_MODE
    ).strip().lower()
    if raw in VALID_RANGE_SCALE_MODES:
        return raw
    warnings.warn(
        f"Unknown DETECTOR_RANGE_SCALE_MODE={raw!r}; defaulting to {DEFAULT_RANGE_SCALE_MODE!r}",
        RuntimeWarning,
        stacklevel=2,
    )
    return DEFAULT_RANGE_SCALE_MODE


def is_generic_scale_mode(mode: str | None = None) -> bool:
    return resolve_range_scale_mode(mode) == RANGE_SCALE_MODE_GENERIC


def is_range_candidate_kind(kind: str | None) -> bool:
    k = str(kind or "").upper()
    return k in ALL_RANGE_KINDS or k.startswith("RANGE_")
