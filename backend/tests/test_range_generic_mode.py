"""Generic range scale mode — no auto major/minor classification."""

from __future__ import annotations

import gc
import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import candle_store
from detection_brain_promotion import review_suggestion
from detection_brain_schema import init_detection_brain_schema
from detection_brain_store import DetectorSuggestion, insert_suggestion, utc_now_ms
from detector.models import DetectionContext, SwingPoint
from detector.normalize import normalize_candles
from detector.period_scan import collect_period_range_candidates
from detector.pipeline import run_detector_v1
from detector.range_candidate import detect_range_suggestions
from detector.range_scale_mode import (
    CANDIDATE_KIND_RANGE,
    RANGE_SCALE_MODE_LEGACY,
    RANGE_SCALE_UNKNOWN,
)
from detector.versions import ENGINE_SOURCE, RANGE_V1


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


class GenericRangeModeTests(unittest.TestCase):
    MAJOR_RH = 3499.88
    MAJOR_RL = 2956.66
    MINOR_RH = 3430.86
    MINOR_RL = 3120.81

    def setUp(self) -> None:
        rows = [(3300.0, 3305.0, 3295.0, 3300.0)] * 12
        self.candles = _rows_to_candles(rows)
        self.active_index = len(self.candles) - 1
        self.swings = [
            _swing(1, "SWING_LOW", self.MAJOR_RL, self.candles[1]),
            _swing(3, "SWING_HIGH", self.MAJOR_RH, self.candles[3]),
            _swing(7, "SWING_LOW", self.MINOR_RL, self.candles[7]),
            _swing(9, "SWING_HIGH", self.MINOR_RH, self.candles[9]),
        ]

    def test_generic_emits_range_candidate_not_major_minor(self) -> None:
        ctx = DetectionContext(
            symbol="XAUUSD",
            source_timeframe="W1",
            candles=self.candles,
            active_index=self.active_index,
            range_scale=RANGE_SCALE_UNKNOWN,
            swings=self.swings,
        )
        out = detect_range_suggestions(ctx)
        self.assertGreaterEqual(len(out), 2)
        kinds = {d.candidate_kind for d in out}
        self.assertIn(CANDIDATE_KIND_RANGE, kinds)
        self.assertFalse(kinds & {"RANGE_MAJOR", "RANGE_MINOR"})
        for draft in out:
            self.assertEqual(draft.range_scale, RANGE_SCALE_UNKNOWN)
            self.assertIsNone(draft.range_role)

    def test_legacy_mode_still_classifies_major_minor(self) -> None:
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
        self.assertEqual(out[0].candidate_kind, "RANGE_MAJOR")

    def test_pipeline_generic_default(self) -> None:
        ctx = DetectionContext(
            symbol="XAUUSD",
            source_timeframe="W1",
            candles=self.candles,
            active_index=self.active_index,
            swings=self.swings,
        )
        result = run_detector_v1(ctx)
        range_drafts = [d for d in result.drafts if d.primitive == "RANGE"]
        self.assertTrue(range_drafts)
        self.assertTrue(all(d.candidate_kind == CANDIDATE_KIND_RANGE for d in range_drafts))

    def test_period_scan_collects_multiple_candidates(self) -> None:
        ctx = DetectionContext(
            symbol="XAUUSD",
            source_timeframe="W1",
            candles=self.candles,
            active_index=self.active_index,
            swings=self.swings,
        )
        collected = collect_period_range_candidates(
            ctx,
            date_from_ms=self.candles[0].time_ms,
            date_to_ms=self.candles[-1].time_ms,
        )
        self.assertGreaterEqual(len(collected), 2)
        self.assertTrue(all(d.candidate_kind == CANDIDATE_KIND_RANGE for d in collected))


class GenericPromotionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db_path = Path(__file__).resolve().parent / "_generic_promotion.db"
        if self.db_path.exists():
            self.db_path.unlink()
        self.old_path = candle_store.DB_PATH
        candle_store.DB_PATH = self.db_path
        candle_store.init_db()
        self.conn = __import__("sqlite3").connect(self.db_path)
        self.conn.row_factory = __import__("sqlite3").Row
        init_detection_brain_schema(self.conn)
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()
        candle_store.DB_PATH = self.old_path
        gc.collect()
        if self.db_path.exists():
            self.db_path.unlink(missing_ok=True)

    def _insert(self, suggestion_id: str, *, scale: str = RANGE_SCALE_UNKNOWN) -> None:
        now = utc_now_ms()
        insert_suggestion(
            self.conn,
            DetectorSuggestion(
                suggestion_id=suggestion_id,
                detector_version=RANGE_V1,
                engine_source=ENGINE_SOURCE,
                candidate_kind=CANDIDATE_KIND_RANGE,
                symbol="XAUUSD",
                structure_layer="WEEKLY",
                source_timeframe="W1",
                chart_timeframe="W1",
                candle_time_utc_ms=now,
                created_at_utc_ms=now,
                suggested_rh=3499.88,
                suggested_rl=2956.66,
                range_scale=scale,
            ),
        )
        self.conn.commit()

    def test_approve_unknown_scale_stores_unknown(self) -> None:
        self._insert("sug-unknown-1")
        out = review_suggestion(self.conn, "sug-unknown-1", action="APPROVE")
        self.assertTrue(out["ok"])
        row = self.conn.execute(
            "SELECT range_scale, range_scope FROM map_ranges WHERE id = ?",
            (out["promoted_range_id"],),
        ).fetchone()
        self.assertEqual(row["range_scale"], "UNKNOWN")

    def test_approve_always_stores_unknown_even_if_edit_requests_major(self) -> None:
        self._insert("sug-force-unknown-1")
        out = review_suggestion(
            self.conn,
            "sug-force-unknown-1",
            action="EDIT",
            edits={"range_scale": "MAJOR", "range_role": "ACTIVE_CONTAINER"},
        )
        self.assertTrue(out["ok"])
        row = self.conn.execute(
            "SELECT range_scale, range_role FROM map_ranges WHERE id = ?",
            (out["promoted_range_id"],),
        ).fetchone()
        self.assertEqual(row["range_scale"], "UNKNOWN")
        self.assertIsNone(row["range_role"])

    def test_approve_plain_confirm_stores_unknown(self) -> None:
        self._insert("sug-plain-1")
        out = review_suggestion(self.conn, "sug-plain-1", action="APPROVE")
        self.assertTrue(out["ok"])
        row = self.conn.execute(
            "SELECT range_scale FROM map_ranges WHERE id = ?",
            (out["promoted_range_id"],),
        ).fetchone()
        self.assertEqual(row["range_scale"], "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
