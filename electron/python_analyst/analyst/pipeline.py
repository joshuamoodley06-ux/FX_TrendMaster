"""Pipeline: load -> derive -> rule models -> audit -> write year outputs -> rebuild combined.

Rule models, in dependency order:
- independent: zones, range duration/size, parent-child, BOS direction
- BOS chain: reclaim -> abandon -> outcome classifier -> retracement
  (uses outcomes) -> rotation -> impulse/retest sequence (uses reclaim,
  retracement and outcome results)
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from analyst import ANALYST_STATS_SCHEMA, __version__
from analyst.audit.audit_warnings import AuditWarning
from analyst.audit.hierarchy_check import check_hierarchy
from analyst.audit.ledger_hash import verify_raw_ledgers
from analyst.io.input_loader import load_input_package
from analyst.models.bos_abandon import BOS_ABANDON_REPORT_FILE, build_bos_abandon_report
from analyst.models.bos_direction import BOS_DIRECTION_REPORT_FILE, build_bos_direction_report
from analyst.models.bos_reclaim import BOS_RECLAIM_REPORT_FILE, build_bos_reclaim_report
from analyst.models.derived_fields import compute_derived_fields
from analyst.models.outcome import build_outcome_summary
from analyst.models.parent_child import PARENT_CHILD_REPORT_FILE, build_parent_child_report
from analyst.models.range_metrics import RANGE_METRICS_REPORT_FILE, build_range_metrics_report
from analyst.models.retracement import RETRACEMENT_REPORT_FILE, build_retracement_report
from analyst.models.rotation import ROTATION_REPORT_FILE, build_rotation_report
from analyst.models.sequence import SEQUENCE_REPORT_FILE, build_sequence_report
from analyst.models.zones import ZONE_REPORT_FILE, build_zone_report
from analyst.reports.markdown_writer import build_year_report
from analyst.storage.combined import rebuild_combined
from analyst.storage.workspace import (
    normalized_events_frame,
    normalized_ranges_frame,
    write_year_outputs,
)


def run_year(
    input_path: str | Path,
    output_dir: str | Path,
    workspace_root: str | Path | None = None,
) -> dict[str, Any]:
    package, warnings = load_input_package(input_path)

    derived = {}
    for rng in package.ranges:
        der = compute_derived_fields(rng, warnings)
        if rng.range_id is not None:
            derived[rng.range_id] = der

    hierarchy_rows, hierarchy_warnings = check_hierarchy(package.ranges)
    warnings.extend(hierarchy_warnings)

    ledger_results, ledger_warnings = verify_raw_ledgers(package.raw_ledgers)
    warnings.extend(ledger_warnings)

    zone_rows, zone_stats = build_zone_report(package, warnings)
    metrics_rows, metrics_stats = build_range_metrics_report(package, derived)
    parent_child_rows, parent_child_stats = build_parent_child_report(package)
    bos_rows, bos_stats = build_bos_direction_report(package)

    reclaim_rows, reclaim_stats = build_bos_reclaim_report(package, warnings)
    abandon_rows, abandon_stats = build_bos_abandon_report(package, warnings)
    outcome_by_new_range_id, outcome_stats = build_outcome_summary(package, abandon_rows)
    retracement_rows, retracement_stats = build_retracement_report(
        package, warnings, outcome_by_new_range_id
    )
    rotation_rows, rotation_stats = build_rotation_report(package, derived, warnings)
    sequence_rows, sequence_stats = build_sequence_report(
        package, reclaim_rows, retracement_rows, outcome_by_new_range_id
    )

    rule_report_rows = {
        ZONE_REPORT_FILE: zone_rows,
        RANGE_METRICS_REPORT_FILE: metrics_rows,
        PARENT_CHILD_REPORT_FILE: parent_child_rows,
        BOS_DIRECTION_REPORT_FILE: bos_rows,
        RETRACEMENT_REPORT_FILE: retracement_rows,
        BOS_RECLAIM_REPORT_FILE: reclaim_rows,
        BOS_ABANDON_REPORT_FILE: abandon_rows,
        ROTATION_REPORT_FILE: rotation_rows,
        SEQUENCE_REPORT_FILE: sequence_rows,
    }
    rule_stats = {
        "zones": zone_stats,
        "range_metrics": metrics_stats,
        "parent_child": parent_child_stats,
        "bos_direction": bos_stats,
        "retracement": retracement_stats,
        "bos_reclaim": reclaim_stats,
        "bos_abandon": abandon_stats,
        "rotation": rotation_stats,
        "sequence": sequence_stats,
        "outcomes": outcome_stats,
    }

    yearly_stats = _build_yearly_stats(package, warnings, rule_stats)
    summary = _build_summary(package, yearly_stats, ledger_results, warnings)
    report_md = build_year_report(package, yearly_stats, ledger_results, warnings)

    ranges_df = normalized_ranges_frame(package.ranges, derived)
    events_df = normalized_events_frame(package.events)

    paths = write_year_outputs(
        output_dir=output_dir,
        package=package,
        ranges_df=ranges_df,
        events_df=events_df,
        yearly_stats=yearly_stats,
        summary=summary,
        report_md=report_md,
        warnings=warnings,
        hierarchy_rows=hierarchy_rows,
        rule_report_rows=rule_report_rows,
    )

    combined_result = None
    root = resolve_workspace_root(output_dir, package.symbol, workspace_root)
    if root is not None:
        combined_result = rebuild_combined(root, package.symbol)

    return {
        "package": package,
        "warnings": warnings,
        "yearly_stats": yearly_stats,
        "summary": summary,
        "paths": paths,
        "combined": combined_result,
        "rule_report_rows": rule_report_rows,
    }


def resolve_workspace_root(
    output_dir: str | Path, symbol: str, workspace_root: str | Path | None
) -> Path | None:
    """Combined artifacts need the workspace root (workspace/<SYMBOL>/<YEAR>).

    An explicit --workspace wins; otherwise the root is inferred from the
    output directory shape. If the output dir is somewhere arbitrary, the
    combined rebuild is skipped rather than guessed.
    """
    if workspace_root is not None:
        return Path(workspace_root)
    out = Path(output_dir).resolve()
    if out.parent.name.upper() == symbol.upper():
        return out.parent.parent
    return None


def _build_yearly_stats(
    package, warnings: list[AuditWarning], rule_stats: dict[str, Any]
) -> dict[str, Any]:
    return {
        "schema_version": ANALYST_STATS_SCHEMA,
        "engine_version": __version__,
        "symbol": package.symbol,
        "year": package.year,
        "label": package.label,
        "case_refs": package.case_refs,
        "generated_at_utc_ms": int(time.time() * 1000),
        "counts": {
            "cases": len(package.case_refs),
            "ranges": len(package.ranges),
            "events": len(package.events),
            "candles": {tf: len(rows) for tf, rows in package.candles.items()},
            "warnings": len(warnings),
        },
        "rule_stats": rule_stats,
    }


def _build_summary(
    package,
    yearly_stats: dict[str, Any],
    ledger_results: list[dict[str, Any]],
    warnings: list[AuditWarning],
) -> dict[str, Any]:
    per_case = []
    for ref in package.case_refs:
        per_case.append(
            {
                "case_ref": ref,
                "ranges": sum(1 for r in package.ranges if r.case_ref == ref),
                "events": sum(1 for e in package.events if e.case_ref == ref),
                "ledger": next(
                    (lr.get("status") for lr in ledger_results if lr.get("case_ref") == ref),
                    "NOT_EMBEDDED",
                ),
            }
        )
    warning_counts: dict[str, int] = {}
    for warning in warnings:
        warning_counts[warning.code] = warning_counts.get(warning.code, 0) + 1
    return {
        "phase": "A",
        "engine_version": __version__,
        "label": package.label,
        "symbol": package.symbol,
        "year": package.year,
        "counts": yearly_stats["counts"],
        "cases": per_case,
        "ledger_results": ledger_results,
        "warning_counts": warning_counts,
    }
