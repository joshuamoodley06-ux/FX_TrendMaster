"""Command-line interface for Range Library Memory schema management."""

from __future__ import annotations

import argparse
from pathlib import Path

from .config import resolve_db_path
from .importer import import_source
from .inspection import (
    InspectionError,
    format_list_runs,
    format_show_run,
    list_runs,
    show_run,
)
from .schema import init_schema


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="range_library_memory")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Initialize the SQLite schema.")
    init_parser.add_argument("--db-path", type=Path, default=None, help="SQLite database path.")

    import_parser = subparsers.add_parser("import", help="Import raw range memory JSON.")
    import_parser.add_argument("--source", type=Path, required=True, help="Raw JSON source path.")
    import_parser.add_argument("--source-kind", required=True, help="Source format label.")
    import_parser.add_argument("--db-path", type=Path, default=None, help="SQLite database path.")

    list_runs_parser = subparsers.add_parser("list-runs", help="List recent import runs.")
    list_runs_parser.add_argument("--db-path", type=Path, default=None, help="SQLite database path.")
    list_runs_parser.add_argument("--limit", type=int, default=20, help="Maximum number of runs to show.")
    list_runs_parser.add_argument("--json", action="store_true", help="Print deterministic JSON.")

    show_run_parser = subparsers.add_parser("show-run", help="Show one import run summary.")
    show_run_parser.add_argument("--db-path", type=Path, default=None, help="SQLite database path.")
    show_run_parser.add_argument("--import-run-id", type=int, required=True, help="Import run id.")
    show_run_parser.add_argument("--json", action="store_true", help="Print deterministic JSON.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init":
        db_path = resolve_db_path(args.db_path)
        init_schema(db_path)
        print(f"Initialized Range Library Memory database at {db_path}")
        return 0

    if args.command == "import":
        db_path = resolve_db_path(args.db_path)
        summary = import_source(db_path, args.source, args.source_kind)
        print(
            "Imported Range Library Memory source "
            f"run={summary.import_run_id} "
            f"ranges={summary.ranges_inserted}/{summary.ranges_seen} "
            f"events={summary.events_inserted}/{summary.events_seen} "
            f"issues={summary.validation_issue_count} "
            f"duplicates={summary.duplicate_candidate_count}"
        )
        return 0

    if args.command == "list-runs":
        db_path = resolve_db_path(args.db_path)
        try:
            print(format_list_runs(list_runs(db_path, limit=args.limit), as_json=args.json))
        except InspectionError as exc:
            parser.error(str(exc))
        return 0

    if args.command == "show-run":
        db_path = resolve_db_path(args.db_path)
        try:
            print(format_show_run(show_run(db_path, import_run_id=args.import_run_id), as_json=args.json))
        except InspectionError as exc:
            parser.error(str(exc))
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
