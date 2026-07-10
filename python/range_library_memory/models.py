"""Data models for Range Library Memory import bookkeeping."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ImportSummary:
    """Counts and identifiers produced by one raw import run."""

    import_run_id: int
    run_uuid: str
    db_path: Path
    ranges_seen: int
    ranges_inserted: int
    ranges_reused: int
    events_seen: int
    events_inserted: int
    events_reused: int
    validation_issue_count: int
