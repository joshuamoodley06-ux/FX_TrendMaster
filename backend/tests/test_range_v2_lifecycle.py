"""Phase A+B tests for RANGE_V2 lifecycle and boundary helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from detector.break_rules import WICK
from detector.models import NormalizedCandle, SwingPoint
from detector.normalize import normalize_candles
from detector.range_boundary import derive_boundaries, evaluate_range_v2_boundaries, select_opposite_swing
from detector.range_lifecycle import evaluate_lifecycle
from detector.range_state import (
    BosDirection,
    BosReclaimChain,
    BrokenBoundary,
    LifecycleEvaluation,
    NoRangeReason,
    OppositeSwingReason,
    RangeLifecycleState,
    RangeSeedContext,
)


def _rows_to_candles(rows: list[tuple[float, float, float, float]], base_ms: int = 1_700_000_000_000):
    payload = []
    for i, (o, h, l, c) in enumerate(rows):
        payload.append(
            {
                "time_ms": base_ms + i * 86_400_000,
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "volume": 100,
            }
        )
    return normalize_candles(payload, "D1")


def _swing(index: int, kind: str, price: float, candle: NormalizedCandle) -> SwingPoint:
    return SwingPoint(index=index, kind=kind, price=price, candle=candle)


class RangeStateTests(unittest.TestCase):
    def test_seed_validity(self) -> None:
        self.assertTrue(RangeSeedContext(110.0, 100.0).is_valid())
        self.assertFalse(RangeSeedContext(100.0, 110.0).is_valid())


class LifecycleNoSeedTests(unittest.TestCase):
    def test_no_seed_returns_no_valid_range(self) -> None:
        candles = _rows_to_candles([(100, 101, 99, 100)])
        out = evaluate_lifecycle(candles, 0, None, break_rule=WICK)
        self.assertEqual(out.state, RangeLifecycleState.NO_VALID_RANGE)
        self.assertEqual(out.no_range_reason, NoRangeReason.NO_SEED_OR_ACTIVE_RANGE)


class LifecycleSeedOnlyTests(unittest.TestCase):
    def test_seed_only_no_bos(self) -> None:
        candles = _rows_to_candles([
            (95, 98, 94, 97),
            (97, 99, 96, 98),
        ])
        seed = RangeSeedContext(range_high=100.0, range_low=90.0, is_manual_seed=True)
        out = evaluate_lifecycle(candles, 1, seed, break_rule=WICK)
        self.assertEqual(out.state, RangeLifecycleState.SEEDED)
        self.assertEqual(out.no_range_reason, NoRangeReason.SEED_ONLY_NO_BOS)
        self.assertIsNone(out.chain)


class LifecycleBosWithoutReclaimTests(unittest.TestCase):
    def test_bos_up_without_reclaim(self) -> None:
        candles = _rows_to_candles([
            (95, 98, 94, 97),
            (97, 99, 96, 98),
            (98, 102, 97, 101),  # BOS up above RH 100
            (101, 104, 100, 103),  # still above, no reclaim
        ])
        seed = RangeSeedContext(range_high=100.0, range_low=90.0)
        out = evaluate_lifecycle(candles, 3, seed, break_rule=WICK)
        self.assertEqual(out.state, RangeLifecycleState.BREACHED_UP)
        self.assertEqual(out.no_range_reason, NoRangeReason.BOS_WITHOUT_RECLAIM)
        self.assertIsNone(out.chain)

    def test_bos_down_without_reclaim(self) -> None:
        candles = _rows_to_candles([
            (95, 98, 94, 97),
            (97, 99, 96, 98),
            (98, 99, 88, 89),  # BOS down below RL 90
            (89, 91, 87, 88),
        ])
        seed = RangeSeedContext(range_high=100.0, range_low=90.0)
        out = evaluate_lifecycle(candles, 3, seed, break_rule=WICK)
        self.assertEqual(out.state, RangeLifecycleState.BREACHED_DOWN)
        self.assertEqual(out.no_range_reason, NoRangeReason.BOS_WITHOUT_RECLAIM)


class LifecycleUnresolvedTests(unittest.TestCase):
    def test_opposite_bos_before_reclaim(self) -> None:
        candles = _rows_to_candles([
            (95, 98, 94, 97),
            (98, 102, 97, 101),   # BOS up
            (101, 103, 100, 102),
            (102, 103, 85, 86),   # opposite BOS down before reclaim
        ])
        seed = RangeSeedContext(range_high=100.0, range_low=90.0)
        out = evaluate_lifecycle(candles, 3, seed, break_rule=WICK)
        self.assertEqual(out.state, RangeLifecycleState.NO_VALID_RANGE)
        self.assertEqual(out.no_range_reason, NoRangeReason.UNRESOLVED_TRANSITION)


class LifecycleBullishChainTests(unittest.TestCase):
    def _bullish_candles(self):
        return _rows_to_candles([
            (95, 98, 94, 97),
            (97, 99, 96, 98),
            (98, 99, 97, 98),
            (99, 100, 98, 99),
            (99, 101, 98, 100),
            (101, 106, 100, 104),  # 5 BOS up
            (104, 105, 101, 103),
            (103, 104, 100, 102),
            (102, 103, 98, 99),    # 8 reclaim close <= 100
        ])

    def test_bullish_bos_reclaim_chain(self) -> None:
        candles = self._bullish_candles()
        seed = RangeSeedContext(range_high=100.0, range_low=90.0)
        out = evaluate_lifecycle(candles, 8, seed, break_rule=WICK)
        self.assertEqual(out.state, RangeLifecycleState.RECLAIMED_DOWN)
        self.assertIsNotNone(out.chain)
        assert out.chain is not None
        self.assertEqual(out.chain.direction, BosDirection.UP)
        self.assertEqual(out.chain.bos_index, 5)
        self.assertEqual(out.chain.bos_boundary_price, 106.0)
        self.assertEqual(out.chain.reclaim_index, 8)
        self.assertEqual(out.chain.broken_boundary, BrokenBoundary.HIGH)

    def test_bullish_rh_is_bos_high_not_latest(self) -> None:
        candles = self._bullish_candles()
        seed = RangeSeedContext(range_high=100.0, range_low=90.0)
        life = evaluate_lifecycle(candles, 8, seed, break_rule=WICK)
        swings = [
            _swing(6, "SWING_LOW", 101.0, candles[6]),
        ]
        bounds = derive_boundaries(life, swings)
        self.assertTrue(bounds.is_valid)
        self.assertEqual(bounds.suggested_rh, 106.0)
        self.assertEqual(bounds.suggested_rl, 101.0)
        self.assertEqual(
            bounds.boundary_selection_reason,
            OppositeSwingReason.OPPOSITE_SWING_BETWEEN_BOS_RECLAIM.value,
        )


class LifecycleBearishChainTests(unittest.TestCase):
    def _bearish_candles(self):
        return _rows_to_candles([
            (95, 98, 94, 97),
            (97, 99, 96, 98),
            (98, 99, 97, 98),
            (97, 98, 96, 97),
            (96, 97, 95, 96),
            (96, 97, 85, 86),   # 5 BOS down
            (86, 88, 84, 85),
            (85, 87, 83, 84),
            (84, 92, 83, 91),   # 8 reclaim close >= 90
        ])

    def test_bearish_bos_reclaim_chain(self) -> None:
        candles = self._bearish_candles()
        seed = RangeSeedContext(range_high=100.0, range_low=90.0)
        out = evaluate_lifecycle(candles, 8, seed, break_rule=WICK)
        self.assertEqual(out.state, RangeLifecycleState.RECLAIMED_UP)
        assert out.chain is not None
        self.assertEqual(out.chain.direction, BosDirection.DOWN)
        self.assertEqual(out.chain.bos_index, 7)
        self.assertEqual(out.chain.bos_boundary_price, 83.0)

    def test_bearish_rl_is_bos_low(self) -> None:
        candles = self._bearish_candles()
        seed = RangeSeedContext(range_high=100.0, range_low=90.0)
        life = evaluate_lifecycle(candles, 8, seed, break_rule=WICK)
        swings = [
            _swing(6, "SWING_HIGH", 88.0, candles[6]),
        ]
        bounds = derive_boundaries(life, swings)
        self.assertTrue(bounds.is_valid)
        self.assertEqual(bounds.suggested_rl, 83.0)
        self.assertEqual(bounds.suggested_rh, 88.0)


class OppositeSwingSelectionTests(unittest.TestCase):
    def test_prefers_swing_between_bos_and_reclaim(self) -> None:
        candles = _rows_to_candles([(100, 101, 99, 100)] * 10)
        chain = BosReclaimChain(
            direction=BosDirection.UP,
            bos_index=2,
            bos_boundary_price=105.0,
            reclaim_index=7,
            broken_boundary=BrokenBoundary.HIGH,
            old_range_high=100.0,
            old_range_low=90.0,
        )
        swings = [
            _swing(1, "SWING_LOW", 92.0, candles[1]),
            _swing(4, "SWING_LOW", 94.0, candles[4]),
            _swing(8, "SWING_LOW", 96.0, candles[8]),
        ]
        picked, reason = select_opposite_swing(swings, chain)
        self.assertIsNotNone(picked)
        assert picked is not None
        self.assertEqual(picked.index, 4)
        self.assertEqual(reason, OppositeSwingReason.OPPOSITE_SWING_BETWEEN_BOS_RECLAIM)

    def test_falls_back_to_swing_before_bos(self) -> None:
        candles = _rows_to_candles([(100, 101, 99, 100)] * 10)
        chain = BosReclaimChain(
            direction=BosDirection.UP,
            bos_index=5,
            bos_boundary_price=106.0,
            reclaim_index=8,
            broken_boundary=BrokenBoundary.HIGH,
            old_range_high=100.0,
            old_range_low=90.0,
        )
        swings = [
            _swing(3, "SWING_LOW", 93.0, candles[3]),
        ]
        picked, reason = select_opposite_swing(swings, chain)
        self.assertIsNotNone(picked)
        self.assertEqual(reason, OppositeSwingReason.LAST_OPPOSITE_SWING_BEFORE_BOS)

    def test_unclear_when_no_swings(self) -> None:
        candles = _rows_to_candles([(100, 101, 99, 100)] * 5)
        chain = BosReclaimChain(
            direction=BosDirection.DOWN,
            bos_index=2,
            bos_boundary_price=85.0,
            reclaim_index=4,
            broken_boundary=BrokenBoundary.LOW,
            old_range_high=100.0,
            old_range_low=90.0,
        )
        picked, reason = select_opposite_swing([], chain)
        self.assertIsNone(picked)
        self.assertEqual(reason, OppositeSwingReason.UNCLEAR_OPPOSITE_SWING)


class BoundaryNoValidTests(unittest.TestCase):
    def test_reclaim_without_opposite_swing_is_no_valid(self) -> None:
        candles = _rows_to_candles([
            (95, 98, 94, 97),
            (98, 106, 97, 104),
            (104, 105, 100, 99),
        ])
        seed = RangeSeedContext(range_high=100.0, range_low=90.0)
        life = evaluate_lifecycle(candles, 2, seed, break_rule=WICK)
        if life.can_suggest_range:
            bounds = derive_boundaries(life, [])
            self.assertEqual(bounds.no_range_reason, NoRangeReason.UNCLEAR_OPPOSITE_SWING)

    def test_evaluate_range_v2_boundaries_rejects_breached(self) -> None:
        life = LifecycleEvaluation(
            state=RangeLifecycleState.BREACHED_UP,
            no_range_reason=NoRangeReason.BOS_WITHOUT_RECLAIM,
            reason_text="no reclaim",
        )
        bounds = evaluate_range_v2_boundaries(life, [])
        self.assertFalse(bounds.is_valid)
        self.assertEqual(bounds.no_range_reason, NoRangeReason.BOS_WITHOUT_RECLAIM)


if __name__ == "__main__":
    unittest.main()
