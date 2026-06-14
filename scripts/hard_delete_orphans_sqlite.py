"""
Hard-delete orphan ranges directly from market_memory.db (run on VPS).

Use when the API hard-delete endpoint is not deployed yet.
Keeps MACRO #152 tree; removes unlinked/orphan ranges for the master case.

On VPS (RDP):
  cd C:\Users\Administrator\Desktop\FXTM App\FX_TrendMaster
  python scripts\hard_delete_orphans_sqlite.py --db "C:\Users\Administrator\Desktop\FXTM App\trading_gate\app\market_memory.db" --dry-run
  python scripts\hard_delete_orphans_sqlite.py --db "C:\Users\Administrator\Desktop\FXTM App\trading_gate\app\market_memory.db" --execute
"""
from __future__ import annotations

import argparse
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

MASTER_RAW_CASE_ID = "388d8181-a9b9-4faf-be16-3364ef741455"
KEEP_MACRO_IDS = {152}


def norm_layer(row: sqlite3.Row) -> str:
    keys = row.keys()
    layer = row["structure_layer"] if "structure_layer" in keys and row["structure_layer"] else None
    if not layer and "layer" in keys:
        layer = row["layer"]
    return str(layer or "").upper()


def range_id(row: sqlite3.Row) -> str:
    return str(row["id"])


def load_ranges(conn: sqlite3.Connection, raw_case_id: str) -> list[sqlite3.Row]:
    cur = conn.execute(
        "SELECT * FROM map_ranges WHERE raw_case_id=? ORDER BY id ASC",
        (raw_case_id,),
    )
    return list(cur.fetchall())


def build_orphan_ids(rows: list[sqlite3.Row]) -> list[int]:
    by_id = {range_id(r): r for r in rows}
    macros = [r for r in rows if norm_layer(r) == "MACRO"]
    visited: set[str] = set()

    def walk(r: sqlite3.Row) -> None:
        rid = range_id(r)
        visited.add(rid)
        for child in rows:
            if str(child["parent_range_id"] or "") == rid:
                walk(child)

    for macro in macros:
        walk(macro)

    orphan_ids: list[int] = []
    for r in rows:
        rid = int(range_id(r))
        if range_id(r) not in visited and rid not in KEEP_MACRO_IDS:
            orphan_ids.append(rid)
    return sorted(orphan_ids)


def hard_delete(conn: sqlite3.Connection, range_ids: list[int]) -> dict[str, int]:
    counts = {
        "deleted_ranges": 0,
        "deleted_events": 0,
        "deleted_points": 0,
        "deleted_routes": 0,
        "deleted_snapshots": 0,
        "deleted_objectives": 0,
    }
    now = datetime.now(UTC).isoformat()

    for rid in range_ids:
        cur = conn.execute(
            "DELETE FROM map_events WHERE range_id=? OR active_range_id=? OR parent_range_id=?",
            (rid, rid, rid),
        )
        counts["deleted_events"] += int(cur.rowcount or 0)
        cur = conn.execute("DELETE FROM map_points WHERE range_id=?", (rid,))
        counts["deleted_points"] += int(cur.rowcount or 0)
        cur = conn.execute("DELETE FROM route_memory WHERE range_id=?", (rid,))
        counts["deleted_routes"] += int(cur.rowcount or 0)
        cur = conn.execute("DELETE FROM htf_state_snapshots WHERE range_id=?", (rid,))
        counts["deleted_snapshots"] += int(cur.rowcount or 0)
        cur = conn.execute("DELETE FROM range_objectives WHERE range_id=?", (rid,))
        counts["deleted_objectives"] += int(cur.rowcount or 0)
        cur = conn.execute("DELETE FROM map_ranges WHERE id=?", (rid,))
        counts["deleted_ranges"] += int(cur.rowcount or 0)

    if range_ids:
        placeholders = ",".join(["?"] * len(range_ids))
        conn.execute(
            f"""
            UPDATE map_ranges
            SET parent_range_id=NULL, old_range_id=NULL, new_range_id=NULL, updated_at=?
            WHERE parent_range_id IN ({placeholders})
               OR old_range_id IN ({placeholders})
               OR new_range_id IN ({placeholders})
            """,
            [now] + range_ids + range_ids + range_ids,
        )
    return counts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True, help="Path to market_memory.db on VPS")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.dry_run and not args.execute:
        parser.error("Pass --dry-run or --execute")

    db_path = Path(args.db)
    if not db_path.is_file():
        raise SystemExit(f"Database not found: {db_path}")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = load_ranges(conn, MASTER_RAW_CASE_ID)
    orphan_ids = build_orphan_ids(rows)

    print(f"Master case ranges in DB: {len(rows)}")
    print(f"Orphan range IDs to delete: {len(orphan_ids)}")
    for rid in orphan_ids:
        row = next((r for r in rows if int(r["id"]) == rid), None)
        if row:
            print(f"  #{rid} {norm_layer(row)} {str(row['range_start_time'] or '')[:10]}")

    if args.execute and orphan_ids:
        counts = hard_delete(conn, orphan_ids)
        conn.commit()
        print("Hard delete complete:", counts)

    conn.close()


if __name__ == "__main__":
    main()
