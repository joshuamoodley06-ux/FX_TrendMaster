"""CLI entry for Python Detector V1 (suggestions only)."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys

from detection_brain_schema import init_detection_brain_schema
from detector.ohlc_loader import build_context, load_context_from_db
from detector.pipeline import run_detector_v1
from detector.writer import write_suggestions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="FX TrendMaster Python Detector V1")
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--timeframe", default="D1")
    parser.add_argument("--active-index", type=int, default=None)
    parser.add_argument("--range-high", type=float, default=None)
    parser.add_argument("--range-low", type=float, default=None)
    parser.add_argument("--range-scale", default="MAJOR")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--dry-run", action="store_true", help="Detect only; do not write suggestions")
    parser.add_argument("--db", default=None, help="Optional SQLite path override")
    args = parser.parse_args(argv)

    if args.db:
        import candle_store

        candle_store.DB_PATH = args.db  # type: ignore[assignment]

    if args.dry_run:
        ctx = load_context_from_db(
            symbol=args.symbol,
            source_timeframe=args.timeframe,
            active_index=args.active_index,
            limit=args.limit,
            range_high=args.range_high,
            range_low=args.range_low,
            range_scale=args.range_scale,
        )
        result = run_detector_v1(ctx)
        print(
            json.dumps(
                {
                    "ok": True,
                    "dry_run": True,
                    "count": len(result.drafts),
                    "drafts": [d.__dict__ for d in result.drafts],
                },
                indent=2,
            )
        )
        return 0

    import candle_store

    candle_store.init_db()
    ctx = load_context_from_db(
        symbol=args.symbol,
        source_timeframe=args.timeframe,
        active_index=args.active_index,
        limit=args.limit,
        range_high=args.range_high,
        range_low=args.range_low,
        range_scale=args.range_scale,
    )
    result = run_detector_v1(ctx)
    with sqlite3.connect(candle_store.DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        init_detection_brain_schema(conn)
        saved = write_suggestions(conn, result.drafts, ctx)
        conn.commit()
    print(json.dumps({"ok": True, "written": len(saved), "suggestion_ids": [s["suggestion_id"] for s in saved]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
