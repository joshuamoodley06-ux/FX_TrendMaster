"""Phase C tests for RANGE_V2 draft suggestion emitter."""

from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from detector.context_window import build_detection_window_meta
from detector.models import DetectionContext, SuggestionDraft, SwingPoint
from detector.normalize import normalize_candles
from detector.range_scale_mode import CANDIDATE_KIND_RANGE, RANGE_SCALE_MODE_LEGACY
from detector.range_candidate import detect_range_suggestions
from detector.range_state import RangeSeedContext
from detector.range_v2 import detect_range_v2_suggestions
from detector.versions import ENGINE_SOURCE, RANGE_V1, RANGE_V2


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


def _swing(index: int, kind: str, price: float, candle) -> SwingPoint:
    return SwingPoint(index=index, kind=kind, price=price, candle=candle)


def _ctx(
    candles,
    *,
    active_index: int,
    seed: RangeSeedContext | None = None,
    range_scale: str = "MAJOR",
    extra_meta: dict | None = None,
) -> DetectionContext:
    active_range_id = seed.active_range_id if seed else 42
    ctx = DetectionContext(
        symbol="XAUUSD",
        source_timeframe="D1",
        candles=candles,
        active_index=active_index,
        range_high=seed.range_high if seed else None,
        range_low=seed.range_low if seed else None,
        range_scale=range_scale,
        active_range_id=active_range_id,
        parent_range_id=10,
        detection_run_id="run-test-001",
        replay_until_time_ms=candles[active_index].time_ms,
        visible_from_time_ms=candles[0].time_ms,
    )
    meta = build_detection_window_meta(ctx, detection_run_id="run-test-001")
    if extra_meta:
        meta.update(extra_meta)
    ctx.detection_window_meta = meta
    return ctx


def _bos_draft(kind: str, index: int, candle, *, suggestion_id: str) -> SuggestionDraft:
    return SuggestionDraft(
        candidate_kind=kind,
        detector_version="BOS_V1",
        candle_index=index,
        candle_time_utc_ms=candle.time_ms,
        meta_json={"suggestion_id": suggestion_id},
    )


def _reclaim_draft(kind: str, index: int, candle, *, suggestion_id: str) -> SuggestionDraft:
    return SuggestionDraft(
        candidate_kind=kind,
        detector_version="RECLAIM_V1",
        candle_index=index,
        candle_time_utc_ms=candle.time_ms,
        meta_json={"suggestion_id": suggestion_id},
    )


REQUIRED_META_KEYS = (
    "detection_run_id",
    "replay_until_time",
    "first_candle_time",
    "last_candle_time",
    "candle_count_used",
    "old_range_id",
    "parent_range_id",
    "broken_boundary",
    "boundary_selection_reason",
    "lifecycle_state",
    "range_scale",
    "range_role",
    "internal_structure_status",
    "engine_source",
)


class NoSeedEmitterTests(unittest.TestCase):
    def test_no_seed_returns_no_valid_range(self) -> None:
        candles = _rows_to_candles([(100, 101, 99, 100)])
        ctx = _ctx(candles, active_index=0)
        out = detect_range_v2_suggestions(ctx, None, [], [], [])
        self.assertEqual(len(out), 1)
        draft = out[0]
        self.assertEqual(draft.candidate_kind, "NO_VALID_RANGE")
        self.assertEqual(draft.detector_version, RANGE_V2)
        self.assertIsNone(draft.suggested_rh)
        self.assertIsNone(draft.suggested_rl)
        self.assertEqual(draft.meta_json["lifecycle_state"], "NO_VALID_RANGE")


class BosWithoutReclaimEmitterTests(unittest.TestCase):
    def test_bos_without_reclaim_returns_breached_lifecycle(self) -> None:
        candles = _rows_to_candles([
            (95, 98, 94, 97),
            (97, 99, 96, 98),
            (98, 102, 97, 101),
            (101, 104, 100.01, 103),  # BOS up held; wick stays above RH
        ])
        seed = RangeSeedContext(range_high=100.0, range_low=90.0, active_range_id=42)
        ctx = _ctx(candles, active_index=3, seed=seed)
        bos = [_bos_draft("BOS_UP", 2, candles[2], suggestion_id="bos-up-1")]
        out = detect_range_v2_suggestions(ctx, seed, bos, [], [])
        self.assertEqual(out[0].candidate_kind, "NO_VALID_RANGE")
        self.assertEqual(out[0].meta_json["lifecycle_state"], "BREACHED_UP")
        self.assertEqual(out[0].meta_json["broken_boundary"], "HIGH")
        self.assertEqual(out[0].meta_json["bos_suggestion_id"], "bos-up-1")


