"""Phase 1 — structural boundary selection decoupled from retracement."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from detector.break_rules import WICK
from detector.models import SwingPoint
from detector.normalize import normalize_candles
from detector.range_boundary import derive_boundaries
from detector.range_lifecycle import evaluate_lifecycle
from detector.range_state import (
    BOUNDARY_SOURCE_BOS_BAR,
    BOUNDARY_SOURCE_LEG_EXPANSION,
    BOUNDARY_SOURCE_STRUCTURAL_SWING,
    EXPANSION_OWNER_BOS_CANDLE,
    EXPANSION_OWNER_IMPULSE_SWING,
    EXPANSION_OWNER_REF_CANDLE,
    BosDirection,
    BosReclaimChain,
    BrokenBoundary,
    LifecycleEvaluation,
    POST_BOS_RETRACEMENT_POINT_NOT_BOUNDARY,
    RangeLifecycleState,
    RangeSeedContext,
)
from tests.detector_audit_fixture import PRICE_TOLERANCE, build_gold_rows


def _rows_to_candles(rows: list[tuple[float, float, float, float]]):
    payload = []
    for i, (o, h, l, c) in enumerate(rows):
        payload.append(
            {
                "time_ms": 1_700_000_000_000 + i * 86_400_000,
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "volume": 100,
            }
        )
    return normalize_candles(payload, "W1")


def _swing(index: int, kind: str, price: float, candle) -> SwingPoint:
    return SwingPoint(index=index, kind=kind, price=price, candle=candle)


class StructuralBoundaryDecouplingTests(unittest.TestCase):
    def test_bullish_rh_not_blindly_bos_high_when_structural_peak_exists(self) -> None:
        candles = _rows_to_candles([
            (95, 98, 94, 97),
            (97, 99, 96, 98),
            (98, 99, 97, 98),
            (99, 100, 98, 99),
            (99, 100, 98, 99),
            (101, 106, 100.01, 104),   # BOS up — high 106
            (104, 112, 103, 111),      # structural peak 112
            (111, 112, 99.5, 102),     # reclaim
        ])
        chain = BosReclaimChain(
            direction=BosDirection.UP,
            bos_index=5,
            bos_boundary_price=106.0,
            reclaim_index=7,
            broken_boundary=BrokenBoundary.HIGH,
            old_range_high=100.0,
            old_range_low=90.0,
        )
        life = LifecycleEvaluation(state=RangeLifecycleState.RECLAIMED_DOWN, chain=chain)
        swings = [
            _swing(3, "SWING_LOW", 98.0, candles[3]),
            _swing(6, "SWING_HIGH", 112.0, candles[6]),
            _swing(7, "SWING_LOW", 99.5, candles[7]),
        ]
        bounds = derive_boundaries(life, swings, candles=candles)
        self.assertTrue(bounds.is_valid)
        self.assertEqual(bounds.suggested_rh, 112.0)
        self.assertNotEqual(bounds.selected_rh_source, BOUNDARY_SOURCE_BOS_BAR)
        leg = bounds.boundary_trace.get("htf_leg_trace") or {}
        self.assertIn(
            leg.get("expansion_extreme_owner"),
            {EXPANSION_OWNER_IMPULSE_SWING, EXPANSION_OWNER_REF_CANDLE},
        )
        self.assertEqual(bounds.selected_rl_source, BOUNDARY_SOURCE_STRUCTURAL_SWING)
        retr_low_between = 99.5
        self.assertNotAlmostEqual(bounds.suggested_rl, retr_low_between, delta=0.01)

    def test_bullish_rl_uses_structural_floor_not_post_bos_retrace(self) -> None:
        candles = _rows_to_candles([
            (100, 102, 88.0, 101),     # structural floor swing low 88
            (101, 103, 95, 102),
            (102, 104, 96, 103),
            (103, 105, 97, 104),
            (104, 106, 98, 105),
            (105, 110, 100.01, 108),   # BOS up
            (108, 109, 92.0, 93),      # post-BOS retrace low 92 — must not be RL
            (93, 94, 99.0, 99.5),      # wick reclaim touch
            (99, 100, 98.5, 99.0),     # reclaim close
        ])
        seed = RangeSeedContext(range_high=100.0, range_low=90.0)
        life = evaluate_lifecycle(candles, 8, seed, break_rule=WICK)
        swings = [
            _swing(0, "SWING_LOW", 88.0, candles[0]),
            _swing(6, "SWING_LOW", 92.0, candles[6]),
        ]
        bounds = derive_boundaries(life, swings, candles=candles)
        self.assertTrue(bounds.is_valid)
        self.assertAlmostEqual(bounds.suggested_rl, 88.0, delta=0.01)
        self.assertNotAlmostEqual(bounds.suggested_rl, 92.0, delta=0.01)
        if life.chain is not None and life.chain.bos_index < 6 < life.chain.reclaim_index:
            rejected = bounds.boundary_trace.get("rejected_boundary_candidates") or []
            reasons = [r.get("rejection_reason") for r in rejected]
            self.assertIn(POST_BOS_RETRACEMENT_POINT_NOT_BOUNDARY, reasons)

    def test_june_22_style_structural_rl_over_retrace_low(self) -> None:
        """Detector must not choose post-BOS retrace low when structural floor exists."""
        candles = _rows_to_candles([(3000, 3010, 2990, 3005)] * 12)
        chain = BosReclaimChain(
            direction=BosDirection.UP,
            bos_index=10,
            bos_boundary_price=3451.19,
            reclaim_index=11,
            broken_boundary=BrokenBoundary.HIGH,
            old_range_high=3446.72,
            old_range_low=3120.81,
        )
        swings = [
            _swing(8, "SWING_LOW", 3120.81, candles[8]),
            _swing(9, "SWING_LOW", 3293.35, candles[9]),
            _swing(10, "SWING_HIGH", 3451.19, candles[10]),
        ]
        life = LifecycleEvaluation(
            state=RangeLifecycleState.RECLAIMED_DOWN,
            chain=chain,
        )
        bounds = derive_boundaries(life, swings, candles=candles)
        self.assertTrue(bounds.is_valid)
        self.assertAlmostEqual(bounds.suggested_rl, 3120.81, delta=PRICE_TOLERANCE)
        self.assertNotAlmostEqual(bounds.suggested_rl, 3293.35, delta=PRICE_TOLERANCE)

    def test_bearish_rh_not_post_bos_retrace_high(self) -> None:
        candles = _rows_to_candles([
            (95, 98, 94, 97),
            (97, 99, 96, 98),
            (98, 99, 97, 98),
            (97, 98, 96, 97),
            (96, 97, 95, 96),
            (96, 97, 85, 86),        # BOS down
            (86, 88, 84, 85),
            (85, 87, 83, 84),
            (84, 94.0, 83, 85),       # post-BOS retrace high 94 — must not be RH
            (85, 90.5, 84, 90.0),     # wick reclaim touch
            (90, 91, 84, 90.5),       # reclaim close
        ])
        seed = RangeSeedContext(range_high=100.0, range_low=90.0)
        life = evaluate_lifecycle(candles, 10, seed, break_rule=WICK)
        swings = [
            _swing(3, "SWING_HIGH", 98.0, candles[3]),
            _swing(8, "SWING_HIGH", 94.0, candles[8]),
        ]
        bounds = derive_boundaries(life, swings, candles=candles)
        self.assertTrue(bounds.is_valid)
        self.assertAlmostEqual(bounds.suggested_rh, 98.0, delta=0.01)
        self.assertNotAlmostEqual(bounds.suggested_rh, 94.0, delta=0.01)
        if life.chain is not None and life.chain.bos_index < 8 < life.chain.reclaim_index:
            rejected = bounds.boundary_trace.get("rejected_boundary_candidates") or []
            reasons = [r.get("rejection_reason") for r in rejected]
            self.assertIn(POST_BOS_RETRACEMENT_POINT_NOT_BOUNDARY, reasons)

    def test_retracement_zone_swing_recorded_as_rejected_candidate(self) -> None:
        chain = BosReclaimChain(
            direction=BosDirection.UP,
            bos_index=5,
            bos_boundary_price=110.0,
            reclaim_index=8,
            broken_boundary=BrokenBoundary.HIGH,
            old_range_high=100.0,
            old_range_low=88.0,
        )
        candles = _rows_to_candles([(100, 101, 99, 100)] * 12)
        swings = [
            _swing(3, "SWING_LOW", 88.0, candles[3]),
            _swing(6, "SWING_LOW", 92.0, candles[6]),
        ]
        life = LifecycleEvaluation(state=RangeLifecycleState.RECLAIMED_DOWN, chain=chain)
        bounds = derive_boundaries(life, swings, candles=candles)
        rejected = bounds.boundary_trace.get("rejected_boundary_candidates") or []
        reasons = [r.get("rejection_reason") for r in rejected]
        self.assertIn(POST_BOS_RETRACEMENT_POINT_NOT_BOUNDARY, reasons)

    def test_boundary_trace_metadata_present(self) -> None:
        candles = _rows_to_candles([
            (95, 98, 88.0, 97),
            (97, 99, 96, 98),
            (98, 106, 97, 104),
            (104, 105, 99.5, 102),
        ])
        seed = RangeSeedContext(range_high=100.0, range_low=90.0)
        life = evaluate_lifecycle(candles, 3, seed, break_rule=WICK)
        swings = [_swing(0, "SWING_LOW", 88.0, candles[0])]
        bounds = derive_boundaries(life, swings, candles=candles)
        self.assertTrue(bounds.is_valid)
        trace = bounds.boundary_trace
        self.assertIn("boundary_candidates_considered", trace)
        self.assertIn("rejected_boundary_candidates", trace)
        self.assertIn("selected_boundary_candidate", trace)
        self.assertIn("htf_leg_trace", trace)
        leg = trace["htf_leg_trace"]
        self.assertIn("expansion_extreme_price", leg)
        self.assertIn("expansion_extreme_time_ms", leg)
        self.assertIn("expansion_extreme_owner", leg)
        self.assertIn("opposite_anchor_price", leg)
        self.assertIn("opposite_anchor_time_ms", leg)
        self.assertTrue(bounds.selected_rh_source)
        self.assertTrue(bounds.selected_rl_source)

    def test_htf_leg_trace_owner_impulse_swing_when_peak_after_bos(self) -> None:
        candles = _rows_to_candles([
            (95, 98, 94, 97),
            (97, 99, 96, 98),
            (98, 99, 97, 98),
            (99, 100, 98, 99),
            (99, 100, 98, 99),
            (101, 106, 100.01, 104),
            (104, 105, 103, 104),
            (105, 112, 104, 111),
            (111, 112, 99.5, 102),
        ])
        chain = BosReclaimChain(
            direction=BosDirection.UP,
            bos_index=5,
            bos_boundary_price=106.0,
            reclaim_index=8,
            broken_boundary=BrokenBoundary.HIGH,
            old_range_high=100.0,
            old_range_low=90.0,
        )
        life = LifecycleEvaluation(state=RangeLifecycleState.RECLAIMED_DOWN, chain=chain)
        swings = [
            _swing(3, "SWING_LOW", 98.0, candles[3]),
            _swing(7, "SWING_HIGH", 112.0, candles[7]),
        ]
        bounds = derive_boundaries(life, swings, candles=candles)
        leg = bounds.boundary_trace.get("htf_leg_trace") or {}
        self.assertEqual(leg.get("expansion_extreme_owner"), EXPANSION_OWNER_IMPULSE_SWING)
        self.assertAlmostEqual(float(leg["expansion_extreme_price"]), 112.0, delta=0.01)


class AuditFixtureCouplingTests(unittest.TestCase):
    """Frozen audit documents old coupling — RL must not equal impulse_low pattern."""

    def test_fixture_rows_documented_coupling_is_measurable(self) -> None:
        rows = build_gold_rows()
        coupled = 0
        for row in rows:
            if row.detector_rl is None or row.retracement_impulse_low is None:
                continue
            if abs(float(row.detector_rl) - float(row.retracement_impulse_low)) <= PRICE_TOLERANCE:
                coupled += 1
        self.assertEqual(coupled, 14, "fixture baseline: old detector coupled RL to impulse_low")


if __name__ == "__main__":
    unittest.main()
