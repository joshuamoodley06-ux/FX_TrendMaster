"""Retracement model (spec section: Retracement Model).

For each BOS-created range sequence (Range A breaks -> Range B forms),
measure how deep price retraced into Range B's impulse leg before B's
own lifecycle ended (next BOS or abandon) or data ran out.

    bullish:  retracement_percent = (impulse_high - lowest low after BOS)
                                    / (impulse_high - impulse_low)
    bearish:  retracement_percent = (highest high after BOS - impulse_low)
                                    / (impulse_high - impulse_low)

    shallow 0.00-0.33 | mid 0.33-0.66 | deep 0.66-1.00 | extreme > 1.00

Outcome: taken from the full outcome classifier (analyst.models.outcome)
when its results are passed in; otherwise a saved-range-facts fallback
(CONTINUED / FAILED / ABANDONED / UNRESOLVED) is used.
"""

from __future__ import annotations

from collections import Counter
from statistics import mean, median
from typing import Any

from analyst.audit.audit_warnings import AuditWarning
from analyst.models.common import candles_between, find_new_range, select_candles
from analyst.models.records import InputPackage, RangeRecord
from analyst.util.timeparse import ms_to_iso

RETRACEMENT_REPORT_FILE = "retracement_stats.csv"


def classify_retracement(percent: float | None) -> str | None:
    if percent is None:
        return None
    if percent > 1.0:
        return "EXTREME"
    if percent >= 0.66:
        return "DEEP"
    if percent >= 0.33:
        return "MID"
    return "SHALLOW"


def build_retracement_report(
    package: InputPackage,
    warnings: list[AuditWarning],
    outcome_by_new_range_id: dict[str, str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    ranges_by_id = {r.range_id: r for r in package.ranges if r.range_id}

    rows: list[dict[str, Any]] = []
    class_counts: Counter[str] = Counter()
    percents: list[float] = []
    seen_pairs: set[tuple[str | None, str | None]] = set()

    for old_range in package.ranges:
        if old_range.status != "BROKEN" or old_range.direction_of_break not in ("UP", "DOWN"):
            continue
        new_range = find_new_range(old_range, ranges_by_id, package.ranges)
        if new_range is None:
            warnings.append(
                AuditWarning(
                    code="RETRACEMENT_NO_NEW_RANGE",
                    case_ref=old_range.case_ref,
                    subject_id=old_range.range_id,
                    message="broken range has no resolvable new range in package",
                )
            )
            continue
        pair = (old_range.range_id, new_range.range_id)
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)

        direction = old_range.direction_of_break
        percent, retr_price, retr_time_ms = _measure_retracement(
            package, old_range, new_range, direction, warnings
        )
        retr_class = classify_retracement(percent)
        if retr_class:
            class_counts[retr_class] += 1
        if percent is not None:
            percents.append(percent)

        rows.append(
            {
                "case_ref": new_range.case_ref,
                "symbol": new_range.symbol,
                "parent_range_id": new_range.parent_range_id,
                "range_id": new_range.range_id,
                "structure_layer": new_range.structure_layer,
                "range_scope": new_range.range_scope,
                "direction_of_break": direction,
                "retracement_percent": percent,
                "retracement_class": retr_class,
                "retracement_price": retr_price,
                "retracement_time": ms_to_iso(retr_time_ms),
                "next_bos_direction": new_range.direction_of_break,
                "outcome": (outcome_by_new_range_id or {}).get(
                    new_range.range_id or "", _fallback_outcome(new_range, direction)
                ),
            }
        )

    stats = {
        "sequences": len(rows),
        "classified": len(percents),
        "class_counts": dict(class_counts),
        "avg_retracement_percent": round(mean(percents), 6) if percents else None,
        "median_retracement_percent": round(median(percents), 6) if percents else None,
    }
    return rows, stats


def _measure_retracement(
    package: InputPackage,
    old_range: RangeRecord,
    new_range: RangeRecord,
    direction: str,
    warnings: list[AuditWarning],
) -> tuple[float | None, float | None, int | None]:
    impulse_high = new_range.range_high_price
    impulse_low = new_range.range_low_price
    if impulse_high is None or impulse_low is None or impulse_high <= impulse_low:
        warnings.append(
            AuditWarning(
                code="RETRACEMENT_IMPULSE_INVALID",
                case_ref=new_range.case_ref,
                subject_id=new_range.range_id,
                message="new range has no valid impulse high/low span",
            )
        )
        return None, None, None

    bos_time = new_range.active_from_time_ms or old_range.inactive_from_time_ms
    if bos_time is None:
        warnings.append(
            AuditWarning(
                code="RETRACEMENT_NO_BOS_TIME",
                case_ref=new_range.case_ref,
                subject_id=new_range.range_id,
                message="no active_from_time/inactive_from_time to anchor the BOS",
            )
        )
        return None, None, None

    candles = select_candles(package, new_range, warnings, "RETRACEMENT_CANDLES_MISSING")
    if not candles:
        return None, None, None

    in_window = candles_between(candles, bos_time, new_range.inactive_from_time_ms)
    if not in_window:
        warnings.append(
            AuditWarning(
                code="RETRACEMENT_NO_CANDLES_AFTER_BOS",
                case_ref=new_range.case_ref,
                subject_id=new_range.range_id,
                message="no candles after BOS inside the range lifecycle window",
            )
        )
        return None, None, None

    span = impulse_high - impulse_low
    if direction == "UP":
        extreme = min((c for c in in_window if c.low is not None), key=lambda c: c.low, default=None)
        if extreme is None:
            return None, None, None
        percent = (impulse_high - extreme.low) / span
        return round(max(percent, 0.0), 6), extreme.low, extreme.time_ms
    extreme = max((c for c in in_window if c.high is not None), key=lambda c: c.high, default=None)
    if extreme is None:
        return None, None, None
    percent = (extreme.high - impulse_low) / span
    return round(max(percent, 0.0), 6), extreme.high, extreme.time_ms


def _fallback_outcome(new_range: RangeRecord, bos_direction: str) -> str:
    if new_range.status == "ABANDONED":
        return "ABANDONED"
    if new_range.direction_of_break == bos_direction:
        return "CONTINUED"
    if new_range.direction_of_break in ("UP", "DOWN"):
        return "FAILED"
    return "UNRESOLVED"
