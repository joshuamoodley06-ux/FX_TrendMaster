"""Derived range fields (spec section: Derived Range Fields).

    anchor_start    = range_start_time  || min(range_high_time, range_low_time)
    anchor_end      = range_end_time    || max(range_high_time, range_low_time)
    lifecycle_start = active_from_time  || anchor_start
    lifecycle_end   = inactive_from_time || null
    price_span      = abs(range_high_price - range_low_price)

Computed per range, never stored back to any backend.
"""

from __future__ import annotations

from dataclasses import dataclass

from analyst.audit.audit_warnings import AuditWarning
from analyst.models.records import RangeRecord


@dataclass(frozen=True)
class DerivedRangeFields:
    range_id: str | None
    case_ref: str | None
    anchor_start_ms: int | None
    anchor_end_ms: int | None
    lifecycle_start_ms: int | None
    lifecycle_end_ms: int | None
    price_span: float | None


def compute_derived_fields(
    rng: RangeRecord, warnings: list[AuditWarning]
) -> DerivedRangeFields:
    anchor_times = [t for t in (rng.range_high_time_ms, rng.range_low_time_ms) if t is not None]

    anchor_start = rng.range_start_time_ms
    if anchor_start is None and anchor_times:
        anchor_start = min(anchor_times)

    anchor_end = rng.range_end_time_ms
    if anchor_end is None and anchor_times:
        anchor_end = max(anchor_times)

    if anchor_start is None and anchor_end is None:
        warnings.append(
            AuditWarning(
                code="RANGE_MISSING_ANCHORS",
                case_ref=rng.case_ref,
                subject_id=rng.range_id,
                message="range has no usable anchor times",
            )
        )
    elif anchor_start is not None and anchor_end is not None and anchor_start > anchor_end:
        # Anchor span warnings must not fail analysis (acceptance test).
        warnings.append(
            AuditWarning(
                code="ANCHOR_SPAN_INVERTED",
                case_ref=rng.case_ref,
                subject_id=rng.range_id,
                message=f"anchor_start {anchor_start} is after anchor_end {anchor_end}",
            )
        )

    lifecycle_start = rng.active_from_time_ms if rng.active_from_time_ms is not None else anchor_start
    lifecycle_end = rng.inactive_from_time_ms

    price_span = None
    if rng.range_high_price is not None and rng.range_low_price is not None:
        price_span = abs(rng.range_high_price - rng.range_low_price)

    return DerivedRangeFields(
        range_id=rng.range_id,
        case_ref=rng.case_ref,
        anchor_start_ms=anchor_start,
        anchor_end_ms=anchor_end,
        lifecycle_start_ms=lifecycle_start,
        lifecycle_end_ms=lifecycle_end,
        price_span=price_span,
    )
