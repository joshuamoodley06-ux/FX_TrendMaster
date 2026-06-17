"""Derived range analytics classification (not manual mapping truth).

Review confirms RANGE_CANDIDATE validity only (range_scale stays UNKNOWN).
This module derives structural role labels from confirmed ranges + behavior.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Analytics-only labels — never written to map_ranges.range_scale on user confirm.
DERIVED_MAJOR = "DERIVED_MAJOR"
DERIVED_MINOR = "DERIVED_MINOR"
TRANSITION_RANGE = "TRANSITION_RANGE"
EXPANSION_LEG = "EXPANSION_LEG"
DERIVED_UNKNOWN = "DERIVED_UNKNOWN"

DERIVED_RANGE_LABELS = frozenset(
    {DERIVED_MAJOR, DERIVED_MINOR, TRANSITION_RANGE, EXPANSION_LEG, DERIVED_UNKNOWN}
)


@dataclass
class RangeAnalyticsInput:
    """Inputs for derived classification (read-only analytics)."""

    range_id: int | None = None
    symbol: str = ""
    structure_layer: str = ""
    source_timeframe: str = ""
    range_high: float | None = None
    range_low: float | None = None
    parent_range_id: int | None = None
    duration_bars: int | None = None
    width_points: float | None = None
    contains_range_ids: list[int] = field(default_factory=list)
    contained_by_range_id: int | None = None
    bos_reclaim_events: list[dict[str, Any]] = field(default_factory=list)
    retracement_pct: float | None = None
    confirmed_from_suggestion_id: str | None = None


@dataclass
class RangeAnalyticsClassification:
    derived_label: str = DERIVED_UNKNOWN
    confidence: str = "LOW"
    reason_text: str = "Classifier not implemented"
    signals: dict[str, Any] = field(default_factory=dict)


def classify_range_analytics(
    inputs: RangeAnalyticsInput,
    *,
    peer_ranges: list[RangeAnalyticsInput] | None = None,
) -> RangeAnalyticsClassification:
    """
    Derive analytics label from containment, duration, width, hierarchy,
    BOS/reclaim behavior, and retracement.

    Not implemented — returns DERIVED_UNKNOWN until analytics pipeline is built.
    """
    _ = peer_ranges
    return RangeAnalyticsClassification(
        derived_label=DERIVED_UNKNOWN,
        confidence="LOW",
        reason_text="Analytics classifier pending — inputs captured only",
        signals={
            "range_id": inputs.range_id,
            "width_points": inputs.width_points,
            "duration_bars": inputs.duration_bars,
            "parent_range_id": inputs.parent_range_id,
            "contains_count": len(inputs.contains_range_ids),
            "retracement_pct": inputs.retracement_pct,
        },
    )
