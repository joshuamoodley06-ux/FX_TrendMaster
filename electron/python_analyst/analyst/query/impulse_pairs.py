"""Join impulse-1 → retrace → impulse-2 chains with range high/low facts."""

from __future__ import annotations

from typing import Any

import pandas as pd

from analyst.query.filters import apply_case_ref_filter, norm_id


def _range_lookup(ranges_df: pd.DataFrame) -> dict[str, dict[str, Any]]:
    if ranges_df.empty:
        return {}
    lookup: dict[str, dict[str, Any]] = {}
    for _, row in ranges_df.iterrows():
        rid = norm_id(row.get("range_id"))
        if rid:
            lookup[rid] = row.to_dict()
    return lookup


def build_impulse_pair_audit_df(
    sequence_df: pd.DataFrame,
    ranges_df: pd.DataFrame,
    retracement_df: pd.DataFrame,
    query: dict[str, Any],
) -> pd.DataFrame:
    """Rows where impulse 1 and impulse 2 share direction (e.g. BOS UP → retrace → BOS UP)."""
    if sequence_df.empty:
        return pd.DataFrame()

    seq = sequence_df.copy()
    direction = (query.get("bos_direction") or "UP").upper()

    if "sequence_direction" in seq.columns:
        seq = seq[seq["sequence_direction"].astype(str).str.upper() == direction]
    if query.get("child_layer") and "layer" in seq.columns:
        seq = seq[seq["layer"].astype(str).str.upper() == query["child_layer"]]
    if query.get("structure_layer") and "layer" in seq.columns:
        seq = seq[seq["layer"].astype(str).str.upper() == query["structure_layer"]]

    seq = apply_case_ref_filter(seq, query["case_refs"])

    imp2 = seq[seq["impulse_index"] == 2].copy()
    if imp2.empty:
        return pd.DataFrame()

    imp1 = seq[seq["impulse_index"] == 1].copy()
    if imp1.empty:
        return pd.DataFrame()

    ranges = _range_lookup(ranges_df)
    retr_lookup: dict[str, dict[str, Any]] = {}
    if not retracement_df.empty:
        for _, row in retracement_df.iterrows():
            rid = norm_id(row.get("range_id"))
            if rid:
                retr_lookup[rid] = row.to_dict()

    imp1_key_cols = ["case_ref", "parent_range_id", "layer"]
    imp1_groups: dict[tuple, pd.Series] = {}
    for _, row in imp1.iterrows():
        key = tuple(norm_id(row[c]) for c in imp1_key_cols)
        imp1_groups[key] = row

    rows: list[dict[str, Any]] = []
    for _, imp2_row in imp2.iterrows():
        key = tuple(norm_id(imp2_row[c]) for c in imp1_key_cols)
        imp1_row = imp1_groups.get(key)
        if imp1_row is None:
            continue

        first_range_id = norm_id(imp1_row.get("child_range_id"))
        impulse_range_id = norm_id(imp2_row.get("child_range_id"))
        if not first_range_id or not impulse_range_id:
            continue

        first_rng = ranges.get(first_range_id, {})
        expected_new = norm_id(first_rng.get("new_range_id"))
        if expected_new and expected_new != impulse_range_id:
            # Allow old_range_id backlink when new_range_id missing on broken range
            impulse_rng = ranges.get(impulse_range_id, {})
            if norm_id(impulse_rng.get("old_range_id")) != first_range_id:
                continue
        elif not expected_new:
            impulse_rng = ranges.get(impulse_range_id, {})
            if norm_id(impulse_rng.get("old_range_id")) != first_range_id:
                continue

        impulse_rng = ranges.get(impulse_range_id, {})
        retr = retr_lookup.get(impulse_range_id, {})

        rows.append(
            {
                "case_ref": imp2_row.get("case_ref"),
                "parent_range_id": imp2_row.get("parent_range_id"),
                "layer": imp2_row.get("layer"),
                "year_label": impulse_rng.get("year_label") or first_rng.get("year_label"),
                "sequence_direction": direction,
                "first_range_id": first_range_id,
                "first_range_high": first_rng.get("range_high_price"),
                "first_range_low": first_rng.get("range_low_price"),
                "bos_1_event_id": imp1_row.get("bos_event_id"),
                "impulse_range_id": impulse_range_id,
                "impulse_range_high": impulse_rng.get("range_high_price"),
                "impulse_range_low": impulse_rng.get("range_low_price"),
                "retracement_percent": retr.get("retracement_percent"),
                "retracement_class": retr.get("retracement_class"),
                "retracement_price": retr.get("retracement_price"),
                "retracement_time": retr.get("retracement_time"),
                "bos_2_event_id": imp2_row.get("bos_event_id"),
                "reclaim_after_bos_1": imp1_row.get("reclaim_detected"),
                "outcome_after_bos_2": imp2_row.get("next_outcome"),
            }
        )

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    if query.get("retracement_class") and "retracement_class" in df.columns:
        df = df[df["retracement_class"].astype(str).str.upper() == query["retracement_class"]]

    limit = int(query.get("row_limit") or 50)
    seed = query.get("random_seed") or 42
    if query.get("random_sample") and len(df) > limit:
        df = df.sample(n=limit, random_state=seed)
    else:
        df = df.head(limit)

    return df
