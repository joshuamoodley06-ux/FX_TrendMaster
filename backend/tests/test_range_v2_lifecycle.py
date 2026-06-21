"""Phase A+B tests for RANGE_V2 lifecycle and boundary helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from detector.break_rules import BODY_CLOSE, RECLAIM_CLOSE, RECLAIM_TOUCH, WICK
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
            (101, 104, 100.01, 103),  # stays above RH; wick does not tag 100
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
            (89, 89.5, 87, 88),  # wick stays below RL 90
        ])
        seed = RangeSeedContext(range_high=100.0, range_low=90.0)
        out = evaluate_lifecycle(candles, 3, seed, break_rule=WICK)
        self.assertEqual(out.state, RangeLifecycleState.BREACHED_DOWN)
        self.assertEqual(out.no_range_reason, NoRangeReason.BOS_WITHOUT_RECLAIM)


class LifecycleUnresolvedTests(unittest.TestCase):
    def test_htf_opposite_break_after_wick_reclaim_completes(self) -> None:
        """HTF: wick tag of old RH after BOS UP completes reclaim even if RL also breaks."""
        candles = _rows_to_candles([
            (95, 98, 94, 97),
            (98, 102, 97, 101),   # BOS up
            (101, 103, 100.5, 102),  # no RH touch yet
            (102, 103, 89, 103),   # wick tags RH → reclaim completes
        ])
        seed = RangeSeedContext(range_high=100.0, range_low=90.0)
        out = evaluate_lifecycle(candles, 3, seed, break_rule=WICK)
        self.assertEqual(out.state, RangeLifecycleState.RECLAIMED_DOWN)
        assert out.chain is not None
        self.assertEqual(out.chain.reclaim_confirmation, RECLAIM_TOUCH)

    def test_opposite_bos_ignored_after_premature_wick_touch_only(self) -> None:
        candles = _rows_to_candles([
            (95, 98, 94, 97),
            (98, 102, 97, 101),        # BOS up
            (101, 108, 99.5, 107),     # RECLAIM_TOUCH only
            (107, 108, 89, 88),        # opposite BOS down ignored after touch-only
            (88, 112, 87, 111),        # continuation
            (111, 112, 98, 99.5),      # RECLAIM_CLOSE
        ])
        seed = RangeSeedContext(range_high=100.0, range_low=90.0)
        out = evaluate_lifecycle(candles, 5, seed, break_rule=WICK)
        self.assertEqual(out.state, RangeLifecycleState.RECLAIMED_DOWN)
        assert out.chain is not None
        self.assertIsNotNone(out.chain.reclaim_touch_index)
        self.assertLessEqual(out.chain.reclaim_touch_index, out.chain.reclaim_index)


class LifecycleHtfWickReclaimTests(unittest.TestCase):
    def test_bullish_wick_touch_completes_htf_lifecycle(self) -> None:
        candles = _rows_to_candles([
            (95, 98, 94, 97),
            (97, 99, 96, 98),
            (98, 99, 97, 98),
            (99, 100, 98, 99),
            (99, 100, 98, 99),
            (101, 106, 100.01, 104),   # BOS up above RH 100
            (104, 108, 99.5, 107),     # wick tags RH — HTF reclaim complete
        ])
        seed = RangeSeedContext(range_high=100.0, range_low=90.0)
        out = evaluate_lifecycle(candles, 6, seed, break_rule=WICK)
        self.assertEqual(out.state, RangeLifecycleState.RECLAIMED_DOWN)
        assert out.chain is not None
        self.assertEqual(out.chain.reclaim_index, 6)
        self.assertEqual(out.chain.reclaim_confirmation, RECLAIM_TOUCH)

    def test_bullish_body_close_also_completes_when_wick_already_tagged(self) -> None:
        candles = _rows_to_candles([
            (95, 98, 94, 97),
            (97, 99, 96, 98),
            (98, 99, 97, 98),
            (99, 100, 98, 99),
            (99, 100, 98, 99),
            (101, 106, 100.01, 104),   # BOS up
            (104, 108, 99.5, 107),     # HTF wick reclaim
            (106, 107, 98, 99.5),      # body close inside (would also qualify)
        ])
        seed = RangeSeedContext(range_high=100.0, range_low=90.0)
        out = evaluate_lifecycle(candles, 7, seed, break_rule=WICK)
        self.assertEqual(out.state, RangeLifecycleState.RECLAIMED_DOWN)
        assert out.chain is not None
        self.assertEqual(out.chain.reclaim_index, 6)
        self.assertEqual(out.chain.reclaim_touch_index, 6)
        self.assertEqual(out.chain.reclaim_confirmation, RECLAIM_TOUCH)

    def test_bearish_wick_touch_completes_htf_lifecycle(self) -> None:
        candles = _rows_to_candles([
            (95, 98, 94, 97),
            (97, 99, 96, 98),
            (98, 99, 97, 98),
            (97, 98, 96, 97),
            (96, 97, 95, 96),
            (96, 97, 85, 86),       # BOS down below RL 90
            (86, 90.5, 84, 85),     # wick tags RL — HTF reclaim complete
        ])
        seed = RangeSeedContext(range_high=100.0, range_low=90.0)
        out = evaluate_lifecycle(candles, 6, seed, break_rule=WICK)
        self.assertEqual(out.state, RangeLifecycleState.RECLAIMED_UP)
        assert out.chain is not None
        self.assertEqual(out.chain.reclaim_confirmation, RECLAIM_TOUCH)

    def test_bearish_wick_then_body_close_still_first_touch_bar(self) -> None:
        candles = _rows_to_candles([
            (95, 98, 94, 97),
            (97, 99, 96, 98),
            (98, 99, 97, 98),
            (97, 98, 96, 97),
            (96, 97, 95, 96),
            (96, 97, 85, 86),       # BOS down
            (86, 90.5, 84, 85),     # HTF wick reclaim
            (85, 91, 84, 90.5),     # body close inside
        ])
        seed = RangeSeedContext(range_high=100.0, range_low=90.0)
        out = evaluate_lifecycle(candles, 7, seed, break_rule=WICK)
        self.assertEqual(out.state, RangeLifecycleState.RECLAIMED_UP)
        assert out.chain is not None
        self.assertEqual(out.chain.reclaim_index, 6)
        self.assertEqual(out.chain.reclaim_confirmation, RECLAIM_TOUCH)

    def test_ltf_body_close_still_required_for_reclaim(self) -> None:
        candles = _rows_to_candles([
            (95, 98, 94, 97),
            (98, 99, 97, 98),
            (99, 100, 98, 99),
            (99, 100, 98, 99),
            (101, 106, 100.01, 104),   # BOS up
            (104, 108, 99.5, 107),     # wick tags RH but close above
        ])
        seed = RangeSeedContext(range_high=100.0, range_low=90.0)
        out = evaluate_lifecycle(candles, 5, seed, break_rule=BODY_CLOSE)
        self.assertEqual(out.state, RangeLifecycleState.BREACHED_UP)
        self.assertEqual(out.no_range_reason, NoRangeReason.BOS_WITHOUT_RECLAIM)

    def test_wick_touch_completes_on_first_htf_tag(self) -> None:
        """HTF: first wick tag after BOS completes reclaim (continuation bars are a new story)."""
        candles = _rows_to_candles([
            (95, 98, 94, 97),
            (98, 102, 97, 101),        # BOS up
            (101, 108, 99.5, 107),     # HTF wick reclaim
            (107, 112, 106, 111),      # continuation BOS up
            (111, 112, 98, 99.5),      # later body close inside
        ])
        seed = RangeSeedContext(range_high=100.0, range_low=90.0)
        out = evaluate_lifecycle(candles, 2, seed, break_rule=WICK)
        self.assertEqual(out.state, RangeLifecycleState.RECLAIMED_DOWN)
        assert out.chain is not None
        self.assertEqual(out.chain.reclaim_index, 2)


class LifecycleBullishChainTests(unittest.TestCase):
    def _bullish_candles(self):
        return _rows_to_candles([
            (95, 98, 94, 97),
            (97, 99, 96, 98),
            (98, 99, 97, 98),
            (99, 100, 98, 99),
            (99, 100, 98, 99),
            (101, 106, 100.01, 104),  # 5 BOS up
            (104, 105, 100.01, 103),
            (103, 104, 100.01, 102),
            (102, 103, 99.5, 102),    # 8 RECLAIM_TOUCH only
            (101, 102, 98, 99.5),     # 9 RECLAIM_CLOSE
        ])

    def test_bullish_bos_reclaim_chain(self) -> None:
        candles = self._bullish_candles()
        seed = RangeSeedContext(range_high=100.0, range_low=90.0)
        out = evaluate_lifecycle(candles, 9, seed, break_rule=WICK)
        self.assertEqual(out.state, RangeLifecycleState.RECLAIMED_DOWN)
        self.assertIsNotNone(out.chain)
        assert out.chain is not None
        self.assertEqual(out.chain.direction, BosDirection.UP)
        self.assertEqual(out.chain.bos_index, 5)
        self.assertEqual(out.chain.bos_boundary_price, 106.0)
        self.assertEqual(out.chain.reclaim_index, 8)
        self.assertEqual(out.chain.reclaim_touch_index, 8)
        self.assertEqual(out.chain.broken_boundary, BrokenBoundary.HIGH)

    def test_bullish_structural_rh_and_rl_not_retracement_defaults(self) -> None:
        candles = self._bullish_candles()
        seed = RangeSeedContext(range_high=100.0, range_low=90.0)
        life = evaluate_lifecycle(candles, 9, seed, break_rule=WICK)
        swings = [
            _swing(3, "SWING_LOW", 98.0, candles[3]),
            _swing(6, "SWING_LOW", 101.0, candles[6]),
        ]
        bounds = derive_boundaries(life, swings, candles=candles)
        self.assertTrue(bounds.is_valid)
        self.assertEqual(bounds.suggested_rl, 98.0)
        self.assertEqual(bounds.selected_rl_source, "STRUCTURAL_SWING")
        self.assertNotEqual(
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
            (96, 97, 85, 86),       # 5 BOS down
            (86, 88, 84, 85),
            (85, 87, 83, 84),
            (84, 90.5, 83, 89),     # 8 RECLAIM_TOUCH only
            (89, 91, 84, 90.5),     # 9 RECLAIM_CLOSE
        ])

    def test_bearish_bos_reclaim_chain(self) -> None:
        candles = self._bearish_candles()
        seed = RangeSeedContext(range_high=100.0, range_low=90.0)
        out = evaluate_lifecycle(candles, 9, seed, break_rule=WICK)
        self.assertEqual(out.state, RangeLifecycleState.RECLAIMED_UP)
        assert out.chain is not None
        self.assertEqual(out.chain.direction, BosDirection.DOWN)
        self.assertEqual(out.chain.bos_index, 7)
        self.assertEqual(out.chain.bos_boundary_price, 83.0)

    def test_bearish_structural_rl_and_rh(self) -> None:
        candles = self._bearish_candles()
        seed = RangeSeedContext(range_high=100.0, range_low=90.0)
        life = evaluate_lifecycle(candles, 9, seed, break_rule=WICK)
        swings = [
            _swing(3, "SWING_HIGH", 98.0, candles[3]),
            _swing(6, "SWING_HIGH", 88.0, candles[6]),
        ]
        bounds = derive_boundaries(life, swings, candles=candles)
        self.assertTrue(bounds.is_valid)
        self.assertEqual(bounds.suggested_rh, 98.0)
        self.assertEqual(bounds.selected_rh_source, "STRUCTURAL_SWING")


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
    def test_reclaim_without_swings_uses_seed_structural_floor(self) -> None:
        candles = _rows_to_candles([
            (95, 98, 94, 97),
            (98, 106, 97, 104),
            (104, 105, 99.5, 102),
        ])
        seed = RangeSeedContext(range_high=100.0, range_low=90.0)
        life = evaluate_lifecycle(candles, 2, seed, break_rule=WICK)
        if life.can_suggest_range:
            bounds = derive_boundaries(life, [], candles=candles)
            self.assertTrue(bounds.is_valid)
            self.assertEqual(bounds.selected_rl_source, "SEED_ANCHORED")
            self.assertAlmostEqual(float(bounds.suggested_rl), 90.0, delta=0.01)

    def test_evaluate_range_v2_boundaries_rejects_breached(self) -> None:
        life = LifecycleEvaluation(
            state=RangeLifecycleState.BREACHED_UP,
            no_range_reason=NoRangeReason.BOS_WITHOUT_RECLAIM,
            reason_text="no reclaim",
        )
        bounds = evaluate_range_v2_boundaries(life, [])
        self.assertFalse(bounds.is_valid)
        self.assertEqual(bounds.no_range_reason, NoRangeReason.BOS_WITHOUT_RECLAIM)


class W1Baseline2025StyleTests(unittest.TestCase):
    """Structural replay matching Review Candidate baseline (seed 2721/2596 → expanded range)."""

    def test_htf_wick_reclaim_expands_range(self) -> None:
        rows = [
            (2680, 2690, 2561, 2580),
            (2580, 2650, 2570, 2640),
            (2640, 2720, 2630, 2710),
            (2710, 2750, 2705, 2745),   # BOS up above seed RH 2721
            (2745, 2790, 2740, 2785),   # continuation to ~2790
            (2785, 2795, 2715, 2760),   # RECLAIM_TOUCH old RH 2721
            (2760, 2770, 2680, 2705),   # RECLAIM_CLOSE inside old RH
        ]
        candles = _rows_to_candles(rows, base_ms=1_735_689_600_000)
        seed = RangeSeedContext(range_high=2721.0, range_low=2596.0, is_manual_seed=True)
        out = evaluate_lifecycle(candles, len(candles) - 1, seed, break_rule=WICK)
        self.assertEqual(out.state, RangeLifecycleState.RECLAIMED_DOWN)
        assert out.chain is not None
        self.assertEqual(out.chain.reclaim_touch_index, 5)
        self.assertEqual(out.chain.reclaim_index, 5)
        self.assertEqual(out.chain.reclaim_confirmation, RECLAIM_TOUCH)

        from detector.swing import detect_swings

        swings = [
            _swing(0, "SWING_LOW", 2561.0, candles[0]),
            _swing(4, "SWING_HIGH", 2790.0, candles[4]),
        ]
        bounds = derive_boundaries(out, swings, candles=candles)
        self.assertTrue(bounds.is_valid, bounds.reason_text)
        self.assertAlmostEqual(float(bounds.suggested_rh), 2790.0, delta=5.0)
        self.assertAlmostEqual(float(bounds.suggested_rl), 2561.0, delta=5.0)


if __name__ == "__main__":
    unittest.main()
