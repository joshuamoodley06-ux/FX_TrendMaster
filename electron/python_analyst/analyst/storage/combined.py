"""Combined (multi-year) artifacts.

Rebuilt exclusively from the saved yearly_stats.json files under
workspace/<SYMBOL>/<YEAR>/ — raw historical data is never reloaded.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from analyst import ANALYST_STATS_SCHEMA
from analyst.reports.csv_writer import write_csv
from analyst.reports.json_writer import write_json
from analyst.storage.batches import list_symbol_batch_dirs, read_yearly_stats

YEAR_COMPARISON_COLUMNS = [
    "year", "label", "cases", "ranges", "events", "candles_total", "warnings",
]


def load_yearly_stats(workspace_root: str | Path, symbol: str) -> list[dict[str, Any]]:
    stats: list[dict[str, Any]] = []
    for batch_dir in list_symbol_batch_dirs(workspace_root, symbol):
        payload = read_yearly_stats(batch_dir)
        if payload:
            stats.append(payload)
    return stats


def rebuild_combined(workspace_root: str | Path, symbol: str) -> dict[str, Any]:
    yearly = load_yearly_stats(workspace_root, symbol)
    combined_dir = Path(workspace_root) / symbol / "combined"

    comparison_rows = []
    totals = {"cases": 0, "ranges": 0, "events": 0, "candles_total": 0, "warnings": 0}
    for stats in yearly:
        counts = stats.get("counts", {})
        candle_counts = counts.get("candles", {})
        candles_total = sum(candle_counts.values()) if isinstance(candle_counts, dict) else 0
        row = {
            "year": stats.get("year"),
            "label": stats.get("label"),
            "cases": counts.get("cases", 0),
            "ranges": counts.get("ranges", 0),
            "events": counts.get("events", 0),
            "candles_total": candles_total,
            "warnings": counts.get("warnings", 0),
        }
        comparison_rows.append(row)
        for key in totals:
            totals[key] += int(row.get(key) or 0)

    combined_stats = {
        "schema_version": ANALYST_STATS_SCHEMA,
        "symbol": symbol,
        "generated_at_utc_ms": int(time.time() * 1000),
        "years_analyzed": [
            stats.get("year_label") or stats.get("label") or stats.get("year")
            for stats in yearly
        ],
        "totals": totals,
        "yearly": yearly,
    }

    if comparison_rows:
        write_json(combined_dir / f"{symbol}_combined_stats.json", combined_stats)
        write_csv(
            combined_dir / f"{symbol}_year_comparison.csv",
            YEAR_COMPARISON_COLUMNS,
            comparison_rows,
        )
        report_path = combined_dir / f"{symbol}_combined_report.md"
        report_path.write_text(_build_combined_report(symbol, comparison_rows, totals), encoding="utf-8")

    return {
        "symbol": symbol,
        "years": len(comparison_rows),
        "comparison_rows": comparison_rows,
        "combined_dir": str(combined_dir),
        "written": bool(comparison_rows),
    }


def _build_combined_report(
    symbol: str, comparison_rows: list[dict[str, Any]], totals: dict[str, int]
) -> str:
    lines = [f"# Combined Analyst Report — {symbol}", ""]
    lines.append(f"Years analyzed: {len(comparison_rows)}")
    lines.append("")
    lines.append("| Year | Label | Cases | Ranges | Events | Candles | Warnings |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for row in comparison_rows:
        lines.append(
            f"| {row.get('year')} | {row.get('label')} | {row.get('cases')} | "
            f"{row.get('ranges')} | {row.get('events')} | {row.get('candles_total')} | "
            f"{row.get('warnings')} |"
        )
    lines.append(
        f"| **Total** | | {totals['cases']} | {totals['ranges']} | {totals['events']} | "
        f"{totals['candles_total']} | {totals['warnings']} |"
    )
    lines.append("")
    lines.append(
        "Rule-model aggregates (zone stats, retracement classes, reclaim/abandon "
        "rates, rotations) are added to this report in Phase B/C."
    )
    lines.append("")
    return "\n".join(lines)
