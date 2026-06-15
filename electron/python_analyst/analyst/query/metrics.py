"""Aggregate metrics for mediator queries."""

from __future__ import annotations

from typing import Any

import pandas as pd

OUTCOME_CONTINUED = "CONTINUED"
OUTCOME_FAILED = "FAILED"
OUTCOME_ABANDONED = "ABANDONED"
OUTCOME_UNRESOLVED = "UNRESOLVED"

SAMPLE_SIZE_SMALL = 20
SAMPLE_SIZE_MODERATE = 50


def outcome_counts(df: pd.DataFrame, outcome_col: str = "outcome") -> dict[str, int]:
    if df.empty or outcome_col not in df.columns:
        return {
            "continued_count": 0,
            "failed_count": 0,
            "abandoned_count": 0,
            "unresolved_count": 0,
        }
    series = df[outcome_col].astype(str).str.upper()
    return {
        "continued_count": int((series == OUTCOME_CONTINUED).sum()),
        "failed_count": int((series == OUTCOME_FAILED).sum()),
        "abandoned_count": int((series == OUTCOME_ABANDONED).sum()),
        "unresolved_count": int((series == OUTCOME_UNRESOLVED).sum()),
    }


def compute_rates(counts: dict[str, int]) -> dict[str, float | None]:
    continued = counts["continued_count"]
    failed = counts["failed_count"]
    abandoned = counts["abandoned_count"]
    resolved = continued + failed + abandoned
    if resolved == 0:
        return {
            "continuation_rate": None,
            "failure_rate": None,
            "abandon_rate": None,
        }
    return {
        "continuation_rate": round(continued / resolved, 6),
        "failure_rate": round(failed / resolved, 6),
        "abandon_rate": round(abandoned / resolved, 6),
    }


def compute_retracement_stats(df: pd.DataFrame) -> dict[str, float | None]:
    if df.empty or "retracement_percent" not in df.columns:
        return {"average_retracement": None, "median_retracement": None}
    series = pd.to_numeric(df["retracement_percent"], errors="coerce").dropna()
    if series.empty:
        return {"average_retracement": None, "median_retracement": None}
    return {
        "average_retracement": round(float(series.mean()), 6),
        "median_retracement": round(float(series.median()), 6),
    }


def compute_rotation_stats(df: pd.DataFrame) -> dict[str, float | None]:
    if df.empty or "rotations_count" not in df.columns:
        return {"average_rotations": None, "median_rotations": None}
    series = pd.to_numeric(df["rotations_count"], errors="coerce").dropna()
    if series.empty:
        return {"average_rotations": None, "median_rotations": None}
    return {
        "average_rotations": round(float(series.mean()), 6),
        "median_rotations": round(float(series.median()), 6),
    }


def compute_reclaim_rate(df: pd.DataFrame) -> dict[str, float | None]:
    if df.empty or "reclaim_occurred" not in df.columns:
        return {"reclaim_rate": None}
    col = df["reclaim_occurred"]
    bool_series = col.map(_to_bool)
    valid = bool_series.dropna()
    if valid.empty:
        return {"reclaim_rate": None}
    return {"reclaim_rate": round(float(valid.mean()), 6)}


def _to_bool(value: Any) -> bool | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("true", "1", "yes"):
        return True
    if text in ("false", "0", "no"):
        return False
    return None


def compute_metrics(df: pd.DataFrame, metrics: list[str], outcome_col: str = "outcome") -> dict[str, Any]:
    result: dict[str, Any] = {}
    counts = outcome_counts(df, outcome_col)
    rates = compute_rates(counts)
    retr = compute_retracement_stats(df)
    rot = compute_rotation_stats(df)
    reclaim = compute_reclaim_rate(df)

    sample_size = len(df)
    pool = {
        "sample_size": sample_size,
        **counts,
        **rates,
        **retr,
        **rot,
        **reclaim,
    }

    for name in metrics:
        if name in pool:
            result[name] = pool[name]

    return result


def compute_grouped_metrics(
    df: pd.DataFrame,
    group_by: list[str],
    metrics: list[str],
    outcome_col: str = "outcome",
) -> list[dict[str, Any]]:
    if df.empty or not group_by:
        return []

    rows: list[dict[str, Any]] = []
    for keys, group in df.groupby(group_by, dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        entry = {col: keys[i] for i, col in enumerate(group_by)}
        entry.update(compute_metrics(group, metrics, outcome_col))
        rows.append(entry)
    return rows


def sample_size_warnings(sample_size: int) -> list[str]:
    if sample_size == 0:
        return ["NO_MATCHING_ROWS"]
    if sample_size < SAMPLE_SIZE_SMALL:
        return [f"SAMPLE_SIZE_SMALL: {sample_size} rows — too small to trust"]
    if sample_size < SAMPLE_SIZE_MODERATE:
        return [f"SAMPLE_SIZE_MODERATE: {sample_size} rows — interpret with caution"]
    return []
