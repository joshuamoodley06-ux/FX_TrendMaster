"""FX TrendMaster Python Analyst V1.1 — CLI entry.

Usage:

    python analyst_v1.py --input <package.json> --output <workspace/SYMBOL/YEAR>
    python analyst_v1.py --rebuild-combined --symbol XAUUSD [--workspace <root>]
    python analyst_v1.py --query query.json [--workspace <root>] [--query-output <dir>]

Read-only: never touches the network or any database. Output is local
files only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from analyst import __version__
from analyst.pipeline import resolve_workspace_root, run_year
from analyst.query_engine import run_query_file
from analyst.query.schema import QueryValidationError
from analyst.storage.combined import rebuild_combined
from analyst.storage.workspace import DEFAULT_WORKSPACE_ROOT


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="analyst_v1",
        description="FX TrendMaster Python Analyst V1.1 (rule-based structural statistics)",
    )
    parser.add_argument("--input", help="path to analyst_input_v1 package JSON")
    parser.add_argument("--output", help="output directory (workspace/SYMBOL/YEAR)")
    parser.add_argument("--rebuild-combined", action="store_true", help="rebuild combined artifacts only")
    parser.add_argument("--symbol", help="symbol for --rebuild-combined")
    parser.add_argument(
        "--workspace",
        help=f"workspace root (default: {DEFAULT_WORKSPACE_ROOT})",
    )
    parser.add_argument("--query", help="path to mediator_query_v1 JSON")
    parser.add_argument(
        "--query-output",
        help="optional output dir for query_result.json (default: workspace/SYMBOL/queries/<query_id>/)",
    )
    parser.add_argument("--sql", help="path to SQL inspector JSON (sql, symbol, year_labels)")
    args = parser.parse_args(argv)

    print(f"[analyst] Python Analyst {__version__}")

    if args.sql:
        from analyst.sql_inspector import SqlValidationError, run_sql_inspector_file

        sql_path = Path(args.sql)
        if not sql_path.is_file():
            print(f"[analyst] ERROR: sql file not found: {sql_path}", file=sys.stderr)
            return 2
        try:
            result = run_sql_inspector_file(sql_path, workspace_root=args.workspace)
        except SqlValidationError as exc:
            print(f"[analyst] ERROR: {exc}", file=sys.stderr)
            return 2
        except (OSError, ValueError, TypeError) as exc:
            print(f"[analyst] ERROR: {exc}", file=sys.stderr)
            return 2
        print(f"[analyst] sql status={result.get('status')} rows={result.get('row_count')}")
        if result.get("error"):
            print(f"[analyst] error {result['error']}", file=sys.stderr)
        for warning in result.get("warnings", []):
            print(f"[analyst] warning {warning}")
        print(json.dumps(result))
        return 0 if result.get("status") == "OK" else 2

    if args.query:
        query_path = Path(args.query)
        if not query_path.is_file():
            print(f"[analyst] ERROR: query file not found: {query_path}", file=sys.stderr)
            return 2
        try:
            result = run_query_file(
                query_path,
                workspace_root=args.workspace,
                query_output_dir=args.query_output,
            )
        except QueryValidationError as exc:
            print(f"[analyst] ERROR: {exc}", file=sys.stderr)
            return 2
        except (OSError, ValueError, TypeError) as exc:
            print(f"[analyst] ERROR: {exc}", file=sys.stderr)
            return 2
        print(
            f"[analyst] query {result.get('query_id')}: status={result.get('status')} "
            f"sample_size={result.get('sample_size')}"
        )
        for warning in result.get("warnings", []):
            print(f"[analyst] warning {warning}")
        print(f"[analyst] query result written to {result.get('result_path')}")
        print(json.dumps(result))
        return 0 if result.get("status") in ("OK", "NO_DATA", "PARTIAL_DATA") else 2

    if args.rebuild_combined:
        if not args.symbol:
            parser.error("--rebuild-combined requires --symbol")
        root = Path(args.workspace) if args.workspace else DEFAULT_WORKSPACE_ROOT
        result = rebuild_combined(root, args.symbol)
        if result["written"]:
            print(f"[analyst] combined rebuilt for {args.symbol}: {result['years']} year(s) -> {result['combined_dir']}")
        else:
            print(f"[analyst] no yearly_stats.json found under {root / args.symbol}; nothing rebuilt")
        return 0

    if not args.input or not args.output:
        parser.error("--input and --output are required (or use --rebuild-combined)")

    input_path = Path(args.input)
    if not input_path.is_file():
        print(f"[analyst] ERROR: input package not found: {input_path}", file=sys.stderr)
        return 2

    print(f"[analyst] loading {input_path}")
    try:
        result = run_year(input_path, args.output, workspace_root=args.workspace)
    except ValueError as exc:
        print(f"[analyst] ERROR: {exc}", file=sys.stderr)
        return 2

    package = result["package"]
    counts = result["yearly_stats"]["counts"]
    print(
        f"[analyst] {package.label}: cases={counts['cases']} ranges={counts['ranges']} "
        f"events={counts['events']} candles={package.candle_count_total} warnings={counts['warnings']}"
    )
    for warning in result["warnings"]:
        print(f"[analyst] warning {warning.code}: {warning.message}")
    print(f"[analyst] outputs written to {Path(args.output).resolve()}")

    combined = result["combined"]
    if combined and combined["written"]:
        print(f"[analyst] combined rebuilt for {package.symbol}: {combined['years']} year(s)")
    elif combined is None:
        inferred = resolve_workspace_root(args.output, package.symbol, args.workspace)
        if inferred is None:
            print("[analyst] combined rebuild skipped (output dir is not workspace/SYMBOL/YEAR; pass --workspace)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
