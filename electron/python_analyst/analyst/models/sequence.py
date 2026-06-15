"""Impulse / Retest sequence model (spec section: Impulse / Retest Sequence).

Neutral mechanical labels only — no P1/P2/P3 strategy terms stored.

Per parent range and structure layer, broken child ranges are ordered by
break time and walked into directional runs:

    first BOS in a new direction        -> impulse_1 (new sequence)
    next BOS in the same direction      -> impulse_2, impulse_3, ...
    pullback/reclaim after impulse_k    -> retest_k (retest_index set when
                                           a pullback was measurable by the
                                           retracement model or a reclaim
                                           was detected)

One row per impulse. child_range_id is the broken range whose break IS
the impulse. reclaim_detected / retracement_class / next_outcome come
from the reclaim, retracement and outcome models for that BOS pair.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from analyst.models.common import find_new_range
from analyst.models.records import InputPackage, RangeRecord

SEQUENCE_REPORT_FILE = "impulse_retest_sequence.csv"


def build_sequence_report(
    package: InputPackage,
    reclaim_rows: list[dict[str, Any]],
    retracement_rows: list[dict[str, Any]],
    outcome_by_new_range_id: dict[str, str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    ranges_by_id = {r.range_id: r for r in package.ranges if r.range_id}
    reclaim_by_range_id = {row["range_id"]: row for row in reclaim_rows}
    retracement_by_range_id = {row["range_id"]: row for row in retracement_rows}

    chains: dict[tuple[str, str], list[RangeRecord]] = defaultdict(list)
    for rng in package.ranges:
        if (
            rng.status == "BROKEN"
            and rng.direction_of_break in ("UP", "DOWN")
            and rng.parent_range_id
            and rng.parent_range_id in ranges_by_id
        ):
            chains[(rng.parent_range_id, rng.structure_layer or "UNKNOWN")].append(rng)

    rows: list[dict[str, Any]] = []
    direction_counts: Counter[str] = Counter()
    max_impulse_index = 0

    for (parent_id, layer), broken_children in sorted(chains.items()):
        broken_children.sort(key=_break_time_key)
        sequence_direction: str | None = None
        impulse_index = 0

        for child in broken_children:
            direction = child.direction_of_break
            if direction != sequence_direction:
                sequence_direction = direction
                impulse_index = 1
            else:
                impulse_index += 1
            max_impulse_index = max(max_impulse_index, impulse_index)
            direction_counts[direction] += 1

            new_range = find_new_range(child, ranges_by_id, package.ranges)
            new_range_id = new_range.range_id if new_range else None

            reclaim_row = reclaim_by_range_id.get(child.range_id)
            reclaim_detected = reclaim_row.get("reclaim_occurred") if reclaim_row else None

            retracement_row = retracement_by_range_id.get(new_range_id) if new_range_id else None
            retracement_class = (
                retracement_row.get("retracement_class") if retracement_row else None
            )

            retest_measured = bool(retracement_class) or reclaim_detected is True
            next_outcome = (
                outcome_by_new_range_id.get(new_range_id, "UNRESOLVED")
                if new_range_id
                else "UNRESOLVED"
            )

            rows.append(
                {
                    "case_ref": child.case_ref,
                    "parent_range_id": parent_id,
                    "child_range_id": child.range_id,
                    "layer": layer,
                    "range_scope": child.range_scope,
                    "sequence_direction": sequence_direction,
                    "impulse_index": impulse_index,
                    "retest_index": impulse_index if retest_measured else None,
                    "bos_event_id": child.broken_by_event_id,
                    "reclaim_detected": reclaim_detected,
                    "retracement_class": retracement_class,
                    "next_outcome": next_outcome,
                }
            )

    stats = {
        "chains": len(chains),
        "impulses": len(rows),
        "max_impulse_index": max_impulse_index or None,
        "direction_counts": dict(direction_counts),
        "retests_measured": sum(1 for row in rows if row["retest_index"] is not None),
    }
    return rows, stats


def _break_time_key(rng: RangeRecord) -> int:
    if rng.inactive_from_time_ms is not None:
        return rng.inactive_from_time_ms
    if rng.active_from_time_ms is not None:
        return rng.active_from_time_ms
    return 0
