"""Shared helpers for rule models: candle selection and BOS pair resolution."""

from __future__ import annotations

from analyst.audit.audit_warnings import AuditWarning
from analyst.models.records import Candle, InputPackage, RangeRecord


def select_candles(
    package: InputPackage,
    rng: RangeRecord,
    warnings: list[AuditWarning],
    missing_code: str,
) -> list[Candle]:
    """Candles for a range: source_timeframe first, chart_timeframe fallback."""
    for timeframe in (rng.source_timeframe, rng.chart_timeframe):
        if timeframe and package.candles.get(timeframe):
            return package.candles[timeframe]
    warnings.append(
        AuditWarning(
            code=missing_code,
            case_ref=rng.case_ref,
            subject_id=rng.range_id,
            message=(
                f"no candles for source_timeframe {rng.source_timeframe!r} "
                f"or chart_timeframe {rng.chart_timeframe!r}"
            ),
        )
    )
    return []


def candles_between(
    candles: list[Candle], start_exclusive_ms: int, end_inclusive_ms: int | None
) -> list[Candle]:
    return [
        c
        for c in candles
        if c.time_ms is not None
        and c.time_ms > start_exclusive_ms
        and (end_inclusive_ms is None or c.time_ms <= end_inclusive_ms)
    ]


def find_new_range(
    old_range: RangeRecord,
    ranges_by_id: dict[str | None, RangeRecord],
    all_ranges: list[RangeRecord],
) -> RangeRecord | None:
    """Resolve the range created by a BOS: new_range_id first, old_range_id backlink fallback."""
    if old_range.new_range_id and old_range.new_range_id in ranges_by_id:
        return ranges_by_id[old_range.new_range_id]
    return next(
        (r for r in all_ranges if r.old_range_id and r.old_range_id == old_range.range_id),
        None,
    )


def broken_pairs(package: InputPackage) -> list[tuple[RangeRecord, RangeRecord | None]]:
    """All (broken range, new range or None) BOS pairs in the package, deduped."""
    ranges_by_id = {r.range_id: r for r in package.ranges if r.range_id}
    pairs: list[tuple[RangeRecord, RangeRecord | None]] = []
    seen: set[tuple[str | None, str | None]] = set()
    for old_range in package.ranges:
        if old_range.status != "BROKEN" or old_range.direction_of_break not in ("UP", "DOWN"):
            continue
        new_range = find_new_range(old_range, ranges_by_id, package.ranges)
        key = (old_range.range_id, new_range.range_id if new_range else None)
        if key in seen:
            continue
        seen.add(key)
        pairs.append((old_range, new_range))
    return pairs


def bos_time_for_pair(
    old_range: RangeRecord, new_range: RangeRecord | None
) -> int | None:
    if old_range.inactive_from_time_ms is not None:
        return old_range.inactive_from_time_ms
    return new_range.active_from_time_ms if new_range else None
