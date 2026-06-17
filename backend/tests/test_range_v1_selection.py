"""RANGE_V1 major/minor swing selection tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from detector.models import DetectionContext, SwingPoint
from detector.normalize import normalize_candles
from detector.range_scale_mode import RANGE_SCALE_MODE_LEGACY
from detector.range_candidate import detect_range_suggestions
from detector.range_selection import (
    SwingRangeCandidate,
    enumerate_swing_range_candidates,
    select_major_candidate,
    select_minor_candidate,
)
from detector.versions import RANGE_V1


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
    return normalize_candles(payload, "W1")


def _swing(index: int, kind: str, price: float, candle) -> SwingPoint:
    return SwingPoint(index=index, kind=kind, price=price, candle=candle)


class MajorMinorSelectionTests(unittest.TestCase):
    """Reproduce XAUUSD W1: red major vs green minor."""

    MAJOR_RH = 3499.88
    MAJOR_RL = 2956.66
    MINOR_RH = 3430.86
    MINOR_RL = 3120.81
    ACTIVE_PRICE = 3300.0

    def setUp(self) -> None:
        rows = [(self.ACTIVE_PRICE, self.ACTIVE_PRICE + 5, self.ACTIVE_PRICE - 5, self.ACTIVE_PRICE)] * 12
        self.candles = _rows_to_candles(rows)
        self.active_index = len(self.candles) - 1
        self.swings = [
            _swing(1, "SWING_LOW", self.MAJOR_RL, self.candles[1]),
            _swing(3, "SWING_HIGH", self.MAJOR_RH, self.candles[3]),
            _swing(7, "SWING_LOW", self.MINOR_RL, self.candles[7]),
            _swing(9, "SWING_HIGH", self.MINOR_RH, self.candles[9]),
        ]

    def test_major_selects_outer_red_container_not_green_minor(self) -> None:
        ctx = DetectionContext(
            symbol="XAUUSD",
            source_timeframe="W1",
            candles=self.candles,
            active_index=self.active_index,
            range_scale="MAJOR",
            swings=self.swings,
        )
        out = detect_range_suggestions(ctx, scale_mode=RANGE_SCALE_MODE_LEGACY)
        self.assertEqual(len(out), 1)
        draft = out[0]
        self.assertEqual(draft.detector_version, RANGE_V1)
        self.assertEqual(draft.candidate_kind, "RANGE_MAJOR")
        self.assertAlmostEqual(draft.suggested_rh, self.MAJOR_RH)
        self.assertAlmostEqual(draft.suggested_rl, self.MAJOR_RL)
        self.assertNotAlmostEqual(draft.suggested_rh, self.MINOR_RH)
        self.assertIn("engulfs", draft.reason_text.lower())

    def test_minor_selects_inner_green_container(self) -> None:
        ctx = DetectionContext(
            symbol="XAUUSD",
            source_timeframe="W1",
            candles=self.candles,
            active_index=self.active_index,
            range_scale="MINOR",
            swings=self.swings,
        )
        out = detect_range_suggestions(ctx, scale_mode=RANGE_SCALE_MODE_LEGACY)
        self.assertEqual(len(out), 1)
        draft = out[0]
        self.assertEqual(draft.candidate_kind, "RANGE_MINOR")
        self.assertAlmostEqual(draft.suggested_rh, self.MINOR_RH)
        self.assertAlmostEqual(draft.suggested_rl, self.MINOR_RL)

    def test_selection_meta_lists_candidates_and_reason(self) -> None:
        ctx = DetectionContext(
            symbol="XAUUSD",
            source_timeframe="W1",
            candles=self.candles,
            active_index=self.active_index,
            range_scale="MAJOR",
            swings=self.swings,
        )
        out = detect_range_suggestions(ctx, scale_mode=RANGE_SCALE_MODE_LEGACY)
        meta = out[0].meta_json.get("range_selection") or {}
        self.assertIn("candidates_considered", meta)
        self.assertGreaterEqual(len(meta["candidates_considered"]), 2)
        self.assertEqual(meta.get("selection_reason"), "outermost_engulfing_major")

    def test_single_pair_still_emits_major_for_backward_compat(self) -> None:
        swings = [
            _swing(2, "SWING_LOW", 98.0, self.candles[2]),
            _swing(7, "SWING_HIGH", 110.0, self.candles[7]),
        ]
        ctx = DetectionContext(
            symbol="XAUUSD",
            source_timeframe="D1",
            candles=self.candles,
            active_index=self.active_index,
            range_scale="MAJOR",
            swings=swings,
        )
        out = detect_range_suggestions(ctx, scale_mode=RANGE_SCALE_MODE_LEGACY)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].candidate_kind, "RANGE_MAJOR")
        self.assertEqual(out[0].suggested_rh, 110.0)
        self.assertEqual(out[0].suggested_rl, 98.0)

    def test_minor_selection_picks_innermost_engulfing(self) -> None:
        candidates = enumerate_swing_range_candidates(self.swings, active_index=self.active_index)
        chosen, code, meta = select_minor_candidate(candidates, active_price=self.ACTIVE_PRICE)
        self.assertIsNotNone(chosen)
        self.assertAlmostEqual(chosen.rh, self.MINOR_RH)  # type: ignore[union-attr]
        self.assertAlmostEqual(chosen.rl, self.MINOR_RL)  # type: ignore[union-attr]
        self.assertIn("innermost", meta["selection_reason"])


if __name__ == "__main__":
    unittest.main()
