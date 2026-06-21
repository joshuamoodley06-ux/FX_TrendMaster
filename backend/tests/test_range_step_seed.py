"""Tests for unified range step seed resolution."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from detector.models import DetectionContext
from detector.range_state import RangeSeedContext
from detector.range_step_seed import (
    SEED_SOURCE_BOOTSTRAP,
    SEED_SOURCE_ROLLED,
    resolve_range_step_seed,
)
from tests.test_historical_range_chain import _chain_fixture_rows, _candles_from_rows


class RangeStepSeedTests(unittest.TestCase):
    def _ctx_at(self, index: int) -> DetectionContext:
        candles = _candles_from_rows(_chain_fixture_rows())
        return DetectionContext(
            symbol="XAUUSD",
            source_timeframe="W1",
            structure_layer="WEEKLY",
            candles=candles,
            active_index=index,
        )

    def test_bootstrap_when_no_working_seed(self) -> None:
        ctx = self._ctx_at(8)
        result = resolve_range_step_seed(ctx, discovery_mode=True)
        self.assertIsNotNone(result.seed)
        self.assertEqual(result.seed_source, SEED_SOURCE_BOOTSTRAP)

    def test_rolled_seed_beats_bootstrap(self) -> None:
        ctx = self._ctx_at(8)
        rolled = RangeSeedContext(range_high=110.0, range_low=95.0)
        result = resolve_range_step_seed(ctx, working_seed=rolled, discovery_mode=True)
        self.assertEqual(result.seed_source, SEED_SOURCE_ROLLED)
        assert result.seed is not None
        self.assertEqual(result.seed.range_high, 110.0)

    def test_stale_chart_seed_skipped_for_bootstrap(self) -> None:
        ctx = self._ctx_at(8)
        payload = {"range_high": 50.0, "range_low": 40.0}
        result = resolve_range_step_seed(ctx, payload=payload, discovery_mode=True)
        self.assertEqual(result.seed_source, SEED_SOURCE_BOOTSTRAP)


if __name__ == "__main__":
    unittest.main()
