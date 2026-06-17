#!/usr/bin/env python3
"""Read-only inspector for latest RANGE_V2 detector run (no detector logic changes)."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys

import candle_store
from detection_brain_schema import init_detection_brain_schema
from detector.debug_run_summary import inspect_db_run


def _latest_run_id(conn: sqlite3.Connection, *, symbol: str) -> str | None:
    rows = conn.execute(
        """
        SELECT meta_json, created_at_utc_ms
        FROM detector_suggestions
        WHERE symbol = ?
        ORDER BY created_at_utc_ms DESC
        LIMIT 50
        """,
        (symbol.upper(),),
    ).fetchall()
    for row in rows:
        raw = row["meta_json"]
        if not raw:
            continue
        try:
            meta = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError:
            continue
        run_id = meta.get("detection_run_id")
        if run_id:
            return str(run_id)
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect latest detector run debug fields")
    parser.add_argument("--db", default=None, help="SQLite path (default: candle_store.DB_PATH)")
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--detection-run-id", default=None, help="Specific run id (default: latest)")
    args = parser.parse_args(argv)

    if args.db:
        candle_store.DB_PATH = args.db  # type: ignore[assignment]
    candle_store.init_db()

    conn = sqlite3.connect(candle_store.DB_PATH)
    conn.row_factory = sqlite3.Row
    init_detection_brain_schema(conn)

    run_id = args.detection_run_id or _latest_run_id(conn, symbol=args.symbol)
    if not run_id:
        print(json.dumps({"error": "no_detection_run_id_found", "db": str(candle_store.DB_PATH)}, indent=2))
        return 1

    report = inspect_db_run(conn, detection_run_id=run_id, symbol=args.symbol)
    report["db_path"] = str(candle_store.DB_PATH)
    print(json.dumps(report, indent=2, default=str))
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