class BullishRangeEmitterTests(unittest.TestCase):
    def _bullish_setup(self):
        # Seed RH=102 so bar 4 (high 101) does not pre-BOS; single clean BOS@5 → reclaim@7 cycle.
        candles = _rows_to_candles([
            (95, 98, 94, 97),
            (97, 99, 96, 98),
            (98, 99, 97, 98),
            (99, 100, 98, 99),
            (99, 101, 98, 100),
            (101, 106, 100, 104),
            (104, 105, 103, 104),
            (103, 104, 102, 103),
            (102, 103, 98, 99),
        ])
        seed = RangeSeedContext(range_high=102.0, range_low=90.0, active_range_id=42)
        swings = [
            _swing(4, "SWING_LOW", 98.0, candles[4]),
            _swing(6, "SWING_LOW", 103.0, candles[6]),
        ]
        bos = [_bos_draft("BOS_UP", 5, candles[5], suggestion_id="bos-up-main")]
        reclaim = [_reclaim_draft("RECLAIM_DOWN", 7, candles[7], suggestion_id="reclaim-down-1")]
        return candles, seed, swings, bos, reclaim

    def test_bullish_bos_reclaim_emits_range_major(self) -> None:
        candles, seed, swings, bos, reclaim = self._bullish_setup()
        ctx = _ctx(candles, active_index=7, seed=seed)
        out = detect_range_v2_suggestions(ctx, seed, bos, reclaim, swings, scale_mode=RANGE_SCALE_MODE_LEGACY)
        self.assertEqual(len(out), 1)
        draft = out[0]
        self.assertEqual(draft.candidate_kind, "RANGE_MAJOR")
        self.assertEqual(draft.detector_version, RANGE_V2)
        self.assertEqual(draft.suggested_rh, 106.0)
        self.assertEqual(draft.suggested_rl, 98.0)
        self.assertEqual(draft.range_role, "ACTIVE_CONTAINER")
        self.assertEqual(
            draft.meta_json["boundary_selection_reason"],
            "STRUCTURAL_SWING_FLOOR_BEFORE_BOS",
        )
        self.assertEqual(draft.meta_json["selected_rl_source"], "STRUCTURAL_SWING")
        self.assertEqual(draft.meta_json["bos_suggestion_id"], "bos-up-main")
        self.assertEqual(draft.meta_json["reclaim_suggestion_id"], "reclaim-down-1")


class BearishRangeEmitterTests(unittest.TestCase):
    def test_bearish_bos_reclaim_emits_range_major(self) -> None:
        candles = _rows_to_candles([
            (95, 98, 94, 97),
            (97, 99, 96, 98),
            (98, 99, 97, 98),
            (97, 98, 96, 97),
            (96, 97, 95, 96),
            (96, 97, 85, 86),
            (86, 88, 84, 85),
            (85, 87, 83, 84),
            (84, 90.5, 83, 89),     # HTF wick reclaim
            (89, 91, 84, 90.5),     # body close inside
        ])
        seed = RangeSeedContext(range_high=100.0, range_low=90.0, active_range_id=42)
        swings = [_swing(6, "SWING_HIGH", 88.0, candles[6])]
        bos = [_bos_draft("BOS_DOWN", 7, candles[7], suggestion_id="bos-down-main")]
        reclaim = [_reclaim_draft("RECLAIM_UP", 8, candles[8], suggestion_id="reclaim-up-1")]
        ctx = _ctx(candles, active_index=8, seed=seed)
        out = detect_range_v2_suggestions(ctx, seed, bos, reclaim, swings, scale_mode=RANGE_SCALE_MODE_LEGACY)
        draft = out[0]
        self.assertEqual(draft.candidate_kind, "RANGE_MAJOR")
        self.assertEqual(draft.suggested_rl, 83.0)
        self.assertEqual(draft.suggested_rh, 88.0)


class UnclearOppositeSwingEmitterTests(unittest.TestCase):
    def test_no_swings_still_emits_seed_anchored_range(self) -> None:
        candles = _rows_to_candles([
            (95, 98, 94, 97),
            (98, 106, 97, 104),
            (104, 105, 99.5, 102),
        ])
        seed = RangeSeedContext(range_high=100.0, range_low=90.0, active_range_id=42)
        ctx = _ctx(candles, active_index=2, seed=seed)
        out = detect_range_v2_suggestions(ctx, seed, [], [], [])
        self.assertIn(out[0].candidate_kind, {"RANGE_MAJOR", "RANGE_CANDIDATE", CANDIDATE_KIND_RANGE})
        self.assertEqual(out[0].meta_json["selected_rl_source"], "SEED_ANCHORED")
        self.assertAlmostEqual(float(out[0].suggested_rl), 90.0, delta=0.01)


