"""Phase D tests — DETECTOR_RANGE_MODE pipeline integration."""

from __future__ import annotations

import inspect
import os
import sys
import unittest
import warnings
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from detector.ohlc_loader import build_context
from detector.pipeline import run_detector_v1
from detector.range_mode import (
    DEFAULT_RANGE_MODE,
    RANGE_MODE_DOCTRINE_V2,
    RANGE_MODE_SMOKE_V1,
    resolve_range_mode,
)
from detector.range_v2 import detect_range_v2_suggestions
from detector.versions import RANGE_V1, RANGE_V2


def _swing_sequence() -> list[tuple[float, float, float, float]]:
    return [
        (102, 104, 100, 101),
        (101, 103, 99, 100),
        (100, 102, 98, 99),
        (99, 101, 97, 98),
        (98, 100, 96, 99),
        (99, 103, 98, 102),
        (102, 106, 101, 105),
        (105, 110, 104, 108),
        (108, 112, 107, 111),
        (111, 113, 109, 110),
    ]


def _candles_from_rows(rows: list[tuple[float, float, float, float]]) -> list[dict]:
    out = []
    base_ms = 1_700_000_000_000
    for i, (o, h, l, c) in enumerate(rows):
        out.append(
            {
                "time_ms": base_ms + i * 86_400_000,
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "volume": 100,
            }
        )
    return out


def _ctx_with_range(*, active_index: int, active_range_id: int | None = 42) -> object:
    rows = _swing_sequence()
    return build_context(
        symbol="XAUUSD",
        source_timeframe="D1",
        candles=_candles_from_rows(rows),
        active_index=active_index,
        range_high=110.0,
        range_low=97.0,
        active_range_id=active_range_id,
        parent_range_id=10,
    )


class DefaultModeTests(unittest.TestCase):
    def test_default_mode_uses_range_v1(self) -> None:
        ctx = _ctx_with_range(active_index=len(_swing_sequence()) - 1)
        result = run_detector_v1(ctx)
        self.assertEqual(result.range_mode, RANGE_MODE_SMOKE_V1)
        self.assertEqual(result.detector_versions["RANGE"], RANGE_V1)
        range_drafts = [
            d
            for d in result.drafts
            if d.candidate_kind in ("RANGE_MAJOR", "RANGE_MINOR", "RANGE_CANDIDATE", "NO_VALID_RANGE", "NO_MINOR_STRUCTURE")
        ]
        for draft in range_drafts:
            self.assertEqual(draft.detector_version, RANGE_V1)

    @patch.dict(os.environ, {}, clear=True)
    def test_unset_env_defaults_to_smoke_v1(self) -> None:
        os.environ.pop("DETECTOR_RANGE_MODE", None)
        self.assertEqual(resolve_range_mode(), RANGE_MODE_SMOKE_V1)


class DoctrineV2ModeTests(unittest.TestCase):
    def test_doctrine_v2_does_not_call_range_v1(self) -> None:
        ctx = _ctx_with_range(active_index=len(_swing_sequence()) - 1)
        with patch("detector.pipeline.detect_range_suggestions") as range_v1_mock:
            result = run_detector_v1(ctx, range_mode=RANGE_MODE_DOCTRINE_V2)
        range_v1_mock.assert_not_called()
        self.assertEqual(result.detector_versions["RANGE"], RANGE_V2)

    def test_doctrine_v2_without_seed_emits_no_valid_range(self) -> None:
        ctx = _ctx_with_range(active_index=len(_swing_sequence()) - 1, active_range_id=None)
        result = run_detector_v1(ctx, range_mode=RANGE_MODE_DOCTRINE_V2)
        range_drafts = [
            d
            for d in result.drafts
            if d.detector_version == RANGE_V2
            and d.candidate_kind in ("RANGE_MAJOR", "RANGE_MINOR", "NO_VALID_RANGE", "NO_MINOR_STRUCTURE")
        ]
        self.assertEqual(len(range_drafts), 1)
        draft = range_drafts[0]
        self.assertEqual(draft.candidate_kind, "NO_VALID_RANGE")
        self.assertTrue(draft.meta_json.get("no_seed_context"))
        self.assertEqual(draft.meta_json.get("lifecycle_state"), "NO_VALID_RANGE")

    def test_doctrine_v2_suggestions_use_range_v2_version(self) -> None:
        ctx = _ctx_with_range(active_index=len(_swing_sequence()) - 1, active_range_id=None)
        result = run_detector_v1(ctx, range_mode=RANGE_MODE_DOCTRINE_V2)
        range_drafts = [d for d in result.drafts if d.detector_version == RANGE_V2]
        self.assertGreaterEqual(len(range_drafts), 1)


class SmokeV1VersionTests(unittest.TestCase):
    def test_smoke_v1_range_suggestions_keep_range_v1_version(self) -> None:
        ctx = _ctx_with_range(active_index=len(_swing_sequence()) - 1)
        result = run_detector_v1(ctx, range_mode=RANGE_MODE_SMOKE_V1)
        range_drafts = [d for d in result.drafts if d.candidate_kind.startswith("RANGE_")]
        if range_drafts:
            self.assertEqual(range_drafts[0].detector_version, RANGE_V1)


class PipelineIsolationTests(unittest.TestCase):
    def test_doctrine_v2_does_not_mutate_map_tables(self) -> None:
        ctx = _ctx_with_range(active_index=len(_swing_sequence()) - 1, active_range_id=None)
        import detector.pipeline as pipeline_mod

        pipeline_source = inspect.getsource(pipeline_mod)
        self.assertNotIn("map_ranges", pipeline_source)
        self.assertNotIn("map_events", pipeline_source)

        with patch("detection_brain_store.insert_suggestion") as insert_mock:
            with patch("detector.writer.write_suggestions") as write_mock:
                run_detector_v1(ctx, range_mode=RANGE_MODE_DOCTRINE_V2)
        insert_mock.assert_not_called()
        write_mock.assert_not_called()


class UnknownModeTests(unittest.TestCase):
    def test_unknown_mode_defaults_to_smoke_v1_with_warning(self) -> None:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            mode = resolve_range_mode("not_a_real_mode")
        self.assertEqual(mode, DEFAULT_RANGE_MODE)
        self.assertEqual(mode, RANGE_MODE_SMOKE_V1)
        self.assertTrue(any("Unknown DETECTOR_RANGE_MODE" in str(w.message) for w in caught))

    @patch.dict(os.environ, {"DETECTOR_RANGE_MODE": "bogus"}, clear=False)
    def test_unknown_env_mode_runs_smoke_v1_pipeline(self) -> None:
        ctx = _ctx_with_range(active_index=len(_swing_sequence()) - 1)
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            result = run_detector_v1(ctx)
        self.assertEqual(result.range_mode, RANGE_MODE_SMOKE_V1)
        self.assertEqual(result.detector_versions["RANGE"], RANGE_V1)


class RangeV2EmitterStrictSeedTests(unittest.TestCase):
    def test_strict_seed_blocks_ctx_range_fallback(self) -> None:
        ctx = _ctx_with_range(active_index=len(_swing_sequence()) - 1, active_range_id=None)
        out = detect_range_v2_suggestions(ctx, None, [], [], [], strict_seed=True)
        self.assertEqual(out[0].candidate_kind, "NO_VALID_RANGE")
        self.assertTrue(out[0].meta_json.get("no_seed_context"))


if __name__ == "__main__":
    unittest.main()
