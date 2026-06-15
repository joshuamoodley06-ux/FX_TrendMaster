"""Mediator query engine orchestrator (M1 — no AI)."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from analyst.query.filters import filters_applied_dict
from analyst.query.loaders import resolve_batch_dirs
from analyst.query.metrics import compute_grouped_metrics, compute_metrics, sample_size_warnings
from analyst.query.schema import (
    MEDIATOR_RESULT_SCHEMA,
    QueryValidationError,
    validate_query,
)
from analyst.query.templates import build_dataset, build_year_comparison
from analyst.reports.json_writer import write_json
from analyst.storage.workspace import DEFAULT_WORKSPACE_ROOT


def run_query(
    query: dict[str, Any],
    workspace_root: str | Path | None = None,
    query_output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Execute mediator_query_v1 against saved workspace data."""
    root = Path(workspace_root or DEFAULT_WORKSPACE_ROOT)
    validated = validate_query(query)
    symbol = validated["symbol"]
    query_id = validated.get("query_id") or _default_query_id()

    batch_dirs, resolve_warnings = resolve_batch_dirs(
        root,
        symbol,
        validated["years"],
        validated["year_labels"],
    )

    warnings: list[str] = list(resolve_warnings)
    data_sources: list[str] = []
    filters_applied = filters_applied_dict(validated)

    if not batch_dirs:
        result = _build_result(
            validated,
            query_id,
            status="NO_WORKSPACE",
            symbol=symbol,
            year_labels_used=[],
            case_refs_used=validated["case_refs"],
            filters_applied=filters_applied,
            sample_size=0,
            metrics={},
            grouped=[],
            warnings=warnings + ["NO_WORKSPACE: no batch folders found for symbol"],
            data_sources=[],
            source_rows=[],
        )
        return _write_output(root, symbol, query_id, validated, result, query_output_dir)

    year_labels_used = [d.name for d in batch_dirs]

    if validated["question_type"] == "year_comparison":
        metrics, tpl_warnings, sources = build_year_comparison(validated, batch_dirs)
        warnings.extend(tpl_warnings)
        data_sources.extend(sources)
        sample_size = int(metrics.get("sample_size", 0))
        warnings.extend(sample_size_warnings(sample_size))
        result = _build_result(
            validated,
            query_id,
            status="OK" if sample_size > 0 else "NO_DATA",
            symbol=symbol,
            year_labels_used=year_labels_used,
            case_refs_used=validated["case_refs"],
            filters_applied=filters_applied,
            sample_size=sample_size,
            metrics=metrics,
            grouped=[],
            warnings=warnings,
            data_sources=data_sources,
            source_rows=[],
        )
        return _write_output(root, symbol, query_id, validated, result, query_output_dir)

    df, tpl_warnings, sources, outcome_col = build_dataset(validated, batch_dirs, symbol)
    warnings.extend(tpl_warnings)
    data_sources.extend(sources)

    sample_size = len(df)
    warnings.extend(sample_size_warnings(sample_size))

    metrics = compute_metrics(df, validated["metrics"], outcome_col)
    grouped = compute_grouped_metrics(df, validated["group_by"], validated["metrics"], outcome_col)

    source_rows: list[dict[str, Any]] = []
    if validated["include_source_rows"] and not df.empty:
        limit = validated["source_row_limit"]
        source_rows = _df_to_records(df.head(limit))

    status = "OK"
    if sample_size == 0:
        status = "NO_DATA"
    if tpl_warnings and any(w.startswith("MISSING_") for w in tpl_warnings):
        status = "PARTIAL_DATA" if sample_size > 0 else status

    result = _build_result(
        validated,
        query_id,
        status=status,
        symbol=symbol,
        year_labels_used=year_labels_used,
        case_refs_used=validated["case_refs"],
        filters_applied=filters_applied,
        sample_size=sample_size,
        metrics=metrics,
        grouped=grouped,
        warnings=warnings,
        data_sources=data_sources,
        source_rows=source_rows,
    )
    return _write_output(root, symbol, query_id, validated, result, query_output_dir)


def run_query_file(
    query_path: str | Path,
    workspace_root: str | Path | None = None,
    query_output_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = Path(query_path)
    if not path.is_file():
        raise FileNotFoundError(f"query file not found: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    return run_query(raw, workspace_root=workspace_root, query_output_dir=query_output_dir)


def _default_query_id() -> str:
    return f"q_{int(time.time())}_{uuid.uuid4().hex[:8]}"


def _build_result(
    query: dict[str, Any],
    query_id: str,
    status: str,
    symbol: str,
    year_labels_used: list[str],
    case_refs_used: list[str],
    filters_applied: dict[str, Any],
    sample_size: int,
    metrics: dict[str, Any],
    grouped: list[dict[str, Any]],
    warnings: list[str],
    data_sources: list[str],
    source_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": MEDIATOR_RESULT_SCHEMA,
        "query_id": query_id,
        "status": status,
        "symbol": symbol,
        "year_labels_used": year_labels_used,
        "case_refs_used": case_refs_used,
        "filters_applied": filters_applied,
        "question_type": query["question_type"],
        "sample_size": sample_size,
        "metrics": metrics,
        "grouped": grouped,
        "warnings": warnings,
        "data_sources": data_sources,
        "source_rows": source_rows,
        "generated_at_utc_ms": int(time.time() * 1000),
    }


def _write_output(
    workspace_root: Path,
    symbol: str,
    query_id: str,
    query: dict[str, Any],
    result: dict[str, Any],
    query_output_dir: str | Path | None,
) -> dict[str, Any]:
    if query_output_dir is not None:
        out_dir = Path(query_output_dir)
    else:
        out_dir = workspace_root / symbol / "queries" / query_id
    out_dir.mkdir(parents=True, exist_ok=True)
    result_path = out_dir / "query_result.json"
    write_json(result_path, result)
    query_copy = out_dir / "query.json"
    write_json(query_copy, query)
    result["output_dir"] = str(out_dir.resolve())
    result["result_path"] = str(result_path.resolve())
    return result


def _df_to_records(df) -> list[dict[str, Any]]:
    records = df.where(df.notna(), None).to_dict(orient="records")
    return records
