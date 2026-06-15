"""Question-type routing: primary report + join plan."""

from __future__ import annotations

from typing import Any

import pandas as pd

from analyst.query.filters import (
    apply_case_ref_filter,
    apply_query_filters,
    attach_outcome_from_retracement,
    attach_parent_layer,
)
from analyst.query.impulse_pairs import build_impulse_pair_audit_df
from analyst.query.loaders import (
    load_multi_ranges,
    load_multi_report,
    load_yearly_stats_list,
)

RETRACEMENT_FILE = "retracement_stats.csv"
RECLAIM_FILE = "bos_reclaim_report.csv"
ZONE_FILE = "range_zone_position.csv"
ROTATION_FILE = "extreme_rotation_report.csv"
SEQUENCE_FILE = "impulse_retest_sequence.csv"


def build_dataset(
    query: dict[str, Any],
    batch_dirs: list,
    symbol: str,
) -> tuple[pd.DataFrame, list[str], list[str], str]:
    """Return filtered dataframe, warnings, data_sources, outcome_col."""
    qtype = query["question_type"]
    if qtype == "year_comparison":
        return pd.DataFrame(), [], [], "outcome"

    warnings: list[str] = []
    sources: list[str] = []

    ranges_df, range_warnings, range_sources = load_multi_ranges(batch_dirs, symbol)
    warnings.extend(range_warnings)
    sources.extend(range_sources)

    if qtype == "range_list":
        df = ranges_df.copy()
        layer = query.get("structure_layer") or query.get("parent_layer") or query.get("child_layer")
        if layer and "structure_layer" in df.columns:
            df = df[df["structure_layer"].astype(str).str.upper() == layer]
        df = apply_case_ref_filter(df, query["case_refs"])
        limit = int(query.get("row_limit") or 50)
        seed = query.get("random_seed") or 42
        if query.get("random_sample") and len(df) > limit:
            df = df.sample(n=limit, random_state=seed)
        else:
            df = df.head(limit)
        return df, warnings, sources, "outcome"

    retracement_df, retr_warnings, retr_sources = load_multi_report(
        batch_dirs, RETRACEMENT_FILE, symbol
    )
    warnings.extend(retr_warnings)
    sources.extend(retr_sources)

    if qtype == "impulse_pair_audit":
        seq_df, seq_warnings, seq_sources = load_multi_report(
            batch_dirs, SEQUENCE_FILE, symbol
        )
        warnings.extend(seq_warnings)
        sources.extend(seq_sources)
        df = build_impulse_pair_audit_df(seq_df, ranges_df, retracement_df, query)
        return df, warnings, sources, "outcome_after_bos_2"

    if qtype == "continuation_rate":
        df = retracement_df
        if query.get("child_layer") and "structure_layer" in df.columns:
            df = df.copy()
        df = attach_parent_layer(df, ranges_df, "parent_range_id")
        df = apply_case_ref_filter(df, query["case_refs"])
        df = apply_query_filters(df, query)
        return df, warnings, sources, "outcome"

    if qtype in ("reclaim_compare", "continuation_reclaim_zone"):
        reclaim_df, reclaim_warnings, reclaim_sources = load_multi_report(
            batch_dirs, RECLAIM_FILE, symbol
        )
        warnings.extend(reclaim_warnings)
        sources.extend(reclaim_sources)
        df = reclaim_df
        df = attach_outcome_from_retracement(df, retracement_df, "range_id")

        if qtype == "continuation_reclaim_zone":
            zone_df, zone_warnings, zone_sources = load_multi_report(
                batch_dirs, ZONE_FILE, symbol
            )
            warnings.extend(zone_warnings)
            sources.extend(zone_sources)
            if not zone_df.empty and not df.empty:
                zone_df = zone_df.copy()
                zone_df["child_range_id_str"] = zone_df["child_range_id"].astype(str)
                df = df.copy()
                df["range_id_str"] = df["range_id"].astype(str)
                zone_subset = zone_df[
                    ["child_range_id_str", "structure_layer", "break_zone", "start_zone", "parent_range_id"]
                ].drop_duplicates(subset=["child_range_id_str"])
                df = df.merge(
                    zone_subset,
                    left_on="range_id_str",
                    right_on="child_range_id_str",
                    how="left",
                    suffixes=("", "_zone"),
                )
                if "structure_layer" in df.columns:
                    df["structure_layer"] = df["structure_layer"].fillna(df.get("structure_layer_zone"))
                df = attach_parent_layer(df, ranges_df, "parent_range_id")

        df = apply_case_ref_filter(df, query["case_refs"])
        df = apply_query_filters(df, query)
        return df, warnings, sources, "outcome"

    if qtype == "zone_continuation":
        zone_df, zone_warnings, zone_sources = load_multi_report(batch_dirs, ZONE_FILE, symbol)
        warnings.extend(zone_warnings)
        sources.extend(zone_sources)
        df = zone_df
        df = attach_parent_layer(df, ranges_df, "parent_range_id")
        df = attach_outcome_from_retracement(
            df, retracement_df, "child_range_id"
        )
        df = apply_case_ref_filter(df, query["case_refs"])
        df = apply_query_filters(df, query)
        return df, warnings, sources, "outcome"

    if qtype == "rotation":
        rot_df, rot_warnings, rot_sources = load_multi_report(batch_dirs, ROTATION_FILE, symbol)
        warnings.extend(rot_warnings)
        sources.extend(rot_sources)
        df = rot_df
        if query.get("parent_layer") and "parent_layer" in df.columns:
            df = df[df["parent_layer"].astype(str).str.upper() == query["parent_layer"]]
        if query.get("child_layer") and "child_layer" in df.columns:
            df = df[df["child_layer"].astype(str).str.upper() == query["child_layer"]]
        df = apply_case_ref_filter(df, query["case_refs"])
        return df, warnings, sources, "outcome"

    if qtype == "sequence":
        seq_df, seq_warnings, seq_sources = load_multi_report(batch_dirs, SEQUENCE_FILE, symbol)
        warnings.extend(seq_warnings)
        sources.extend(seq_sources)
        df = seq_df
        if "next_outcome" in df.columns:
            df = df.copy()
            df["outcome"] = df["next_outcome"]
        df = attach_parent_layer(df, ranges_df, "parent_range_id")
        df = apply_case_ref_filter(df, query["case_refs"])
        df = apply_query_filters(df, query)
        return df, warnings, sources, "outcome"

    # fallback
    df = retracement_df
    df = apply_case_ref_filter(df, query["case_refs"])
    df = apply_query_filters(df, query)
    return df, warnings, sources, "outcome"


