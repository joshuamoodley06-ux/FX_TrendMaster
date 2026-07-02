"""Tests for scoped recursive hard delete of structural map ranges."""

from __future__ import annotations

import gc
import sqlite3
import sys
import unittest
import uuid
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import candle_store


def _insert_range(
    conn: sqlite3.Connection,
    *,
    symbol: str = "XAUUSD",
    raw_case_id: str = "case-a",
    case_ref: str = "raw:case-a",
    structure_layer: str = "DAILY",
    parent_range_id: int | None = None,
    old_range_id: int | None = None,
    new_range_id: int | None = None,
    status: str = "ACTIVE",
) -> int:
    now = candle_store.now_iso()
    cur = conn.execute(
        """
        INSERT INTO map_ranges(
            symbol, timeframe, structure_layer, layer, source_timeframe, chart_timeframe,
            range_high, range_low, status, raw_case_id, case_ref, parent_range_id,
            old_range_id, new_range_id, range_scope, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'MAJOR', ?, ?)
        """,
        (
            symbol,
            "D1" if structure_layer == "DAILY" else "H4",
            structure_layer,
            structure_layer,
            "D1" if structure_layer == "DAILY" else "H4",
            "D1" if structure_layer == "DAILY" else "H4",
            100.0,
            90.0,
            status,
            raw_case_id,
            case_ref,
            parent_range_id,
            old_range_id,
            new_range_id,
            now,
            now,
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def _insert_event(conn: sqlite3.Connection, *, range_id: int, active_range_id: int | None = None) -> int:
    now = candle_store.now_iso()
    cur = conn.execute(
        """
        INSERT INTO map_events(
            range_id, active_range_id, symbol, timeframe, event_type, event_name, time, price,
            source, created_at, updated_at
        ) VALUES (?, ?, 'XAUUSD', 'D1', 'BOS_UP', 'BOS Up', ?, 101.0, 'test', ?, ?)
        """,
        (range_id, active_range_id or range_id, now, now, now),
    )
    conn.commit()
    return int(cur.lastrowid)


class HardDeleteMapRangesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db_path = Path(__file__).resolve().parent / f"_hard_delete_{uuid.uuid4().hex}.db"
        self.old_path = candle_store.DB_PATH
        candle_store.DB_PATH = self.db_path
        candle_store.init_db()
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.raw_case_id = "case-a"
        self.case_ref = f"raw:{self.raw_case_id}"

    def tearDown(self) -> None:
        self.conn.close()
        candle_store.DB_PATH = self.old_path
        gc.collect()
        if self.db_path.exists():
            self.db_path.unlink(missing_ok=True)

    def _delete(self, range_ids: list[int], **kwargs):
        return candle_store.hard_delete_map_ranges(
            range_ids=range_ids,
            symbol="XAUUSD",
            raw_case_id=self.raw_case_id,
            case_ref=self.case_ref,
            confirm="DELETE",
            include_descendants=True,
            **kwargs,
        )

    def test_delete_leaf_micro_range(self) -> None:
        micro_id = _insert_range(self.conn, structure_layer="MICRO")
        event_id = _insert_event(self.conn, range_id=micro_id)
        result = self._delete([micro_id])
        self.assertTrue(result["ok"])
        self.assertEqual(result["deleted_range_ids"], [micro_id])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM map_ranges WHERE id=?", (micro_id,)).fetchone()[0], 0)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM map_events WHERE id=?", (event_id,)).fetchone()[0], 0)

    def test_delete_parent_intraday_with_micro_child(self) -> None:
        parent_id = _insert_range(self.conn, structure_layer="INTRADAY")
        child_id = _insert_range(self.conn, structure_layer="MICRO", parent_range_id=parent_id)
        result = self._delete([parent_id])
        self.assertTrue(result["ok"])
        self.assertIn(parent_id, result["deleted_range_ids"])
        self.assertIn(child_id, result["deleted_range_ids"])
        self.assertGreaterEqual(result["deleted_child_count"], 1)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM map_ranges").fetchone()[0], 0)

    def test_delete_chain_linked_successor(self) -> None:
        first_id = _insert_range(self.conn, structure_layer="DAILY")
        second_id = _insert_range(self.conn, structure_layer="DAILY", old_range_id=first_id)
        self.conn.execute("UPDATE map_ranges SET new_range_id=? WHERE id=?", (second_id, first_id))
        self.conn.commit()
        result = self._delete([first_id])
        self.assertTrue(result["ok"])
        self.assertIn(first_id, result["deleted_range_ids"])
        self.assertIn(second_id, result["deleted_range_ids"])

    def test_scope_rejects_other_case(self) -> None:
        other_id = _insert_range(self.conn, raw_case_id="other-case", case_ref="raw:other-case")
        result = self._delete([other_id])
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "SCOPE_VALIDATION_FAILED")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM map_ranges WHERE id=?", (other_id,)).fetchone()[0], 1)

    def test_scope_rejects_other_symbol(self) -> None:
        other_id = _insert_range(self.conn, symbol="EURUSD")
        result = self._delete([other_id])
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "SCOPE_VALIDATION_FAILED")

    def test_delete_scope_accepts_derived_case_ref(self) -> None:
        now = candle_store.now_iso()
        cur = self.conn.execute(
            """
            INSERT INTO map_ranges(
                symbol, timeframe, structure_layer, layer, source_timeframe, chart_timeframe,
                range_high, range_low, status, raw_case_id, case_ref, range_scope, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 'MAJOR', ?, ?)
            """,
            ("XAUUSD", "M15", "MICRO", "MICRO", "M15", "M15", 100.0, 90.0, "ACTIVE", self.raw_case_id, now, now),
        )
        self.conn.commit()
        micro_id = int(cur.lastrowid)
        result = candle_store.hard_delete_map_ranges(
            range_ids=[micro_id],
            symbol="XAUUSD",
            raw_case_id=self.raw_case_id,
            case_ref=self.case_ref,
            confirm="DELETE",
            include_descendants=True,
        )
        self.assertTrue(result["ok"])
        self.assertIn(micro_id, result["deleted_range_ids"])

    def test_delete_zero_rows_not_ok(self) -> None:
        missing_id = 999999
        result = self._delete([missing_id])
        self.assertFalse(result["ok"])

    def test_scrubs_survivor_chain_refs(self) -> None:
        survivor_id = _insert_range(self.conn, structure_layer="DAILY")
        doomed_id = _insert_range(self.conn, structure_layer="DAILY")
        self.conn.execute("UPDATE map_ranges SET new_range_id=? WHERE id=?", (doomed_id, survivor_id))
        self.conn.commit()
        result = self._delete([doomed_id])
        self.assertTrue(result["ok"])
        row = self.conn.execute("SELECT new_range_id FROM map_ranges WHERE id=?", (survivor_id,)).fetchone()
        self.assertIsNone(row["new_range_id"])
        self.assertGreaterEqual(result["scrubbed_reference_count"], 1)

    def test_scrubs_survivor_parent_ref_when_parent_deleted_without_descendants(self) -> None:
        parent_id = _insert_range(self.conn, structure_layer="WEEKLY")
        child_id = _insert_range(self.conn, structure_layer="DAILY", parent_range_id=parent_id)
        result = candle_store.hard_delete_map_ranges(
            range_ids=[parent_id],
            symbol="XAUUSD",
            raw_case_id=self.raw_case_id,
            case_ref=self.case_ref,
            confirm="DELETE",
            include_descendants=False,
        )
        self.assertTrue(result["ok"])
        row = self.conn.execute("SELECT parent_range_id FROM map_ranges WHERE id=?", (child_id,)).fetchone()
        self.assertIsNone(row["parent_range_id"])
        self.assertGreaterEqual(result["scrubbed_reference_count"], 1)

    def test_audit_has_no_invalid_parent_refs_after_delete(self) -> None:
        parent_id = _insert_range(self.conn, structure_layer="WEEKLY")
        child_id = _insert_range(self.conn, structure_layer="DAILY", parent_range_id=parent_id)
        result = self._delete([parent_id])
        self.assertTrue(result["ok"])
        invalid = self.conn.execute(
            """
            SELECT COUNT(*) FROM map_ranges child
            LEFT JOIN map_ranges parent ON parent.id = child.parent_range_id
            WHERE child.parent_range_id IS NOT NULL AND parent.id IS NULL
            """
        ).fetchone()[0]
        self.assertEqual(int(invalid), 0)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM map_ranges WHERE id=?", (child_id,)).fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
