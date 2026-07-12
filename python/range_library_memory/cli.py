"""Command-line interface for Range Library Memory schema management."""

from __future__ import annotations

import argparse
from pathlib import Path

from .bulk_import import bulk_import_source_dir, format_bulk_import_summary
from .config import resolve_db_path
from .duplicate_summary import format_duplicate_summary, summarize_duplicates
from .event_ohlc_evidence import (
    EventOhlcEvidenceError,
    build_event_ohlc_evidence,
    format_build_summary as format_event_ohlc_build_summary,
    format_event_ohlc_summary,
    summarize_event_ohlc,
)
from .importer import import_source
from .inspection import (
    InspectionError,
    format_list_runs,
    format_show_run,
    list_runs,
    show_run,
)
from .parent_child import (
    build_parent_child,
    format_build_summary,
    format_parent_child_summary,
    summarize_parent_child,
)
from .review import (
    ALLOWED_DUPLICATE_STATUSES,
    format_duplicates,
    format_issues,
    list_duplicates,
    list_issues,
    resolve_issue,
    review_duplicate,
)
from .schema import init_schema
from .weekly_family_coverage import (
    WeeklyFamilyCoverageError,
    analyze_weekly_family_coverage,
    format_weekly_family_coverage,
)
from .weekly_break_reclaim import (
    WeeklyBreakReclaimError,
    build_weekly_break_reclaim,
    format_summary as format_weekly_break_reclaim_summary,
    summarize_weekly_break_reclaim,
)
from .weekly_phase_sequence import (
    WeeklyPhaseSequenceError,
    build_weekly_phase_sequences,
    format_summary as format_weekly_phase_summary,
    summarize_weekly_phase_sequences,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="range_library_memory")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Initialize the SQLite schema.")
    init_parser.add_argument("--db-path", type=Path, default=None, help="SQLite database path.")

    import_parser = subparsers.add_parser("import", help="Import raw range memory JSON.")
    import_parser.add_argument("--source", type=Path, required=True, help="Raw JSON source path.")
    import_parser.add_argument("--source-kind", required=True, help="Source format label.")
    import_parser.add_argument("--db-path", type=Path, default=None, help="SQLite database path.")

    bulk_import_parser = subparsers.add_parser("bulk-import", help="Import all JSON files from a folder.")
    bulk_import_parser.add_argument("--source-dir", type=Path, required=True, help="Folder containing JSON exports.")
    bulk_import_parser.add_argument("--source-kind", required=True, help="Source format label.")
    bulk_import_parser.add_argument("--db-path", type=Path, default=None, help="SQLite database path.")
    bulk_import_parser.add_argument("--json", action="store_true", help="Print deterministic JSON.")

    list_runs_parser = subparsers.add_parser("list-runs", help="List recent import runs.")
    list_runs_parser.add_argument("--db-path", type=Path, default=None, help="SQLite database path.")
    list_runs_parser.add_argument("--limit", type=int, default=20, help="Maximum number of runs to show.")
    list_runs_parser.add_argument("--json", action="store_true", help="Print deterministic JSON.")

    show_run_parser = subparsers.add_parser("show-run", help="Show one import run summary.")
    show_run_parser.add_argument("--db-path", type=Path, default=None, help="SQLite database path.")
    show_run_parser.add_argument("--import-run-id", type=int, required=True, help="Import run id.")
    show_run_parser.add_argument("--json", action="store_true", help="Print deterministic JSON.")

    list_issues_parser = subparsers.add_parser("list-issues", help="List validation issues.")
    list_issues_parser.add_argument("--db-path", type=Path, default=None, help="SQLite database path.")
    list_issues_parser.add_argument("--status", choices=("open", "resolved"), default="open")
    list_issues_parser.add_argument("--limit", type=int, default=20, help="Maximum number of issues to show.")
    list_issues_parser.add_argument("--json", action="store_true", help="Print deterministic JSON.")

    resolve_issue_parser = subparsers.add_parser("resolve-issue", help="Resolve a validation issue.")
    resolve_issue_parser.add_argument("--db-path", type=Path, default=None, help="SQLite database path.")
    resolve_issue_parser.add_argument("--issue-id", type=int, required=True, help="Validation issue id.")
    resolve_issue_parser.add_argument("--notes", required=True, help="Manual resolution notes.")

    list_duplicates_parser = subparsers.add_parser("list-duplicates", help="List duplicate candidates.")
    list_duplicates_parser.add_argument("--db-path", type=Path, default=None, help="SQLite database path.")
    list_duplicates_parser.add_argument("--status", default="open", choices=ALLOWED_DUPLICATE_STATUSES)
    list_duplicates_parser.add_argument("--limit", type=int, default=20, help="Maximum number of candidates to show.")
    list_duplicates_parser.add_argument("--json", action="store_true", help="Print deterministic JSON.")

    review_duplicate_parser = subparsers.add_parser("review-duplicate", help="Review a duplicate candidate.")
    review_duplicate_parser.add_argument("--db-path", type=Path, default=None, help="SQLite database path.")
    review_duplicate_parser.add_argument("--candidate-id", type=int, required=True, help="Duplicate candidate id.")
    review_duplicate_parser.add_argument("--status", required=True, choices=ALLOWED_DUPLICATE_STATUSES)
    review_duplicate_parser.add_argument("--notes", required=True, help="Manual review notes.")

    duplicate_summary_parser = subparsers.add_parser("duplicate-summary", help="Summarize duplicate candidates.")
    duplicate_summary_parser.add_argument("--db-path", type=Path, default=None, help="SQLite database path.")
    duplicate_summary_parser.add_argument("--case-ref", default=None, help="Filter by case_ref in linked raw payloads.")
    duplicate_summary_parser.add_argument("--rule-code", default=None, help="Filter by duplicate rule_code.")
    duplicate_summary_parser.add_argument("--candidate-type", default=None, help="Filter by candidate_type.")
    duplicate_summary_parser.add_argument("--confidence", default=None, help="Filter by confidence.")
    duplicate_summary_parser.add_argument("--status", default=None, help="Filter by review status.")
    duplicate_summary_parser.add_argument("--json", action="store_true", help="Print deterministic JSON.")

    build_parent_child_parser = subparsers.add_parser("build-parent-child", help="Build derived parent-child relationships.")
    build_parent_child_parser.add_argument("--db-path", type=Path, default=None, help="SQLite database path.")
    build_parent_child_parser.add_argument("--parent-layer", required=True, help="Parent layer. Only WEEKLY is supported.")
    build_parent_child_parser.add_argument("--child-layer", required=True, help="Child layer. Only DAILY is supported.")
    build_parent_child_parser.add_argument("--case-ref", default=None, help="Filter by case_ref.")

    parent_child_summary_parser = subparsers.add_parser("parent-child-summary", help="Summarize parent-child relationships.")
    parent_child_summary_parser.add_argument("--db-path", type=Path, default=None, help="SQLite database path.")
    parent_child_summary_parser.add_argument("--case-ref", default=None, help="Filter by case_ref.")
    parent_child_summary_parser.add_argument("--json", action="store_true", help="Print deterministic JSON.")

    weekly_family_parser = subparsers.add_parser(
        "weekly-family-coverage",
        help="Measure D1 candle coverage for a Weekly range's linked Daily family.",
    )
    weekly_family_parser.add_argument("--db-path", type=Path, default=None, help="SQLite database path.")
    weekly_family_parser.add_argument("--source-db", type=Path, required=True, help="Original market_memory.db path.")
    weekly_family_parser.add_argument("--weekly-source-id", required=True, help="Original map_ranges id for the Weekly.")
    weekly_family_parser.add_argument("--as-of", default=None, help="Required cutoff for active Weekly ranges.")
    weekly_family_parser.add_argument("--json", action="store_true", help="Print deterministic JSON.")

    build_event_parser = subparsers.add_parser("build-event-ohlc-evidence", help="Build mapped BOS vs OHLC evidence.")
    build_event_parser.add_argument("--db-path", type=Path, default=None, help="SQLite database path.")
    build_event_parser.add_argument("--source-db", type=Path, required=True, help="Original market_memory.db path.")
    build_event_parser.add_argument("--case-ref", default=None)
    build_event_parser.add_argument("--symbol", default=None)
    build_event_parser.add_argument("--layer", default=None)
    build_event_parser.add_argument("--range-source-id", default=None)
    build_event_parser.add_argument("--event-source-id", default=None)
    build_event_parser.add_argument("--as-of", default=None)
    build_event_parser.add_argument("--json", action="store_true", help="Print deterministic JSON.")

    event_summary_parser = subparsers.add_parser("event-ohlc-summary", help="Summarize mapped BOS vs OHLC evidence.")
    event_summary_parser.add_argument("--db-path", type=Path, default=None, help="SQLite database path.")
    event_summary_parser.add_argument("--case-ref", default=None)
    event_summary_parser.add_argument("--symbol", default=None)
    event_summary_parser.add_argument("--layer", default=None)
    event_summary_parser.add_argument("--range-source-id", default=None)
    event_summary_parser.add_argument("--evidence-status", default=None)
    event_summary_parser.add_argument("--resolution-status", default=None)
    event_summary_parser.add_argument("--json", action="store_true", help="Print deterministic JSON.")

    break_reclaim_parser = subparsers.add_parser("build-weekly-break-reclaim", help="Build Weekly break-reclaim lifecycles.")
    break_reclaim_parser.add_argument("--db-path", type=Path, default=None)
    break_reclaim_parser.add_argument("--source-db", type=Path, required=True)
    break_reclaim_parser.add_argument("--case-ref", default=None)
    break_reclaim_parser.add_argument("--symbol", default=None)
    break_reclaim_parser.add_argument("--weekly-source-id", default=None)
    break_reclaim_parser.add_argument("--as-of", default=None)
    break_reclaim_parser.add_argument("--json", action="store_true")

    break_reclaim_summary_parser = subparsers.add_parser("weekly-break-reclaim-summary", help="Summarize Weekly break-reclaim lifecycles.")
    break_reclaim_summary_parser.add_argument("--db-path", type=Path, default=None)
    break_reclaim_summary_parser.add_argument("--case-ref", default=None)
    break_reclaim_summary_parser.add_argument("--symbol", default=None)
    break_reclaim_summary_parser.add_argument("--weekly-source-id", default=None)
    break_reclaim_summary_parser.add_argument("--state", default=None)
    break_reclaim_summary_parser.add_argument("--observation-status", default=None)
    break_reclaim_summary_parser.add_argument("--json", action="store_true")

    phase_parser = subparsers.add_parser("build-weekly-phase-sequences", help="Build factual dated Weekly phase sequences.")
    phase_parser.add_argument("--db-path", required=True)
    phase_parser.add_argument("--source-db", required=True)
    phase_parser.add_argument("--case-ref")
    phase_parser.add_argument("--symbol")
    phase_parser.add_argument("--weekly-source-id")
    phase_parser.add_argument("--as-of")
    phase_parser.add_argument("--json", action="store_true")

    phase_summary_parser = subparsers.add_parser("weekly-phase-sequence-summary", help="Summarize Weekly phase sequences.")
    phase_summary_parser.add_argument("--db-path", required=True)
    phase_summary_parser.add_argument("--case-ref")
    phase_summary_parser.add_argument("--symbol")
    phase_summary_parser.add_argument("--weekly-source-id")
    phase_summary_parser.add_argument("--state")
    phase_summary_parser.add_argument("--observation-status")
    phase_summary_parser.add_argument("--json", action="store_true")

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

    if args.command == "bulk-import":
        db_path = resolve_db_path(args.db_path)
        try:
            summary = bulk_import_source_dir(db_path, args.source_dir, args.source_kind)
        except (FileNotFoundError, NotADirectoryError) as exc:
            parser.error(str(exc))
        print(format_bulk_import_summary(summary, as_json=args.json))
        return 0

    if args.command == "list-runs":
        db_path = resolve_db_path(args.db_path)
        try:
            print(format_list_runs(list_runs(db_path, limit=args.limit), as_json=args.json))
        except InspectionError as exc:
            parser.error(str(exc))
        return 0

    if args.command == "list-issues":
        db_path = resolve_db_path(args.db_path)
        try:
            print(format_issues(list_issues(db_path, status=args.status, limit=args.limit), as_json=args.json))
        except InspectionError as exc:
            parser.error(str(exc))
        return 0

    if args.command == "resolve-issue":
        db_path = resolve_db_path(args.db_path)
        try:
            resolve_issue(db_path, issue_id=args.issue_id, notes=args.notes)
        except InspectionError as exc:
            parser.error(str(exc))
        print(f"Resolved validation issue {args.issue_id}")
        return 0

    if args.command == "list-duplicates":
        db_path = resolve_db_path(args.db_path)
        try:
            print(format_duplicates(list_duplicates(db_path, status=args.status, limit=args.limit), as_json=args.json))
        except InspectionError as exc:
            parser.error(str(exc))
        return 0

    if args.command == "review-duplicate":
        db_path = resolve_db_path(args.db_path)
        try:
            review_duplicate(db_path, candidate_id=args.candidate_id, status=args.status, notes=args.notes)
        except InspectionError as exc:
            parser.error(str(exc))
        print(f"Reviewed duplicate candidate {args.candidate_id}")
        return 0

    if args.command == "duplicate-summary":
        db_path = resolve_db_path(args.db_path)
        try:
            summary = summarize_duplicates(
                db_path,
                case_ref=args.case_ref,
                rule_code=args.rule_code,
                candidate_type=args.candidate_type,
                confidence=args.confidence,
                status=args.status,
            )
        except InspectionError as exc:
            parser.error(str(exc))
        print(format_duplicate_summary(summary, as_json=args.json))
        return 0

    if args.command == "build-parent-child":
        db_path = resolve_db_path(args.db_path)
        try:
            summary = build_parent_child(
                db_path,
                parent_layer=args.parent_layer,
                child_layer=args.child_layer,
                case_ref=args.case_ref,
            )
        except (InspectionError, ValueError) as exc:
            parser.error(str(exc))
        print(format_build_summary(summary))
        return 0

    if args.command == "parent-child-summary":
        db_path = resolve_db_path(args.db_path)
        try:
            summary = summarize_parent_child(db_path, case_ref=args.case_ref)
        except InspectionError as exc:
            parser.error(str(exc))
        print(format_parent_child_summary(summary, as_json=args.json))
        return 0

    if args.command == "weekly-family-coverage":
        db_path = resolve_db_path(args.db_path)
        try:
            report = analyze_weekly_family_coverage(
                db_path,
                source_db=args.source_db,
                weekly_source_id=args.weekly_source_id,
                as_of=args.as_of,
            )
        except (InspectionError, WeeklyFamilyCoverageError, ValueError) as exc:
            parser.error(str(exc))
        print(format_weekly_family_coverage(report, as_json=args.json))
        return 0

    if args.command == "build-event-ohlc-evidence":
        db_path = resolve_db_path(args.db_path)
        try:
            summary = build_event_ohlc_evidence(
                db_path,
                source_db=args.source_db,
                case_ref=args.case_ref,
                symbol=args.symbol,
                layer=args.layer,
                range_source_id=args.range_source_id,
                event_source_id=args.event_source_id,
                as_of=args.as_of,
            )
        except (InspectionError, EventOhlcEvidenceError, ValueError) as exc:
            parser.error(str(exc))
        print(format_event_ohlc_build_summary(summary, as_json=args.json))
        return 0

    if args.command == "event-ohlc-summary":
        db_path = resolve_db_path(args.db_path)
        try:
            summary = summarize_event_ohlc(
                db_path,
                case_ref=args.case_ref,
                symbol=args.symbol,
                layer=args.layer,
                range_source_id=args.range_source_id,
                evidence_status=args.evidence_status,
                resolution_status=args.resolution_status,
            )
        except InspectionError as exc:
            parser.error(str(exc))
        print(format_event_ohlc_summary(summary, as_json=args.json))
        return 0

    if args.command == "build-weekly-break-reclaim":
        db_path = resolve_db_path(args.db_path)
        try:
            summary = build_weekly_break_reclaim(
                db_path, source_db=args.source_db, case_ref=args.case_ref, symbol=args.symbol,
                weekly_source_id=args.weekly_source_id, as_of=args.as_of,
            )
        except (InspectionError, WeeklyBreakReclaimError, ValueError) as exc:
            parser.error(str(exc))
        print(format_weekly_break_reclaim_summary(summary, as_json=args.json))
        return 0

    if args.command == "weekly-break-reclaim-summary":
        db_path = resolve_db_path(args.db_path)
        try:
            summary = summarize_weekly_break_reclaim(
                db_path, case_ref=args.case_ref, symbol=args.symbol,
                weekly_source_id=args.weekly_source_id, state=args.state,
                observation_status=args.observation_status,
            )
        except InspectionError as exc:
            parser.error(str(exc))
        print(format_weekly_break_reclaim_summary(summary, as_json=args.json))
        return 0

    if args.command == "build-weekly-phase-sequences":
        try:
            summary = build_weekly_phase_sequences(args.db_path, source_db=args.source_db, case_ref=args.case_ref,
                symbol=args.symbol, weekly_source_id=args.weekly_source_id, as_of=args.as_of)
        except (InspectionError, WeeklyPhaseSequenceError, ValueError) as exc:
            parser.error(str(exc))
        print(format_weekly_phase_summary(summary, as_json=args.json))
        return 0

    if args.command == "weekly-phase-sequence-summary":
        try:
            summary = summarize_weekly_phase_sequences(args.db_path, case_ref=args.case_ref, symbol=args.symbol,
                weekly_source_id=args.weekly_source_id, state=args.state, observation_status=args.observation_status)
        except (InspectionError, WeeklyPhaseSequenceError, ValueError) as exc:
            parser.error(str(exc))
        print(format_weekly_phase_summary(summary, as_json=args.json))
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
