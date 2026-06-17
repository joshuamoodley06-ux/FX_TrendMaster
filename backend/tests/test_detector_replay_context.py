"""Acceptance tests: detector must respect replay candle window and rerun context."""

from __future__ import annotations

import json
import sqlite3
import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from detection_brain_api import list_pending_suggestions, run_detector_and_store
from detection_brain_schema import init_detection_brain_schema
from detector.context_window import meta_matches_context_filter
from detector.normalize import parse_time_to_ms
from detector.ohlc_loader import build_context
from detector.pipeline import run_detector_v1
from detector.writer import write_suggestions


def _monthly_candles() -> list[dict]:
    """Jan–Jun monthly bars with rising highs (future months leak if not truncated)."""
    months = [
        ("2024-01-01", 100, 105, 98, 102),
        ("2024-02-01", 102, 108, 101, 106),
        ("2024-03-01", 106, 112, 105, 110),
        ("2024-04-01", 110, 130, 109, 125),  # April spike — must not affect March run
        ("2024-05-01", 125, 140, 124, 135),
        ("2024-06-01", 135, 150, 134, 145),
    ]
    out = []
    for i, (t, o, h, l, c) in enumerate(months):
        out.append(
            {
                "time": t,
                "time_ms": parse_time_to_ms(t),
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "volume": 1000,
            }
        )
    return out


MARCH_MONTH_MS = parse_time_to_ms("2024-03-01")
JUNE_MONTH_MS = parse_time_to_ms("2024-06-01")


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
        (110, 145, 109, 140),  # future-only spike (index 10)
        (140, 160, 139, 155),  # future-only spike (index 11)
    ]


def _timed_swing_candles() -> list[dict]:
    """Swing series with monthly timestamps for replay window tests."""
    base = parse_time_to_ms("2024-01-01")
    out = []
    for i, (o, h, l, c) in enumerate(_swing_sequence()):
        t_ms = base + i * 2_592_000_000  # ~30d steps
        out.append(
            {
                "time_ms": t_ms,
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "volume": 100,
            }
        )
    return out


def _march_ms() -> int:
    return parse_time_to_ms("2024-01-01") + 4 * 2_592_000_000


def _june_ms() -> int:
    return parse_time_to_ms("2024-01-01") + 9 * 2_592_000_000


class WindowFilterTests(unittest.TestCase):
    def test_replay_until_excludes_future_months(self) -> None:
        candles = _monthly_candles()
        ctx = build_context(
            symbol="XAUUSD",
            source_timeframe="W1",
            candles=candles,
            active_index=99,
            replay_until_time_ms=MARCH_MONTH_MS,
            detection_run_id="run-march",
        )
        self.assertEqual(len(ctx.candles), 3)
        self.assertEqual(ctx.candles[-1].time_ms, MARCH_MONTH_MS)
        self.assertNotIn(130, [c.high for c in ctx.candles])

    def test_visible_from_and_until_window(self) -> None:
        candles = _monthly_candles()
        ctx = build_context(
            symbol="XAUUSD",
            source_timeframe="W1",
            candles=candles,
            active_index=0,
            visible_from_time_ms=parse_time_to_ms("2024-02-01"),
            replay_until_time_ms=MARCH_MONTH_MS,
        )
        self.assertEqual(len(ctx.candles), 2)
        self.assertEqual(ctx.candles[0].time_ms, parse_time_to_ms("2024-02-01"))


class DetectionMetaTests(unittest.TestCase):
    def test_meta_json_includes_context_fields(self) -> None:
        candles = _monthly_candles()
        ctx = build_context(
            symbol="XAUUSD",
            source_timeframe="W1",
            structure_layer="WEEKLY",
            candles=candles,
            active_index=2,
            replay_until_time_ms=MARCH_MONTH_MS,
            visible_from_time_ms=parse_time_to_ms("2024-01-01"),
            detection_run_id="run-abc",
        )
        meta = ctx.detection_window_meta
        self.assertEqual(meta["detection_run_id"], "run-abc")
        self.assertEqual(meta["replay_until_time_ms"], MARCH_MONTH_MS)
        self.assertEqual(meta["visible_from_time_ms"], parse_time_to_ms("2024-01-01"))
        self.assertEqual(meta["candle_count_used"], 3)
        self.assertEqual(meta["first_candle_time_ms"], parse_time_to_ms("2024-01-01"))
        self.assertEqual(meta["last_candle_time_ms"], MARCH_MONTH_MS)


