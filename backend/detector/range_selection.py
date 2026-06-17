"""Swing-pair range candidate enumeration and MAJOR/MINOR selection (RANGE_V1)."""

from __future__ import annotations

from dataclasses import dataclass

from detector.models import SwingPoint


@dataclass(frozen=True)
class SwingRangeCandidate:
    swing_high: SwingPoint
    swing_low: SwingPoint

    @property
    def rh(self) -> float:
        return self.swing_high.price

    @property
    def rl(self) -> float:
        return self.swing_low.price

    @property
    def span(self) -> float:
        return self.rh - self.rl

    @property
    def anchor_index(self) -> int:
        return max(self.swing_high.index, self.swing_low.index)

    def engulfs_price(self, price: float) -> bool:
        return self.rl <= price <= self.rh

    def strictly_contains(self, other: SwingRangeCandidate) -> bool:
        """True when *other* is a narrower range fully inside this container."""
        if other.anchor_index > self.anchor_index:
            return False
        return self.rh >= other.rh and self.rl <= other.rl and self.span > other.span


def enumerate_swing_range_candidates(
    swings: list[SwingPoint],
    *,
    active_index: int,
) -> list[SwingRangeCandidate]:
    highs = [s for s in swings if s.kind == "SWING_HIGH" and s.index <= active_index]
    lows = [s for s in swings if s.kind == "SWING_LOW" and s.index <= active_index]
    out: list[SwingRangeCandidate] = []
    for high in highs:
        for low in lows:
            if high.price <= low.price:
                continue
            candidate = SwingRangeCandidate(swing_high=high, swing_low=low)
            if candidate.anchor_index > active_index:
                continue
            out.append(candidate)
    return out


def _is_major_eligible(candidate: SwingRangeCandidate, pool: list[SwingRangeCandidate]) -> bool:
    """
    MAJOR must contain at least one strictly narrower valid range inside.
    Degenerate charts: widest top-level container (not nested inside another) qualifies.
    """
    has_inner = any(candidate.strictly_contains(inner) for inner in pool if inner is not candidate)
    if has_inner:
        return True
    nested_inside_other = any(
        other.strictly_contains(candidate) for other in pool if other is not candidate
    )
    if nested_inside_other:
        return False
    max_span = max(c.span for c in pool)
    return candidate.span == max_span


def _outermost_key(candidate: SwingRangeCandidate) -> tuple[float, float, float]:
    return (candidate.span, candidate.rh, -candidate.rl)


def _innermost_key(candidate: SwingRangeCandidate) -> tuple[float, int]:
    return (candidate.span, candidate.anchor_index)


def _candidate_debug_row(candidate: SwingRangeCandidate) -> dict[str, float | int]:
    return {
        "rh": candidate.rh,
        "rl": candidate.rl,
        "span": candidate.span,
        "swing_high_index": candidate.swing_high.index,
        "swing_low_index": candidate.swing_low.index,
        "anchor_index": candidate.anchor_index,
    }


def select_major_candidate(
    candidates: list[SwingRangeCandidate],
    *,
    active_price: float,
) -> tuple[SwingRangeCandidate | None, str, dict]:
    """
    Pick the outermost MAJOR-eligible range that engulfs active price.
    Falls back to largest MAJOR-eligible span, then NO_MAJOR_STRUCTURE.
    """
    meta: dict = {
        "candidates_considered": [_candidate_debug_row(c) for c in candidates],
        "major_eligible": [],
        "engulfing_major": [],
        "rejected": [],
    }
    if not candidates:
        return None, "NO_CANDIDATES", meta

    major_pool = [c for c in candidates if _is_major_eligible(c, candidates)]
    meta["major_eligible"] = [_candidate_debug_row(c) for c in major_pool]

    for c in candidates:
        if c not in major_pool:
            meta["rejected"].append(
                {
                    **_candidate_debug_row(c),
                    "reason": "no_contained_minor",
                }
            )

    if not major_pool:
        meta["selection_reason"] = "no_major_eligible"
        return None, "NO_MAJOR_STRUCTURE", meta

    engulfing = [c for c in major_pool if c.engulfs_price(active_price)]
    meta["engulfing_major"] = [_candidate_debug_row(c) for c in engulfing]

    if engulfing:
        chosen = max(engulfing, key=_outermost_key)
        meta["selection_reason"] = "outermost_engulfing_major"
        return chosen, "OUTERMOST_ENGULFING", meta

    chosen = max(major_pool, key=_outermost_key)
    meta["selection_reason"] = "outermost_major_no_engulf"
    meta["rejected"].extend(
        {
            **_candidate_debug_row(c),
            "reason": "major_does_not_engulf_price",
        }
        for c in major_pool
    )
    return chosen, "OUTERMOST_MAJOR_FALLBACK", meta


def select_minor_candidate(
    candidates: list[SwingRangeCandidate],
    *,
    active_price: float,
) -> tuple[SwingRangeCandidate | None, str, dict]:
    """Pick the innermost engulfing range; prefer one nested inside a MAJOR-eligible outer."""
    meta: dict = {
        "candidates_considered": [_candidate_debug_row(c) for c in candidates],
        "engulfing": [],
        "rejected": [],
    }
    if not candidates:
        return None, "NO_CANDIDATES", meta

    engulfing = [c for c in candidates if c.engulfs_price(active_price)]
    meta["engulfing"] = [_candidate_debug_row(c) for c in engulfing]

    if engulfing:
        major_outers = [c for c in candidates if _is_major_eligible(c, candidates)]
        nested = [
            c
            for c in engulfing
            if any(outer.strictly_contains(c) for outer in major_outers if outer is not c)
        ]
        pool = nested if nested else engulfing
        chosen = min(pool, key=_innermost_key)
        meta["selection_reason"] = (
            "innermost_engulfing_nested_minor"
            if nested
            else "innermost_engulfing_minor"
        )
        return chosen, meta["selection_reason"], meta

    for c in candidates:
        meta["rejected"].append({**_candidate_debug_row(c), "reason": "does_not_engulf_price"})

    meta["selection_reason"] = "no_engulfing_minor"
    return None, "NO_MINOR_STRUCTURE", meta