def build_year_comparison(
    query: dict[str, Any],
    batch_dirs: list,
) -> tuple[dict[str, Any], list[str], list[str]]:
    warnings: list[str] = []
    sources: list[str] = []
    yearly = load_yearly_stats_list(batch_dirs)
    for batch_dir in batch_dirs:
        sources.append(f"{query['symbol']}/{batch_dir.name}/yearly_stats.json")

    rows: list[dict[str, Any]] = []
    for stats in yearly:
        counts = stats.get("counts", {})
        rule_stats = stats.get("rule_stats", {})
        retr = rule_stats.get("retracement", {}) or {}
        reclaim = rule_stats.get("bos_reclaim", {}) or {}
        rotation = rule_stats.get("rotation", {}) or {}
        rows.append(
            {
                "year": stats.get("year"),
                "year_label": stats.get("year_label") or stats.get("label"),
                "label": stats.get("label"),
                "ranges": counts.get("ranges"),
                "retracement_sequences": retr.get("sequences"),
                "retracement_class_counts": retr.get("class_counts"),
                "reclaim_bos_count": reclaim.get("bos_count"),
                "rotation_parents": rotation.get("parents"),
                "rotations_total": rotation.get("rotations"),
            }
        )

    metrics = {
        "sample_size": len(rows),
        "year_rows": rows,
    }
    return metrics, warnings, sources
