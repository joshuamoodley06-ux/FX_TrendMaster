"""Row filters and cross-report joins for the query engine."""

from __future__ import annotations

import pandas as pd


def norm_id(value) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    return text or None


def zone_matches(cell_value: str | None, filter_zone: str | None) -> bool:
    if filter_zone is None:
        return True
    if cell_value is None or (isinstance(cell_value, float) and pd.isna(cell_value)):
        return False
    text = str(cell_value).strip().upper()
    zone = filter_zone.upper()
    return text == zone or text.startswith(zone + "_")


def apply_case_ref_filter(df: pd.DataFrame, case_refs: list[str]) -> pd.DataFrame:
    if not case_refs or "case_ref" not in df.columns:
        return df
    allowed = set(case_refs)
    return df[df["case_ref"].isin(allowed)]


def attach_parent_layer(
    df: pd.DataFrame,
    ranges_df: pd.DataFrame,
    parent_id_col: str = "parent_range_id",
) -> pd.DataFrame:
    if df.empty or ranges_df.empty:
        df = df.copy()
        df["parent_layer"] = None
        return df

    ranges = ranges_df.copy()
    ranges["range_id_str"] = ranges["range_id"].map(norm_id)
    ranges["parent_layer"] = ranges["structure_layer"]
    parent_map = ranges.set_index("range_id_str")["parent_layer"].to_dict()

    out = df.copy()
    out["parent_layer"] = out[parent_id_col].map(lambda v: parent_map.get(norm_id(v)))
    return out


def attach_outcome_from_retracement(
    df: pd.DataFrame,
    retracement_df: pd.DataFrame,
    range_id_col: str = "range_id",
) -> pd.DataFrame:
    if df.empty:
        df = df.copy()
        df["outcome"] = None
        return df
    if retracement_df.empty or "outcome" not in retracement_df.columns:
        out = df.copy()
        out["outcome"] = None
        return out

    retr = retracement_df.copy()
    retr["range_id_str"] = retr["range_id"].map(norm_id)
    outcome_map = retr.set_index("range_id_str")["outcome"].to_dict()

    out = df.copy()
    out["outcome"] = out[range_id_col].map(lambda v: outcome_map.get(norm_id(v)))
    return out


def apply_query_filters(df: pd.DataFrame, query: dict) -> pd.DataFrame:
    if df.empty:
        return df

    out = df

    if query.get("child_layer") and "structure_layer" in out.columns:
        layer = query["child_layer"]
        out = out[out["structure_layer"].astype(str).str.upper() == layer]
    if query.get("child_layer") and "layer" in out.columns and "structure_layer" not in out.columns:
        out = out[out["layer"].astype(str).str.upper() == query["child_layer"]]

    if query.get("range_scope"):
        scope = str(query["range_scope"]).upper()
        for col in ("range_scope",):
            if col in out.columns:
                out = out[out[col].astype(str).str.upper() == scope]
                break

    if query.get("parent_layer") and "parent_layer" in out.columns:
        out = out[out["parent_layer"].astype(str).str.upper() == query["parent_layer"]]

    if query.get("bos_direction"):
        col = None
        for candidate in ("bos_direction", "direction_of_break"):
            if candidate in out.columns:
                col = candidate
                break
        if col:
            out = out[out[col].astype(str).str.upper() == query["bos_direction"]]

    if query.get("reclaim_class") and "reclaim_class" in out.columns:
        out = out[out["reclaim_class"].astype(str).str.upper() == query["reclaim_class"]]

    if query.get("retracement_class") and "retracement_class" in out.columns:
        out = out[out["retracement_class"].astype(str).str.upper() == query["retracement_class"]]

    if query.get("outcome") and "outcome" in out.columns:
        out = out[out["outcome"].astype(str).str.upper() == query["outcome"]]

    if query.get("impulse_index") is not None and "impulse_index" in out.columns:
        out = out[out["impulse_index"] == query["impulse_index"]]

    if query.get("parent_zone"):
        zone_col = "break_zone" if "break_zone" in out.columns else "start_zone"
        if zone_col in out.columns:
            out = out[out[zone_col].apply(lambda v: zone_matches(v, query["parent_zone"]))]

    if query.get("child_zone") and "start_zone" in out.columns:
        out = out[out["start_zone"].apply(lambda v: zone_matches(v, query["child_zone"]))]

    if query.get("break_zone") and "break_zone" in out.columns:
        out = out[out["break_zone"].apply(lambda v: zone_matches(v, query["break_zone"]))]

    return out


def filters_applied_dict(query: dict) -> dict[str, str | int | list | None]:
    keys = (
        "parent_layer",
        "child_layer",
        "range_scope",
        "bos_direction",
        "parent_zone",
        "child_zone",
        "break_zone",
        "reclaim_class",
        "retracement_class",
        "outcome",
        "impulse_index",
    )
    out = {k: query.get(k) for k in keys if query.get(k) is not None}
    years = query.get("years")
    if isinstance(years, list) and years:
        out["years"] = years
    labels = query.get("year_labels")
    if isinstance(labels, list) and labels:
        out["year_labels"] = labels
    return out