class RerunSupersedeTests(unittest.TestCase):
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
        init_detection_brain_schema(self.conn)
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def test_march_then_june_supersedes_stale_pending(self) -> None:
        candles = _timed_swing_candles()
        march_ctx = build_context(
            symbol="XAUUSD",
            source_timeframe="D1",
            structure_layer="DAILY",
            candles=candles,
            active_index=4,
            replay_until_time_ms=_march_ms(),
            detection_run_id="run-march",
            range_high=110.0,
            range_low=97.0,
        )
        march_result = run_detector_v1(march_ctx)
        self.assertGreater(len(march_result.drafts), 0)
        write_suggestions(self.conn, march_result.drafts, march_ctx)
        self.conn.commit()

        march_pending = self.conn.execute(
            "SELECT COUNT(*) AS n FROM detector_suggestions WHERE status = 'PENDING'"
        ).fetchone()["n"]
        self.assertGreater(march_pending, 0)

        june_ctx = build_context(
            symbol="XAUUSD",
            source_timeframe="D1",
            structure_layer="DAILY",
            candles=candles,
            active_index=9,
            replay_until_time_ms=_june_ms(),
            detection_run_id="run-june",
            range_high=110.0,
            range_low=97.0,
        )
        june_result = run_detector_v1(june_ctx)
        self.assertGreater(len(june_result.drafts), 0)
        write_suggestions(self.conn, june_result.drafts, june_ctx)
        self.conn.commit()

        pending = self.conn.execute(
            "SELECT meta_json FROM detector_suggestions WHERE status = 'PENDING'"
        ).fetchall()
        superseded = self.conn.execute(
            "SELECT COUNT(*) AS n FROM detector_suggestions WHERE status = 'SUPERSEDED'"
        ).fetchone()["n"]
        self.assertGreater(superseded, 0)
        self.assertGreater(len(pending), 0)
        for row in pending:
            meta = json.loads(row["meta_json"] or "{}")
            self.assertEqual(meta.get("detection_run_id"), "run-june")
            self.assertEqual(meta.get("replay_until_time_ms"), _june_ms())

    def test_june_run_sees_higher_high_than_march(self) -> None:
        candles = _timed_swing_candles()
        march_ctx = build_context(
            symbol="XAUUSD",
            source_timeframe="D1",
            candles=candles,
            active_index=4,
            replay_until_time_ms=_march_ms(),
        )
        june_ctx = build_context(
            symbol="XAUUSD",
            source_timeframe="D1",
            candles=candles,
            active_index=9,
            replay_until_time_ms=_june_ms(),
        )
        march_max = max(c.high for c in march_ctx.candles)
        june_max = max(c.high for c in june_ctx.candles)
        self.assertLess(march_max, june_max)
        self.assertNotIn(145, [c.high for c in march_ctx.candles])


class ListFilterTests(unittest.TestCase):
    def test_detection_run_id_filter_is_strict(self) -> None:
        meta_march = {"detection_run_id": "run-march", "replay_until_time_ms": _march_ms()}
        meta_june = {"detection_run_id": "run-june", "replay_until_time_ms": _june_ms()}
        self.assertTrue(
            meta_matches_context_filter(meta_march, detection_run_id="run-march")
        )
        self.assertFalse(
            meta_matches_context_filter(meta_june, detection_run_id="run-march")
        )
        self.assertTrue(
            meta_matches_context_filter(meta_june, replay_until_time_ms=_june_ms())
        )


class FutureLeakDetectorTests(unittest.TestCase):
    def test_bos_not_detected_from_future_only_break_when_cut_at_march(self) -> None:
        """April+ bars break RH; March cut must not see that BOS."""
        candles = _monthly_candles()
        march_ctx = build_context(
            symbol="XAUUSD",
            source_timeframe="W1",
            candles=candles,
            active_index=2,
            replay_until_time_ms=MARCH_MONTH_MS,
            range_high=112.0,
            range_low=105.0,
        )
        full_ctx = build_context(
            symbol="XAUUSD",
            source_timeframe="W1",
            candles=candles,
            active_index=5,
            replay_until_time_ms=JUNE_MONTH_MS,
            range_high=112.0,
            range_low=105.0,
        )
        march_bos = run_detector_v1(march_ctx).by_kind("BOS_UP")
        full_bos = run_detector_v1(full_ctx).by_kind("BOS_UP")
        self.assertEqual(len(march_bos), 0)
        self.assertGreaterEqual(len(full_bos), 0)


