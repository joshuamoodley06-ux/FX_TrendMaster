"""Phase 3 promotion workflow tests."""

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
from detection_brain_promotion import review_suggestion
from detection_brain_schema import init_detection_brain_schema
from detection_brain_store import DetectorSuggestion, insert_suggestion, utc_now_ms
from detector.versions import ENGINE_SOURCE, RANGE_V1


def _insert_range_suggestion(conn: sqlite3.Connection, suggestion_id: str, rh: float = 110.0, rl: float = 100.0) -> None:
    now = utc_now_ms()
    insert_suggestion(
        conn,
        DetectorSuggestion(
            suggestion_id=suggestion_id,
            detector_version=RANGE_V1,
            engine_source=ENGINE_SOURCE,
            candidate_kind="RANGE_MAJOR",
            symbol="XAUUSD",
            structure_layer="WEEKLY",
            source_timeframe="W1",
            chart_timeframe="W1",
            candle_time_utc_ms=now,
            created_at_utc_ms=now,
            suggested_rh=rh,
            suggested_rl=rl,
            suggested_rh_time_ms=now,
            suggested_rl_time_ms=now - 86_400_000,
            range_scale="MAJOR",
            range_role="ACTIVE_CONTAINER",
        ),
    )
    conn.commit()


class PromotionWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db_path = Path(__file__).resolve().parent / "_phase3_promotion.db"
        if self.db_path.exists():
            self.db_path.unlink()
        self.old_path = candle_store.DB_PATH
        candle_store.DB_PATH = self.db_path
        candle_store.init_db()
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        init_detection_brain_schema(self.conn)
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()
        candle_store.DB_PATH = self.old_path
        gc.collect()
        if self.db_path.exists():
            self.db_path.unlink(missing_ok=True)

    def test_approve_creates_confirmed_range_and_correction(self) -> None:
        _insert_range_suggestion(self.conn, "sug-approve-1")
        out = review_suggestion(self.conn, "sug-approve-1", action="APPROVE")
        self.assertTrue(out["ok"])
        self.assertIsNotNone(out["promoted_range_id"])

        row = self.conn.execute(
            "SELECT range_high_price, range_low_price, confirmed_from_suggestion_id, user_action_at_confirm "
            "FROM map_ranges WHERE id = ?",
            (out["promoted_range_id"],),
        ).fetchone()
        self.assertEqual(float(row["range_high_price"]), 110.0)
        self.assertEqual(float(row["range_low_price"]), 100.0)
        self.assertEqual(row["confirmed_from_suggestion_id"], "sug-approve-1")
        self.assertEqual(row["user_action_at_confirm"], "APPROVE")

        corr = self.conn.execute(
            "SELECT error_category, user_action FROM detector_corrections WHERE suggestion_id = ?",
            ("sug-approve-1",),
        ).fetchone()
        self.assertEqual(corr["error_category"], "NO_ERROR")
        self.assertEqual(corr["user_action"], "APPROVE")

    def test_edit_approve_uses_edited_final_values(self) -> None:
        _insert_range_suggestion(self.conn, "sug-edit-1", rh=110.0, rl=100.0)
        out = review_suggestion(
            self.conn,
            "sug-edit-1",
            action="EDIT",
            edits={"suggested_rh": 115.0, "suggested_rl": 95.0},
            error_category="WRONG_RH",
        )
        self.assertTrue(out["ok"])
        row = self.conn.execute(
            "SELECT range_high_price, range_low_price FROM map_ranges WHERE id = ?",
            (out["promoted_range_id"],),
        ).fetchone()
        self.assertEqual(float(row["range_high_price"]), 115.0)
        self.assertEqual(float(row["range_low_price"]), 95.0)

        corr = self.conn.execute(
            "SELECT error_category FROM detector_corrections WHERE suggestion_id = ?",
            ("sug-edit-1",),
        ).fetchone()
        self.assertEqual(corr["error_category"], "WRONG_RH")

    def test_reject_creates_no_confirmed_row(self) -> None:
        _insert_range_suggestion(self.conn, "sug-reject-1")
        before_ranges = self.conn.execute("SELECT COUNT(*) AS n FROM map_ranges").fetchone()["n"]
        before_events = self.conn.execute("SELECT COUNT(*) AS n FROM map_events").fetchone()["n"]
        out = review_suggestion(
            self.conn,
            "sug-reject-1",
            action="REJECT",
            error_category="WRONG_RL",
            notes="not valid",
        )
        self.assertTrue(out["ok"])
        self.assertIsNone(out.get("promoted_range_id"))
        after_ranges = self.conn.execute("SELECT COUNT(*) AS n FROM map_ranges").fetchone()["n"]
        after_events = self.conn.execute("SELECT COUNT(*) AS n FROM map_events").fetchone()["n"]
        self.assertEqual(before_ranges, after_ranges)
        self.assertEqual(before_events, after_events)
        status = self.conn.execute(
            "SELECT status FROM detector_suggestions WHERE suggestion_id = ?",
            ("sug-reject-1",),
        ).fetchone()["status"]
        self.assertEqual(status, "REJECTED")

    def test_duplicate_approve_does_not_create_second_range(self) -> None:
        _insert_range_suggestion(self.conn, "sug-dup-1")
        first = review_suggestion(self.conn, "sug-dup-1", action="APPROVE")
        second = review_suggestion(self.conn, "sug-dup-1", action="APPROVE")
        self.assertTrue(second.get("duplicate"))
        count = self.conn.execute("SELECT COUNT(*) AS n FROM map_ranges").fetchone()["n"]
        self.assertEqual(count, 1)
        self.assertEqual(first["promoted_range_id"], second["suggestion"].get("promoted_range_id"))


if __name__ == "__main__":
    unittest.main()
