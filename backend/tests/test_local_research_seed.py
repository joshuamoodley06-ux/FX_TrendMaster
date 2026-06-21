"""Local research weekly seed CLI tests."""

from __future__ import annotations

import gc
import sqlite3
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import candle_store
from detection_brain_schema import init_detection_brain_schema
from local_research_seed import (
    activate_weekly_seed,
    create_manual_weekly_seed,
    diagnose_historical_scan,
    has_active_weekly_seed,
    list_weekly_ranges,
    main,
)


class LocalResearchSeedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db_path = Path(tempfile.gettempdir()) / f"_local_research_seed_{uuid.uuid4().hex}.db"
        self.old_path = candle_store.DB_PATH
        candle_store.DB_PATH = self.db_path
        candle_store.init_db()
        schema_conn = sqlite3.connect(self.db_path)
        init_detection_brain_schema(schema_conn)
        schema_conn.close()
        self._conn: sqlite3.Connection | None = None

    def tearDown(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
        candle_store.DB_PATH = self.old_path
        gc.collect()
        if self.db_path.exists():
            try:
                self.db_path.unlink()
            except OSError:
                pass

    def _open_conn(self) -> sqlite3.Connection:
        if self._conn is not None:
            self._conn.close()
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        self._conn = conn
        return conn

    def test_check_reports_no_seed_initially(self) -> None:
        out = has_active_weekly_seed(self._open_conn(), "XAUUSD")
        self.assertTrue(out["ok"])
        self.assertFalse(out["has_seed"])
        self.assertEqual(out["count"], 0)

    def test_create_manual_seed_becomes_active_weekly_range(self) -> None:
        created = create_manual_weekly_seed(
            symbol="XAUUSD",
            range_high_price=2500.0,
            range_low_price=2300.0,
            db_path=str(self.db_path),
        )
        self.assertTrue(created["ok"])
        self.assertTrue(created["has_seed"])
        row = self._open_conn().execute(
            """
            SELECT status, structure_layer, source_timeframe, range_scale,
                   user_action_at_confirm, source, range_high_price, range_low_price
            FROM map_ranges WHERE id = ?
            """,
            (created["range_id"],),
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["status"], "ACTIVE")
        self.assertEqual(row["structure_layer"], "WEEKLY")
        self.assertEqual(row["source_timeframe"], "W1")
        self.assertEqual(row["range_scale"], "UNKNOWN")
        self.assertEqual(row["user_action_at_confirm"], "MANUAL_SEED")
        self.assertEqual(row["source"], "manual")
        self.assertEqual(float(row["range_high_price"]), 2500.0)
        self.assertEqual(float(row["range_low_price"]), 2300.0)

    def test_activate_existing_range_sets_single_active_seed(self) -> None:
        first = create_manual_weekly_seed(
            symbol="XAUUSD",
            range_high_price=2400.0,
            range_low_price=2200.0,
            db_path=str(self.db_path),
        )
        second = create_manual_weekly_seed(
            symbol="XAUUSD",
            range_high_price=2600.0,
            range_low_price=2400.0,
            db_path=str(self.db_path),
        )
        self.assertTrue(first["ok"])
        self.assertTrue(second["ok"])

        activated = activate_weekly_seed(
            self._open_conn(),
            symbol="XAUUSD",
            range_id=int(first["range_id"]),
        )
        self.assertTrue(activated["ok"])
        self.assertTrue(activated["has_seed"])

        rows = self._conn.execute(
            """
            SELECT id, status FROM map_ranges
            WHERE symbol = 'XAUUSD'
              AND COALESCE(structure_layer, layer) = 'WEEKLY'
              AND COALESCE(source_timeframe, timeframe) = 'W1'
            ORDER BY id
            """
        ).fetchall()
        active_ids = [int(r["id"]) for r in rows if str(r["status"]).upper() == "ACTIVE"]
        self.assertEqual(active_ids, [int(first["range_id"])])

    def test_list_weekly_ranges_marks_selectable_rows(self) -> None:
        create_manual_weekly_seed(
            symbol="XAUUSD",
            range_high_price=2450.0,
            range_low_price=2350.0,
            db_path=str(self.db_path),
        )
        ranges = list_weekly_ranges(self._open_conn(), "XAUUSD")
        self.assertEqual(len(ranges), 1)
        self.assertTrue(ranges[0]["selectable"])

    def test_cli_check_json_exit_code(self) -> None:
        code = main(["check", "--db", str(self.db_path), "--json", "--symbol", "XAUUSD"])
        self.assertEqual(code, 0)

    def test_diagnose_scan_reports_missing_run(self) -> None:
        out = diagnose_historical_scan(
            self._open_conn(),
            symbol="XAUUSD",
            detection_run_id="missing-run-id",
        )
        self.assertFalse(out["ok"])
        self.assertIn("No historical_scan", out["error"])


if __name__ == "__main__":
    unittest.main()