class SafetyTests(unittest.TestCase):
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
            [(1, "XAUUSD", "W1", 112.0, 105.0, "t", "t")],
        )
        self.conn.executemany(
            "INSERT INTO map_events(id,symbol,timeframe,event_type,price,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
            [(1, "XAUUSD", "W1", "BOS_UP", 130.0, "t", "t")],
        )
        init_detection_brain_schema(self.conn)
        self.conn.commit()
        self.ranges_before = self.conn.execute("SELECT COUNT(*) AS n FROM map_ranges").fetchone()["n"]
        self.events_before = self.conn.execute("SELECT COUNT(*) AS n FROM map_events").fetchone()["n"]

    def tearDown(self) -> None:
        self.conn.close()

    def test_detector_run_does_not_mutate_confirmed_structure(self) -> None:
        candles = _timed_swing_candles()
        ctx = build_context(
            symbol="XAUUSD",
            source_timeframe="D1",
            candles=candles,
            active_index=9,
            replay_until_time_ms=_june_ms(),
            detection_run_id="safety-run",
            range_high=110.0,
            range_low=97.0,
        )
        result = run_detector_v1(ctx)
        write_suggestions(self.conn, result.drafts, ctx)
        self.conn.commit()
        ranges_after = self.conn.execute("SELECT COUNT(*) AS n FROM map_ranges").fetchone()["n"]
        events_after = self.conn.execute("SELECT COUNT(*) AS n FROM map_events").fetchone()["n"]
        suggestions_after = self.conn.execute(
            "SELECT COUNT(*) AS n FROM detector_suggestions"
        ).fetchone()["n"]
        self.assertEqual(self.ranges_before, ranges_after)
        self.assertEqual(self.events_before, events_after)
        self.assertGreater(suggestions_after, 0)


class ApiListFilterTests(unittest.TestCase):
    def test_list_filters_by_detection_run_id(self) -> None:
        run1 = run_detector_and_store(
            {
                "symbol": "XAUUSD",
                "source_timeframe": "W1",
                "structure_layer": "WEEKLY",
                "candles": _monthly_candles(),
                "replay_until_time_ms": MARCH_MONTH_MS,
                "detection_run_id": "list-run-march",
                "range_high": 112.0,
                "range_low": 105.0,
            }
        )
        run2 = run_detector_and_store(
            {
                "symbol": "XAUUSD",
                "source_timeframe": "W1",
                "structure_layer": "WEEKLY",
                "candles": _monthly_candles(),
                "replay_until_time_ms": JUNE_MONTH_MS,
                "detection_run_id": "list-run-june",
                "range_high": 112.0,
                "range_low": 105.0,
            }
        )
        self.assertTrue(run1.get("ok"))
        self.assertTrue(run2.get("ok"))
        listed = list_pending_suggestions(
            symbol="XAUUSD",
            structure_layer="WEEKLY",
            source_timeframe="W1",
            detection_run_id="list-run-june",
        )
        self.assertTrue(listed.get("ok"))
        for row in listed.get("suggestions") or []:
            meta = row.get("meta_json") or {}
            self.assertEqual(meta.get("detection_run_id"), "list-run-june")


class ApiIntegrationTests(unittest.TestCase):
    def test_run_detector_payload_returns_context(self) -> None:
        out = run_detector_and_store(
            {
                "symbol": "XAUUSD",
                "source_timeframe": "W1",
                "structure_layer": "WEEKLY",
                "candles": _monthly_candles(),
                "replay_until_time_ms": MARCH_MONTH_MS,
                "detection_run_id": "api-run-1",
            }
        )
        self.assertTrue(out.get("ok"))
        self.assertEqual(out.get("detection_run_id"), "api-run-1")
        self.assertEqual(out.get("replay_until_time_ms"), MARCH_MONTH_MS)
        ctx = out.get("detection_context") or {}
        self.assertEqual(ctx.get("candle_count_used"), 3)
        self.assertEqual(ctx.get("last_candle_time_ms"), MARCH_MONTH_MS)
        if out.get("written_count", 0) > 0:
            suggestions = out.get("suggestions") or []
            meta = suggestions[0].get("meta_json") or {}
            self.assertEqual(meta.get("detection_run_id"), "api-run-1")
            self.assertEqual(meta.get("replay_until_time_ms"), MARCH_MONTH_MS)
            self.assertEqual(meta.get("candle_count_used"), 3)
            self.assertEqual(meta.get("first_candle_time_ms"), parse_time_to_ms("2024-01-01"))
            self.assertEqual(meta.get("last_candle_time_ms"), MARCH_MONTH_MS)


if __name__ == "__main__":
    unittest.main()
