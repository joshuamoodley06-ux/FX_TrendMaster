"""Workspace batch directory discovery.

A batch folder is any subfolder of workspace/<SYMBOL>/ that contains
yearly_stats.json. Folder names are user-chosen labels (2020, 2019_Q3-2021_Q1).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SKIP_SYMBOL_SUBDIRS = frozenset({"combined", "queries"})


def list_symbol_batch_dirs(workspace_root: str | Path, symbol: str) -> list[Path]:
    symbol_dir = Path(workspace_root) / symbol
    if not symbol_dir.is_dir():
        return []
    dirs: list[Path] = []
    for child in sorted(symbol_dir.iterdir()):
        if not child.is_dir() or child.name in SKIP_SYMBOL_SUBDIRS:
            continue
        if (child / "yearly_stats.json").is_file():
            dirs.append(child)
    return dirs


def read_yearly_stats(batch_dir: Path) -> dict[str, Any] | None:
    stats_path = batch_dir / "yearly_stats.json"
    if not stats_path.is_file():
        return None
    try:
        payload = json.loads(stats_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    payload.setdefault("year_label", batch_dir.name)
    return payload
