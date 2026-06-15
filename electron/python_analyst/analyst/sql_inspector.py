"""Read-only DuckDB SQL over saved analyst workspace parquet/CSV tables."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

import pandas as pd

from analyst.query.loaders import resolve_batch_dirs
from analyst.storage.workspace import DEFAULT_WORKSPACE_ROOT

FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|ATTACH|DETACH|TRUNCATE|REPLACE|GRANT|REVOKE|PRAGMA|COPY|EXPORT|IMPORT|LOAD|INSTALL)\b",
    re.IGNORECASE,
)
DEFAULT_ROW_LIMIT = 200


class SqlValidationError(ValueError):
    pass


def validate_sql(sql: str) -> str:
    text = str(sql or "").strip()
    if not text:
        raise SqlValidationError("SQL is empty")
    if ";" in text.rstrip(";"):
        raise SqlValidationError("only one SQL statement allowed")
    text = text.rstrip(";").strip()
    if not re.match(r"^SELECT\b", text, re.IGNORECASE):
        raise SqlValidationError("only SELECT statements are allowed")
    if FORBIDDEN.search(text):
        raise SqlValidationError("statement contains forbidden keywords")
    return text


def _load_ranges(batch_dirs: list[Path], symbol: str) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for batch_dir in batch_dirs:
        path = batch_dir / "normalized_ranges.parquet"
        if not path.is_file():
            continue
        df = pd.read_parquet(path)
        df = df.copy()
        df["batch_label"] = batch_dir.name
        df["year_label"] = df.get("year_label", batch_dir.name)
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    if "symbol" in out.columns:
        out = out[out["symbol"].astype(str).str.upper() == symbol.upper()]
    return out


def _load_report_csv(batch_dirs: list[Path], symbol: str, file_name: str) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for batch_dir in batch_dirs:
        path = batch_dir / "reports" / file_name
        if not path.is_file():
            continue
        df = pd.read_csv(path)
        df = df.copy()
        df["batch_label"] = batch_dir.name
        df["year_label"] = batch_dir.name
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    if "symbol" in out.columns:
        out = out[out["symbol"].astype(str).str.upper() == symbol.upper()]
    return out


def run_sql_inspector(
    sql: str,
    symbol: str,
    workspace_root: str | Path | None = None,
    year_labels: list[str] | None = None,
    years: list[int] | None = None,
    row_limit: int = DEFAULT_ROW_LIMIT,
) -> dict[str, Any]:
    root = Path(workspace_root or DEFAULT_WORKSPACE_ROOT)
    sym = symbol.upper().strip()
    validated = validate_sql(sql)

    batch_dirs, warnings = resolve_batch_dirs(root, sym, years or [], year_labels or [])
    if not batch_dirs:
        return {
            "schema_version": "sql_inspector_result_v1",
            "status": "NO_WORKSPACE",
            "symbol": sym,
            "sql": validated,
            "row_count": 0,
            "columns": [],
            "rows": [],
            "warnings": warnings + ["NO_WORKSPACE: no batch folders found"],
            "generated_at_utc_ms": int(time.time() * 1000),
        }

    ranges_df = _load_ranges(batch_dirs, sym)
    retr_df = _load_report_csv(batch_dirs, sym, "retracement_stats.csv")
    seq_df = _load_report_csv(batch_dirs, sym, "impulse_retest_sequence.csv")

    try:
        import duckdb
    except ImportError:
        return {
            "schema_version": "sql_inspector_result_v1",
            "status": "ERROR",
            "symbol": sym,
            "sql": validated,
            "error": "duckdb package not installed — pip install duckdb",
            "generated_at_utc_ms": int(time.time() * 1000),
        }

    con = duckdb.connect()
    try:
        con.register("ranges", ranges_df if not ranges_df.empty else pd.DataFrame())
        con.register("retracement", retr_df if not retr_df.empty else pd.DataFrame())
        con.register("sequence", seq_df if not seq_df.empty else pd.DataFrame())
        wrapped = f"SELECT * FROM ({validated}) AS _q LIMIT {int(row_limit)}"
        result_df = con.execute(wrapped).fetchdf()
    except Exception as exc:
        return {
            "schema_version": "sql_inspector_result_v1",
            "status": "ERROR",
            "symbol": sym,
            "sql": validated,
            "error": str(exc),
            "warnings": warnings,
            "generated_at_utc_ms": int(time.time() * 1000),
        }
    finally:
        con.close()

    rows = result_df.where(result_df.notna(), None).to_dict(orient="records")
    return {
        "schema_version": "sql_inspector_result_v1",
        "status": "OK",
        "symbol": sym,
        "sql": validated,
        "row_count": len(rows),
        "columns": list(result_df.columns),
        "rows": rows,
        "warnings": warnings,
        "batches_used": [d.name for d in batch_dirs],
        "generated_at_utc_ms": int(time.time() * 1000),
    }


def run_sql_inspector_file(
    path: str | Path,
    workspace_root: str | Path | None = None,
) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return run_sql_inspector(
        sql=payload.get("sql", ""),
        symbol=payload.get("symbol", "XAUUSD"),
        workspace_root=workspace_root or payload.get("workspace_root"),
        year_labels=payload.get("year_labels") or [],
        years=payload.get("years") or [],
        row_limit=int(payload.get("row_limit") or DEFAULT_ROW_LIMIT),
    )
