"""Phase E tests — active range seed context wiring."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from detection_brain_api import run_detector_and_store
from detector.context_window import build_detection_window_meta
from detector.models import DetectionContext, SwingPoint
from detector.normalize import normalize_candles
from detector.pipeline import run_detector_v1
from detector.range_mode import RANGE_MODE_DOCTRINE_V2, RANGE_MODE_SMOKE_V1
from detector.range_seed import (
    SEED_LOOKUP_MISMATCH,
    SEED_LOOKUP_MULTIPLE,
    SEED_SOURCE_BACKEND,
    SEED_SOURCE_ELECTRON,
    SEED_SOURCE_EXPLICIT,
    SeedResolutionResult,
    load_active_range_seed_context,
    resolve_detector_seed_context,
    seed_resolution_to_meta,
)
from detector.range_state import RangeSeedContext
from detector.versions import RANGE_V1, RANGE_V2


def _bullish_rows():
    return [
        (95, 98, 94, 97),
        (97, 99, 96, 98),
        (98, 99, 97, 98),
        (99, 100, 98, 99),
        (99, 101, 98, 100),
        (101, 106, 100, 104),
        (104, 105, 101, 103),
        (103, 104, 100, 102),
        (102, 103, 98, 99),
    ]


def _candles():
    payload = []
    base_ms = 1_700_000_000_000
    for i, (o, h, l, c) in enumerate(_bullish_rows()):
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


def _seed(active_id: int = 42) -> RangeSeedContext:
    return RangeSeedContext(
        range_high=100.0,
        range_low=90.0,
        active_range_id=active_id,
        range_scale="MAJOR",
        range_role="ACTIVE_CONTAINER",
        structure_layer="DAILY",
        source_timeframe="D1",
        status="ACTIVE",
        seed_source=SEED_SOURCE_EXPLICIT,
    )


def _ctx_with_seed(seed: RangeSeedContext | None) -> DetectionContext:
    candles = _candles()
    swings = []
    if seed:
        swings = [SwingPoint(index=6, kind="SWING_LOW", price=101.0, candle=candles[6])]
    ctx = DetectionContext(
        symbol="XAUUSD",
        source_timeframe="D1",
        candles=candles,
        active_index=8,
        structure_layer="DAILY",
        range_high=seed.range_high if seed else None,
        range_low=seed.range_low if seed else None,
        range_scale=seed.range_scale if seed else "MAJOR",
        range_role=seed.range_role if seed else None,
        active_range_id=seed.active_range_id if seed else None,
        parent_range_id=10,
        detection_run_id="seed-test",
        swings=swings,
    )
    ctx.detection_window_meta = build_detection_window_meta(ctx, detection_run_id="seed-test")
    ctx.range_seed = seed
    if seed:
        ctx.range_seed_meta = seed_resolution_to_meta(
            SeedResolutionResult(seed=seed, seed_source=seed.seed_source or SEED_SOURCE_EXPLICIT)
        )
    else:
        ctx.range_seed_meta = seed_resolution_to_meta(SeedResolutionResult())
    return ctx


class MapRangesTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(
            """
            CREATE TABLE map_ranges (
                id INTEGER PRIMARY KEY,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                source_timeframe TEXT,
                structure_layer TEXT,
                layer TEXT,
                range_high REAL,
                range_low REAL,
                range_high_price REAL,
                range_low_price REAL,
                status TEXT,
                parent_range_id INTEGER,
                range_scope TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )

    def _insert_range(
        self,
        *,
        range_id: int,
        symbol: str = "XAUUSD",
        layer: str = "DAILY",
        tf: str = "D1",
        high: float = 100.0,
        low: float = 90.0,
        status: str = "ACTIVE",
        parent_range_id: int | None = None,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO map_ranges (
                id, symbol, timeframe, source_timeframe, structure_layer, layer,
                range_high, range_low, range_high_price, range_low_price,
                status, parent_range_id, range_scope, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                range_id,
                symbol,
                tf,
                tf,
                layer,
                layer,
                high,
                low,
                high,
                low,
                status,
                parent_range_id,
                "MAJOR",
                "2026-01-01",
                "2026-01-01",
            ),
        )
        self.conn.commit()


