"""Parent-child summary.

One row per parent range that has children inside the package: how many
children formed, their layers, and their factual break/abandon states.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from analyst.models.records import InputPackage, RangeRecord

PARENT_CHILD_REPORT_FILE = "parent_child_summary.csv"

PARENT_CHILD_COLUMNS = [
    "case_ref", "parent_range_id", "parent_layer", "parent_status",
    "child_count", "child_layers",
    "children_broken_up", "children_broken_down",
    "children_abandoned", "children_active",
]


def build_parent_child_report(
    package: InputPackage,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    ranges_by_id = {r.range_id: r for r in package.ranges if r.range_id}

    children_by_parent: dict[str, list[RangeRecord]] = defaultdict(list)
    orphan_children = 0
    for rng in package.ranges:
        if not rng.parent_range_id:
            continue
        if rng.parent_range_id in ranges_by_id:
            children_by_parent[rng.parent_range_id].append(rng)
        else:
            orphan_children += 1

    rows: list[dict[str, Any]] = []
    for parent_id, children in sorted(children_by_parent.items()):
        parent = ranges_by_id[parent_id]
        layers = sorted({c.structure_layer for c in children if c.structure_layer})
        rows.append(
            {
                "case_ref": parent.case_ref,
                "parent_range_id": parent_id,
                "parent_layer": parent.structure_layer,
                "parent_scope": parent.range_scope,
                "parent_status": parent.status,
                "child_count": len(children),
                "child_layers": "|".join(layers),
                "children_broken_up": sum(
                    1 for c in children if c.status == "BROKEN" and c.direction_of_break == "UP"
                ),
                "children_broken_down": sum(
                    1 for c in children if c.status == "BROKEN" and c.direction_of_break == "DOWN"
                ),
                "children_abandoned": sum(1 for c in children if c.status == "ABANDONED"),
                "children_active": sum(1 for c in children if c.status == "ACTIVE"),
            }
        )

    child_counts = [row["child_count"] for row in rows]
    stats = {
        "parents_with_children": len(rows),
        "total_children": sum(child_counts),
        "avg_children_per_parent": round(sum(child_counts) / len(child_counts), 6)
        if child_counts
        else None,
        "max_children_per_parent": max(child_counts) if child_counts else None,
        "orphan_children": orphan_children,
    }
    return rows, stats
