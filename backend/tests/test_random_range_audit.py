"""Random range audit sampler tests."""

from __future__ import annotations

import gc
import sqlite3
import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import candle_store
from detection_brain_batch_promote import BatchPromoteFilters, batch_promote_range_candidates
from detection_brain_random_audit import RandomAuditFilters, sample_random_audit_rows
from detection_brain_schema import init_detection_brain_schema
from detection_brain_store import DetectorSuggestion, insert_suggestion, utc_now_ms
from detector.versions import ENGINE_SOURCE, RANGE_V1


def _insert_candidate(conn: sqlite3.Connection, suggestion_id: str, candle_ms: int, candidate_index: int = 0) -> None:
    insert_suggestion(
        conn,
        DetectorSuggestion(
            suggestion_id=suggestion_id,
            detector_version=RANGE_V1,
            engine_source=ENGINE_SOURCE,
            candidate_kind="RANGE_CANDIDATE",
            candidate_index=candidate_index,
            symbol="XAUUSD",
            structure_layer="WEEKLY",
            source_timeframe="W1",
            chart_timeframe="W1",
            candle_time_utc_ms=candle_ms,
            created_at_utc_ms=candle_ms,
            suggested_rh=120.0,
            suggested_rl=100.0,
            suggested_rh_time_ms=candle_ms,
            suggested_rl_time_ms=candle_ms - 86_400_000,
            range_scale="UNKNOWN",
            meta_json={
                "replay_until_time_ms": candle_ms,
                "lifecycle_state": "ACTIVE_RANGE",
                "boundary_selection_reason": "OPPOSITE_SWING",
            },
        ),
    )
    conn.commit()


class RandomRangeAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db_path = Path(__file__).resolve().parent / "_random_range_audit.db"
        if self.db_path.exists():
            self.db_path.unlink()
        self.old_path = candle_store.DB_PATH
        candle_store.DB_PATH = self.db_path
        candle_store.init_db()
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        init_detection_brain_schema(self.conn)
        self.conn.commit()

        base = 1_704_067_200_000
        for idx in range(6):
            _insert_candidate(self.conn, f"sug-audit-{idx}", base + idx * 86_400_000, candidate_index=idx)

    def tearDown(self) -> None:
        self.conn.close()
        candle_store.DB_PATH = self.old_path
        gc.collect()
        if self.db_path.exists():
            self.db_path.unlink(missing_ok=True)

    def test_random_sampler_returns_valid_rows(self) -> None:
        out = sample_random_audit_rows(
            self.conn,
            RandomAuditFilters(
                symbol="XAUUSD",
                source_timeframe="W1",
                structure_layer="WEEKLY",
                limit=3,
                source="suggestions",
            ),
        )
        self.assertTrue(out["ok"])
        self.assertEqual(out["count"], 3)
        self.assertGreaterEqual(out["pool_size"], 6)
        for row in out["samples"]:
            self.assertIn("rh", row)
            self.assertIn("rl", row)
            self.assertEqual(row["structure_layer"], "WEEKLY")
            self.assertEqual(row["source_timeframe"], "W1")
            self.assertIn("lifecycle_state", row)
            self.assertIn("boundary_selection_reason", row)

    def test_confirmed_ranges_source(self) -> None:
        promote = batch_promote_range_candidates(
            self.conn,
            BatchPromoteFilters(
                symbol="XAUUSD",
                source_timeframe="W1",
                structure_layer="WEEKLY",
                candidate_kind="RANGE_CANDIDATE",
                status="PENDING",
            ),
            confirm=True,
        )
        self.assertEqual(promote.counts.promoted, 6)
        out = sample_random_audit_rows(
            self.conn,
            RandomAuditFilters(
                symbol="XAUUSD",
                source_timeframe="W1",
                structure_layer="WEEKLY",
                limit=2,
                source="confirmed_ranges",
            ),
        )
        self.assertEqual(out["count"], 2)
        for row in out["samples"]:
            self.assertEqual(row["source"], "confirmed_ranges")
            self.assertIsNotNone(row["range_id"])


if __name__ == "__main__":
    unittest.main()