class DoctrineV2SeedPipelineTests(unittest.TestCase):
    def test_explicit_seed_emits_lifecycle_result_not_no_seed_context(self) -> None:
        ctx = _ctx_with_seed(_seed())
        result = run_detector_v1(ctx, range_mode=RANGE_MODE_DOCTRINE_V2)
        range_drafts = [d for d in result.drafts if d.detector_version == RANGE_V2]
        self.assertEqual(len(range_drafts), 1)
        meta = range_drafts[0].meta_json
        self.assertFalse(meta.get("no_seed_context"))
        self.assertEqual(meta.get("seed_source"), SEED_SOURCE_EXPLICIT)
        self.assertEqual(meta.get("seed_rh"), 100.0)
        self.assertEqual(meta.get("seed_rl"), 90.0)
        self.assertEqual(range_drafts[0].candidate_kind, "RANGE_CANDIDATE")
        self.assertEqual(range_drafts[0].range_scale, "UNKNOWN")

    def test_no_seed_keeps_no_valid_range(self) -> None:
        ctx = _ctx_with_seed(None)
        result = run_detector_v1(ctx, range_mode=RANGE_MODE_DOCTRINE_V2)
        draft = [d for d in result.drafts if d.detector_version == RANGE_V2][0]
        self.assertEqual(draft.candidate_kind, "NO_VALID_RANGE")
        self.assertTrue(draft.meta_json.get("no_seed_context"))


class LoadActiveRangeSeedTests(MapRangesTestBase):
    def test_backend_lookup_finds_single_active_range(self) -> None:
        self._insert_range(range_id=7)
        seed, err = load_active_range_seed_context(
            self.conn,
            symbol="XAUUSD",
            structure_layer="DAILY",
            source_timeframe="D1",
        )
        self.assertIsNone(err)
        self.assertIsNotNone(seed)
        assert seed is not None
        self.assertEqual(seed.active_range_id, 7)
        self.assertEqual(seed.range_high, 100.0)
        self.assertEqual(seed.range_low, 90.0)
        self.assertEqual(seed.status, "ACTIVE")

    def test_backend_lookup_refuses_multiple_active_ranges(self) -> None:
        self._insert_range(range_id=1)
        self._insert_range(range_id=2, high=110.0, low=95.0)
        seed, err = load_active_range_seed_context(
            self.conn,
            symbol="XAUUSD",
            structure_layer="DAILY",
            source_timeframe="D1",
        )
        self.assertIsNone(seed)
        self.assertEqual(err, SEED_LOOKUP_MULTIPLE)

    def test_backend_lookup_refuses_scope_mismatch(self) -> None:
        self._insert_range(range_id=3, layer="WEEKLY", tf="W1")
        seed, err = load_active_range_seed_context(
            self.conn,
            symbol="XAUUSD",
            structure_layer="DAILY",
            source_timeframe="D1",
            active_range_id=3,
        )
        self.assertIsNone(seed)
        self.assertEqual(err, SEED_LOOKUP_MISMATCH)

    def test_resolve_explicit_payload_by_id(self) -> None:
        self._insert_range(range_id=9)
        result = resolve_detector_seed_context(
            self.conn,
            {"active_range_id": 9, "range_high": 100.0, "range_low": 90.0},
            symbol="XAUUSD",
            structure_layer="DAILY",
            source_timeframe="D1",
        )
        self.assertIsNotNone(result.seed)
        self.assertEqual(result.seed_source, SEED_SOURCE_EXPLICIT)

    def test_resolve_electron_selected_range(self) -> None:
        self._insert_range(range_id=11)
        result = resolve_detector_seed_context(
            self.conn,
            {"active_range_id": 11, "seed_from_electron": True},
            symbol="XAUUSD",
            structure_layer="DAILY",
            source_timeframe="D1",
        )
        self.assertEqual(result.seed_source, SEED_SOURCE_ELECTRON)

    def test_resolve_backend_lookup_when_no_payload_id(self) -> None:
        self._insert_range(range_id=12)
        result = resolve_detector_seed_context(
            self.conn,
            {},
            symbol="XAUUSD",
            structure_layer="DAILY",
            source_timeframe="D1",
        )
        self.assertEqual(result.seed_source, SEED_SOURCE_BACKEND)
        self.assertEqual(result.seed.active_range_id, 12)  # type: ignore[union-attr]

    def test_multiple_active_sets_lookup_error_in_meta(self) -> None:
        self._insert_range(range_id=20)
        self._insert_range(range_id=21, high=120.0, low=100.0)
        result = resolve_detector_seed_context(
            self.conn,
            {},
            symbol="XAUUSD",
            structure_layer="DAILY",
            source_timeframe="D1",
        )
        self.assertIsNone(result.seed)
        self.assertEqual(result.seed_lookup_error, SEED_LOOKUP_MULTIPLE)
        meta = seed_resolution_to_meta(result)
        self.assertTrue(meta["no_seed_context"])
        self.assertEqual(meta["seed_lookup_error"], SEED_LOOKUP_MULTIPLE)


