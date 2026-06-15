"""BOS direction statistics.

Counts factual break directions per (case_ref, structure_layer) from two
sources kept side by side:
- ranges: status BROKEN + direction_of_break
- events: BOS-typed events (BOS / MANUAL_BOS / AUTO_BOS) + direction
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from analyst.models.records import InputPackage

BOS_DIRECTION_REPORT_FILE = "bos_direction_stats.csv"

BOS_DIRECTION_COLUMNS = [
    "case_ref", "structure_layer",
    "range_bos_up", "range_bos_down",
    "event_bos_up", "event_bos_down",
]


def is_bos_event_type(event_type: str | None) -> bool:
    return bool(event_type) and "BOS" in event_type


def build_bos_direction_report(
    package: InputPackage,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    counts: dict[tuple[str, str], dict[str, int]] = defaultdict(
        lambda: {"range_bos_up": 0, "range_bos_down": 0, "event_bos_up": 0, "event_bos_down": 0}
    )

    for rng in package.ranges:
        if rng.status != "BROKEN" or rng.direction_of_break not in ("UP", "DOWN"):
            continue
        key = (rng.case_ref or "", rng.structure_layer or "UNKNOWN")
        counts[key]["range_bos_up" if rng.direction_of_break == "UP" else "range_bos_down"] += 1

    for event in package.events:
        if not is_bos_event_type(event.event_type) or event.direction not in ("UP", "DOWN"):
            continue
        key = (event.case_ref or "", event.structure_layer or "UNKNOWN")
        counts[key]["event_bos_up" if event.direction == "UP" else "event_bos_down"] += 1

    rows = [
        {"case_ref": case_ref, "structure_layer": layer, **values}
        for (case_ref, layer), values in sorted(counts.items())
    ]

    totals = {"range_bos_up": 0, "range_bos_down": 0, "event_bos_up": 0, "event_bos_down": 0}
    by_layer: dict[str, dict[str, int]] = defaultdict(
        lambda: {"range_bos_up": 0, "range_bos_down": 0, "event_bos_up": 0, "event_bos_down": 0}
    )
    for row in rows:
        for field in totals:
            totals[field] += row[field]
            by_layer[row["structure_layer"]][field] += row[field]

    stats = {"totals": totals, "by_layer": {k: dict(v) for k, v in sorted(by_layer.items())}}
    return rows, stats
