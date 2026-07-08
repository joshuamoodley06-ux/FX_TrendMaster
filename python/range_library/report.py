"""Summary report generation for normalized ranges."""

from __future__ import annotations

from collections import Counter
from typing import Any

from .ingest import load_export
from .models import RangeRecord
from .normalize import extract_raw_ranges, normalize_ranges
from .validate import validate_records


def generate_summary_report(records: list[RangeRecord]) -> dict[str, Any]:
    """Generate aggregate counts for normalized ranges."""

    validation_errors = validate_records(records)
    if validation_errors:
        raise ValueError("; ".join(validation_errors))

    return {
        "total_ranges": len(records),
        "counts_by_layer": dict(Counter(record.layer for record in records)),
        "counts_by_status": dict(Counter(record.status for record in records)),
        "orphan_count": sum(1 for record in records if record.is_orphan),
    }


def generate_report_from_export(path: str) -> dict[str, Any]:
    """Load, normalize, and summarize a JSON export."""

    export = load_export(path)
    records = normalize_ranges(extract_raw_ranges(export))
    return generate_summary_report(records)