class SmokeV1RegressionTests(unittest.TestCase):
    def test_smoke_v1_unchanged_without_seed_resolution(self) -> None:
        candles = _candles()
        swings = []
        ctx = DetectionContext(
            symbol="XAUUSD",
            source_timeframe="D1",
            candles=candles,
            active_index=8,
            range_high=110.0,
            range_low=97.0,
        )
        result = run_detector_v1(ctx, range_mode=RANGE_MODE_SMOKE_V1)
        self.assertEqual(result.detector_versions["RANGE"], RANGE_V1)


class ApiPayloadTests(MapRangesTestBase):
    def test_run_detector_payload_accepts_active_range_fields(self) -> None:
        self._insert_range(range_id=55, high=100.0, low=90.0)
        candles_payload = []
        base_ms = 1_700_000_000_000
        for i, (o, h, l, c) in enumerate(_bullish_rows()):
            candles_payload.append(
                {
                    "time_ms": base_ms + i * 86_400_000,
                    "open": o,
                    "high": h,
                    "low": l,
                    "close": c,
                    "volume": 100,
                }
            )

        class _ConnCtx:
            def __init__(self, conn: sqlite3.Connection) -> None:
                self.conn = conn

            def __enter__(self) -> sqlite3.Connection:
                return self.conn

            def __exit__(self, *args) -> None:
                return None

        with patch("detection_brain_api._connect", return_value=_ConnCtx(self.conn)):
            with patch("detection_brain_api.init_detection_brain_schema"):
                with patch("detection_brain_api.write_suggestions", return_value=[]):
                    out = run_detector_and_store(
                        {
                            "symbol": "XAUUSD",
                            "source_timeframe": "D1",
                            "structure_layer": "DAILY",
                            "range_mode": "doctrine_v2",
                            "active_range_id": 55,
                            "range_high": 100.0,
                            "range_low": 90.0,
                            "candles": candles_payload,
                            "active_index": 8,
                        }
                    )
        self.assertTrue(out.get("ok"))
        self.assertEqual(out.get("range_mode"), RANGE_MODE_DOCTRINE_V2)
        ctx_meta = out.get("detection_context") or {}
        self.assertFalse(ctx_meta.get("no_seed_context"))
        self.assertEqual(ctx_meta.get("seed_source"), SEED_SOURCE_EXPLICIT)

    def test_run_detector_does_not_mutate_map_ranges(self) -> None:
        self._insert_range(range_id=77)
        count_before = self.conn.execute("SELECT COUNT(*) AS n FROM map_ranges").fetchone()["n"]

        class _ConnCtx:
            def __init__(self, conn: sqlite3.Connection) -> None:
                self.conn = conn

            def __enter__(self) -> sqlite3.Connection:
                return self.conn

            def __exit__(self, *args) -> None:
                return None

        with patch("detection_brain_api._connect", return_value=_ConnCtx(self.conn)):
            with patch("detection_brain_api.init_detection_brain_schema"):
                with patch("detection_brain_api.write_suggestions", return_value=[]):
                    run_detector_and_store(
                        {
                            "symbol": "XAUUSD",
                            "source_timeframe": "D1",
                            "structure_layer": "DAILY",
                            "range_mode": "doctrine_v2",
                            "active_range_id": 77,
                            "candles": [{"time_ms": 1, "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 1}],
                        }
                    )
        count_after = self.conn.execute("SELECT COUNT(*) AS n FROM map_ranges").fetchone()["n"]
        self.assertEqual(count_before, count_after)


if __name__ == "__main__":
    unittest.main()
