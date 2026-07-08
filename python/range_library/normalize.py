"""Normalization helpers for raw range dictionaries."""

from __future__ import annotations

from typing import Any, Iterable

from .models import RangeRecord


def extract_raw_ranges(export: Any) -> list[dict[str, Any]]:
    """Extract range dictionaries from known export-like shapes."""

    if isinstance(export, list):
        return [item for item in export if isinstance(item, dict)]

    if not isinstance(export, dict):
        return []

    for key in ("ranges", "range_records", "records"):
        value = export.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]

    return []


def normalize_range(raw_range: dict[str, Any]) -> RangeRecord:
    """Normalize a raw range dictionary into a RangeRecord."""

    range_id = str(raw_range.get("id") or raw_range.get("range_id") or "")
    layer = str(raw_range.get("layer") or raw_range.get("timeframe") or "unknown")
    status = str(raw_range.get("status") or raw_range.get("state") or "unknown")
    parent_id = raw_range.get("parent_id") or raw_range.get("parentRangeId")
    normalized_parent_id = str(parent_id) if parent_id else None

    return RangeRecord(
        range_id=range_id,
        layer=layer,
        status=status,
        parent_id=normalized_parent_id,
        source=dict(raw_range),
    )


def normalize_ranges(raw_ranges: Iterable[dict[str, Any]]) -> list[RangeRecord]:
    """Normalize raw range dictionaries into RangeRecord objects."""

    return [normalize_range(raw_range) for raw_range in raw_ranges]
