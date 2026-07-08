"""Validation hook for normalized range records."""

from __future__ import annotations

from .models import RangeRecord


def validate_records(records: list[RangeRecord]) -> list[str]:
    """Return placeholder validation messages for normalized records."""

    errors: list[str] = []
    for index, record in enumerate(records):
        if not record.range_id:
            errors.append(f"record {index} is missing range_id")
    return errors
