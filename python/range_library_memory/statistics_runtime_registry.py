"""Install statistics snapshots after the active Weekly + Daily doctrine pipeline."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .statistics_reports import (
    StatisticsReportError,
    apply_persisted_statistics_report_metadata,
    build_statistics_report,
)


def install(pipeline: Any) -> None:
    if getattr(pipeline, "_weekly_daily_statistics_installed", False):
        return
    base_run_active = pipeline.run_active_pipeline
    base_apply_approved = pipeline.apply_approved_enrichments

    def apply_approved_enrichments(
        connection: Any,
        master_map: dict[str, Any],
        *,
        symbol: str,
    ) -> None:
        base_apply_approved(connection, master_map, symbol=symbol)
        apply_persisted_statistics_report_metadata(
            connection,
            master_map,
            symbol=symbol,
        )

    def run_active_pipeline(
        db_path: str | Path,
        *,
        case_ref: str,
        symbol: str,
        source_db: str | Path,
    ) -> dict[str, Any]:
        summary = base_run_active(
            db_path,
            case_ref=case_ref,
            symbol=symbol,
            source_db=source_db,
        )
        try:
            summary["statistics_report"] = build_statistics_report(
                db_path,
                case_ref=case_ref,
                symbol=symbol,
            )
        except (StatisticsReportError, OSError, ValueError) as exc:
            summary["statistics_report"] = {
                "status": "FAILED",
                "error": str(exc),
            }
        return summary

    pipeline.apply_approved_enrichments = apply_approved_enrichments
    pipeline.run_active_pipeline = run_active_pipeline
    pipeline._weekly_daily_statistics_installed = True
