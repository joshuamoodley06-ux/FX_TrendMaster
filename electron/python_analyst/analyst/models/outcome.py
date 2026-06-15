"""Full outcome classifier (spec section: Outcome Classification).

Classifies every BOS pair (broken range -> new range) using saved-range
facts plus the abandon model's candle rule. Neutral mechanical labels,
applied in precedence order:

    ABANDONED    - new range status ABANDONED, or abandon model detected a
                   close beyond the new range's opposite extreme
    CONTINUED    - new range breaks in the BOS direction
    FAILED       - new range breaks opposite to the BOS direction
    PARENT_BOS   - new range unbroken, but its parent broke in the
                   sequence direction (child sequence contributed to the
                   parent break)
    OPPOSITE_BOS - new range unbroken, but its parent broke against the
                   sequence direction
    UNRESOLVED   - nothing decisive yet (or no new range resolvable)
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from analyst.models.common import broken_pairs
from analyst.models.records import InputPackage, RangeRecord

OUTCOMES = ("CONTINUED", "FAILED", "ABANDONED", "UNRESOLVED", "OPPOSITE_BOS", "PARENT_BOS")

_PRICE_ABANDON_REASONS = {"PRICE_BROKE_NEW_RANGE_LOW", "PRICE_BROKE_NEW_RANGE_HIGH"}


def classify_pair_outcome(
    new_range: RangeRecord | None,
    bos_direction: str,
    parent_range: RangeRecord | None = None,
    price_abandoned: bool = False,
) -> str:
    if new_range is None:
        return "UNRESOLVED"
    if new_range.status == "ABANDONED" or price_abandoned:
        return "ABANDONED"
    if new_range.direction_of_break == bos_direction:
        return "CONTINUED"
    if new_range.direction_of_break in ("UP", "DOWN"):
        return "FAILED"
    if (
        parent_range is not None
        and parent_range.status == "BROKEN"
        and parent_range.direction_of_break in ("UP", "DOWN")
    ):
        return "PARENT_BOS" if parent_range.direction_of_break == bos_direction else "OPPOSITE_BOS"
    return "UNRESOLVED"


def build_outcome_summary(
    package: InputPackage, abandon_rows: list[dict[str, Any]]
) -> tuple[dict[str, str], dict[str, Any]]:
    """Returns ({new_range_id: outcome}, stats) over all BOS pairs."""
    price_abandoned_ids = {
        row["new_range_id"]
        for row in abandon_rows
        if row.get("abandoned") is True and row.get("abandon_reason") in _PRICE_ABANDON_REASONS
    }
    ranges_by_id = {r.range_id: r for r in package.ranges if r.range_id}

    outcome_by_new_range_id: dict[str, str] = {}
    counts: Counter[str] = Counter()
    for old_range, new_range in broken_pairs(package):
        parent = (
            ranges_by_id.get(new_range.parent_range_id)
            if new_range and new_range.parent_range_id
            else None
        )
        outcome = classify_pair_outcome(
            new_range,
            old_range.direction_of_break,
            parent_range=parent,
            price_abandoned=bool(new_range and new_range.range_id in price_abandoned_ids),
        )
        counts[outcome] += 1
        if new_range and new_range.range_id:
            outcome_by_new_range_id[new_range.range_id] = outcome

    stats = {"pairs": sum(counts.values()), "counts": dict(counts)}
    return outcome_by_new_range_id, stats
