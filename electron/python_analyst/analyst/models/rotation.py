"""Bounce Between Extremes model (spec section: Bounce Between Extremes).

Per parent range with children, over candles inside the parent lifecycle:

    premium threshold  = parent_low + 0.66 * span
    discount threshold = parent_low + 0.33 * span

Touch rule: a candle touches premium if high >= premium threshold, and
discount if low <= discount threshold.

A "touch" in the report counts contiguous episodes (consecutive candles
in the same extreme collapse into one visit). A rotation is a collapsed
visit pair: premium -> discount or discount -> premium. The window ends
at the parent's lifecycle end (its BOS) when broken, otherwise at the
end of data.
"""

from __future__ import annotations

from typing import Any

from analyst.audit.audit_warnings import AuditWarning
from analyst.models.derived_fields import DerivedRangeFields
from analyst.models.records import InputPackage
from analyst.models.common import select_candles

ROTATION_REPORT_FILE = "extreme_rotation_report.csv"

_PREMIUM_THRESHOLD = 0.66
_DISCOUNT_THRESHOLD = 0.33


def build_rotation_report(
    package: InputPackage,
    derived: dict[str | None, DerivedRangeFields],
    warnings: list[AuditWarning],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    ranges_by_id = {r.range_id: r for r in package.ranges if r.range_id}
    children_by_parent: dict[str, list] = {}
    for rng in package.ranges:
        if rng.parent_range_id and rng.parent_range_id in ranges_by_id:
            children_by_parent.setdefault(rng.parent_range_id, []).append(rng)

    rows: list[dict[str, Any]] = []
    totals = {"premium_touches": 0, "discount_touches": 0, "rotations": 0,
              "premium_to_discount": 0, "discount_to_premium": 0}

    for parent_id, children in sorted(children_by_parent.items()):
        parent = ranges_by_id[parent_id]
        if (
            parent.range_high_price is None
            or parent.range_low_price is None
            or parent.range_high_price <= parent.range_low_price
        ):
            warnings.append(
                AuditWarning(
                    code="ROTATION_PARENT_SPAN_INVALID",
                    case_ref=parent.case_ref,
                    subject_id=parent_id,
                    message="parent range has no valid high/low span for rotation analysis",
                )
            )
            continue

        span = parent.range_high_price - parent.range_low_price
        premium_threshold = parent.range_low_price + _PREMIUM_THRESHOLD * span
        discount_threshold = parent.range_low_price + _DISCOUNT_THRESHOLD * span

        parent_derived = derived.get(parent_id)
        window_start = parent_derived.lifecycle_start_ms if parent_derived else None
        window_end = parent_derived.lifecycle_end_ms if parent_derived else None

        candles = select_candles(package, parent, warnings, "ROTATION_CANDLES_MISSING")
        in_window = [
            c
            for c in candles
            if c.time_ms is not None
            and (window_start is None or c.time_ms >= window_start)
            and (window_end is None or c.time_ms <= window_end)
        ]

        visits = _collapse_visits(in_window, premium_threshold, discount_threshold)
        premium_touches = sum(1 for v in visits if v == "PREMIUM")
        discount_touches = sum(1 for v in visits if v == "DISCOUNT")
        p2d = sum(
            1 for a, b in zip(visits, visits[1:]) if a == "PREMIUM" and b == "DISCOUNT"
        )
        d2p = sum(
            1 for a, b in zip(visits, visits[1:]) if a == "DISCOUNT" and b == "PREMIUM"
        )

        child_count_before_break = len(children)
        if window_end is not None:
            child_count_before_break = sum(
                1
                for child in children
                if (
                    (derived.get(child.range_id).lifecycle_start_ms if derived.get(child.range_id) else None)
                    or 0
                )
                < window_end
            )

        child_layers = sorted({c.structure_layer for c in children if c.structure_layer})
        rows.append(
            {
                "parent_range_id": parent_id,
                "parent_layer": parent.structure_layer,
                "child_layer": "|".join(child_layers),
                "premium_touches": premium_touches,
                "discount_touches": discount_touches,
                "rotations_count": p2d + d2p,
                "final_break_direction": parent.direction_of_break,
                "child_count_before_break": child_count_before_break,
            }
        )
        totals["premium_touches"] += premium_touches
        totals["discount_touches"] += discount_touches
        totals["rotations"] += p2d + d2p
        totals["premium_to_discount"] += p2d
        totals["discount_to_premium"] += d2p

    stats = {"parents": len(rows), **totals}
    return rows, stats


def _collapse_visits(
    candles: list, premium_threshold: float, discount_threshold: float
) -> list[str]:
    """Chronological extreme-zone visits with consecutive duplicates collapsed."""
    visits: list[str] = []
    for candle in candles:
        touched: list[str] = []
        touches_discount = candle.low is not None and candle.low <= discount_threshold
        touches_premium = candle.high is not None and candle.high >= premium_threshold
        if touches_discount and touches_premium:
            # Order both touches by candle direction.
            bullish = (
                candle.close is not None
                and candle.open is not None
                and candle.close >= candle.open
            )
            touched = ["DISCOUNT", "PREMIUM"] if bullish else ["PREMIUM", "DISCOUNT"]
        elif touches_discount:
            touched = ["DISCOUNT"]
        elif touches_premium:
            touched = ["PREMIUM"]
        for zone in touched:
            if not visits or visits[-1] != zone:
                visits.append(zone)
    return visits
