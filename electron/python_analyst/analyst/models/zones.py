"""Premium / Discount / Fair Price zone position model.

For every child range with a resolvable parent:

    price_position_percent = (price - parent_low) / (parent_high - parent_low)

    Discount   0.00-0.33   (M1 0.00-0.11, M2 0.11-0.22, M3 0.22-0.33)
    Fair Price 0.33-0.66   (M1 0.33-0.44, M2 0.44-0.55, M3 0.55-0.66)
    Premium    0.66-1.00   (M1 0.66-0.77, M2 0.77-0.88, M3 0.88-1.00)

V1 definitions:
- start_zone  = zone of the child range midpoint inside the parent
- break_zone  = zone of the child's BOS event price (broken_by_event_id),
  when that event is available in the package
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from analyst.audit.audit_warnings import AuditWarning
from analyst.models.records import InputPackage

ZONE_REPORT_FILE = "range_zone_position.csv"

_DISCOUNT_MAX = 0.33
_FAIR_MAX = 0.66

_THIRD_BOUNDS = [
    (0.11, "DISCOUNT_M1"), (0.22, "DISCOUNT_M2"), (0.33, "DISCOUNT_M3"),
    (0.44, "FAIR_M1"), (0.55, "FAIR_M2"), (0.66, "FAIR_M3"),
    (0.77, "PREMIUM_M1"), (0.88, "PREMIUM_M2"), (1.0 + 1e-9, "PREMIUM_M3"),
]


def position_percent(price: float | None, low: float | None, high: float | None) -> float | None:
    if price is None or low is None or high is None:
        return None
    span = high - low
    if span <= 0:
        return None
    return round((price - low) / span, 6)


def classify_zone(percent: float | None) -> tuple[str | None, str | None]:
    """Returns (zone, detailed_third) for a position percent."""
    if percent is None:
        return None, None
    if percent < 0.0:
        return "BELOW_RANGE", "BELOW_RANGE"
    if percent > 1.0:
        return "ABOVE_RANGE", "ABOVE_RANGE"
    zone = "DISCOUNT" if percent < _DISCOUNT_MAX else "FAIR" if percent < _FAIR_MAX else "PREMIUM"
    third = next(label for bound, label in _THIRD_BOUNDS if percent < bound or bound > 1.0)
    return zone, third


def build_zone_report(
    package: InputPackage, warnings: list[AuditWarning]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    ranges_by_id = {r.range_id: r for r in package.ranges if r.range_id}
    events_by_id = {e.event_id: e for e in package.events if e.event_id}

    rows: list[dict[str, Any]] = []
    start_counts: Counter[str] = Counter()
    break_counts: Counter[str] = Counter()

    for child in package.ranges:
        if not child.parent_range_id:
            continue
        parent = ranges_by_id.get(child.parent_range_id)
        if parent is None:
            # WRONG_PARENT_LINK is already raised by the hierarchy check.
            continue
        if (
            parent.range_high_price is None
            or parent.range_low_price is None
            or parent.range_high_price <= parent.range_low_price
        ):
            warnings.append(
                AuditWarning(
                    code="ZONE_PARENT_SPAN_INVALID",
                    case_ref=child.case_ref,
                    subject_id=child.range_id,
                    message=f"parent range {parent.range_id} has no valid high/low span",
                )
            )
            continue

        low, high = parent.range_low_price, parent.range_high_price
        rh_pos = position_percent(child.range_high_price, low, high)
        rl_pos = position_percent(child.range_low_price, low, high)
        midpoint = None
        if child.range_high_price is not None and child.range_low_price is not None:
            midpoint = (child.range_high_price + child.range_low_price) / 2.0
        mid_pos = position_percent(midpoint, low, high)

        bos_pos = None
        if child.broken_by_event_id:
            event = events_by_id.get(child.broken_by_event_id)
            if event is None:
                warnings.append(
                    AuditWarning(
                        code="ZONE_BOS_EVENT_MISSING",
                        case_ref=child.case_ref,
                        subject_id=child.range_id,
                        message=f"broken_by_event_id {child.broken_by_event_id} not in package events",
                    )
                )
            else:
                bos_pos = position_percent(event.event_price, low, high)

        start_zone, start_third = classify_zone(mid_pos)
        break_zone, break_third = classify_zone(bos_pos)
        if start_zone:
            start_counts[start_zone] += 1
        if break_zone:
            break_counts[break_zone] += 1

        rows.append(
            {
                "case_ref": child.case_ref,
                "symbol": child.symbol,
                "parent_range_id": child.parent_range_id,
                "child_range_id": child.range_id,
                "structure_layer": child.structure_layer,
                "range_scope": child.range_scope,
                "rh_position_percent": rh_pos,
                "rl_position_percent": rl_pos,
                "midpoint_position_percent": mid_pos,
                "bos_position_percent": bos_pos,
                "start_zone": start_zone,
                "start_zone_third": start_third,
                "break_zone": break_zone,
                "break_zone_third": break_third,
            }
        )

    stats = {
        "children_classified": len(rows),
        "start_zone_counts": dict(start_counts),
        "break_zone_counts": dict(break_counts),
    }
    return rows, stats
