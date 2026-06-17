"""Phase 3.5 detector performance reporting tests."""

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
from detection_brain_schema import DETECTOR_ANALYTICS_VIEWS, init_detection_brain_schema
from detection_brain_store import DetectorCorrection, insert_correction, utc_now_ms
from detector.versions import RANGE_V1
from detector_performance import (
    PerformanceFilters,
    get_candidate_kind_stats,
    get_detector_health_summary,
    get_detector_scorecard,
    get_detector_summary,
    get_detector_version_stats,
    get_error_category_analysis,
    get_guided_workflow_readiness,
    get_timeframe_stats,
    render_cli_report,
)


def _insert_correction(
    conn: sqlite3.Connection,
    *,
    correction_id: str,
    suggestion_id: str,
    user_action: str,
    error_category: str,
    candidate_kind: str = "RANGE_MAJOR",
    detector_version: str = RANGE_V1,
    source_timeframe: str = "W1",
    range_scale: str = "MAJOR",
) -> None:
    now = utc_now_ms()
    snapshot = {
        "suggestion_id": suggestion_id,
        "candidate_kind": candidate_kind,
        "detector_version": detector_version,
        "range_scale": range_scale,
        "suggested_rh": 110.0,
        "suggested_rl": 100.0,
    }
    insert_correction(
        conn,
        DetectorCorrection(
            correction_id=correction_id,
            suggestion_id=suggestion_id,
            candidate_kind=candidate_kind,
            detector_version=detector_version,
            symbol="XAUUSD",
            structure_layer="WEEKLY",
            source_timeframe=source_timeframe,
            user_action=user_action,
            error_category=error_category,
            suggested_snapshot_json=snapshot,
            created_at_utc_ms=now,
        ),
    )


class DetectorPerformanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db_path = Path(__file__).resolve().parent / "_phase35_performance.db"
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

    def test_analytics_view_exists(self) -> None:
        for view in DETECTOR_ANALYTICS_VIEWS:
            row = self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='view' AND name=?",
                (view,),
            ).fetchone()
            self.assertIsNotNone(row, f"missing view {view}")

    def test_empty_db_returns_zero_rates(self) -> None:
        summary = get_detector_summary(self.conn)
        self.assertEqual(summary["total_reviewed"], 0)
        self.assertIsNone(summary["approval_rate"])

    def test_summary_rates_from_corrections(self) -> None:
        _insert_correction(self.conn, correction_id="c1", suggestion_id="s1", user_action="APPROVE", error_category="NO_ERROR")
        _insert_correction(self.conn, correction_id="c2", suggestion_id="s2", user_action="APPROVE", error_category="NO_ERROR")
        _insert_correction(self.conn, correction_id="c3", suggestion_id="s3", user_action="EDIT", error_category="WRONG_RH")
        _insert_correction(self.conn, correction_id="c4", suggestion_id="s4", user_action="REJECT", error_category="WRONG_RL")
        self.conn.commit()

        summary = get_detector_summary(self.conn)
        self.assertEqual(summary["total_reviewed"], 4)
        self.assertEqual(summary["approved"], 2)
        self.assertEqual(summary["edited"], 1)
        self.assertEqual(summary["rejected"], 1)
        self.assertAlmostEqual(summary["approval_rate"], 0.5)
        self.assertAlmostEqual(summary["edit_rate"], 0.25)
        self.assertAlmostEqual(summary["rejection_rate"], 0.25)

    def test_version_and_kind_stats(self) -> None:
        _insert_correction(self.conn, correction_id="c1", suggestion_id="s1", user_action="APPROVE", error_category="NO_ERROR")
        _insert_correction(
            self.conn,
            correction_id="c2",
            suggestion_id="s2",
            user_action="REJECT",
            error_category="WRONG_BOS",
            candidate_kind="BOS_UP",
            detector_version="BOS_V1",
        )
        self.conn.commit()

        version_stats = get_detector_version_stats(self.conn, "BOS_V1")
        self.assertEqual(version_stats["total_reviewed"], 1)
        self.assertEqual(version_stats["rejected"], 1)
        self.assertEqual(version_stats["approval_rate"], 0.0)

        kind_stats = get_candidate_kind_stats(self.conn, "RANGE_MAJOR")
        self.assertEqual(kind_stats["approved"], 1)
        self.assertEqual(kind_stats["approval_rate"], 1.0)

    def test_timeframe_stats(self) -> None:
        _insert_correction(
            self.conn,
            correction_id="c1",
            suggestion_id="s1",
            user_action="APPROVE",
            error_category="NO_ERROR",
            source_timeframe="D1",
        )
        self.conn.commit()
        tf = get_timeframe_stats(self.conn, "D1")
        self.assertEqual(tf["total_reviewed"], 1)
        self.assertEqual(tf["approval_rate"], 1.0)

    def test_error_category_analysis(self) -> None:
        _insert_correction(self.conn, correction_id="c1", suggestion_id="s1", user_action="EDIT", error_category="WRONG_RH")
        _insert_correction(self.conn, correction_id="c2", suggestion_id="s2", user_action="EDIT", error_category="WRONG_RH")
        _insert_correction(
            self.conn,
            correction_id="c3",
            suggestion_id="s3",
            user_action="REJECT",
            error_category="FALSE_SWING",
            candidate_kind="SWING_HIGH",
            detector_version="SWING_V1",
        )
        self.conn.commit()

        analysis = get_error_category_analysis(self.conn)
        totals = {row["error_category"]: row["count"] for row in analysis["totals"]}
        self.assertEqual(totals["WRONG_RH"], 2)
        self.assertEqual(totals["FALSE_SWING"], 1)
        self.assertIn("SWING_V1", [x["detector_version"] for x in analysis["by_detector_version"]["FALSE_SWING"]])

    def test_scorecard_text(self) -> None:
        _insert_correction(self.conn, correction_id="c1", suggestion_id="s1", user_action="APPROVE", error_category="NO_ERROR")
        _insert_correction(
            self.conn,
            correction_id="c2",
            suggestion_id="s2",
            user_action="REJECT",
            error_category="OTHER",
            candidate_kind="REF_CANDLE",
            detector_version="REF_CANDLE_V1",
        )
        self.conn.commit()

        scorecard = get_detector_scorecard(self.conn)
        text = scorecard["text"]
        self.assertIn("RANGE_MAJOR", text)
        self.assertIn("Approval:", text)
        self.assertIn("REF_CANDLE", text)

    def test_guided_workflow_readiness_thresholds(self) -> None:
        for i in range(6):
            _insert_correction(
                self.conn,
                correction_id=f"rm-{i}",
                suggestion_id=f"sm-{i}",
                user_action="APPROVE",
                error_category="NO_ERROR",
                candidate_kind="RANGE_MAJOR",
            )
        for i in range(6):
            _insert_correction(
                self.conn,
                correction_id=f"bos-{i}",
                suggestion_id=f"sb-{i}",
                user_action="REJECT",
                error_category="WRONG_BOS",
                candidate_kind="BOS_UP",
                detector_version="BOS_V1",
            )
        self.conn.commit()

        readiness = get_guided_workflow_readiness(self.conn)
        by_name = {c["component"]: c for c in readiness["components"]}
        self.assertTrue(by_name["RANGE_MAJOR"]["trustworthy"])
        self.assertFalse(by_name["BOS"]["trustworthy"])
        self.assertEqual(readiness["workflow_engine"], "GUIDED_WORKFLOW_ENGINE")
        self.assertFalse(readiness["ready_for_phase_4_guided_acceleration"])

    def test_health_summary_and_cli_report(self) -> None:
        _insert_correction(self.conn, correction_id="c1", suggestion_id="s1", user_action="APPROVE", error_category="NO_ERROR")
        self.conn.commit()
        health = get_detector_health_summary(self.conn, PerformanceFilters(symbol="XAUUSD"))
        self.assertIn("summary", health)
        self.assertIn("guided_workflow_readiness", health)
        report = render_cli_report(self.conn)
        self.assertIn("Detector Performance Report", report)
        self.assertIn("GUIDED WORKFLOW READINESS", report)


if __name__ == "__main__":
    unittest.main()
