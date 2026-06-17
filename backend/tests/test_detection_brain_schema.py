"""Phase 1 Detection Brain migration and storage smoke tests."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from detection_brain_schema import (  # noqa: E402
    DETECTION_BRAIN_SCHEMA,
    detection_brain_schema_status,
    init_detection_brain_schema,
)
from detection_brain_store import (  # noqa: E402
    DetectorCorrection,
    DetectorSuggestion,
    DetectorVersionRecord,
    DuplicateOpenSuggestionError,
    MappingSession,
    RetracementMeasurement,
    insert_correction,
    insert_mapping_session,
    insert_retracement_measurement,
    insert_suggestion,
    map_range_phase1_view,
    normalise_range_scale,
    register_detector_version,
    supersede_pending_suggestion,
    utc_now_ms,
)


def _legacy_map_ranges(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE map_ranges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            range_high REAL NOT NULL,
            range_low REAL NOT NULL,
            status TEXT DEFAULT 'active',
            range_scope TEXT NOT NULL DEFAULT 'MAJOR',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        INSERT INTO map_ranges(symbol, timeframe, range_high, range_low, status, range_scope, created_at, updated_at)
        VALUES ('XAUUSD', 'W1', 2000.0, 1900.0, 'ACTIVE', 'MINOR', '2026-01-01', '2026-01-01')
        """
    )


def _legacy_map_events(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE map_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            event_type TEXT NOT NULL,
            time TEXT,
            price REAL NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )


class DetectionBrainSchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        _legacy_map_ranges(self.conn)
        _legacy_map_events(self.conn)
        init_detection_brain_schema(self.conn)
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def test_schema_status_ok(self) -> None:
        status = detection_brain_schema_status(self.conn)
        self.assertTrue(status["ok"])
        self.assertEqual(status["schema_version"], DETECTION_BRAIN_SCHEMA)
        self.assertTrue(status["map_ranges_phase1_ready"])
        self.assertTrue(status["map_events_phase1_ready"])
        for table in (
            "detector_suggestions",
            "detector_corrections",
            "retracement_measurements",
            "mapping_sessions",
            "detector_version_registry",
        ):
            self.assertTrue(status["tables"][table]["exists"])

    def test_range_scale_backfill_from_legacy_range_scope(self) -> None:
        row = self.conn.execute("SELECT range_scale, range_scope FROM map_ranges WHERE id = 1").fetchone()
        self.assertEqual(row["range_scale"], "MINOR")
        view = map_range_phase1_view(self.conn, 1)
        self.assertIsNotNone(view)
        assert view is not None
        self.assertEqual(view["range_scale"], "MINOR")

    def test_range_scale_normalise_fallback(self) -> None:
        self.assertEqual(normalise_range_scale(None, row={"range_scope": "MINOR"}), "MINOR")
        self.assertEqual(normalise_range_scale("MAJOR"), "MAJOR")

    def test_open_suggestion_unique_constraint(self) -> None:
        now = utc_now_ms()
        base = dict(
            suggestion_id="sug-1",
            detector_version="RANGE_V1",
            engine_source="python_detector",
            candidate_kind="RANGE_MAJOR",
            symbol="XAUUSD",
            structure_layer="WEEKLY",
            source_timeframe="W1",
            chart_timeframe="W1",
            candle_time_utc_ms=now,
            created_at_utc_ms=now,
            candidate_index=0,
            parent_range_id=None,
        )
        insert_suggestion(self.conn, DetectorSuggestion(**base))
        with self.assertRaises(DuplicateOpenSuggestionError):
            insert_suggestion(
                self.conn,
                DetectorSuggestion(**{**base, "suggestion_id": "sug-2"}),
            )
        self.assertTrue(supersede_pending_suggestion(self.conn, "sug-1"))
        insert_suggestion(self.conn, DetectorSuggestion(**{**base, "suggestion_id": "sug-2"}))
        pending = self.conn.execute(
            "SELECT COUNT(*) AS n FROM detector_suggestions WHERE status = 'PENDING'"
        ).fetchone()["n"]
        self.assertEqual(pending, 1)

    def test_correction_requires_no_error_on_approve(self) -> None:
        now = utc_now_ms()
        with self.assertRaises(Exception):
            insert_correction(
                self.conn,
                DetectorCorrection(
                    correction_id="corr-bad",
                    suggestion_id="sug-x",
                    candidate_kind="RANGE_MAJOR",
                    detector_version="RANGE_V1",
                    symbol="XAUUSD",
                    structure_layer="WEEKLY",
                    source_timeframe="W1",
                    user_action="APPROVE",
                    error_category="WRONG_RH",
                    suggested_snapshot_json={"suggested_rh": 2000},
                    created_at_utc_ms=now,
                ),
            )
        row = insert_correction(
            self.conn,
            DetectorCorrection(
                correction_id="corr-good",
                suggestion_id="sug-x",
                candidate_kind="RANGE_MAJOR",
                detector_version="RANGE_V1",
                symbol="XAUUSD",
                structure_layer="WEEKLY",
                source_timeframe="W1",
                user_action="APPROVE",
                error_category="NO_ERROR",
                suggested_snapshot_json={"suggested_rh": 2000},
                created_at_utc_ms=now,
            ),
        )
        self.assertEqual(row["error_category"], "NO_ERROR")

    def test_storage_roundtrip_helpers(self) -> None:
        now = utc_now_ms()
        session = insert_mapping_session(
            self.conn,
            MappingSession(
                session_id="sess-1",
                symbol="XAUUSD",
                structure_layer="WEEKLY",
                source_timeframe="W1",
                chart_timeframe="W1",
                created_at_utc_ms=now,
                path_outcome="NO_MINOR_STRUCTURE",
                internal_structure_status="NO_MINOR_STRUCTURE",
            ),
        )
        self.assertEqual(session["path_outcome"], "NO_MINOR_STRUCTURE")

        register_detector_version(
            self.conn,
            DetectorVersionRecord(
                detector_version="RANGE_V1",
                domain="RANGE",
                major_number=1,
                created_at_utc_ms=now,
            ),
        )

        measurement = insert_retracement_measurement(
            self.conn,
            RetracementMeasurement(
                measurement_id="meas-1",
                detector_version="RETRACE_V1",
                old_range_id=1,
                new_range_id=2,
                bos_event_id=10,
                symbol="XAUUSD",
                structure_layer="WEEKLY",
                source_timeframe="W1",
                bos_direction="UP",
                retracement_direction="INTO_OLD_RANGE_UP",
                old_range_boundary_touched="LOW",
                retrace_start_time_ms=now,
                deepest_retrace_price=1950.0,
                max_retrace_percent=0.45,
                created_at_utc_ms=now,
            ),
        )
        self.assertEqual(measurement["retracement_direction"], "INTO_OLD_RANGE_UP")


class DetectionBrainInitDbSmokeTests(unittest.TestCase):
    def test_init_db_on_temp_file_preserves_legacy_rows(self) -> None:
        import gc
        import candle_store

        db_path = Path(__file__).resolve().parent / "_phase1_smoke.db"
        if db_path.exists():
            db_path.unlink()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        _legacy_map_ranges(conn)
        _legacy_map_events(conn)
        conn.commit()
        conn.close()

        old_path = candle_store.DB_PATH
        try:
            candle_store.DB_PATH = db_path
            candle_store.init_db()
            conn2 = candle_store.connect()
            try:
                status = detection_brain_schema_status(conn2)
                self.assertTrue(status["ok"])
                count = conn2.execute("SELECT COUNT(*) AS n FROM map_ranges").fetchone()["n"]
                self.assertEqual(count, 1)
                row = conn2.execute(
                    "SELECT range_scale, range_scope FROM map_ranges WHERE id = 1"
                ).fetchone()
                self.assertEqual(row["range_scale"], "MINOR")
            finally:
                conn2.close()
                del conn2
                gc.collect()
        finally:
            candle_store.DB_PATH = old_path
            if db_path.exists():
                db_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
