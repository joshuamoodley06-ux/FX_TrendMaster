"""BOS + Reclaim model (spec section: BOS + Reclaim Model).

BOS = a range marked BROKEN with direction_of_break (+ broken_by_event_id
and inactive_from_time when available).

Broken level:
    BOS UP   -> the broken range's high
    BOS DOWN -> the broken range's low

Reclaim (UP case, DOWN mirrored): after the BOS, price pulls back below
the broken level, then a candle CLOSES back above it. Detected from
candles between the BOS time and the end of the new range's lifecycle
(or end of data).

reclaim_depth_percent = depth of the pullback beyond the broken level,
relative to the new range's impulse span (falls back to the broken
range's span when the new range is unusable):

    UP:   (broken_level - lowest_low_before_reclaim) / span
    DOWN: (highest_high_before_reclaim - broken_level) / span

    shallow < 0.33 | mid < 0.66 | deep >= 0.66

When candles are missing the row stays unresolved (empty reclaim fields)
with an audit warning — never a crash.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from analyst.audit.audit_warnings import AuditWarning
from analyst.models.common import (
    bos_time_for_pair,
    broken_pairs,
    candles_between,
    select_candles,
)
from analyst.models.records import InputPackage, RangeRecord
from analyst.util.timeparse import ms_to_iso

BOS_RECLAIM_REPORT_FILE = "bos_reclaim_report.csv"


def classify_reclaim_depth(percent: float | None) -> str | None:
    if percent is None:
        return None
    if percent >= 0.66:
        return "DEEP"
    if percent >= 0.33:
        return "MID"
    return "SHALLOW"


def build_bos_reclaim_report(
    package: InputPackage, warnings: list[AuditWarning]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    class_counts: Counter[str] = Counter()
    reclaim_true = reclaim_false = unresolved = continuation_count = 0

    for old_range, new_range in broken_pairs(package):
        direction = old_range.direction_of_break
        row: dict[str, Any] = {
            "case_ref": old_range.case_ref,
            "symbol": old_range.symbol,
            "range_id": old_range.range_id,
            "structure_layer": old_range.structure_layer,
            "range_scope": old_range.range_scope,
            "bos_direction": direction,
            "reclaim_occurred": None,
            "reclaim_time": None,
            "reclaim_candle_count_after_bos": None,
            "reclaim_depth_percent": None,
            "reclaim_class": None,
            "continuation_after_reclaim": None,
            "candles_to_continuation_bos": None,
            "abandon_after_reclaim": None,
        }
        rows.append(row)

        broken_level = (
            old_range.range_high_price if direction == "UP" else old_range.range_low_price
        )
        bos_time = bos_time_for_pair(old_range, new_range)
        if broken_level is None or bos_time is None:
            warnings.append(
                AuditWarning(
                    code="RECLAIM_INPUTS_MISSING",
                    case_ref=old_range.case_ref,
                    subject_id=old_range.range_id,
                    message="no broken level price or BOS time; reclaim unresolved",
                )
            )
            unresolved += 1
            continue

        candles = select_candles(package, old_range, warnings, "RECLAIM_CANDLES_MISSING")
        window_end = new_range.inactive_from_time_ms if new_range else None
        in_window = candles_between(candles, bos_time, window_end)
        if not in_window:
            unresolved += 1
            continue

        detection = _detect_reclaim(in_window, broken_level, direction)
        if detection is None:
            row["reclaim_occurred"] = False
            reclaim_false += 1
            continue

        reclaim_candle_index, reclaim_time_ms, pullback_extreme = detection
        span = _span_reference(new_range, old_range)
        depth = None
        if span:
            depth = round(abs(broken_level - pullback_extreme) / span, 6)
        depth_class = classify_reclaim_depth(depth)
        if depth_class:
            class_counts[depth_class] += 1

        continuation, candles_to_continuation, abandon_after = _after_reclaim(
            new_range, direction, reclaim_time_ms, in_window
        )
        if continuation:
            continuation_count += 1

        row.update(
            {
                "reclaim_occurred": True,
                "reclaim_time": ms_to_iso(reclaim_time_ms),
                "reclaim_candle_count_after_bos": reclaim_candle_index,
                "reclaim_depth_percent": depth,
                "reclaim_class": depth_class,
                "continuation_after_reclaim": continuation,
                "candles_to_continuation_bos": candles_to_continuation,
                "abandon_after_reclaim": abandon_after,
            }
        )
        reclaim_true += 1

    stats = {
        "bos_count": len(rows),
        "reclaim_true": reclaim_true,
        "reclaim_false": reclaim_false,
        "unresolved": unresolved,
        "reclaim_rate": round(reclaim_true / (reclaim_true + reclaim_false), 6)
        if (reclaim_true + reclaim_false)
        else None,
        "class_counts": dict(class_counts),
        "continuation_after_reclaim": continuation_count,
    }
    return rows, stats


def _detect_reclaim(
    in_window: list, broken_level: float, direction: str
) -> tuple[int, int, float] | None:
    """Returns (1-based candle index, reclaim time ms, pullback extreme) or None."""
    pullback_started = False
    pullback_extreme: float | None = None
    for index, candle in enumerate(in_window, start=1):
        if direction == "UP":
            if candle.low is not None and candle.low < broken_level:
                pullback_started = True
                pullback_extreme = (
                    candle.low if pullback_extreme is None else min(pullback_extreme, candle.low)
                )
            if pullback_started and candle.close is not None and candle.close > broken_level:
                return index, candle.time_ms, pullback_extreme
        else:
            if candle.high is not None and candle.high > broken_level:
                pullback_started = True
                pullback_extreme = (
                    candle.high if pullback_extreme is None else max(pullback_extreme, candle.high)
                )
            if pullback_started and candle.close is not None and candle.close < broken_level:
                return index, candle.time_ms, pullback_extreme
    return None


def _span_reference(new_range: RangeRecord | None, old_range: RangeRecord) -> float | None:
    for rng in (new_range, old_range):
        if (
            rng is not None
            and rng.range_high_price is not None
            and rng.range_low_price is not None
            and rng.range_high_price > rng.range_low_price
        ):
            return rng.range_high_price - rng.range_low_price
    return None


def _after_reclaim(
    new_range: RangeRecord | None,
    direction: str,
    reclaim_time_ms: int,
    in_window: list,
) -> tuple[bool | None, int | None, bool | None]:
    """Continuation/abandon facts after the reclaim, from saved ranges only."""
    if new_range is None:
        return None, None, None
    if new_range.status == "ABANDONED":
        return False, None, True
    if new_range.direction_of_break == direction:
        break_time = new_range.inactive_from_time_ms
        candles_to = None
        if break_time is not None:
            candles_to = sum(
                1
                for c in in_window
                if c.time_ms is not None and reclaim_time_ms < c.time_ms <= break_time
            )
        return True, candles_to, False
    if new_range.direction_of_break in ("UP", "DOWN"):
        return False, None, True
    return None, None, None  # new range still unbroken: unresolved
