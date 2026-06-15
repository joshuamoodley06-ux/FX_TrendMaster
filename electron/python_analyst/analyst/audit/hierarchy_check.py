"""Parent/child hierarchy completeness check.

Per case: a range without a parent is an accepted root only if it sits on
the highest structure layer present in that case (Weekly root accepted
when Macro absent). Parent links pointing at unknown range ids are wrong
parent links and become audit warnings.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from analyst.audit.audit_warnings import AuditWarning
from analyst.models.records import RangeRecord

LAYER_ORDER = ["MACRO", "WEEKLY", "DAILY", "INTRADAY", "MICRO"]

HIERARCHY_COLUMNS = [
    "case_ref",
    "range_id",
    "structure_layer",
    "parent_range_id",
    "parent_found",
    "is_root",
    "root_accepted",
]


def check_hierarchy(
    ranges: list[RangeRecord],
) -> tuple[list[dict[str, Any]], list[AuditWarning]]:
    rows: list[dict[str, Any]] = []
    warnings: list[AuditWarning] = []

    by_case: dict[str, list[RangeRecord]] = defaultdict(list)
    for rng in ranges:
        by_case[rng.case_ref or ""].append(rng)

    for case_ref, case_ranges in by_case.items():
        ids = {r.range_id for r in case_ranges if r.range_id}
        layers_present = {r.structure_layer for r in case_ranges if r.structure_layer}
        top_layer = next((layer for layer in LAYER_ORDER if layer in layers_present), None)

        for rng in case_ranges:
            is_root = rng.parent_range_id is None
            parent_found = rng.parent_range_id in ids if rng.parent_range_id else None
            root_accepted = is_root and (top_layer is None or rng.structure_layer == top_layer)

            if rng.parent_range_id and not parent_found:
                warnings.append(
                    AuditWarning(
                        code="WRONG_PARENT_LINK",
                        case_ref=rng.case_ref,
                        subject_id=rng.range_id,
                        message=f"parent_range_id {rng.parent_range_id} not found in package",
                    )
                )
            if is_root and not root_accepted:
                warnings.append(
                    AuditWarning(
                        code="UNEXPECTED_ROOT_LAYER",
                        case_ref=rng.case_ref,
                        subject_id=rng.range_id,
                        message=(
                            f"rootless range on layer {rng.structure_layer} while "
                            f"higher layer {top_layer} exists in case"
                        ),
                    )
                )

            rows.append(
                {
                    "case_ref": rng.case_ref or "",
                    "range_id": rng.range_id or "",
                    "structure_layer": rng.structure_layer or "",
                    "parent_range_id": rng.parent_range_id or "",
                    "parent_found": "" if parent_found is None else str(bool(parent_found)).lower(),
                    "is_root": str(is_root).lower(),
                    "root_accepted": str(bool(root_accepted)).lower(),
                }
            )
    return rows, warnings
