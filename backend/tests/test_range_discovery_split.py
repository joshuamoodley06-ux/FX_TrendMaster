"""Discovery vs persistence split for promoted-range historical replay."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from detector.context_window import build_detection_window_meta
from detector.historical_range_chain import BootstrapEvaluationResult
from detector.models import DetectionContext, SuggestionDraft, SwingPoint
from detector.normalize import normalize_candles
from detector.range_scale_mode import RANGE_SCALE_MODE_LEGACY
from detector.range_seed import (
    DISCOVERY_SOURCE_LOCAL_ACTIVE_REPLAY,
    DISCOVERY_SOURCE_PROMOTED_SEED_LIFECYCLE,
    SEED_SOURCE_PROMOTED_RANGE,
)
from detector.range_state import RangeSeedContext
from detector.range_v2 import detect_range_v2_suggestions


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


def _promoted_ctx(
    candles,
    *,
    active_index: int,
    seed: RangeSeedContext,
    extra_meta: dict | None = None,
) -> DetectionContext:
    seed = RangeSeedContext(
        range_high=seed.range_high,
        range_low=seed.range_low,
        active_range_id=seed.active_range_id,
        seed_source=SEED_SOURCE_PROMOTED_RANGE,
    )
    ctx = DetectionContext(
        symbol="XAUUSD",
        source_timeframe="D1",
        candles=candles,
        active_index=active_index,
        range_high=seed.range_high,
        range_low=seed.range_low,
        range_scale="MAJOR",
        active_range_id=seed.active_range_id,
        parent_range_id=10,
        detection_run_id="discovery-split-test",
        replay_until_time_ms=candles[active_index].time_ms,
        visible_from_time_ms=candles[0].time_ms,
        range_seed=seed,
        range_seed_meta={
            "seed_source": SEED_SOURCE_PROMOTED_RANGE,
            "seed_rh": seed.range_high,
            "seed_rl": seed.range_low,
            "seed_policy": "reviewed_truth_only",
        },
    )
    meta = build_detection_window_meta(ctx, detection_run_id="discovery-split-test")
    meta["max_reclaim_lag_bars"] = 1
    meta["historical_scan"] = True
    if extra_meta:
        meta.update(extra_meta)
    ctx.detection_window_meta = meta
    return ctx


def _stale_promoted_fixture():
    """Promoted seed lifecycle completes reclaim @7; active week @10 is stale (lag=1)."""
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
        (99, 101, 98, 100),
        (100, 102, 99, 101),
    ])
    seed = RangeSeedContext(range_high=102.0, range_low=90.0, active_range_id=42)
    swings = [
        _swing(4, "SWING_LOW", 98.0, candles[4]),
        _swing(6, "SWING_LOW", 103.0, candles[6]),
    ]
    bos = [_bos_draft("BOS_UP", 5, candles[5], suggestion_id="bos-up-main")]
    reclaim = [_reclaim_draft("RECLAIM_DOWN", 7, candles[7], suggestion_id="reclaim-down-1")]
    return candles, seed, swings, bos, reclaim


class StalePromotedDoesNotEmitDirectlyTests(unittest.TestCase):
    @patch("detector.range_v2._reclaim_cycle_is_fresh", return_value=False)
    @patch("detector.range_discovery_split.evaluate_bootstrap_candidates")
    def test_stale_promoted_cycle_blocked_without_local_match(self, mock_boot, _mock_fresh) -> None:
        candles, seed, swings, bos, reclaim = _stale_promoted_fixture()
        ctx = _promoted_ctx(candles, active_index=10, seed=seed)
        mock_boot.return_value = BootstrapEvaluationResult(seed=None, trace=None)

        out = detect_range_v2_suggestions(
            ctx, seed, bos, reclaim, swings, scale_mode=RANGE_SCALE_MODE_LEGACY
        )
        self.assertEqual(len(out), 1)
        draft = out[0]
        self.assertEqual(draft.candidate_kind, "NO_VALID_RANGE")
        meta = draft.meta_json
        self.assertTrue(meta.get("stale_context_rejected"))
        self.assertTrue(meta.get("local_discovery_attempted"))
        self.assertEqual(meta.get("context_seed_source"), SEED_SOURCE_PROMOTED_RANGE)
        self.assertNotEqual(meta.get("discovery_source"), DISCOVERY_SOURCE_PROMOTED_SEED_LIFECYCLE)
        self.assertIn("Promoted context reclaim stale", draft.reason_text or "")
        mock_boot.assert_called_once()

    @patch("detector.range_v2._reclaim_cycle_is_fresh", return_value=False)
    def test_stale_non_promoted_still_uses_plain_stale_gate(self, _mock_fresh) -> None:
        candles, seed, swings, bos, reclaim = _stale_promoted_fixture()
        ctx = DetectionContext(
            symbol="XAUUSD",
            source_timeframe="D1",
            candles=candles,
            active_index=10,
            range_high=seed.range_high,
            range_low=seed.range_low,
            range_scale="MAJOR",
            active_range_id=42,
            detection_run_id="discovery-split-test",
            replay_until_time_ms=candles[10].time_ms,
            visible_from_time_ms=candles[0].time_ms,
        )
        meta = build_detection_window_meta(ctx, detection_run_id="discovery-split-test")
        meta["max_reclaim_lag_bars"] = 1
        ctx.detection_window_meta = meta

        out = detect_range_v2_suggestions(
            ctx, seed, bos, reclaim, swings, scale_mode=RANGE_SCALE_MODE_LEGACY
        )
        self.assertEqual(out[0].candidate_kind, "NO_VALID_RANGE")
        self.assertEqual(out[0].reason_text, "Reclaim cycle completed before active replay week")
        self.assertFalse(out[0].meta_json.get("local_discovery_attempted"))


class LocalDiscoveryEmitsWhenAvailableTests(unittest.TestCase):
    @patch("detector.range_discovery_split._reclaim_cycle_is_fresh", return_value=True)
    @patch("detector.range_v2._reclaim_cycle_is_fresh", return_value=False)
    @patch("detector.range_discovery_split.evaluate_bootstrap_candidates")
    def test_stale_promoted_with_local_cycle_emits_local(self, mock_boot, _mock_v2_fresh, _mock_split_fresh) -> None:
        candles, seed, swings, bos, reclaim = _stale_promoted_fixture()
        ctx = _promoted_ctx(candles, active_index=10, seed=seed)

        discovery_seed = RangeSeedContext(
            range_high=106.0,
            range_low=98.0,
            active_range_id=None,
            seed_source="bootstrap_candidate",
        )
        mock_boot.return_value = BootstrapEvaluationResult(seed=discovery_seed, trace=None)

        out = detect_range_v2_suggestions(
            ctx, seed, bos, reclaim, swings, scale_mode=RANGE_SCALE_MODE_LEGACY
        )
        self.assertEqual(len(out), 1)
        draft = out[0]
        self.assertIn(
            draft.candidate_kind,
            {"RANGE_MAJOR", "RANGE_CANDIDATE", "NO_MINOR_STRUCTURE"},
        )
        meta = draft.meta_json
        self.assertEqual(meta.get("discovery_source"), DISCOVERY_SOURCE_LOCAL_ACTIVE_REPLAY)
        self.assertTrue(meta.get("stale_context_rejected"))
        self.assertEqual(meta.get("local_discovery_result"), "RANGE_CANDIDATE")
        self.assertEqual(meta.get("context_seed_source"), SEED_SOURCE_PROMOTED_RANGE)
        self.assertEqual(meta.get("context_seed_rh"), seed.range_high)
        self.assertEqual(meta.get("context_seed_rl"), seed.range_low)


class FreshPromotedLifecycleTests(unittest.TestCase):
    def test_fresh_promoted_emits_with_promoted_seed_lifecycle_metadata(self) -> None:
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
        ctx = _promoted_ctx(candles, active_index=7, seed=seed)

        out = detect_range_v2_suggestions(
            ctx, seed, bos, reclaim, swings, scale_mode=RANGE_SCALE_MODE_LEGACY
        )
        self.assertIn(
            out[0].candidate_kind,
            {"RANGE_MAJOR", "RANGE_CANDIDATE", "NO_MINOR_STRUCTURE"},
        )
        meta = out[0].meta_json
        self.assertEqual(meta.get("discovery_source"), DISCOVERY_SOURCE_PROMOTED_SEED_LIFECYCLE)
        self.assertFalse(meta.get("stale_context_rejected"))
        self.assertFalse(meta.get("local_discovery_attempted"))


class W1StaleWeekIntegrationTests(unittest.TestCase):
    """Replay 2025 stale weeks against local W1 candles when DB is available."""

    STALE_WEEKS = (
        "2025-06-08",
        "2025-06-15",
        "2025-06-29",
        "2025-07-06",
        "2025-07-13",
    )

    @classmethod
    def setUpClass(cls) -> None:
        cls.candles = cls._load_candles()
        if cls.candles is None:
            return
        from tests.detector_audit_fixture import build_gold_rows, load_audit_fixture, _rh_rl_from_snapshot

        baseline = load_audit_fixture()
        corrections = {c["suggestion_id"]: c for c in baseline.get("corrections") or []}
        weeks = sorted(baseline.get("suggestions") or [], key=lambda s: int(s["replay_until_time_ms"]))
        cls.promoted_chain: dict[str, tuple[float, float]] = {}
        for i, suggestion in enumerate(weeks):
            if i == 0:
                continue
            week = str(suggestion["replay_until_time"])
            prev = weeks[i - 1]
            corr = corrections.get(str(prev["suggestion_id"]))
            if corr and corr.get("final_snapshot_json"):
                rh, rl = _rh_rl_from_snapshot(corr["final_snapshot_json"])
                if rh is not None and rl is not None:
                    cls.promoted_chain[week] = (rh, rl)
        cls.rows = {r.week: r for r in build_gold_rows(baseline)}

    @staticmethod
    def _load_candles():
        from pathlib import Path

        import candle_store

        for db in (
            Path.home() / "Documents" / "FXTM_Research" / "raw_mapping_v159.db",
            BACKEND_DIR / "data" / "raw_mapping_v159.db",
        ):
            if not db.is_file():
                continue
            candle_store.DB_PATH = db
            candle_store.init_db()
            payload = candle_store.get_candles(symbol="XAUUSD", timeframe="W1", limit=5000)
            candles = list(payload.get("candles") or [])
            if len(candles) >= 200:
                return candles
        return None

    def setUp(self) -> None:
        if self.candles is None:
            self.skipTest("local W1 candle DB not available")

    def test_stale_weeks_never_emit_stale_promoted_lifecycle_directly(self) -> None:
        from detector.range_mode import RANGE_MODE_DOCTRINE_V2
        from detector.pipeline import run_detector_v1
        from detector.range_scan_runner import SCAN_MAX_RECLAIM_LAG_BARS
        from tests.detector_audit_fixture import range_candidate_from_result, replay_context_for_week

        for week in self.STALE_WEEKS:
            row = self.rows[week]
            ctx, _ = replay_context_for_week(all_candles=self.candles, row=row)
            rh, rl = self.promoted_chain[week]
            seed = RangeSeedContext(
                range_high=rh,
                range_low=rl,
                seed_source=SEED_SOURCE_PROMOTED_RANGE,
            )
            ctx.range_seed = seed
            ctx.range_high = rh
            ctx.range_low = rl
            ctx.range_seed_meta = {
                "seed_source": SEED_SOURCE_PROMOTED_RANGE,
                "seed_rh": rh,
                "seed_rl": rl,
                "seed_policy": "reviewed_truth_only",
            }
            if row.meta_json.get("date_from_ms"):
                ctx.detection_window_meta["min_reclaim_time_ms"] = row.meta_json["date_from_ms"]
            ctx.detection_window_meta["max_reclaim_lag_bars"] = SCAN_MAX_RECLAIM_LAG_BARS

            result = run_detector_v1(ctx, range_mode=RANGE_MODE_DOCTRINE_V2)
            range_draft = range_candidate_from_result(result)
            no_valid = next(
                (d for d in result.drafts if d.candidate_kind == "NO_VALID_RANGE"),
                None,
            )
            if range_draft is not None:
                meta = range_draft.meta_json or {}
                self.assertNotEqual(
                    meta.get("discovery_source"),
                    DISCOVERY_SOURCE_PROMOTED_SEED_LIFECYCLE,
                    msg=f"{week} emitted stale promoted lifecycle",
                )
                if meta.get("stale_context_rejected"):
                    self.assertEqual(
                        meta.get("discovery_source"),
                        DISCOVERY_SOURCE_LOCAL_ACTIVE_REPLAY,
                    )
            elif no_valid is not None:
                meta = no_valid.meta_json or {}
                self.assertTrue(meta.get("stale_context_rejected") or "stale" in (no_valid.reason_text or "").lower())


if __name__ == "__main__":
    unittest.main()
