"""Command-line interface for Range Library Memory schema management."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .bulk_import import bulk_import_source_dir, format_bulk_import_summary
from .config import resolve_db_path
from .daily_range_timeline import (
    DailyRangeTimelineError,
    build_daily_range_timelines,
    format_summary as format_daily_range_timeline_summary,
    summarize_daily_range_timelines,
)
from .daily_trend_relationship import (
    DailyTrendRelationshipError,
    build_daily_trend_relationships,
    format_summary as format_daily_trend_summary,
    summarize_daily_trend_relationships,
)
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
from .weekly_direction_context import (
    WeeklyDirectionContextError,
    build_weekly_direction_contexts,
    format_summary as format_weekly_direction_summary,
    summarize_weekly_direction_contexts,
)
from .weekly_chronology_bos import (
    WeeklyChronologyBosError,
    build_weekly_chronology_bos,
    concise_summary as concise_weekly_script1_summary,
    review_weekly_script1_run,
)
from .xauusd_first_query_doctrine import (
    DoctrineError,
    build_first_query_doctrine_report,
    load_json as load_doctrine_json,
    load_master_map_output_readonly,
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

    daily_parser = subparsers.add_parser("build-daily-range-timelines", help="Build factual Daily range timelines.")
    daily_parser.add_argument("--db-path", type=Path, default=None)
    daily_parser.add_argument("--source-db", type=Path, required=True)
    daily_parser.add_argument("--case-ref")
    daily_parser.add_argument("--symbol")
    daily_parser.add_argument("--daily-source-id")
    daily_parser.add_argument("--weekly-source-id")
    daily_parser.add_argument("--as-of")
    daily_parser.add_argument("--json", action="store_true")

    daily_summary_parser = subparsers.add_parser("daily-range-timeline-summary", help="Summarize Daily range timelines.")
    daily_summary_parser.add_argument("--db-path", type=Path, default=None)
    daily_summary_parser.add_argument("--case-ref")
    daily_summary_parser.add_argument("--symbol")
    daily_summary_parser.add_argument("--daily-source-id")
    daily_summary_parser.add_argument("--weekly-source-id")
    daily_summary_parser.add_argument("--daily-state")
    daily_summary_parser.add_argument("--parent-link-status")
    daily_summary_parser.add_argument("--weekly-phase")
    daily_summary_parser.add_argument("--observation-status")
    daily_summary_parser.add_argument("--json", action="store_true")

    weekly_direction_parser = subparsers.add_parser(
        "build-weekly-direction-contexts",
        help="Build historical Weekly direction context from the break that created each Weekly.",
    )
    weekly_direction_parser.add_argument("--db-path", type=Path, default=None)
    weekly_direction_parser.add_argument("--case-ref")
    weekly_direction_parser.add_argument("--symbol")
    weekly_direction_parser.add_argument("--weekly-source-id")
    weekly_direction_parser.add_argument("--as-of")
    weekly_direction_parser.add_argument("--json", action="store_true")

    weekly_direction_summary_parser = subparsers.add_parser(
        "weekly-direction-context-summary",
        help="Summarize Weekly direction contexts.",
    )
    weekly_direction_summary_parser.add_argument("--db-path", type=Path, default=None)
    weekly_direction_summary_parser.add_argument("--case-ref")
    weekly_direction_summary_parser.add_argument("--symbol")
    weekly_direction_summary_parser.add_argument("--weekly-source-id")
    weekly_direction_summary_parser.add_argument("--direction-state")
    weekly_direction_summary_parser.add_argument("--observation-status")
    weekly_direction_summary_parser.add_argument("--json", action="store_true")

    daily_trend_parser = subparsers.add_parser(
        "build-daily-trend-relationships",
        help="Classify Daily BOS direction against historical Weekly direction context.",
    )
    daily_trend_parser.add_argument("--db-path", type=Path, default=None)
    daily_trend_parser.add_argument("--case-ref")
    daily_trend_parser.add_argument("--symbol")
    daily_trend_parser.add_argument("--daily-source-id")
    daily_trend_parser.add_argument("--weekly-source-id")
    daily_trend_parser.add_argument("--as-of")
    daily_trend_parser.add_argument("--json", action="store_true")

    daily_trend_summary_parser = subparsers.add_parser(
        "daily-trend-relationship-summary",
        help="Summarize Daily ProTrend, CounterTrend, transition, and pending relationships.",
    )
    daily_trend_summary_parser.add_argument("--db-path", type=Path, default=None)
    daily_trend_summary_parser.add_argument("--case-ref")
    daily_trend_summary_parser.add_argument("--symbol")
    daily_trend_summary_parser.add_argument("--daily-source-id")
    daily_trend_summary_parser.add_argument("--weekly-source-id")
    daily_trend_summary_parser.add_argument("--trend-relationship")
    daily_trend_summary_parser.add_argument("--observation-status")
    daily_trend_summary_parser.add_argument("--json", action="store_true")

    weekly_script1_parser = subparsers.add_parser(
        "build-weekly-script1",
        help="Build trusted Weekly chronology and first strict BOS derived rows.",
    )
    weekly_script1_parser.add_argument(
        "--db-path", type=Path, required=True, help="Explicit Range Library SQLite path."
    )
    weekly_script1_parser.add_argument(
        "--source-db", type=Path, required=True, help="Explicit read-only candle SQLite path."
    )
    weekly_script1_parser.add_argument("--symbol", default="XAUUSD", choices=("XAUUSD",))
    weekly_script1_parser.add_argument("--case-ref", required=True)
    weekly_script1_parser.add_argument("--year", type=int, default=None)
    weekly_script1_parser.add_argument("--json", action="store_true")

    weekly_script1_review_parser = subparsers.add_parser(
        "review-weekly-script1", help="Persist one trader review on a disposable Script 1 result."
    )
    weekly_script1_review_parser.add_argument("--db-path", type=Path, required=True)
    weekly_script1_review_parser.add_argument("--run-id", required=True)
    weekly_script1_review_parser.add_argument("--case-ref", required=True)
    weekly_script1_review_parser.add_argument("--symbol", default="XAUUSD", choices=("XAUUSD",))
    weekly_script1_review_parser.add_argument("--canonical-range-id", required=True)
    weekly_script1_review_parser.add_argument("--decision", required=True, choices=("APPROVED", "REJECTED"))
    weekly_script1_review_parser.add_argument("--json", action="store_true")

    first_query_parser = subparsers.add_parser(
        "first-query-doctrine",
        help="Build a disposable XAUUSD first-query doctrine report.",
    )
    first_query_source = first_query_parser.add_mutually_exclusive_group(required=True)
    first_query_source.add_argument("--master-map")
    first_query_source.add_argument("--range-library-db")
    first_query_parser.add_argument("--output", required=True)
    first_query_parser.add_argument("--compact", action="store_true")

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

    if args.command == "build-daily-range-timelines":
        db_path = resolve_db_path(args.db_path)
        try:
            summary = build_daily_range_timelines(
                db_path,
                source_db=args.source_db,
                case_ref=args.case_ref,
                symbol=args.symbol,
                daily_source_id=args.daily_source_id,
                weekly_source_id=args.weekly_source_id,
                as_of=args.as_of,
            )
        except (InspectionError, DailyRangeTimelineError, ValueError) as exc:
            parser.error(str(exc))
        print(format_daily_range_timeline_summary(summary, as_json=args.json))
        return 0

    if args.command == "daily-range-timeline-summary":
        db_path = resolve_db_path(args.db_path)
        try:
            summary = summarize_daily_range_timelines(
                db_path,
                case_ref=args.case_ref,
                symbol=args.symbol,
                daily_source_id=args.daily_source_id,
                weekly_source_id=args.weekly_source_id,
                daily_state=args.daily_state,
                parent_link_status=args.parent_link_status,
                weekly_phase=args.weekly_phase,
                observation_status=args.observation_status,
            )
        except (InspectionError, DailyRangeTimelineError, ValueError) as exc:
            parser.error(str(exc))
        print(format_daily_range_timeline_summary(summary, as_json=args.json))
        return 0

    if args.command == "build-weekly-direction-contexts":
        db_path = resolve_db_path(args.db_path)
        try:
            summary = build_weekly_direction_contexts(
                db_path,
                case_ref=args.case_ref,
                symbol=args.symbol,
                weekly_source_id=args.weekly_source_id,
                as_of=args.as_of,
            )
        except (InspectionError, WeeklyDirectionContextError, ValueError) as exc:
            parser.error(str(exc))
        print(format_weekly_direction_summary(summary, as_json=args.json))
        return 0

    if args.command == "weekly-direction-context-summary":
        db_path = resolve_db_path(args.db_path)
        try:
            summary = summarize_weekly_direction_contexts(
                db_path,
                case_ref=args.case_ref,
                symbol=args.symbol,
                weekly_source_id=args.weekly_source_id,
                direction_state=args.direction_state,
                observation_status=args.observation_status,
            )
        except (InspectionError, WeeklyDirectionContextError, ValueError) as exc:
            parser.error(str(exc))
        print(format_weekly_direction_summary(summary, as_json=args.json))
        return 0

    if args.command == "build-daily-trend-relationships":
        db_path = resolve_db_path(args.db_path)
        try:
            summary = build_daily_trend_relationships(
                db_path,
                case_ref=args.case_ref,
                symbol=args.symbol,
                daily_source_id=args.daily_source_id,
                weekly_source_id=args.weekly_source_id,
                as_of=args.as_of,
            )
        except (InspectionError, DailyTrendRelationshipError, ValueError) as exc:
            parser.error(str(exc))
        print(format_daily_trend_summary(summary, as_json=args.json))
        return 0

    if args.command == "daily-trend-relationship-summary":
        db_path = resolve_db_path(args.db_path)
        try:
            summary = summarize_daily_trend_relationships(
                db_path,
                case_ref=args.case_ref,
                symbol=args.symbol,
                daily_source_id=args.daily_source_id,
                weekly_source_id=args.weekly_source_id,
                trend_relationship=args.trend_relationship,
                observation_status=args.observation_status,
            )
        except (InspectionError, DailyTrendRelationshipError, ValueError) as exc:
            parser.error(str(exc))
        print(format_daily_trend_summary(summary, as_json=args.json))
        return 0

    if args.command == "build-weekly-script1":
        try:
            summary = build_weekly_chronology_bos(
                args.db_path,
                source_db=args.source_db,
                case_ref=args.case_ref,
                symbol=args.symbol,
                year=args.year,
            )
        except (InspectionError, WeeklyChronologyBosError, ValueError) as exc:
            parser.error(str(exc))
        concise = concise_weekly_script1_summary(summary)
        if args.json:
            print(json.dumps(concise, sort_keys=True, separators=(",", ":")))
        else:
            for key, value in concise.items():
                print(f"{key}: {value}")
        return 0

    if args.command == "review-weekly-script1":
        try:
            result = review_weekly_script1_run(
                args.db_path,
                run_id=args.run_id,
                case_ref=args.case_ref,
                symbol=args.symbol,
                canonical_range_id=args.canonical_range_id,
                decision=args.decision,
            )
        except (InspectionError, WeeklyChronologyBosError, ValueError) as exc:
            parser.error(str(exc))
        print(json.dumps(result, sort_keys=True, separators=(",", ":")) if args.json else result)
        return 0

    if args.command == "first-query-doctrine":
        try:
            master_map = (
                load_doctrine_json(args.master_map)
                if args.master_map
                else load_master_map_output_readonly(args.range_library_db, symbol="XAUUSD")
            )
            report = build_first_query_doctrine_report(master_map)
        except DoctrineError as exc:
            parser.error(str(exc))
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, indent=None if args.compact else 2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps({
            "output": str(output),
            "structural_content_hash": report["summary"]["structural_content_hash"],
            "frozen_candidate_count": report["summary"]["frozen_candidate_count"],
            "enriched_candidate_count": report["summary"]["enriched_candidate_count"],
            "query_ready_count": report["summary"]["query_ready_count"],
            "needs_review_count": report["summary"]["needs_review_count"],
            "excluded_count": report["summary"]["excluded_count"],
            "determinism_hash": report["determinism_hash"],
        }, sort_keys=True))
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
