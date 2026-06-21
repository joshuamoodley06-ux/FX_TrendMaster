"""Tests for historical range scan runner."""

from __future__ import annotations

import gc
import sqlite3
import sys
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import candle_store
from detection_brain_schema import init_detection_brain_schema
from detector.normalize import normalize_candles
from detector.range_mode import RANGE_MODE_DOCTRINE_V2
from detector.range_scan_runner import (
    HistoricalRangeScanConfig,
    format_audit_sample,
    parse_scan_date_ms,
    run_historical_range_scan,
    sample_scan_suggestions,
)
from tests.test_historical_range_chain import _chain_fixture_rows, _candles_from_rows


def _candles(base_ms: int = 1_735_689_600_000):
    return _candles_from_rows(_chain_fixture_rows(), base_ms=base_ms)


class HistoricalRangeScanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db_path = Path(__file__).resolve().parent / f"_historical_scan_{uuid.uuid4().hex}.db"
        self.old_path = candle_store.DB_PATH
        candle_store.DB_PATH = self.db_path
        candle_store.init_db()
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        init_detection_brain_schema(self.conn)
        self.candles = _candles()
        self.date_from_ms = self.candles[0].time_ms
        self.date_to_ms = self.candles[-1].time_ms
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()
        candle_store.DB_PATH = self.old_path
        gc.collect()
        if self.db_path.exists():
            self.db_path.unlink(missing_ok=True)

    def _insert_active_range(self) -> None:
        self.conn.execute(
            """
            INSERT INTO map_ranges (
                id, symbol, timeframe, source_timeframe, structure_layer, layer,
                range_high, range_low, range_high_price, range_low_price,
                range_scope, range_scale, status, range_key, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                7,
                "XAUUSD",
                "D1",
                "D1",
                "DAILY",
                "DAILY",
                100.0,
                90.0,
                100.0,
                90.0,
                "UNKNOWN",
                "UNKNOWN",
                "ACTIVE",
                "scan_seed",
                "2025-01-01",
                "2025-01-01",
            ),
        )
        self.conn.commit()

    def _suggestion_count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) AS n FROM detector_suggestions").fetchone()
        return int(row["n"])

    def _config(self, **kwargs) -> HistoricalRangeScanConfig:
        base = dict(
            symbol="XAUUSD",
            source_timeframe="W1",
            structure_layer="WEEKLY",
            date_from_ms=self.date_from_ms,
            date_to_ms=self.date_to_ms,
            range_mode=RANGE_MODE_DOCTRINE_V2,
            range_scale_mode="generic",
            detection_run_id="scan-test-run-001",
        )
        base.update(kwargs)
        return HistoricalRangeScanConfig(**base)

    def test_dry_run_creates_no_suggestions(self) -> None:
        before = self._suggestion_count()
        result = run_historical_range_scan(
            self.conn,
            self._config(dry_run=True),
            candles=self.candles,
        )
        after = self._suggestion_count()
        self.assertEqual(before, after)
        self.assertTrue(result.dry_run)
        self.assertEqual(result.suggestions_created, 0)
        self.assertGreater(result.candles_scanned, 0)

    def test_normal_run_creates_range_candidate_suggestions(self) -> None:
        result = run_historical_range_scan(
            self.conn,
            self._config(candidate_kind_filter="RANGE_CANDIDATE"),
            candles=self.candles,
        )
        self.assertGreater(result.suggestions_created, 0)
        self.assertGreater(result.range_candidate_count, 0)
        row = self.conn.execute(
            "SELECT candidate_kind, range_scale FROM detector_suggestions LIMIT 1"
        ).fetchone()
        self.assertEqual(row["candidate_kind"], "RANGE_CANDIDATE")
        self.assertEqual(row["range_scale"], "UNKNOWN")

    def test_map_tables_unchanged(self) -> None:
        ranges_before = self.conn.execute("SELECT COUNT(*) FROM map_ranges").fetchone()[0]
        events_before = self.conn.execute("SELECT COUNT(*) FROM map_events").fetchone()[0]
        run_historical_range_scan(self.conn, self._config(), candles=self.candles)
        ranges_after = self.conn.execute("SELECT COUNT(*) FROM map_ranges").fetchone()[0]
        events_after = self.conn.execute("SELECT COUNT(*) FROM map_events").fetchone()[0]
        self.assertEqual(ranges_before, ranges_after)
        self.assertEqual(events_before, events_after)

    def test_date_window_respected(self) -> None:
        mid_ms = self.candles[4].time_ms
        result = run_historical_range_scan(
            self.conn,
            self._config(date_from_ms=mid_ms, date_to_ms=mid_ms),
            candles=self.candles,
        )
        self.assertEqual(result.candles_scanned, 1)

    def test_replay_until_stored_in_meta(self) -> None:
        run_historical_range_scan(
            self.conn,
            self._config(max_steps=2),
            candles=self.candles,
        )
        row = self.conn.execute(
            "SELECT meta_json FROM detector_suggestions ORDER BY created_at_utc_ms ASC LIMIT 1"
        ).fetchone()
        import json

        meta = json.loads(row["meta_json"])
        self.assertIn("replay_until_time_ms", meta)
        self.assertEqual(meta.get("detection_run_id"), "scan-test-run-001")
        self.assertTrue(meta.get("historical_scan"))

    def test_no_major_minor_in_generic_mode(self) -> None:
        run_historical_range_scan(self.conn, self._config(), candles=self.candles)
        rows = self.conn.execute(
            "SELECT candidate_kind FROM detector_suggestions"
        ).fetchall()
        kinds = {str(r["candidate_kind"]) for r in rows}
        self.assertFalse(kinds & {"RANGE_MAJOR", "RANGE_MINOR"})

    def test_sample_returns_valid_rows(self) -> None:
        result = run_historical_range_scan(
            self.conn,
            self._config(),
            candles=self.candles,
        )
        sample = sample_scan_suggestions(
            self.conn,
            detection_run_id=result.detection_run_id,
            sample_n=2,
            candidate_kind="RANGE_CANDIDATE",
        )
        self.assertGreaterEqual(len(sample), 1)
        text = format_audit_sample(sample)
        self.assertIn("id=", text)
        self.assertIn("replay=", text)

    def _insert_candles_into_db(self) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for candle in self.candles:
            t = datetime.fromtimestamp(candle.time_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            self.conn.execute(
                """
                INSERT INTO candles (
                    symbol, timeframe, time, open, high, low, close, volume, source, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "XAUUSD",
                    "W1",
                    t,
                    candle.open,
                    candle.high,
                    candle.low,
                    candle.close,
                    candle.volume,
                    "test",
                    now,
                    now,
                ),
            )
        self.conn.commit()

    def test_loads_candles_from_open_connection_without_lock(self) -> None:
        self._insert_candles_into_db()
        result = run_historical_range_scan(self.conn, self._config(dry_run=True))
        self.assertTrue(result.dry_run)
        self.assertGreater(result.candles_scanned, 0)

    def test_parse_scan_date(self) -> None:
        ms = parse_scan_date_ms("2025-01-01")
        self.assertGreater(ms, 0)

    def test_duplicate_range_candidates_deduped_across_steps(self) -> None:
        """Same RH/RL on consecutive replay weeks should emit one candidate only."""
        result = run_historical_range_scan(
            self.conn,
            self._config(candidate_kind_filter="RANGE_CANDIDATE"),
            candles=self.candles,
        )
        rows = self.conn.execute(
            """
            SELECT suggested_rh, suggested_rl
            FROM detector_suggestions
            WHERE candidate_kind = 'RANGE_CANDIDATE'
            ORDER BY candle_time_utc_ms ASC
            """
        ).fetchall()
        seen: set[tuple[float, float]] = set()
        for row in rows:
            key = (float(row["suggested_rh"]), float(row["suggested_rl"]))
            self.assertNotIn(key, seen, "duplicate RANGE_CANDIDATE RH/RL pair")
            seen.add(key)
        self.assertEqual(len(rows), result.range_candidate_count)


if __name__ == "__main__":
    unittest.main()
