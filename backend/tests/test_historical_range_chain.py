"""Tests for candles-only historical range chain."""

from __future__ import annotations

import gc
import json
import sqlite3
import sys
import unittest
import uuid
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import candle_store
from detection_brain_schema import init_detection_brain_schema
from detector.historical_range_chain import (
    DETECTION_MODE_HISTORICAL_CANDLES_ONLY,
    HistoricalRangeChainConfig,
    detect_historical_range_chain,
    evaluate_bootstrap_candidates,
    format_bootstrap_trace_report,
    run_historical_range_chain,
    try_bootstrap_seed,
)
from detector.models import DetectionContext
from detector.normalize import normalize_candles
from detector.range_mode import RANGE_MODE_DOCTRINE_V2
from detector.range_scan_runner import HistoricalRangeScanConfig, run_historical_range_scan
from detector.range_v2 import detect_range_v2_suggestions


def _chain_fixture_rows():
    """Swing low 92, swing high 100, BOS at 6, reclaim at 8 — candles-only bootstrap."""
    return [
        (94.0, 96.0, 93.0, 95.0),
        (95.0, 97.0, 94.0, 96.0),
        (96.0, 97.0, 92.0, 93.0),
        (93.0, 96.0, 92.0, 95.0),
        (95.0, 100.0, 94.0, 99.0),
        (99.0, 99.5, 96.0, 97.0),
        (97.0, 105.0, 96.0, 104.0),
        (104.0, 105.0, 101.0, 102.0),
        (102.0, 103.0, 99.5, 102.0),   # RECLAIM_TOUCH only
        (101.0, 102.0, 98.0, 99.5),    # RECLAIM_CLOSE on active bar
    ]


def _candles_from_rows(rows, base_ms: int = 1_735_689_600_000):
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


def _candles(base_ms: int = 1_735_689_600_000):
    payload = []
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


class HistoricalRangeChainTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db_path = Path(__file__).resolve().parent / f"_historical_chain_{uuid.uuid4().hex}.db"
        self.old_path = candle_store.DB_PATH
        candle_store.DB_PATH = self.db_path
        candle_store.init_db()
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        init_detection_brain_schema(self.conn)
        self.candles = _candles_from_rows(_chain_fixture_rows())
        self.date_from_ms = self.candles[0].time_ms
        self.date_to_ms = self.candles[-1].time_ms
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()
        candle_store.DB_PATH = self.old_path
        gc.collect()
        if self.db_path.exists():
            self.db_path.unlink(missing_ok=True)

    def _config(self, **kwargs) -> HistoricalRangeChainConfig:
        base = dict(
            symbol="XAUUSD",
            source_timeframe="D1",
            structure_layer="DAILY",
            date_from_ms=self.date_from_ms,
            date_to_ms=self.date_to_ms,
            range_mode=RANGE_MODE_DOCTRINE_V2,
            range_scale_mode="generic",
            detection_run_id="chain-test-001",
        )
        base.update(kwargs)
        return HistoricalRangeChainConfig(**base)

    def test_candles_only_chain_produces_range_candidate(self) -> None:
        result = run_historical_range_chain(
            self.conn,
            self._config(),
            candles=self.candles,
        )
        self.assertGreater(result.range_candidate_count, 0)
        self.assertGreater(result.chain_candidates, 0)
        self.assertIsNotNone(result.bootstrap_step_index)

    def test_no_map_ranges_required(self) -> None:
        count = self.conn.execute("SELECT COUNT(*) AS n FROM map_ranges").fetchone()["n"]
        self.assertEqual(int(count), 0)
        result = run_historical_range_chain(self.conn, self._config(), candles=self.candles)
        self.assertGreater(result.suggestions_created, 0)

    def test_chain_does_not_mutate_map_tables(self) -> None:
        ranges_before = self.conn.execute("SELECT COUNT(*) FROM map_ranges").fetchone()[0]
        events_before = self.conn.execute("SELECT COUNT(*) FROM map_events").fetchone()[0]
        run_historical_range_chain(self.conn, self._config(), candles=self.candles)
        ranges_after = self.conn.execute("SELECT COUNT(*) FROM map_ranges").fetchone()[0]
        events_after = self.conn.execute("SELECT COUNT(*) FROM map_events").fetchone()[0]
        self.assertEqual(ranges_before, ranges_after)
        self.assertEqual(events_before, events_after)

    def test_chain_meta_fields_present(self) -> None:
        run_historical_range_chain(self.conn, self._config(), candles=self.candles)
        row = self.conn.execute(
            """
            SELECT candidate_kind, meta_json, range_scale
            FROM detector_suggestions
            WHERE candidate_kind = 'RANGE_CANDIDATE'
            ORDER BY created_at_utc_ms ASC
            LIMIT 1
            """
        ).fetchone()
        self.assertIsNotNone(row)
        meta = json.loads(row["meta_json"])
        self.assertTrue(meta.get("historical_chain"))
        self.assertEqual(meta.get("detection_mode"), DETECTION_MODE_HISTORICAL_CANDLES_ONLY)
        self.assertIn("chain_id", meta)
        self.assertIn("chain_index", meta)
        self.assertIn("lifecycle_state", meta)
        self.assertEqual(row["range_scale"], "UNKNOWN")

    def test_no_major_minor_output(self) -> None:
        run_historical_range_chain(self.conn, self._config(), candles=self.candles)
        rows = self.conn.execute("SELECT candidate_kind FROM detector_suggestions").fetchall()
        kinds = {str(r["candidate_kind"]) for r in rows}
        self.assertFalse(kinds & {"RANGE_MAJOR", "RANGE_MINOR"})

    def test_later_steps_use_previous_candidate_context(self) -> None:
        run_historical_range_chain(self.conn, self._config(), candles=self.candles)
        rows = self.conn.execute(
            "SELECT meta_json FROM detector_suggestions ORDER BY created_at_utc_ms ASC"
        ).fetchall()
        sources = [json.loads(row["meta_json"]).get("working_context_source") for row in rows]
        self.assertIn("bootstrap_candidate", sources)

    def test_incomplete_lifecycle_emits_no_valid_range_not_fake_range(self) -> None:
        short = self.candles[:3]
        steps, aggregate = detect_historical_range_chain(
            short,
            symbol="XAUUSD",
            source_timeframe="D1",
            structure_layer="DAILY",
            date_from_ms=short[0].time_ms,
            date_to_ms=short[-1].time_ms,
            detection_run_id="short-chain",
        )
        kinds = []
        for _ctx, drafts, _meta in steps:
            kinds.extend(str(d.candidate_kind) for d in drafts)
        self.assertNotIn("RANGE_MAJOR", kinds)
        self.assertNotIn("RANGE_MINOR", kinds)
        if kinds:
            self.assertTrue(all(k in {"RANGE_CANDIDATE", "NO_VALID_RANGE", "NO_MINOR_STRUCTURE"} for k in kinds))

    def test_live_strict_mode_still_requires_seed(self) -> None:
        ctx = DetectionContext(
            symbol="XAUUSD",
            source_timeframe="D1",
            structure_layer="DAILY",
            candles=self.candles,
            active_index=len(self.candles) - 1,
        )
        drafts = detect_range_v2_suggestions(
            ctx,
            None,
            [],
            [],
            [],
            strict_seed=True,
        )
        self.assertEqual(len(drafts), 1)
        self.assertEqual(drafts[0].candidate_kind, "NO_VALID_RANGE")

    def test_legacy_scan_without_seed_produces_only_no_valid_range(self) -> None:
        legacy_candles = _candles_from_rows(_bullish_rows())
        result = run_historical_range_scan(
            self.conn,
            HistoricalRangeScanConfig(
                symbol="XAUUSD",
                source_timeframe="D1",
                structure_layer="DAILY",
                date_from_ms=legacy_candles[0].time_ms,
                date_to_ms=legacy_candles[-1].time_ms,
                detection_run_id="legacy-no-seed",
            ),
            candles=legacy_candles,
        )
        self.assertEqual(result.range_candidate_count, 0)
        self.assertGreater(result.no_valid_range_count, 0)

    def test_bootstrap_seed_finds_completed_cycle(self) -> None:
        seed = try_bootstrap_seed(
            self.candles,
            len(self.candles) - 1,
            break_rule="BODY_CLOSE",
        )
        self.assertIsNotNone(seed)
        self.assertGreater(seed.range_high, seed.range_low)  # type: ignore[union-attr]
        self.assertAlmostEqual(seed.range_high, 100.0)  # type: ignore[union-attr]

    def test_bootstrap_trace_lists_first_candidates(self) -> None:
        eval_result = evaluate_bootstrap_candidates(
            self.candles,
            len(self.candles) - 1,
            break_rule="BODY_CLOSE",
        )
        self.assertIsNotNone(eval_result.trace)
        trace = eval_result.trace
        assert trace is not None
        self.assertGreater(trace.candidates_considered, 0)
        self.assertLessEqual(len(trace.candidates_traced), 10)
        self.assertIsNotNone(trace.selected)
        text = format_bootstrap_trace_report(trace)
        self.assertIn("freshness_score", text)
        self.assertIn("price_coherence_score", text)
        self.assertIn("final selection", text)

    def test_chain_result_includes_bootstrap_trace(self) -> None:
        steps, aggregate = detect_historical_range_chain(
            self.candles,
            symbol="XAUUSD",
            source_timeframe="D1",
            structure_layer="DAILY",
            date_from_ms=self.date_from_ms,
            date_to_ms=self.date_to_ms,
            detection_run_id="trace-chain",
        )
        self.assertGreater(len(steps), 0)
        self.assertIsNotNone(aggregate.bootstrap_trace)
        trace = aggregate.bootstrap_trace
        assert trace is not None
        self.assertIsNotNone(trace.selected or trace.no_selection_reason)

    def test_ancient_cycle_rejected_in_bootstrap_trace(self) -> None:
        old_rows = [
            (94.0, 96.0, 93.0, 95.0),
            (95.0, 97.0, 94.0, 96.0),
            (96.0, 97.0, 92.0, 93.0),
            (93.0, 96.0, 92.0, 95.0),
            (95.0, 100.0, 94.0, 99.0),
            (99.0, 99.5, 96.0, 97.0),
            (97.0, 105.0, 96.0, 104.0),
            (104.0, 105.0, 101.0, 102.0),
            (102.0, 103.0, 98.0, 99.0),
        ]
        gap_rows = [(250.0, 255.0, 248.0, 252.0)] * 20
        tail_rows = [(252.0, 258.0, 251.0, 256.0)]
        base_ms = 1_735_689_600_000
        payload = []
        for i, (o, h, l, c) in enumerate(old_rows + gap_rows + tail_rows):
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
        candles = normalize_candles(payload, "D1")
        eval_result = evaluate_bootstrap_candidates(
            candles,
            len(candles) - 1,
            break_rule="BODY_CLOSE",
        )
        trace = eval_result.trace
        assert trace is not None
        reasons = [rec.rejection_reason or "" for rec in trace.candidates_traced]
        self.assertTrue(
            any("stale reclaim" in r or "ancient cycle" in r for r in reasons)
            or trace.no_selection_reason is not None
        )
        self.assertIsNone(eval_result.seed)

    def test_stale_reclaim_cycle_not_promoted_on_active_week(self) -> None:
        old_rows = [
            (94.0, 96.0, 93.0, 95.0),
            (95.0, 97.0, 94.0, 96.0),
            (96.0, 97.0, 92.0, 93.0),
            (93.0, 96.0, 92.0, 95.0),
            (95.0, 100.0, 94.0, 99.0),
            (99.0, 99.5, 96.0, 97.0),
            (97.0, 105.0, 96.0, 104.0),
            (104.0, 105.0, 101.0, 102.0),
            (102.0, 103.0, 98.0, 99.0),
        ]
        gap_rows = [(250.0, 255.0, 248.0, 252.0)] * 20
        tail_rows = [(252.0, 258.0, 251.0, 256.0)]
        base_ms = 1_735_689_600_000
        payload = []
        for i, (o, h, l, c) in enumerate(old_rows + gap_rows + tail_rows):
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
        candles = normalize_candles(payload, "D1")
        last_ms = candles[-1].time_ms
        steps, _ = detect_historical_range_chain(
            candles,
            symbol="XAUUSD",
            source_timeframe="D1",
            structure_layer="DAILY",
            date_from_ms=last_ms,
            date_to_ms=last_ms,
            detection_run_id="stale-cycle-test",
        )
        kinds = []
        for _ctx, drafts, _meta in steps:
            kinds.extend(str(d.candidate_kind) for d in drafts)
        self.assertNotIn("RANGE_CANDIDATE", kinds)

    def test_date_from_scan_keeps_pre_period_lookback_in_context(self) -> None:
        rows = _chain_fixture_rows()
        base_ms = 1_735_689_600_000
        payload = []
        for i in range(8):
            payload.append(
                {
                    "time_ms": base_ms + i * 86_400_000,
                    "open": 90.0,
                    "high": 91.0,
                    "low": 89.0,
                    "close": 90.5,
                    "volume": 100,
                }
            )
        for i, (o, h, l, c) in enumerate(rows):
            payload.append(
                {
                    "time_ms": base_ms + (8 + i) * 86_400_000,
                    "open": o,
                    "high": h,
                    "low": l,
                    "close": c,
                    "volume": 100,
                }
            )
        candles = normalize_candles(payload, "D1")
        scan_from_ms = candles[8].time_ms
        steps, _ = detect_historical_range_chain(
            candles,
            symbol="XAUUSD",
            source_timeframe="D1",
            structure_layer="DAILY",
            date_from_ms=scan_from_ms,
            date_to_ms=candles[-1].time_ms,
            detection_run_id="lookback-test",
        )
        self.assertGreater(len(steps), 0)
        first_ctx = steps[0][0]
        self.assertGreater(len(first_ctx.candles), 1)
        self.assertLess(first_ctx.candles[0].time_ms, scan_from_ms)


if __name__ == "__main__":
    unittest.main()
