#!/usr/bin/env python3
"""CLI: batch promote RANGE_CANDIDATE suggestions to confirmed map_ranges."""

from __future__ import annotations

import argparse
import json
import os
import sys

import candle_store
from detection_brain_batch_promote import (
    BatchPromoteFilters,
    batch_promote_range_candidates,
    batch_promote_result_to_dict,
)
from detection_brain_schema import init_detection_brain_schema
from detector.break_rules import structure_layer_for_timeframe
from detector.range_scan_runner import HistoricalScanError, parse_scan_date_ms


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Batch promote RANGE_CANDIDATE suggestions (dry-run unless --confirm)",
    )
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--timeframe", default="W1", help="source_timeframe")
    parser.add_argument("--layer", default=None, help="structure_layer")
    parser.add_argument("--from", dest="date_from", default=None, help="YYYY-MM-DD")
    parser.add_argument("--to", dest="date_to", default=None, help="YYYY-MM-DD")
    parser.add_argument("--candidate-kind", default="RANGE_CANDIDATE")
    parser.add_argument("--status", default="PENDING")
    parser.add_argument("--detector-version", default=None)
    parser.add_argument("--detection-run-id", default=None)
    parser.add_argument("--confirm", action="store_true", help="actually promote (default: dry-run)")
    parser.add_argument("--json", action="store_true", help="print full JSON result")
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
    try:
        if args.date_from:
            date_from_ms = parse_scan_date_ms(args.date_from)
        if args.date_to:
            date_to_ms = parse_scan_date_ms(args.date_to)
    except HistoricalScanError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    filters = BatchPromoteFilters(
        symbol=args.symbol,
        source_timeframe=args.timeframe,
        structure_layer=layer,
        date_from_ms=date_from_ms,
        date_to_ms=date_to_ms,
        candidate_kind=args.candidate_kind,
        status=args.status,
        detector_version=args.detector_version,
        detection_run_id=args.detection_run_id,
    )

    with candle_store.connect() as conn:
        init_detection_brain_schema(conn)
        result = batch_promote_range_candidates(conn, filters, confirm=bool(args.confirm))

    out = batch_promote_result_to_dict(result)
    if args.json:
        print(json.dumps(out, indent=2, default=str))
    else:
        print(result.message)
        print(
            f"date_range: {out['date_range'].get('date_from') or '—'} → "
            f"{out['date_range'].get('date_to') or '—'}"
        )
        counts = out["counts"]
        print(
            "counts: "
            f"pending={counts['pending_candidates_found']} "
            f"already_promoted={counts['already_promoted']} "
            f"would_promote={counts['would_promote']} "
            f"promoted={counts['promoted']} "
            f"skipped={counts['skipped']} "
            f"duplicate_risks={counts['duplicate_risks']} "
            f"errors={counts['errors']}"
        )
        if not args.confirm:
            print("dry-run only — pass --confirm to commit promotions")

    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
