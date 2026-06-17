"""Tests for derived range analytics classifier stub."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from detector.range_analytics_classifier import (
    DERIVED_UNKNOWN,
    RangeAnalyticsInput,
    classify_range_analytics,
)


class RangeAnalyticsClassifierTests(unittest.TestCase):
    def test_stub_returns_derived_unknown(self) -> None:
        out = classify_range_analytics(
            RangeAnalyticsInput(
                range_id=1,
                symbol="XAUUSD",
                structure_layer="WEEKLY",
                source_timeframe="W1",
                range_high=3500.0,
                range_low=2950.0,
                width_points=550.0,
                duration_bars=24,
            )
        )
        self.assertEqual(out.derived_label, DERIVED_UNKNOWN)
        self.assertIn("pending", out.reason_text.lower())


if __name__ == "__main__":
    unittest.main()