class NoMinorStructureEmitterTests(unittest.TestCase):
    def test_no_minor_structure_emits_correct_kind_status_role(self) -> None:
        candles = _rows_to_candles([
            (95, 98, 94, 97),
            (97, 99, 96, 98),
            (98, 99, 97, 98),
            (99, 100, 98, 99),
            (99, 101, 98, 100),
            (101, 106, 100, 104),
            (104, 105, 103, 104),
            (103, 104, 102, 103),
            (102, 103, 98, 99),
        ])
        seed = RangeSeedContext(range_high=102.0, range_low=90.0, active_range_id=42)
        swings = [
            _swing(4, "SWING_LOW", 98.0, candles[4]),
            _swing(6, "SWING_LOW", 103.0, candles[6]),
        ]
        ctx = _ctx(
            candles,
            active_index=7,
            seed=seed,
            extra_meta={"internal_structure_status": "NO_MINOR_STRUCTURE"},
        )
        out = detect_range_v2_suggestions(
            ctx, seed, [], [], swings, scale_mode=RANGE_SCALE_MODE_LEGACY,
        )
        draft = out[0]
        self.assertEqual(draft.candidate_kind, "NO_MINOR_STRUCTURE")
        self.assertEqual(draft.range_role, "EXPANSION_LEG")
        self.assertEqual(draft.meta_json["internal_structure_status"], "NO_MINOR_STRUCTURE")
        self.assertEqual(draft.suggested_rh, 106.0)
        self.assertEqual(draft.suggested_rl, 98.0)


class MetaJsonEmitterTests(unittest.TestCase):
    def test_meta_json_contains_required_replay_and_lifecycle_fields(self) -> None:
        candles = _rows_to_candles([
            (95, 98, 94, 97),
            (97, 99, 96, 98),
            (98, 99, 97, 98),
            (99, 100, 98, 99),
            (99, 101, 98, 100),
            (101, 106, 100, 104),
            (104, 105, 103, 104),
            (103, 104, 102, 103),
            (102, 103, 98, 99),
        ])
        seed = RangeSeedContext(range_high=102.0, range_low=90.0, active_range_id=42)
        swings = [
            _swing(4, "SWING_LOW", 98.0, candles[4]),
            _swing(6, "SWING_LOW", 103.0, candles[6]),
        ]
        bos = [_bos_draft("BOS_UP", 5, candles[5], suggestion_id="bos-meta")]
        reclaim = [_reclaim_draft("RECLAIM_DOWN", 7, candles[7], suggestion_id="reclaim-meta")]
        ctx = _ctx(candles, active_index=7, seed=seed)
        out = detect_range_v2_suggestions(ctx, seed, bos, reclaim, swings, scale_mode=RANGE_SCALE_MODE_LEGACY)
        meta = out[0].meta_json

        for key in REQUIRED_META_KEYS:
            self.assertIn(key, meta, msg=f"missing meta key: {key}")

        self.assertEqual(meta["detection_run_id"], "run-test-001")
        self.assertEqual(meta["engine_source"], ENGINE_SOURCE)
        self.assertEqual(meta["old_range_id"], 42)
        self.assertEqual(meta["parent_range_id"], 10)
        self.assertEqual(meta["bos_suggestion_id"], "bos-meta")
        self.assertEqual(meta["reclaim_suggestion_id"], "reclaim-meta")
        self.assertEqual(meta["opposite_swing_index"], 4)
        self.assertEqual(meta["selected_rl_source"], "STRUCTURAL_SWING")
        self.assertIsNotNone(meta.get("visible_from_time_ms"))
        self.assertIsNotNone(meta.get("replay_until_time_ms"))


