"""Year workspace writer.

Writes one analyzed year into workspace/<SYMBOL>/<YEAR>/:

    input_snapshot.json
    normalized_ranges.parquet
    normalized_events.parquet
    yearly_stats.json
    reports/   (analyst_summary.json, analyst_report.md, all CSVs)

Every rule-model CSV is always written: with rows when its model has run,
headers-only otherwise, so schemas are stable for the Electron UI.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from analyst.audit.audit_warnings import AUDIT_WARNING_COLUMNS, AuditWarning
from analyst.audit.hierarchy_check import HIERARCHY_COLUMNS
from analyst.models.derived_fields import DerivedRangeFields
from analyst.models.records import EventRecord, InputPackage, RangeRecord
from analyst.reports.csv_writer import write_csv
from analyst.reports.json_writer import write_json


def _resolve_default_workspace_root() -> Path:
    """Prefer OneDrive Documents when present (common on Windows)."""
    home = Path.home()
    candidates = [
        home / "OneDrive" / "Documents" / "FXTM_Analyst" / "workspace",
        home / "Documents" / "FXTM_Analyst" / "workspace",
    ]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return candidates[0]


DEFAULT_WORKSPACE_ROOT = _resolve_default_workspace_root()

# Final column contracts for all rule-model reports (from the build spec).
RULE_REPORT_COLUMNS: dict[str, list[str]] = {
    "range_zone_position.csv": [
        "case_ref", "symbol", "parent_range_id", "child_range_id", "structure_layer", "range_scope",
        "rh_position_percent", "rl_position_percent", "midpoint_position_percent",
        "bos_position_percent", "start_zone", "start_zone_third", "break_zone", "break_zone_third",
    ],
    "range_duration_size.csv": [
        "case_ref", "symbol", "range_id", "structure_layer", "range_scope", "status",
        "anchor_start_ms", "anchor_end_ms", "anchor_span_ms",
        "lifecycle_start_ms", "lifecycle_end_ms", "lifecycle_span_ms",
        "price_span", "price_span_percent_of_parent",
    ],
    "parent_child_summary.csv": [
        "case_ref", "parent_range_id", "parent_layer", "parent_scope", "parent_status",
        "child_count", "child_layers",
        "children_broken_up", "children_broken_down",
        "children_abandoned", "children_active",
    ],
    "bos_direction_stats.csv": [
        "case_ref", "structure_layer",
        "range_bos_up", "range_bos_down",
        "event_bos_up", "event_bos_down",
    ],
    "retracement_stats.csv": [
        "case_ref", "symbol", "parent_range_id", "range_id", "structure_layer", "range_scope",
        "direction_of_break", "retracement_percent", "retracement_class",
        "retracement_price", "retracement_time", "next_bos_direction", "outcome",
    ],
    "bos_reclaim_report.csv": [
        "case_ref", "symbol", "range_id", "structure_layer", "range_scope", "bos_direction", "reclaim_occurred",
        "reclaim_time", "reclaim_candle_count_after_bos", "reclaim_depth_percent",
        "reclaim_class", "continuation_after_reclaim", "candles_to_continuation_bos",
        "abandon_after_reclaim",
    ],
    "bos_abandon_report.csv": [
        "old_range_id", "new_range_id", "structure_layer", "range_scope", "bos_direction", "abandoned",
        "abandon_reason", "opposite_break_time", "candles_before_abandon",
    ],
    "extreme_rotation_report.csv": [
        "parent_range_id", "parent_layer", "child_layer", "premium_touches",
        "discount_touches", "rotations_count", "final_break_direction",
        "child_count_before_break",
    ],
    "impulse_retest_sequence.csv": [
        "case_ref", "parent_range_id", "child_range_id", "layer", "range_scope", "sequence_direction",
        "impulse_index", "retest_index", "bos_event_id", "reclaim_detected",
        "retracement_class", "next_outcome",
    ],
}

YEARLY_SUMMARY_COLUMNS = [
    "symbol", "year", "label", "cases", "ranges", "events", "candles_total", "warnings",
]


def normalized_ranges_frame(
    ranges: list[RangeRecord], derived: dict[str | None, DerivedRangeFields]
) -> pd.DataFrame:
    rows = []
    for rng in ranges:
        der = derived.get(rng.range_id)
        rows.append(
            {
                "range_id": rng.range_id,
                "case_ref": rng.case_ref,
                "symbol": rng.symbol,
                "structure_layer": rng.structure_layer,
                "range_scope": rng.range_scope,
                "source_timeframe": rng.source_timeframe,
                "chart_timeframe": rng.chart_timeframe,
                "parent_range_id": rng.parent_range_id,
                "old_range_id": rng.old_range_id,
                "new_range_id": rng.new_range_id,
                "status": rng.status,
                "direction_of_break": rng.direction_of_break,
                "broken_by_event_id": rng.broken_by_event_id,
                "created_by_event_id": rng.created_by_event_id,
                "range_high_price": rng.range_high_price,
                "range_low_price": rng.range_low_price,
                "range_high_time_ms": rng.range_high_time_ms,
                "range_low_time_ms": rng.range_low_time_ms,
                "range_start_time_ms": rng.range_start_time_ms,
                "range_end_time_ms": rng.range_end_time_ms,
                "active_from_time_ms": rng.active_from_time_ms,
                "inactive_from_time_ms": rng.inactive_from_time_ms,
                "anchor_start_ms": der.anchor_start_ms if der else None,
                "anchor_end_ms": der.anchor_end_ms if der else None,
                "lifecycle_start_ms": der.lifecycle_start_ms if der else None,
                "lifecycle_end_ms": der.lifecycle_end_ms if der else None,
                "price_span": der.price_span if der else None,
            }
        )
    return pd.DataFrame(rows)


def normalized_events_frame(events: list[EventRecord]) -> pd.DataFrame:
    rows = [
        {
            "event_id": e.event_id,
            "case_ref": e.case_ref,
            "symbol": e.symbol,
            "timeframe": e.timeframe,
            "event_type": e.event_type,
            "structure_layer": e.structure_layer,
            "source_timeframe": e.source_timeframe,
            "active_range_id": e.active_range_id,
            "parent_range_id": e.parent_range_id,
            "event_time_ms": e.event_time_ms,
            "event_price": e.event_price,
            "direction": e.direction,
            "candle_open": e.candle_open,
            "candle_high": e.candle_high,
            "candle_low": e.candle_low,
            "candle_close": e.candle_close,
        }
        for e in events
    ]
    return pd.DataFrame(rows)


def write_year_outputs(
    output_dir: str | Path,
    package: InputPackage,
    ranges_df: pd.DataFrame,
    events_df: pd.DataFrame,
    yearly_stats: dict[str, Any],
    summary: dict[str, Any],
    report_md: str,
    warnings: list[AuditWarning],
    hierarchy_rows: list[dict[str, Any]],
    rule_report_rows: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Path]:
    out = Path(output_dir)
    reports_dir = out / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    paths: dict[str, Path] = {}
    paths["input_snapshot"] = write_json(out / "input_snapshot.json", package.raw)
    paths["yearly_stats"] = write_json(out / "yearly_stats.json", yearly_stats)

    ranges_df.to_parquet(out / "normalized_ranges.parquet", index=False)
    paths["normalized_ranges"] = out / "normalized_ranges.parquet"
    events_df.to_parquet(out / "normalized_events.parquet", index=False)
    paths["normalized_events"] = out / "normalized_events.parquet"

    paths["analyst_summary"] = write_json(reports_dir / "analyst_summary.json", summary)
    report_path = reports_dir / "analyst_report.md"
    report_path.write_text(report_md, encoding="utf-8")
    paths["analyst_report"] = report_path

    paths["audit_warnings"] = write_csv(
        reports_dir / "audit_warnings.csv",
        AUDIT_WARNING_COLUMNS,
        [w.to_row() for w in warnings],
    )
    paths["hierarchy_completeness"] = write_csv(
        reports_dir / "hierarchy_completeness.csv", HIERARCHY_COLUMNS, hierarchy_rows
    )
    paths["yearly_summary"] = write_csv(
        reports_dir / "yearly_summary.csv",
        YEARLY_SUMMARY_COLUMNS,
        [
            {
                "symbol": package.symbol,
                "year": package.year,
                "label": package.label,
                "cases": len(package.case_refs),
                "ranges": len(package.ranges),
                "events": len(package.events),
                "candles_total": package.candle_count_total,
                "warnings": len(warnings),
            }
        ],
    )

    rule_rows = rule_report_rows or {}
    for filename, columns in RULE_REPORT_COLUMNS.items():
        paths[filename] = write_csv(reports_dir / filename, columns, rule_rows.get(filename, []))

    return paths
