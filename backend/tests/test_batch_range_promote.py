"""Batch promote RANGE_CANDIDATE tests."""

from __future__ import annotations

import gc
import json
import sqlite3
import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import candle_store
from detection_brain_batch_promote import BatchPromoteFilters, batch_promote_range_candidates
from detection_brain_schema import init_detection_brain_schema
from detection_brain_store import DetectorSuggestion, insert_suggestion, utc_now_ms
from detector.versions import ENGINE_SOURCE, RANGE_V1


def _insert_candidate(
    conn: sqlite3.Connection,
    suggestion_id: str,
    *,
    rh: float = 110.0,
    rl: float = 100.0,
    candle_ms: int | None = None,
    status: str = "PENDING",
    detector_version: str = RANGE_V1,
    detection_run_id: str | None = None,
    candidate_index: int = 0,
    structure_layer: str = "WEEKLY",
    source_timeframe: str = "W1",
    chart_timeframe: str = "W1",
) -> None:
    now = candle_ms or utc_now_ms()
    meta = {
        "historical_scan": 1,
        "detection_run_id": detection_run_id or "run-test-1",
        "replay_until_time_ms": now,
        "lifecycle_state": "ACTIVE_RANGE",
        "boundary_selection_reason": "OPPOSITE_SWING",
    }
    insert_suggestion(
        conn,
        DetectorSuggestion(
            suggestion_id=suggestion_id,
            detector_version=detector_version,
            engine_source=ENGINE_SOURCE,
            candidate_kind="RANGE_CANDIDATE",
            candidate_index=candidate_index,
            status=status,
            symbol="XAUUSD",
            structure_layer=structure_layer,
            source_timeframe=source_timeframe,
            chart_timeframe=chart_timeframe,
            candle_time_utc_ms=now,
            created_at_utc_ms=now,
            suggested_rh=rh,
            suggested_rl=rl,
            suggested_rh_time_ms=now,
            suggested_rl_time_ms=now - 86_400_000,
            range_scale="UNKNOWN",
            meta_json=meta,
        ),
    )
    conn.commit()


class BatchRangePromoteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db_path = Path(__file__).resolve().parent / "_batch_range_promote.db"
        if self.db_path.exists():
            self.db_path.unlink()
        self.old_path = candle_store.DB_PATH
        candle_store.DB_PATH = self.db_path
        candle_store.init_db()
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        init_detection_brain_schema(self.conn)
        self.conn.commit()

        base_ms = 1_704_067_200_000  # 2024-01-01 UTC
        _insert_candidate(self.conn, "sug-batch-1", candle_ms=base_ms, candidate_index=0)
        _insert_candidate(self.conn, "sug-batch-2", candle_ms=base_ms + 86_400_000 * 7, candidate_index=1)
        _insert_candidate(
            self.conn,
            "sug-batch-other-tf",
            candle_ms=base_ms,
            rh=200.0,
            rl=180.0,
            candidate_index=0,
            structure_layer="DAILY",
            source_timeframe="D1",
            chart_timeframe="D1",
        )
        self.conn.commit()

        self.filters = BatchPromoteFilters(
            symbol="XAUUSD",
            source_timeframe="W1",
            structure_layer="WEEKLY",
            date_from_ms=base_ms - 1,
            date_to_ms=base_ms + 86_400_000 * 30,
            candidate_kind="RANGE_CANDIDATE",
            status="PENDING",
        )

    def tearDown(self) -> None:
        self.conn.close()
        candle_store.DB_PATH = self.old_path
        gc.collect()
        if self.db_path.exists():
            self.db_path.unlink(missing_ok=True)

    def test_dry_run_creates_no_map_ranges(self) -> None:
        before = self.conn.execute("SELECT COUNT(*) AS n FROM map_ranges").fetchone()["n"]
        result = batch_promote_range_candidates(self.conn, self.filters, confirm=False)
        after = self.conn.execute("SELECT COUNT(*) AS n FROM map_ranges").fetchone()["n"]
        self.assertEqual(before, after)
        self.assertTrue(result.dry_run)
        self.assertEqual(result.counts.pending_candidates_found, 2)
        self.assertEqual(result.counts.would_promote, 2)
        self.assertEqual(result.counts.promoted, 0)

    def test_confirm_creates_map_ranges(self) -> None:
        result = batch_promote_range_candidates(self.conn, self.filters, confirm=True)
        self.assertTrue(result.ok)
        self.assertEqual(result.counts.promoted, 2)
        count = self.conn.execute("SELECT COUNT(*) AS n FROM map_ranges").fetchone()["n"]
        self.assertEqual(count, 2)
        row = self.conn.execute(
            "SELECT range_scale, user_action_at_confirm FROM map_ranges WHERE confirmed_from_suggestion_id = ?",
            ("sug-batch-1",),
        ).fetchone()
        self.assertEqual(row["range_scale"], "UNKNOWN")
        self.assertEqual(row["user_action_at_confirm"], "BATCH_APPROVE")

    def test_rerun_is_idempotent(self) -> None:
        first = batch_promote_range_candidates(self.conn, self.filters, confirm=True)
        second = batch_promote_range_candidates(self.conn, self.filters, confirm=True)
        count = self.conn.execute("SELECT COUNT(*) AS n FROM map_ranges").fetchone()["n"]
        self.assertEqual(first.counts.promoted, 2)
        self.assertEqual(second.counts.promoted, 0)
        self.assertEqual(second.counts.pending_candidates_found, 0)
        self.assertEqual(count, 2)

    def test_corrections_written_with_no_error(self) -> None:
        batch_promote_range_candidates(self.conn, self.filters, confirm=True)
        corr = self.conn.execute(
            "SELECT user_action, error_category FROM detector_corrections WHERE suggestion_id = ?",
            ("sug-batch-1",),
        ).fetchone()
        self.assertEqual(corr["user_action"], "BATCH_APPROVE")
        self.assertEqual(corr["error_category"], "NO_ERROR")

    def test_filters_by_timeframe_layer(self) -> None:
        d1_filters = BatchPromoteFilters(
            symbol="XAUUSD",
            source_timeframe="D1",
            structure_layer="DAILY",
            candidate_kind="RANGE_CANDIDATE",
            status="PENDING",
        )
        dry = batch_promote_range_candidates(self.conn, d1_filters, confirm=False)
        self.assertEqual(dry.counts.pending_candidates_found, 1)
        self.assertEqual(dry.counts.would_promote, 1)

    def test_no_major_minor_forced(self) -> None:
        batch_promote_range_candidates(self.conn, self.filters, confirm=True)
        rows = self.conn.execute(
            "SELECT range_scale, range_role FROM map_ranges WHERE confirmed_from_suggestion_id LIKE 'sug-batch-%'"
        ).fetchall()
        for row in rows:
            self.assertEqual(row["range_scale"], "UNKNOWN")
            self.assertIsNone(row["range_role"])


if __name__ == "__main__":
    unittest.main()
