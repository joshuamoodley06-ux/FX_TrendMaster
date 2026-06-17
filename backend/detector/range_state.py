"""RANGE_V2 lifecycle state types (Phase A — no pipeline hook)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RangeLifecycleState(str, Enum):
    NO_VALID_RANGE = "NO_VALID_RANGE"
    SEEDED = "SEEDED"
    ACTIVE_RANGE = "ACTIVE_RANGE"
    BREACHED_UP = "BREACHED_UP"
    BREACHED_DOWN = "BREACHED_DOWN"
    RECLAIMED_UP = "RECLAIMED_UP"
    RECLAIMED_DOWN = "RECLAIMED_DOWN"
    REBASED = "REBASED"
    ABANDONED = "ABANDONED"


class NoRangeReason(str, Enum):
    NO_SEED_OR_ACTIVE_RANGE = "NO_SEED_OR_ACTIVE_RANGE"
    SEED_ONLY_NO_BOS = "SEED_ONLY_NO_BOS"
    BOS_WITHOUT_RECLAIM = "BOS_WITHOUT_RECLAIM"
    UNRESOLVED_TRANSITION = "UNRESOLVED_TRANSITION"
    NO_LINKED_OPPOSITE_SWING = "NO_LINKED_OPPOSITE_SWING"
    UNCLEAR_OPPOSITE_SWING = "UNCLEAR_OPPOSITE_SWING"
    RANGE_ABANDONED = "RANGE_ABANDONED"


class BrokenBoundary(str, Enum):
    HIGH = "HIGH"
    LOW = "LOW"


class BosDirection(str, Enum):
    UP = "UP"
    DOWN = "DOWN"


class OppositeSwingReason(str, Enum):
    OPPOSITE_SWING_BETWEEN_BOS_RECLAIM = "OPPOSITE_SWING_BETWEEN_BOS_RECLAIM"
    LAST_OPPOSITE_SWING_BEFORE_BOS = "LAST_OPPOSITE_SWING_BEFORE_BOS"
    UNCLEAR_OPPOSITE_SWING = "UNCLEAR_OPPOSITE_SWING"


@dataclass(frozen=True)
class RangeSeedContext:
    """Manual seed or confirmed active range — never swing-pair invented."""

    range_high: float
    range_low: float
    active_range_id: int | None = None
    is_manual_seed: bool = False
    range_scale: str | None = None
    range_role: str | None = None
    parent_range_id: int | None = None
    structure_layer: str | None = None
    source_timeframe: str | None = None
    status: str | None = None
    seed_source: str | None = None

    def is_valid(self) -> bool:
        return self.range_high > self.range_low


@dataclass(frozen=True)
class BosReclaimChain:
    """Completed BOS → reclaim cycle within one active range."""

    direction: BosDirection
    bos_index: int
    bos_boundary_price: float
    reclaim_index: int
    broken_boundary: BrokenBoundary
    old_range_high: float
    old_range_low: float


@dataclass
class LifecycleEvaluation:
    state: RangeLifecycleState
    chain: BosReclaimChain | None = None
    no_range_reason: NoRangeReason | None = None
    reason_text: str = ""

    @property
    def can_suggest_range(self) -> bool:
        return self.state in {
            RangeLifecycleState.RECLAIMED_UP,
            RangeLifecycleState.RECLAIMED_DOWN,
            RangeLifecycleState.REBASED,
        } and self.chain is not None


@dataclass
class BoundarySelection:
    suggested_rh: float | None = None
    suggested_rl: float | None = None
    opposite_swing_index: int | None = None
    opposite_swing_kind: str | None = None
    opposite_swing_price: float | None = None
    boundary_selection_reason: str = ""
    confidence: str = "MEDIUM"
    no_range_reason: NoRangeReason | None = None
    reason_text: str = ""

    @property
    def is_valid(self) -> bool:
        return (
            self.suggested_rh is not None
            and self.suggested_rl is not None
            and self.suggested_rh > self.suggested_rl
            and self.no_range_reason is None
        )
