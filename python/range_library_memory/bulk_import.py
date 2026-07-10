"""Bulk import JSON folders into Range Library Memory."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .importer import import_source


@dataclass(frozen=True)
class BulkImportFailure:
    source_path: str
    error: str


@dataclass(frozen=True)
class BulkImportSummary:
    files_seen: int
    files_imported: int
    files_failed: int
    total_ranges_seen: int
    total_events_seen: int
    total_validation_issues: int
    total_duplicate_candidates: int
    imported_files: list[str]
    failed_files: list[BulkImportFailure]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def json_files(source_dir: str | Path) -> list[Path]:
    source = Path(source_dir)
    if not source.exists():
        raise FileNotFoundError(f"Source directory does not exist: {source}")
    if not source.is_dir():
        raise NotADirectoryError(f"Source path is not a directory: {source}")
    return sorted(path for path in source.rglob("*.json") if path.is_file())


def bulk_import_source_dir(db_path: str | Path, source_dir: str | Path, source_kind: str) -> BulkImportSummary:
    files = json_files(source_dir)
    imported_files: list[str] = []
    failed_files: list[BulkImportFailure] = []
    total_ranges_seen = 0
    total_events_seen = 0
    total_validation_issues = 0
    total_duplicate_candidates = 0

    for source_path in files:
        try:
            summary = import_source(db_path, source_path, source_kind)
        except Exception as exc:
            failed_files.append(BulkImportFailure(source_path=str(source_path), error=str(exc)))
            continue
        imported_files.append(str(source_path))
        total_ranges_seen += summary.ranges_seen
        total_events_seen += summary.events_seen
        total_validation_issues += summary.validation_issue_count
        total_duplicate_candidates += summary.duplicate_candidate_count

    return BulkImportSummary(
        files_seen=len(files),
        files_imported=len(imported_files),
        files_failed=len(failed_files),
        total_ranges_seen=total_ranges_seen,
        total_events_seen=total_events_seen,
        total_validation_issues=total_validation_issues,
        total_duplicate_candidates=total_duplicate_candidates,
        imported_files=imported_files,
        failed_files=failed_files,
    )


def format_bulk_import_summary(summary: BulkImportSummary, *, as_json: bool = False) -> str:
    payload = summary.to_dict()
    if as_json:
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    lines = [
        "Bulk import complete",
        f"files_seen={summary.files_seen}",
        f"files_imported={summary.files_imported}",
        f"files_failed={summary.files_failed}",
        f"total_ranges_seen={summary.total_ranges_seen}",
        f"total_events_seen={summary.total_events_seen}",
        f"total_validation_issues={summary.total_validation_issues}",
        f"total_duplicate_candidates={summary.total_duplicate_candidates}",
    ]
    if summary.failed_files:
        lines.append("failed_files:")
        for failure in summary.failed_files:
            lines.append(f"- {failure.source_path}: {failure.error}")
    return "\n".join(lines)
