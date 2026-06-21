"""Tests for RANGE_V2 retracement measurement."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from detector.break_rules import WICK
from detector.models import SwingPoint
from detector.range_boundary import derive_boundaries
from detector.range_lifecycle import evaluate_lifecycle
from detector.range_state import RangeSeedContext
from detector.retracement import classify_retracement, measure_retracement_for_chain
from detector.normalize import normalize_candles


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


class RetracementClassifierTests(unittest.TestCase):
    def test_classes(self) -> None:
        self.assertEqual(classify_retracement(0.1), "SHALLOW")
        self.assertEqual(classify_retracement(0.33), "MID")
        self.assertEqual(classify_retracement(0.66), "DEEP")
        self.assertEqual(classify_retracement(1.01), "EXTREME")
        self.assertIsNone(classify_retracement(None))


class RetracementMeasurementTests(unittest.TestCase):
    def test_bullish_deep_retracement_between_bos_and_reclaim(self) -> None:
        candles = _rows_to_candles([
            (95, 98, 94, 97),
            (97, 99, 96, 98),
            (98, 99, 97, 98),
            (99, 100, 98, 99),
            (99, 100, 98, 99),
            (101, 106, 100.01, 104),   # BOS up
            (104, 105, 100.01, 103),
            (103, 104, 100.01, 102),
            (102, 103, 99.5, 102),     # wick reclaim
        ])
        seed = RangeSeedContext(range_high=100.0, range_low=90.0)
        life = evaluate_lifecycle(candles, 8, seed, break_rule=WICK)
        assert life.chain is not None
        swings = [
            SwingPoint(index=6, kind="SWING_LOW", price=100.01, candle=candles[6]),
            SwingPoint(index=3, kind="SWING_LOW", price=98.0, candle=candles[3]),
        ]
        bounds = derive_boundaries(life, swings, candles=candles)
        assert bounds.is_valid
        retr = measure_retracement_for_chain(
            candles,
            life.chain,
            impulse_high=float(bounds.suggested_rh),
            impulse_low=float(bounds.suggested_rl),
        )
        self.assertIsNotNone(retr.percent)
        assert retr.percent is not None
        self.assertGreater(retr.percent, 0.0)
        self.assertIn(retr.retracement_class, {"SHALLOW", "MID", "DEEP", "EXTREME"})
        self.assertIsNotNone(retr.retracement_price)


if __name__ == "__main__":
    unittest.main()
