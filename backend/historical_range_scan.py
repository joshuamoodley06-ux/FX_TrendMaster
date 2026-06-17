#!/usr/bin/env python3
"""CLI: historical RANGE_CANDIDATE scan over a date period (suggestions only)."""

from __future__ import annotations

import argparse
import os
import sys

import candle_store
from detection_brain_schema import init_detection_brain_schema
from detector.range_mode import RANGE_MODE_DOCTRINE_V2
from detector.range_scan_runner import (
    HistoricalRangeScanConfig,
    HistoricalScanError,
    ConfirmedStructureMutatedError,
    format_audit_sample,
    format_scan_summary,
    parse_scan_date_ms,
    run_historical_range_scan,
    sample_scan_suggestions,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Historical range scan — RANGE_CANDIDATE suggestions only, no promotion",
    )
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--timeframe", default="W1", help="source_timeframe e.g. W1, D1, H1")
    parser.add_argument("--layer", default=None, help="structure_layer e.g. WEEKLY, DAILY, INTRADAY")
    parser.add_argument("--from", dest="date_from", required=True, help="start date YYYY-MM-DD")
    parser.add_argument("--to", dest="date_to", required=True, help="end date YYYY-MM-DD")
    parser.add_argument(
        "--range-mode",
        default=os.environ.get("DETECTOR_RANGE_MODE", RANGE_MODE_DOCTRINE_V2),
        help=f"default: env or {RANGE_MODE_DOCTRINE_V2}",
    )
    parser.add_argument(
        "--range-scale-mode",
        default=os.environ.get("DETECTOR_RANGE_SCALE_MODE", "generic"),
        help="default: env or generic",
    )
    parser.add_argument("--detection-run-id", default=None, help="reuse run id (supersedes prior pending)")
    parser.add_argument("--candidate-kind", default=None, help="filter writes e.g. RANGE_CANDIDATE")
    parser.add_argument("--limit", type=int, default=None, help="max replay steps to scan")
    parser.add_argument("--candle-limit", type=int, default=5000, help="max candles loaded from DB")
    parser.add_argument("--sample", type=int, default=0, help="print N random audit rows after scan")
    parser.add_argument("--dry-run", action="store_true", help="detect only; do not write suggestions")
    parser.add_argument("--db", default=None, help="SQLite path override")
    return parser


def _default_layer(timeframe: str) -> str:
    from detector.break_rules import structure_layer_for_timeframe

    return structure_layer_for_timeframe(timeframe)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.db:
        candle_store.DB_PATH = args.db  # type: ignore[assignment]

    candle_store.init_db()
    layer = str(args.layer or _default_layer(args.timeframe)).upper()

    try:
        date_from_ms = parse_scan_date_ms(args.date_from)
        date_to_ms = parse_scan_date_ms(args.date_to)
    except HistoricalScanError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    config = HistoricalRangeScanConfig(
        symbol=args.symbol,
        source_timeframe=args.timeframe,
        structure_layer=layer,
        date_from_ms=date_from_ms,
        date_to_ms=date_to_ms,
        range_mode=args.range_mode,
        range_scale_mode=args.range_scale_mode,
        detection_run_id=args.detection_run_id,
        candidate_kind_filter=args.candidate_kind,
        candle_limit=args.candle_limit,
        max_steps=args.limit,
        dry_run=args.dry_run,
    )

    try:
        with candle_store.connect() as conn:
            init_detection_brain_schema(conn)
            result = run_historical_range_scan(conn, config)
            print(format_scan_summary(result))
            if args.sample and args.sample > 0 and not args.dry_run:
                sample_kind = args.candidate_kind or "RANGE_CANDIDATE"
                rows = sample_scan_suggestions(
                    conn,
                    detection_run_id=result.detection_run_id,
                    sample_n=args.sample,
                    candidate_kind=sample_kind,
                )
                print()
                print(format_audit_sample(rows))
    except ConfirmedStructureMutatedError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        return 3
    except HistoricalScanError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