class MarketTimeMetadataTests(unittest.TestCase):
    def test_range_major_includes_bos_and_reclaim_market_times(self) -> None:
        candles = _rows_to_candles([
            (95, 98, 94, 97),
            (97, 99, 96, 98),
            (98, 99, 97, 98),
            (99, 100, 98, 99),
            (99, 101, 98, 100),
            (101, 106, 100, 104),
            (104, 105, 103, 104),
            (103, 104, 102, 103),
            (102, 103, 98, 99),
        ])
        seed = RangeSeedContext(range_high=102.0, range_low=90.0, active_range_id=42)
        swings = [
            _swing(4, "SWING_LOW", 98.0, candles[4]),
            _swing(6, "SWING_LOW", 103.0, candles[6]),
        ]
        bos = [_bos_draft("BOS_UP", 5, candles[5], suggestion_id="bos-mt")]
        reclaim = [_reclaim_draft("RECLAIM_DOWN", 7, candles[7], suggestion_id="reclaim-mt")]
        ctx = _ctx(candles, active_index=7, seed=seed)
        out = detect_range_v2_suggestions(ctx, seed, bos, reclaim, swings, scale_mode=RANGE_SCALE_MODE_LEGACY)
        meta = out[0].meta_json

        self.assertEqual(meta.get("candle_index_scope"), "replay_window")
        self.assertEqual(meta.get("bos_time_ms"), candles[5].time_ms)
        self.assertEqual(meta.get("reclaim_time_ms"), candles[7].time_ms)
        self.assertEqual(meta.get("bos_candle_index"), 5)
        self.assertEqual(meta.get("reclaim_candle_index"), 7)
        self.assertNotEqual(meta.get("bos_candle_index"), 103)

    def test_structural_boundaries_include_boundary_market_times(self) -> None:
        candles = _rows_to_candles([
            (95, 98, 94, 97),
            (97, 99, 96, 98),
            (98, 99, 97, 98),
            (99, 100, 98, 99),
            (99, 101, 98, 100),
            (101, 106, 100, 104),
            (104, 112, 103, 111),
            (111, 112, 98, 99),
        ])
        seed = RangeSeedContext(range_high=102.0, range_low=90.0, active_range_id=42)
        swings = [
            _swing(4, "SWING_LOW", 98.0, candles[4]),
            _swing(6, "SWING_HIGH", 112.0, candles[6]),
        ]
        bos = [_bos_draft("BOS_UP", 5, candles[5], suggestion_id="bos-mt2")]
        reclaim = [_reclaim_draft("RECLAIM_DOWN", 7, candles[7], suggestion_id="reclaim-mt2")]
        ctx = _ctx(candles, active_index=7, seed=seed)
        out = detect_range_v2_suggestions(ctx, seed, bos, reclaim, swings, scale_mode=RANGE_SCALE_MODE_LEGACY)
        meta = out[0].meta_json

        self.assertEqual(meta.get("rh_boundary_time_ms"), candles[6].time_ms)
        self.assertEqual(meta.get("rl_boundary_time_ms"), candles[4].time_ms)
        self.assertIsNotNone(meta.get("rh_boundary_time"))
        self.assertIsNotNone(meta.get("rl_boundary_time"))


class EmitterIsolationTests(unittest.TestCase):
    def test_emitter_does_not_import_writer_or_touch_db(self) -> None:
        import detector.range_v2 as range_v2_mod

        source = inspect.getsource(range_v2_mod)
        self.assertNotIn("writer", source)
        self.assertNotIn("sqlite", source.lower())
        self.assertNotIn("map_ranges", source)
        self.assertNotIn("map_events", source)

        candles = _rows_to_candles([(95, 98, 94, 97)])
        seed = RangeSeedContext(range_high=100.0, range_low=90.0)
        ctx = _ctx(candles, active_index=0, seed=seed)

        with patch("detection_brain_store.insert_suggestion") as insert_mock:
            with patch("detector.writer.write_suggestions") as write_mock:
                detect_range_v2_suggestions(ctx, seed, [], [], [])
        insert_mock.assert_not_called()
        write_mock.assert_not_called()


class RangeV1UntouchedTests(unittest.TestCase):
    def test_range_v1_still_emits_swing_pair_suggestion(self) -> None:
        rows = [
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
        candles = _rows_to_candles(rows)
        swings = [
            _swing(2, "SWING_LOW", 98.0, candles[2]),
            _swing(7, "SWING_HIGH", 110.0, candles[7]),
        ]
        ctx = DetectionContext(
            symbol="XAUUSD",
            source_timeframe="D1",
            candles=candles,
            active_index=len(candles) - 1,
            range_scale="MAJOR",
            swings=swings,
        )
        out = detect_range_suggestions(ctx, scale_mode=RANGE_SCALE_MODE_LEGACY)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].detector_version, RANGE_V1)
        self.assertEqual(out[0].candidate_kind, "RANGE_MAJOR")
        self.assertEqual(out[0].suggested_rh, 110.0)
        self.assertEqual(out[0].suggested_rl, 98.0)


if __name__ == "__main__":
    unittest.main()
