"""Unit tests for Python Detector V1."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from dataclasses import replace
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from detection_brain_schema import init_detection_brain_schema
from detector.break_rules import BODY_CLOSE, WICK, break_rule_for_timeframe
from detector.ohlc_loader import build_context
from detector.pipeline import run_detector_v1
from detector.versions import BOS_V1, ENGINE_SOURCE
from detector.writer import write_suggestions


def _candles_from_ohlc(
    rows: list[tuple[float, float, float, float]],
    *,
    timeframe: str = "D1",
    base_ms: int = 1_700_000_000_000,
) -> list[dict]:
    out = []
    for i, (o, h, l, c) in enumerate(rows):
        out.append(
            {
                "time_ms": base_ms + i * 86_400_000,
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "volume": 100,
                "timeframe": timeframe,
            }
        )
    return out


def _swing_sequence() -> list[tuple[float, float, float, float]]:
    """Clear swing low then swing high for range detection."""
    return [
        (102, 104, 100, 101),
        (101, 103, 99, 100),
        (100, 102, 98, 99),
        (99, 101, 97, 98),   # swing low region
        (98, 100, 96, 99),
        (99, 103, 98, 102),
        (102, 106, 101, 105),
        (105, 110, 104, 108),
        (108, 112, 107, 111),  # swing high region
        (111, 113, 109, 110),
    ]


class BreakRuleTests(unittest.TestCase):
    def test_htf_uses_wick(self) -> None:
        self.assertEqual(break_rule_for_timeframe("D1"), WICK)
        self.assertEqual(break_rule_for_timeframe("W1"), WICK)

    def test_m15_uses_body_close(self) -> None:
        self.assertEqual(break_rule_for_timeframe("M15"), BODY_CLOSE)


class ReplayContextTests(unittest.TestCase):
    def test_active_candle_time_truncates_future_bars(self) -> None:
        rows = _candles_from_ohlc(_swing_sequence())
        cut_ms = int(rows[5]["time_ms"])
        ctx = build_context(
            symbol="XAUUSD",
            source_timeframe="D1",
            candles=rows,
            active_index=99,
            active_candle_time_ms=cut_ms,
        )
        self.assertEqual(len(ctx.candles), 6)
        self.assertEqual(ctx.active_index, 5)
        self.assertEqual(ctx.candles[-1].time_ms, cut_ms)


class BosDetectorTests(unittest.TestCase):
    def test_wick_bos_up_on_d1(self) -> None:
        rows = _swing_sequence() + [(110, 112, 109, 109.5)]  # wick above 110, close inside
        ctx = build_context(
            symbol="XAUUSD",
            source_timeframe="D1",
            candles=_candles_from_ohlc(rows, timeframe="D1"),
            active_index=len(rows) - 1,
            range_high=110.0,
            range_low=97.0,
        )
        result = run_detector_v1(ctx)
        bos = result.by_kind("BOS_UP")
        self.assertEqual(len(bos), 1)
        self.assertEqual(bos[0].detector_version, BOS_V1)
        self.assertEqual(bos[0].break_rule, WICK)
        self.assertEqual(bos[0].movement_rule, "STRUCTURE_BOS_UP")

    def test_m15_requires_body_close_for_bos_up(self) -> None:
        # Wick only — no BOS
        rows_wick_only = _swing_sequence() + [(110, 112, 109, 109.5)]
        ctx_fail = build_context(
            symbol="XAUUSD",
            source_timeframe="M15",
            candles=_candles_from_ohlc(rows_wick_only, timeframe="M15"),
            active_index=len(rows_wick_only) - 1,
            range_high=110.0,
            range_low=97.0,
        )
        self.assertEqual(len(run_detector_v1(ctx_fail).by_kind("BOS_UP")), 0)

        # Body close above RH — BOS
        rows_body = _swing_sequence() + [(110, 112, 109, 111.0)]
        ctx_ok = build_context(
            symbol="XAUUSD",
            source_timeframe="M15",
            candles=_candles_from_ohlc(rows_body, timeframe="M15"),
            active_index=len(rows_body) - 1,
            range_high=110.0,
            range_low=97.0,
        )
        bos = run_detector_v1(ctx_ok).by_kind("BOS_UP")
        self.assertEqual(len(bos), 1)
        self.assertEqual(bos[0].break_rule, BODY_CLOSE)


class SweepReclaimTests(unittest.TestCase):
    def test_sweep_low_then_reclaim_up(self) -> None:
        rows = _swing_sequence()
        rows.append((104, 105, 98, 102))   # sweep below 100, close inside
        rows.append((102, 108, 101, 105))  # reclaim above 100
        ctx_sweep = build_context(
            symbol="XAUUSD",
            source_timeframe="D1",
            candles=_candles_from_ohlc(rows, timeframe="D1"),
            active_index=len(rows) - 2,
            range_high=110.0,
            range_low=100.0,
        )
        sweeps = run_detector_v1(ctx_sweep).by_kind("SWEEP_LOW")
        self.assertEqual(len(sweeps), 1)

        ctx_reclaim = build_context(
            symbol="XAUUSD",
            source_timeframe="D1",
            candles=_candles_from_ohlc(rows, timeframe="D1"),
            active_index=len(rows) - 1,
            range_high=110.0,
            range_low=100.0,
        )
        reclaims = run_detector_v1(ctx_reclaim).by_kind("RECLAIM_UP")
        self.assertEqual(len(reclaims), 1)


class WriterIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(
            """
            CREATE TABLE map_ranges (
                id INTEGER PRIMARY KEY,
                symbol TEXT, timeframe TEXT,
                range_high REAL, range_low REAL,
                range_scope TEXT DEFAULT 'MAJOR',
                range_scale TEXT DEFAULT 'MAJOR',
                created_at TEXT, updated_at TEXT
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE map_events (
                id INTEGER PRIMARY KEY,
                symbol TEXT, timeframe TEXT,
                event_type TEXT, price REAL,
                created_at TEXT, updated_at TEXT
            )
            """
        )
        self.conn.executemany(
            "INSERT INTO map_ranges(id,symbol,timeframe,range_high,range_low,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
            [(1, "XAUUSD", "D1", 110.0, 97.0, "t", "t")],
        )
        self.conn.executemany(
            "INSERT INTO map_events(id,symbol,timeframe,event_type,price,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
            [(1, "XAUUSD", "D1", "BOS_UP", 111.0, "t", "t")],
        )
        init_detection_brain_schema(self.conn)
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def test_writes_suggestions_with_python_detector_source(self) -> None:
        rows = _swing_sequence() + [(110, 112, 109, 111.5)]
        ctx = build_context(
            symbol="XAUUSD",
            source_timeframe="D1",
            candles=_candles_from_ohlc(rows),
            active_index=len(rows) - 1,
            range_high=110.0,
            range_low=97.0,
        )
        result = run_detector_v1(ctx)
        saved = write_suggestions(self.conn, result.drafts, ctx)
        self.conn.commit()
        self.assertGreater(len(saved), 0)
        for row in saved:
            self.assertEqual(row["engine_source"], ENGINE_SOURCE)
            self.assertTrue(row.get("detector_version"))

    def test_no_duplicate_pending_same_slot_uses_supersede(self) -> None:
        rows = _swing_sequence() + [(110, 112, 109, 111.5)]
        ctx = build_context(
            symbol="XAUUSD",
            source_timeframe="D1",
            candles=_candles_from_ohlc(rows),
            active_index=len(rows) - 1,
            range_high=110.0,
            range_low=97.0,
            parent_range_id=None,
        )
        result = run_detector_v1(ctx)
        bos_drafts = [d for d in result.drafts if d.candidate_kind == "BOS_UP"]
        self.assertEqual(len(bos_drafts), 1)

        write_suggestions(self.conn, bos_drafts, ctx)
        write_suggestions(self.conn, bos_drafts, ctx)
        self.conn.commit()

        pending = self.conn.execute(
            "SELECT COUNT(*) AS n FROM detector_suggestions WHERE status = 'PENDING'"
        ).fetchone()["n"]
        superseded = self.conn.execute(
            "SELECT COUNT(*) AS n FROM detector_suggestions WHERE status = 'SUPERSEDED'"
        ).fetchone()["n"]
        self.assertEqual(pending, 1)
        self.assertEqual(superseded, 1)

    def test_candidate_index_allows_two_pending_different_index(self) -> None:
        rows = _swing_sequence() + [(110, 112, 109, 111.5)]
        ctx = build_context(
            symbol="XAUUSD",
            source_timeframe="D1",
            candles=_candles_from_ohlc(rows),
            active_index=len(rows) - 1,
            range_high=110.0,
            range_low=97.0,
        )
        result = run_detector_v1(ctx)
        # Force two BOS drafts with different candidate_index (hypothetical dual slot)
        drafts = [d for d in result.drafts if d.candidate_kind == "BOS_UP"]
        if len(drafts) == 1:
            drafts.append(replace(drafts[0], candidate_index=1, reason_text="alt slot"))
        write_suggestions(self.conn, drafts, ctx)
        self.conn.commit()
        pending = self.conn.execute(
            """
            SELECT candidate_index, COUNT(*) AS n
            FROM detector_suggestions
            WHERE status = 'PENDING' AND candidate_kind = 'BOS_UP'
            GROUP BY candidate_index
            """
        ).fetchall()
        self.assertEqual(len(pending), 2)

    def test_does_not_mutate_confirmed_structure(self) -> None:
        rows = _swing_sequence() + [(110, 112, 109, 111.5)]
        ctx = build_context(
            symbol="XAUUSD",
            source_timeframe="D1",
            candles=_candles_from_ohlc(rows),
            active_index=len(rows) - 1,
            range_high=110.0,
            range_low=97.0,
        )
        ranges_before = self.conn.execute("SELECT COUNT(*) AS n FROM map_ranges").fetchone()["n"]
        events_before = self.conn.execute("SELECT COUNT(*) AS n FROM map_events").fetchone()["n"]

        result = run_detector_v1(ctx)
        write_suggestions(self.conn, result.drafts, ctx)
        self.conn.commit()

        ranges_after = self.conn.execute("SELECT COUNT(*) AS n FROM map_ranges").fetchone()["n"]
        events_after = self.conn.execute("SELECT COUNT(*) AS n FROM map_events").fetchone()["n"]
        suggestions_after = self.conn.execute(
            "SELECT COUNT(*) AS n FROM detector_suggestions"
        ).fetchone()["n"]

        self.assertEqual(ranges_before, ranges_after)
        self.assertEqual(events_before, events_after)
        self.assertGreater(suggestions_after, 0)


if __name__ == "__main__":
    unittest.main()
