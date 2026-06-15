"""BOS + Abandon model (spec section: BOS + Abandon Model, Rule V1).

After a BOS, the move is abandoned when price fails to build a valid
continuation and instead gives the move back. Saved ranges are consulted
first, then a candle rule:

    1. STATUS_ABANDONED        - new range status is ABANDONED
    2. OPPOSITE_BREAK          - new range later breaks opposite direction
    3. CONTINUED               - new range breaks in the BOS direction (not abandoned)
    4. PRICE_BROKE_NEW_RANGE_LOW / _HIGH
                               - new range still open but a candle closed
                                 beyond its opposite extreme before any
                                 continuation BOS
    5. UNRESOLVED              - new range open, no opposite break yet
    6. NO_NEXT_RANGE           - no new range resolvable (unresolved)
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
from analyst.models.records import InputPackage
from analyst.util.timeparse import ms_to_iso

BOS_ABANDON_REPORT_FILE = "bos_abandon_report.csv"


def build_bos_abandon_report(
    package: InputPackage, warnings: list[AuditWarning]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    reason_counts: Counter[str] = Counter()
    abandoned_count = continued_count = unresolved_count = 0

    for old_range, new_range in broken_pairs(package):
        direction = old_range.direction_of_break
        row: dict[str, Any] = {
            "old_range_id": old_range.range_id,
            "new_range_id": new_range.range_id if new_range else None,
            "structure_layer": old_range.structure_layer,
            "range_scope": old_range.range_scope,
            "bos_direction": direction,
            "abandoned": None,
            "abandon_reason": None,
            "opposite_break_time": None,
            "candles_before_abandon": None,
        }
        rows.append(row)

        if new_range is None:
            row["abandon_reason"] = "NO_NEXT_RANGE"
            unresolved_count += 1
            reason_counts["NO_NEXT_RANGE"] += 1
            continue

        bos_time = bos_time_for_pair(old_range, new_range)

        if new_range.status == "ABANDONED":
            row["abandoned"] = True
            row["abandon_reason"] = "STATUS_ABANDONED"
            row["opposite_break_time"] = ms_to_iso(new_range.inactive_from_time_ms)
            row["candles_before_abandon"] = _candle_count(
                package, old_range, new_range, bos_time, new_range.inactive_from_time_ms, warnings
            )
        elif new_range.direction_of_break in ("UP", "DOWN") and new_range.direction_of_break != direction:
            row["abandoned"] = True
            row["abandon_reason"] = "OPPOSITE_BREAK"
            row["opposite_break_time"] = ms_to_iso(new_range.inactive_from_time_ms)
            row["candles_before_abandon"] = _candle_count(
                package, old_range, new_range, bos_time, new_range.inactive_from_time_ms, warnings
            )
        elif new_range.direction_of_break == direction:
            row["abandoned"] = False
            row["abandon_reason"] = "CONTINUED"
        else:
            price_break = _price_broke_opposite_extreme(
                package, old_range, new_range, direction, bos_time, warnings
            )
            if price_break is not None:
                break_time_ms, candle_count = price_break
                row["abandoned"] = True
                row["abandon_reason"] = (
                    "PRICE_BROKE_NEW_RANGE_LOW" if direction == "UP" else "PRICE_BROKE_NEW_RANGE_HIGH"
                )
                row["opposite_break_time"] = ms_to_iso(break_time_ms)
                row["candles_before_abandon"] = candle_count
            else:
                row["abandon_reason"] = "UNRESOLVED"

        reason = row["abandon_reason"]
        reason_counts[reason] += 1
        if row["abandoned"] is True:
            abandoned_count += 1
        elif row["abandoned"] is False:
            continued_count += 1
        else:
            unresolved_count += 1

    stats = {
        "pairs": len(rows),
        "abandoned": abandoned_count,
        "continued": continued_count,
        "unresolved": unresolved_count,
        "reason_counts": dict(reason_counts),
    }
    return rows, stats


def _price_broke_opposite_extreme(
    package, old_range, new_range, direction, bos_time, warnings
) -> tuple[int, int] | None:
    """First candle close beyond the new range's opposite extreme, if any."""
    opposite_level = (
        new_range.range_low_price if direction == "UP" else new_range.range_high_price
    )
    if opposite_level is None or bos_time is None:
        return None
    candles = select_candles(package, new_range, warnings, "ABANDON_CANDLES_MISSING")
    in_window = candles_between(candles, bos_time, None)
    for index, candle in enumerate(in_window, start=1):
        if candle.close is None:
            continue
        if direction == "UP" and candle.close < opposite_level:
            return candle.time_ms, index
        if direction == "DOWN" and candle.close > opposite_level:
            return candle.time_ms, index
    return None


def _candle_count(
    package, old_range, new_range, bos_time, end_ms, warnings
) -> int | None:
    if bos_time is None or end_ms is None:
        return None
    candles = select_candles(package, new_range, warnings, "ABANDON_CANDLES_MISSING")
    if not candles:
        return None
    return len(candles_between(candles, bos_time, end_ms))
