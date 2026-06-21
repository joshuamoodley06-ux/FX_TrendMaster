#!/usr/bin/env python3
"""CLI: random visual audit sampler (local research workstation)."""

from __future__ import annotations

import argparse
import json
import sys

import candle_store
from detection_brain_random_audit import RandomAuditFilters, sample_random_audit_rows
from detection_brain_schema import init_detection_brain_schema
from detector.break_rules import structure_layer_for_timeframe
from detector.range_scan_runner import HistoricalScanError, parse_scan_date_ms


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Random range audit sampler")
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--timeframe", default="W1", help="source_timeframe")
    parser.add_argument("--layer", default=None, help="structure_layer")
    parser.add_argument("--from", dest="date_from", default=None, help="YYYY-MM-DD")
    parser.add_argument("--to", dest="date_to", default=None, help="YYYY-MM-DD")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--source", default="confirmed_ranges", choices=["suggestions", "confirmed_ranges"])
    parser.add_argument("--detection-run-id", default=None)
    parser.add_argument("--json", action="store_true", help="emit JSON result")
    parser.add_argument("--db", default=None, help="SQLite path override")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.db:
        candle_store.DB_PATH = args.db  # type: ignore[assignment]

    candle_store.init_db()
    layer = str(args.layer or structure_layer_for_timeframe(args.timeframe)).upper()

    date_from_ms = None
    date_to_ms = None
    if args.date_from:
        try:
            date_from_ms = parse_scan_date_ms(args.date_from)
        except HistoricalScanError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    if args.date_to:
        try:
            date_to_ms = parse_scan_date_ms(args.date_to)
        except HistoricalScanError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    filters = RandomAuditFilters(
        symbol=args.symbol,
        source_timeframe=args.timeframe,
        structure_layer=layer,
        date_from_ms=date_from_ms,
        date_to_ms=date_to_ms,
        limit=max(1, min(int(args.limit or 5), 100)),
        source=args.source,
        detection_run_id=args.detection_run_id,
    )

    with candle_store.connect() as conn:
        init_detection_brain_schema(conn)
        result = sample_random_audit_rows(conn, filters)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"pool_size={result.get('pool_size', 0)} count={result.get('count', 0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
