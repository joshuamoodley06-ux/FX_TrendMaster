"""Range duration / size metrics.

Factual per-range measurements: anchor span, lifecycle span, price span,
and child size relative to parent size. No interpretation.
"""

from __future__ import annotations

from collections import defaultdict
from statistics import mean, median
from typing import Any

from analyst.models.derived_fields import DerivedRangeFields
from analyst.models.records import InputPackage

RANGE_METRICS_REPORT_FILE = "range_duration_size.csv"

RANGE_METRICS_COLUMNS = [
    "case_ref", "symbol", "range_id", "structure_layer", "range_scope", "status",
    "anchor_start_ms", "anchor_end_ms", "anchor_span_ms",
    "lifecycle_start_ms", "lifecycle_end_ms", "lifecycle_span_ms",
    "price_span", "price_span_percent_of_parent",
]


def build_range_metrics_report(
    package: InputPackage, derived: dict[str | None, DerivedRangeFields]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    ranges_by_id = {r.range_id: r for r in package.ranges if r.range_id}

    rows: list[dict[str, Any]] = []
    by_layer: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: {"lifecycle_spans": [], "price_spans": []}
    )

    for rng in package.ranges:
        der = derived.get(rng.range_id)
        anchor_span = _span(der.anchor_start_ms if der else None, der.anchor_end_ms if der else None)
        lifecycle_span = _span(
            der.lifecycle_start_ms if der else None, der.lifecycle_end_ms if der else None
        )
        price_span = der.price_span if der else None

        parent_percent = None
        parent = ranges_by_id.get(rng.parent_range_id) if rng.parent_range_id else None
        if parent is not None and price_span is not None:
            parent_der = derived.get(parent.range_id)
            parent_span = parent_der.price_span if parent_der else None
            if parent_span:
                parent_percent = round(price_span / parent_span, 6)

        layer = rng.structure_layer or "UNKNOWN"
        if lifecycle_span is not None:
            by_layer[layer]["lifecycle_spans"].append(lifecycle_span)
        if price_span is not None:
            by_layer[layer]["price_spans"].append(price_span)

        rows.append(
            {
                "case_ref": rng.case_ref,
                "symbol": rng.symbol,
                "range_id": rng.range_id,
                "structure_layer": rng.structure_layer,
                "range_scope": rng.range_scope,
                "status": rng.status,
                "anchor_start_ms": der.anchor_start_ms if der else None,
                "anchor_end_ms": der.anchor_end_ms if der else None,
                "anchor_span_ms": anchor_span,
                "lifecycle_start_ms": der.lifecycle_start_ms if der else None,
                "lifecycle_end_ms": der.lifecycle_end_ms if der else None,
                "lifecycle_span_ms": lifecycle_span,
                "price_span": price_span,
                "price_span_percent_of_parent": parent_percent,
            }
        )

    stats = {
        "ranges": len(rows),
        "by_layer": {
            layer: {
                "count": sum(1 for r in rows if (r["structure_layer"] or "UNKNOWN") == layer),
                "avg_lifecycle_span_ms": _avg(values["lifecycle_spans"]),
                "median_lifecycle_span_ms": _med(values["lifecycle_spans"]),
                "avg_price_span": _avg(values["price_spans"]),
                "median_price_span": _med(values["price_spans"]),
            }
            for layer, values in sorted(by_layer.items())
        },
    }
    return rows, stats


def _span(start: int | None, end: int | None) -> int | None:
    if start is None or end is None:
        return None
    return end - start


def _avg(values: list[float]) -> float | None:
    return round(mean(values), 6) if values else None


def _med(values: list[float]) -> float | None:
    return round(median(values), 6) if values else None
