"""Load saved workspace reports and parquet for query execution."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from analyst.storage.batches import list_symbol_batch_dirs, read_yearly_stats
from analyst.storage.workspace import RULE_REPORT_COLUMNS

REPORT_FILES = dict(RULE_REPORT_COLUMNS)


def resolve_batch_dirs(
    workspace_root: str | Path,
    symbol: str,
    years: list[int],
    year_labels: list[str],
) -> tuple[list[Path], list[str]]:
    """Return batch dirs to query and warnings for missing selections."""
    warnings: list[str] = []
    all_dirs = list_symbol_batch_dirs(workspace_root, symbol)
    if not all_dirs:
        return [], warnings

    if not years and not year_labels:
        return all_dirs, warnings

    selected: list[Path] = []
    label_set = {lbl.strip() for lbl in year_labels}
    year_set = set(years)

    for batch_dir in all_dirs:
        stats = read_yearly_stats(batch_dir)
        folder_name = batch_dir.name
        stats_year = stats.get("year") if stats else None
        if label_set and folder_name in label_set:
            selected.append(batch_dir)
            continue
        if year_set and stats_year in year_set:
            selected.append(batch_dir)
            continue
        if year_set and folder_name.isdigit() and int(folder_name) in year_set:
            selected.append(batch_dir)

    if (years or year_labels) and not selected:
        warnings.append(
            "MISSING_YEAR_FOLDER: no batch folders matched years/year_labels filter"
        )
    return selected, warnings


def load_report_csv(batch_dir: Path, filename: str) -> pd.DataFrame | None:
    path = batch_dir / "reports" / filename
    if not path.is_file():
        return None
    try:
        df = pd.read_csv(path)
    except (OSError, ValueError):
        return None
    if df.empty and len(df.columns) == 0:
        return pd.DataFrame(columns=REPORT_FILES.get(filename, []))
    return df


def load_ranges_parquet(batch_dir: Path) -> pd.DataFrame | None:
    path = batch_dir / "normalized_ranges.parquet"
    if not path.is_file():
        return None
    try:
        return pd.read_parquet(path)
    except (OSError, ValueError):
        return None


def load_multi_report(
    batch_dirs: list[Path],
    filename: str,
    symbol: str,
) -> tuple[pd.DataFrame, list[str], list[str]]:
    """Load and concatenate a report CSV across batches."""
    warnings: list[str] = []
    sources: list[str] = []
    frames: list[pd.DataFrame] = []

    for batch_dir in batch_dirs:
        rel = f"{symbol}/{batch_dir.name}/reports/{filename}"
        df = load_report_csv(batch_dir, filename)
        if df is None:
            warnings.append(f"MISSING_REPORT_FILE: {rel}")
            continue
        sources.append(rel)
        df = df.copy()
        df["year_label"] = batch_dir.name
        stats = read_yearly_stats(batch_dir)
        df["batch_year"] = stats.get("year") if stats else None
        df["symbol"] = symbol
        frames.append(df)

    if not frames:
        columns = REPORT_FILES.get(filename, [])
        return pd.DataFrame(columns=columns), warnings, sources

    combined = pd.concat(frames, ignore_index=True)
    return combined, warnings, sources


def load_multi_ranges(
    batch_dirs: list[Path],
    symbol: str,
) -> tuple[pd.DataFrame, list[str], list[str]]:
    warnings: list[str] = []
    sources: list[str] = []
    frames: list[pd.DataFrame] = []

    for batch_dir in batch_dirs:
        rel = f"{symbol}/{batch_dir.name}/normalized_ranges.parquet"
        df = load_ranges_parquet(batch_dir)
        if df is None:
            warnings.append(f"MISSING_RANGES_PARQUET: {rel}")
            continue
        sources.append(rel)
        df = df.copy()
        df["year_label"] = batch_dir.name
        frames.append(df)

    if not frames:
        return pd.DataFrame(), warnings, sources
    return pd.concat(frames, ignore_index=True), warnings, sources


def load_yearly_stats_list(batch_dirs: list[Path]) -> list[dict[str, Any]]:
    stats_list: list[dict[str, Any]] = []
    for batch_dir in batch_dirs:
        stats = read_yearly_stats(batch_dir)
        if stats:
            stats_list.append(stats)
    return stats_list
