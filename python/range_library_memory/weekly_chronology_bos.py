"""Weekly Script 1: trusted anchor chronology and first strict BOS breach.

This module owns rebuildable analytical truth only. It reads the persisted
Master Map and read-only W1 candles, writes a versioned derived table, and
projects derived fields back into Master Map JSON without changing mapped
identity, hierarchy links, raw records, or the structural content hash.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from .db import connect
from .inspection import deterministic_json, require_existing_db
from .source_market_db import (
    SourceCandle,
    SourceMarketDbError,
    latest_candle_time,
    load_candles,
    open_source_market_db,
)

VERSION = "weekly_script1_v1"
SCRIPT_CONTENT_HASH = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
TABLE = "weekly_script1_results"
RUN_TABLE = "weekly_script1_runs"
SAMPLE_TABLE = "weekly_script1_validation_samples"
REVIEW_STATUSES = {"PENDING", "APPROVED", "NEEDS_REVIEW", "REJECTED"}

SCHEMA_SQL = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
    canonical_range_id TEXT NOT NULL,
    processing_version TEXT NOT NULL,
    run_id TEXT NOT NULL,
    source_range_id TEXT,
    source_range_ids_json TEXT NOT NULL,
    source_refs_json TEXT NOT NULL,
    source_structural_hash TEXT,
    case_ref TEXT NOT NULL,
    symbol TEXT NOT NULL,
    structure_layer TEXT NOT NULL,
    source_timeframe TEXT NOT NULL,
    range_high REAL,
    range_low REAL,
    range_high_time TEXT,
    range_low_time TEXT,
    chronology_result TEXT NOT NULL,
    chronology_start_time TEXT,
    chronology_end_time TEXT,
    bos_boundary REAL,
    expected_bos_direction TEXT,
    bos_direction TEXT NOT NULL,
    reclaim_direction TEXT,
    bos_candle_time TEXT,
    bos_candle_open REAL,
    bos_candle_high REAL,
    bos_candle_low REAL,
    bos_candle_close REAL,
    bos_evidence_price REAL,
    candles_scanned INTEGER NOT NULL,
    exact_touch_count INTEGER NOT NULL,
    exact_touch_examples_json TEXT NOT NULL,
    processing_status TEXT NOT NULL,
    review_status TEXT NOT NULL DEFAULT 'PENDING',
    reason_codes_json TEXT NOT NULL,
    result_hash TEXT NOT NULL,
    PRIMARY KEY (canonical_range_id, processing_version)
);
CREATE INDEX IF NOT EXISTS idx_weekly_script1_scope
ON {TABLE}(symbol, processing_version, processing_status, chronology_end_time);
CREATE TABLE IF NOT EXISTS {RUN_TABLE} (
    run_id TEXT PRIMARY KEY,
    pipeline_name TEXT NOT NULL,
    analysis_version TEXT NOT NULL,
    executed_at TEXT NOT NULL,
    input_structural_content_hash TEXT,
    case_ref TEXT NOT NULL,
    symbol TEXT NOT NULL,
    eligible_count INTEGER NOT NULL,
    analysed_count INTEGER NOT NULL,
    pending_count INTEGER NOT NULL,
    needs_review_count INTEGER NOT NULL,
    approval_state TEXT NOT NULL DEFAULT 'PENDING',
    approved_at TEXT,
    script_content_hash TEXT NOT NULL DEFAULT '',
    sample_count INTEGER NOT NULL DEFAULT 0,
    approval_count INTEGER NOT NULL DEFAULT 0,
    publication_status TEXT NOT NULL DEFAULT 'UNPUBLISHED',
    publication_version TEXT,
    published_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_weekly_script1_runs_scope
ON {RUN_TABLE}(symbol, case_ref, analysis_version, executed_at);
CREATE TABLE IF NOT EXISTS {SAMPLE_TABLE} (
    run_id TEXT NOT NULL,
    canonical_range_id TEXT NOT NULL,
    sample_order INTEGER NOT NULL,
    decision TEXT NOT NULL DEFAULT 'PENDING',
    decided_at TEXT,
    PRIMARY KEY (run_id, canonical_range_id),
    UNIQUE (run_id, sample_order)
);
"""


class WeeklyChronologyBosError(RuntimeError):
    """Raised when Weekly Script 1 cannot run safely."""


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


def normalized_break_direction(value: Any) -> str | None:
    direction = str(value or "").strip().upper()
    if direction in {"UP", "BOS_UP"}:
        return "BOS_UP"
    if direction in {"DOWN", "BOS_DOWN"}:
        return "BOS_DOWN"
    return None


def load_master_map(connection: sqlite3.Connection, symbol: str) -> dict[str, Any]:
    row = connection.execute(
        "SELECT output_json FROM master_map_outputs WHERE UPPER(symbol)=?",
        (symbol.upper(),),
    ).fetchone()
    if row is None:
        raise WeeklyChronologyBosError(
            "Persisted Master Map is missing. Build it explicitly before Weekly Script 1."
        )
    try:
        output = json.loads(row["output_json"])
    except (TypeError, json.JSONDecodeError) as exc:
        raise WeeklyChronologyBosError("Persisted Master Map output_json is invalid.") from exc
    if str(output.get("symbol") or "").upper() != symbol.upper():
        raise WeeklyChronologyBosError("Persisted Master Map symbol does not match Script 1 scope.")
    return output


def walk_ranges(root: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    def visit(node: Mapping[str, Any]) -> None:
        if str(node.get("node_type") or "").upper() == "RANGE":
            rows.append(dict(node))
        for child in node.get("children") or []:
            if isinstance(child, Mapping):
                visit(child)

    visit(root)
    return rows


def node_has_case_ref(node: Mapping[str, Any], case_ref: str) -> bool:
    return any(
        str(ref.get("case_ref") or "").strip() == case_ref
        for ref in node.get("source_refs") or []
        if isinstance(ref, Mapping)
    )


def trusted_weeklies(master_map: Mapping[str, Any], year: int | None, case_ref: str) -> list[dict[str, Any]]:
    root = master_map.get("trusted_root")
    if not isinstance(root, Mapping):
        raise WeeklyChronologyBosError("Persisted Master Map trusted_root is missing.")
    unique: dict[str, dict[str, Any]] = {}
    for node in walk_ranges(root):
        if str(node.get("structure_layer") or "").upper() != "WEEKLY":
            continue
        if str(node.get("navigation_status") or "").upper() != "TRUSTED":
            continue
        if str(node.get("statistics_status") or "").upper() != "ELIGIBLE":
            continue
        if not node_has_case_ref(node, case_ref):
            continue
        canonical_id = str(node.get("id") or "").strip()
        if not canonical_id:
            continue
        anchor_times = (parse_time(node.get("range_high_time")), parse_time(node.get("range_low_time")))
        if year is not None and year not in {value.year for value in anchor_times if value is not None}:
            continue
        unique.setdefault(canonical_id, node)
    return sorted(
        unique.values(),
        key=lambda node: (
            min(
                str(node.get("range_high_time") or "9999"),
                str(node.get("range_low_time") or "9999"),
            ),
            str(node.get("id") or ""),
        ),
    )


def source_provenance(node: Mapping[str, Any]) -> tuple[str | None, list[str], list[dict[str, Any]]]:
    refs = [dict(ref) for ref in node.get("source_refs") or [] if isinstance(ref, Mapping)]
    refs.sort(key=lambda ref: canonical_json(ref))
    source_ids = sorted({
        str(ref.get("source_record_id") or ref.get("raw_id") or "").strip()
        for ref in refs
        if str(ref.get("source_record_id") or ref.get("raw_id") or "").strip()
    })
    return (source_ids[0] if source_ids else None, source_ids, refs)


def base_result(node: Mapping[str, Any], structural_hash: str | None, case_ref: str, run_id: str) -> dict[str, Any]:
    source_range_id, source_range_ids, refs = source_provenance(node)
    return {
        "canonical_range_id": str(node.get("id") or ""),
        "processing_version": VERSION,
        "run_id": run_id,
        "source_range_id": source_range_id,
        "source_range_ids": source_range_ids,
        "source_refs": refs,
        "source_structural_hash": structural_hash,
        "case_ref": case_ref,
        "symbol": str(node.get("symbol") or "XAUUSD").upper(),
        "structure_layer": "WEEKLY",
        "source_timeframe": "W1",
        "range_high": number(node.get("range_high")),
        "range_low": number(node.get("range_low")),
        "range_high_time": node.get("range_high_time"),
        "range_low_time": node.get("range_low_time"),
        "chronology_result": "PENDING",
        "chronology_start_time": None,
        "chronology_end_time": None,
        "bos_boundary": None,
        "expected_bos_direction": None,
        "bos_direction": "PENDING",
        "reclaim_direction": None,
        "bos_candle_time": None,
        "bos_candle_open": None,
        "bos_candle_high": None,
        "bos_candle_low": None,
        "bos_candle_close": None,
        "bos_evidence_price": None,
        "candles_scanned": 0,
        "exact_touch_count": 0,
        "exact_touch_examples": [],
        "processing_status": "NEEDS_REVIEW",
        "review_status": "PENDING",
        "reason_codes": [],
        "result_hash": "",
    }


def finish(row: dict[str, Any], status: str, reasons: set[str]) -> dict[str, Any]:
    row["processing_status"] = status
    row["reason_codes"] = sorted(reasons)
    stable = {key: value for key, value in row.items() if key not in {"result_hash", "run_id", "review_status"}}
    row["result_hash"] = hashlib.sha256(canonical_json(stable).encode("utf-8")).hexdigest()
    return row


def direction_aliases(node: Mapping[str, Any]) -> set[str]:
    return {
        normalized
        for field in (
            "direction_of_break",
            "lifecycle_direction_of_break",
            "script1_bos_direction",
        )
        if (normalized := normalized_break_direction(node.get(field))) is not None
    }


def strict_breach(candle: SourceCandle, direction: str, boundary: float) -> bool:
    return candle.high > boundary if direction == "BOS_UP" else candle.low < boundary


def exact_touch(candle: SourceCandle, direction: str, boundary: float) -> bool:
    return candle.high == boundary if direction == "BOS_UP" else candle.low == boundary


def candle_evidence(candle: SourceCandle, direction: str) -> dict[str, Any]:
    return {
        "time": candle.time,
        "open": candle.open,
        "high": candle.high,
        "low": candle.low,
        "close": candle.close,
        "price": candle.high if direction == "BOS_UP" else candle.low,
    }


def evaluate_weekly(
    source: sqlite3.Connection,
    node: Mapping[str, Any],
    *,
    structural_hash: str | None,
    case_ref: str,
    run_id: str,
) -> dict[str, Any]:
    row = base_result(node, structural_hash, case_ref, run_id)
    high, low = row["range_high"], row["range_low"]
    high_time, low_time = parse_time(row["range_high_time"]), parse_time(row["range_low_time"])
    if high is None or low is None or high <= low:
        return finish(row, "NEEDS_REVIEW", {"INVALID_RANGE_PRICES"})
    if high_time is None or low_time is None:
        return finish(row, "NEEDS_REVIEW", {"MISSING_OR_INVALID_ANCHOR_TIME"})
    if high_time == low_time:
        return finish(row, "NEEDS_REVIEW", {"EQUAL_ANCHOR_TIMES"})

    if low_time < high_time:
        chronology, start_time, end_time = "RL_TO_RH", row["range_low_time"], row["range_high_time"]
        direction, reclaim, boundary = "BOS_UP", "DOWN", high
    else:
        chronology, start_time, end_time = "RH_TO_RL", row["range_high_time"], row["range_low_time"]
        direction, reclaim, boundary = "BOS_DOWN", "UP", low
    row.update({
        "chronology_result": chronology,
        "chronology_start_time": start_time,
        "chronology_end_time": end_time,
        "bos_boundary": boundary,
        "expected_bos_direction": direction,
        "reclaim_direction": reclaim,
    })

    aliases = direction_aliases(node)
    if len(aliases) > 1:
        return finish(row, "NEEDS_REVIEW", {"CONFLICTING_DIRECTION_ALIASES"})
    if aliases and direction not in aliases:
        return finish(row, "NEEDS_REVIEW", {"DERIVED_DIRECTION_CONFLICTS_WITH_STRUCTURAL_ALIAS"})

    latest = latest_candle_time(source, symbol=row["symbol"], timeframe="W1")
    parsed_end = parse_time(end_time)
    if latest is None or parsed_end is None or (parse_time(latest) or parsed_end) <= parsed_end:
        return finish(row, "PENDING", {"NO_W1_CANDLES_AFTER_ENDING_ANCHOR"})
    candles = load_candles(
        source,
        symbol=row["symbol"],
        timeframe="W1",
        start_time=str(end_time),
        end_time=latest,
    )
    candidates = [candle for candle in candles if (parse_time(candle.time) or parsed_end) > parsed_end]
    row["candles_scanned"] = len(candidates)
    touches = [candle_evidence(candle, direction) for candle in candidates if exact_touch(candle, direction, boundary)]
    row["exact_touch_count"] = len(touches)
    row["exact_touch_examples"] = touches[:3]
    breach = next((candle for candle in candidates if strict_breach(candle, direction, boundary)), None)
    if breach is None:
        return finish(row, "PENDING", {"STRICT_BOS_NOT_PROVEN"})
    evidence = candle_evidence(breach, direction)
    row.update({
        "bos_direction": direction,
        "bos_candle_time": evidence["time"],
        "bos_candle_open": evidence["open"],
        "bos_candle_high": evidence["high"],
        "bos_candle_low": evidence["low"],
        "bos_candle_close": evidence["close"],
        "bos_evidence_price": evidence["price"],
    })
    return finish(row, "COMPLETE", set())


JSON_COLUMNS = {
    "source_range_ids": "source_range_ids_json",
    "source_refs": "source_refs_json",
    "exact_touch_examples": "exact_touch_examples_json",
    "reason_codes": "reason_codes_json",
}

DB_COLUMNS = [
    "canonical_range_id", "processing_version", "run_id", "source_range_id",
    "source_range_ids_json", "source_refs_json", "source_structural_hash", "case_ref", "symbol",
    "structure_layer", "source_timeframe", "range_high", "range_low", "range_high_time",
    "range_low_time", "chronology_result", "chronology_start_time", "chronology_end_time",
    "bos_boundary", "expected_bos_direction", "bos_direction", "reclaim_direction",
    "bos_candle_time", "bos_candle_open", "bos_candle_high", "bos_candle_low",
    "bos_candle_close", "bos_evidence_price", "candles_scanned", "exact_touch_count",
    "exact_touch_examples_json", "processing_status", "review_status", "reason_codes_json", "result_hash",
]


def ensure_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA_SQL)
    columns = {str(row[1]) for row in connection.execute(f"PRAGMA table_info({TABLE})")}
    if "case_ref" not in columns:
        connection.execute(f"ALTER TABLE {TABLE} ADD COLUMN case_ref TEXT NOT NULL DEFAULT ''")
    if "review_status" not in columns:
        connection.execute(f"ALTER TABLE {TABLE} ADD COLUMN review_status TEXT NOT NULL DEFAULT 'PENDING'")
    if "run_id" not in columns:
        connection.execute(f"ALTER TABLE {TABLE} ADD COLUMN run_id TEXT NOT NULL DEFAULT ''")
    run_columns = {str(row[1]) for row in connection.execute(f"PRAGMA table_info({RUN_TABLE})")}
    for name, definition in {
        "script_content_hash": "TEXT NOT NULL DEFAULT ''",
        "sample_count": "INTEGER NOT NULL DEFAULT 0",
        "approval_count": "INTEGER NOT NULL DEFAULT 0",
        "publication_status": "TEXT NOT NULL DEFAULT 'UNPUBLISHED'",
        "publication_version": "TEXT",
        "published_at": "TEXT",
    }.items():
        if name not in run_columns:
            connection.execute(f"ALTER TABLE {RUN_TABLE} ADD COLUMN {name} {definition}")


def insert_result(connection: sqlite3.Connection, row: Mapping[str, Any]) -> None:
    values = dict(row)
    for source_key, db_key in JSON_COLUMNS.items():
        values[db_key] = canonical_json(values.pop(source_key))
    placeholders = ",".join("?" for _ in DB_COLUMNS)
    assignments = ",".join(
        f"{column}=excluded.{column}"
        for column in DB_COLUMNS
        if column not in {"canonical_range_id", "processing_version"}
    )
    connection.execute(
        f"INSERT INTO {TABLE} ({','.join(DB_COLUMNS)}) VALUES ({placeholders}) "
        f"ON CONFLICT(canonical_range_id,processing_version) DO UPDATE SET {assignments}",
        tuple(values[column] for column in DB_COLUMNS),
    )


def decode_stored_row(row: sqlite3.Row) -> dict[str, Any]:
    result = dict(row)
    for source_key, db_key in JSON_COLUMNS.items():
        result[source_key] = json.loads(result.pop(db_key))
    return result


def load_stored_results(connection: sqlite3.Connection, symbol: str, case_ref: str | None = None) -> list[dict[str, Any]]:
    ensure_schema(connection)
    query = f"SELECT * FROM {TABLE} WHERE symbol=? AND processing_version=?"
    params: list[Any] = [symbol.upper(), VERSION]
    if case_ref is not None:
        query += " AND case_ref=?"
        params.append(case_ref)
    rows = connection.execute(
        query + " ORDER BY chronology_start_time,canonical_range_id", params
    ).fetchall()
    return [decode_stored_row(row) for row in rows]


def project_result_into_node(node: dict[str, Any], result: Mapping[str, Any]) -> None:
    node["script1_chronology"] = result.get("chronology_result")
    node["script1_chronology_start_time"] = result.get("chronology_start_time")
    node["script1_chronology_end_time"] = result.get("chronology_end_time")
    node["script1_bos_direction"] = result.get("bos_direction")
    node["script1_bos_time"] = result.get("bos_candle_time")
    node["script1_bos_price"] = result.get("bos_evidence_price")
    node["script1_reclaim_direction"] = result.get("reclaim_direction")
    node["script1_processing_version"] = result.get("processing_version")
    node["script1_run_id"] = result.get("run_id")
    node["script1_processing_status"] = result.get("processing_status")
    node["script1_review_status"] = result.get("review_status")
    node["script1_reason_codes"] = list(result.get("reason_codes") or [])
    node["script1_result_hash"] = result.get("result_hash")


def project_results(master_map: dict[str, Any], results: Sequence[Mapping[str, Any]]) -> None:
    index = {str(row["canonical_range_id"]): row for row in results}

    def visit(node: dict[str, Any]) -> None:
        canonical_id = str(node.get("id") or "")
        if canonical_id in index:
            project_result_into_node(node, index[canonical_id])
        for child in node.get("children") or []:
            if isinstance(child, dict):
                visit(child)

    for root_key in ("root", "trusted_root", "review_root"):
        root = master_map.get(root_key)
        if isinstance(root, dict):
            visit(root)
    stable = sorted(
        ({key: value for key, value in row.items()} for row in results),
        key=lambda row: (str(row.get("chronology_start_time") or ""), str(row["canonical_range_id"])),
    )
    analysis_hash = hashlib.sha256(canonical_json(stable).encode("utf-8")).hexdigest()
    master_map.setdefault("analysis", {})["weekly_script1"] = {
        "pipeline_name": "Weekly analysis",
        "script_content_hash": SCRIPT_CONTENT_HASH,
        "processing_version": VERSION,
        "run_id": stable[0].get("run_id") if stable else None,
        "approval_state": stable[0].get("review_status") if stable else "PENDING",
        "analysis_hash": analysis_hash,
        "total": len(stable),
        "complete": sum(row.get("processing_status") == "COMPLETE" for row in stable),
        "pending": sum(row.get("processing_status") == "PENDING" for row in stable),
        "needs_review": sum(row.get("processing_status") == "NEEDS_REVIEW" for row in stable),
    }


def persist_projection(
    connection: sqlite3.Connection,
    *,
    symbol: str,
    master_map: dict[str, Any],
    results: Sequence[Mapping[str, Any]],
) -> None:
    project_results(master_map, results)
    connection.execute(
        "UPDATE master_map_outputs SET output_json=? WHERE UPPER(symbol)=?",
        (json.dumps(master_map, sort_keys=True), symbol.upper()),
    )
    for result in results:
        stored = connection.execute(
            "SELECT canonical_payload_json FROM master_map_ranges WHERE canonical_range_id=?",
            (result["canonical_range_id"],),
        ).fetchone()
        if stored is None:
            continue
        try:
            payload = json.loads(stored["canonical_payload_json"])
        except (TypeError, json.JSONDecodeError):
            continue
        project_result_into_node(payload, result)
        connection.execute(
            "UPDATE master_map_ranges SET canonical_payload_json=? WHERE canonical_range_id=?",
            (json.dumps(payload, sort_keys=True), result["canonical_range_id"]),
        )


def project_stored_results(
    connection: sqlite3.Connection,
    master_map: dict[str, Any],
    *,
    symbol: str,
) -> list[dict[str, Any]]:
    results = load_stored_results(connection, symbol)
    if results:
        project_run_metadata(connection, master_map, str(results[0].get("run_id") or ""))
        persist_projection(connection, symbol=symbol, master_map=master_map, results=results)
    return results


def project_run_metadata(connection: sqlite3.Connection, master_map: dict[str, Any], run_id: str) -> None:
    if not run_id:
        return
    run = connection.execute(f"SELECT * FROM {RUN_TABLE} WHERE run_id=?", (run_id,)).fetchone()
    if run is None:
        return
    target = master_map.setdefault("analysis", {}).setdefault("weekly_script1", {})
    target.update({
        "pipeline_name": run["pipeline_name"],
        "processing_version": run["analysis_version"],
        "run_id": run["run_id"],
        "executed_at": run["executed_at"],
        "input_structural_content_hash": run["input_structural_content_hash"],
        "approval_state": run["approval_state"],
        "approved_at": run["approved_at"],
        "eligible": run["eligible_count"],
        "analysed": run["analysed_count"],
        "pending": run["pending_count"],
        "needs_review": run["needs_review_count"],
        "script_content_hash": run["script_content_hash"],
        "sample_count": run["sample_count"],
        "approval_count": run["approval_count"],
        "publication_status": run["publication_status"],
        "publication_version": run["publication_version"],
        "published_at": run["published_at"],
        "validation_samples": [dict(row) for row in connection.execute(
            f"SELECT canonical_range_id,sample_order,decision,decided_at FROM {SAMPLE_TABLE} "
            "WHERE run_id=? ORDER BY sample_order", (run_id,)
        )],
    })


def select_validation_samples(results: Sequence[Mapping[str, Any]], limit: int = 5) -> list[Mapping[str, Any]]:
    ordered = sorted(results, key=lambda row: (str(row.get("chronology_start_time") or ""), str(row["canonical_range_id"])))
    selected: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    for row in ordered:
        key = f"{row.get('chronology_result')}|{row.get('bos_direction')}|{row.get('processing_status')}"
        if key not in seen:
            selected.append(row); seen.add(key)
        if len(selected) == limit:
            return selected
    for row in ordered:
        if row not in selected:
            selected.append(row)
        if len(selected) == limit:
            break
    return selected


def review_weekly_script1_run(
    db_path: str | Path,
    *,
    run_id: str,
    case_ref: str,
    symbol: str,
    canonical_range_id: str,
    decision: str,
) -> dict[str, Any]:
    db = require_existing_db(db_path)
    run_id = str(run_id or "").strip()
    case_ref = str(case_ref or "").strip()
    symbol = str(symbol or "").strip().upper()
    canonical_range_id = str(canonical_range_id or "").strip()
    decision = str(decision or "").strip().upper()
    if not run_id or not case_ref or not symbol or not canonical_range_id:
        raise WeeklyChronologyBosError("Review requires run identity, case_ref, and symbol.")
    if decision not in {"APPROVED", "REJECTED"}:
        raise WeeklyChronologyBosError(f"Unsupported sample decision: {decision}")
    with connect(db) as connection:
        ensure_schema(connection)
        run = connection.execute(
            f"SELECT * FROM {RUN_TABLE} WHERE run_id=? AND analysis_version=? AND case_ref=? AND symbol=?",
            (run_id, VERSION, case_ref, symbol),
        ).fetchone()
        latest = connection.execute(
            f"SELECT run_id FROM {RUN_TABLE} WHERE analysis_version=? AND case_ref=? AND symbol=? "
            "ORDER BY executed_at DESC, run_id DESC LIMIT 1", (VERSION, case_ref, symbol),
        ).fetchone()
        if run is None or latest is None or str(latest["run_id"]) != run_id:
            raise WeeklyChronologyBosError("Analysis run provenance is missing or stale.")
        master_map = load_master_map(connection, symbol)
        if str(run["input_structural_content_hash"] or "") != str(master_map.get("structural_content_hash") or ""):
            raise WeeklyChronologyBosError("Analysis run provenance is stale for the current structure.")
        sample = connection.execute(
            f"SELECT decision FROM {SAMPLE_TABLE} WHERE run_id=? AND canonical_range_id=?",
            (run_id, canonical_range_id),
        ).fetchone()
        if sample is None:
            raise WeeklyChronologyBosError("Validation sample is missing for this analysis run.")
        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        if str(sample["decision"]) == "PENDING":
            connection.execute(
                f"UPDATE {SAMPLE_TABLE} SET decision=?,decided_at=? WHERE run_id=? AND canonical_range_id=?",
                (decision, now, run_id, canonical_range_id),
            )
        decisions = [str(row[0]) for row in connection.execute(
            f"SELECT decision FROM {SAMPLE_TABLE} WHERE run_id=? ORDER BY sample_order", (run_id,)
        )]
        approval_count = sum(value == "APPROVED" for value in decisions)
        rejected = any(value == "REJECTED" for value in decisions)
        approved = bool(decisions) and approval_count == len(decisions)
        approval_state = "REJECTED" if rejected else "APPROVED" if approved else "PENDING"
        publication_status = "PUBLISHED" if approved else "UNPUBLISHED"
        approved_at = now if approved else None
        connection.execute(
            f"UPDATE {RUN_TABLE} SET approval_state=?,approved_at=?,approval_count=?,publication_status=?,"
            "publication_version=?,published_at=? WHERE run_id=?",
            (approval_state, approved_at, approval_count, publication_status,
             SCRIPT_CONTENT_HASH if approved else None, now if approved else None, run_id),
        )
        if approved:
            connection.execute(
                f"UPDATE {TABLE} SET review_status="
                "CASE WHEN processing_status='COMPLETE' THEN 'APPROVED' ELSE 'NEEDS_REVIEW' END "
                "WHERE run_id=? AND case_ref=? AND symbol=?",
                (run_id, case_ref, symbol),
            )
        elif rejected:
            connection.execute(
                f"UPDATE {TABLE} SET review_status='REJECTED' WHERE run_id=? AND case_ref=? AND symbol=?",
                (run_id, case_ref, symbol),
            )
        results = load_stored_results(connection, symbol, case_ref)
        project_run_metadata(connection, master_map, run_id)
        persist_projection(connection, symbol=symbol, master_map=master_map, results=results)
        connection.commit()
    return {
        "run_id": run_id,
        "case_ref": case_ref,
        "symbol": symbol,
        "approval_state": approval_state,
        "approved_at": approved_at,
        "approval_count": approval_count,
        "sample_count": len(decisions),
        "publication_status": publication_status,
    }


def summarize(results: Sequence[Mapping[str, Any]], *, symbol: str, year: int | None, run_id: str, executed_at: str, structural_hash: str | None) -> dict[str, Any]:
    stable_rows = sorted(
        results,
        key=lambda row: (str(row.get("chronology_start_time") or ""), str(row["canonical_range_id"])),
    )
    hashes = [str(row["result_hash"]) for row in stable_rows]
    return {
        "script": VERSION,
        "pipeline_name": "Weekly analysis",
        "run_id": run_id,
        "executed_at": executed_at,
        "input_structural_content_hash": structural_hash,
        "approval_state": "PENDING",
        "symbol": symbol,
        "year": year,
        "weekly_rows_processed": len(stable_rows),
        "rl_to_rh": sum(row.get("chronology_result") == "RL_TO_RH" for row in stable_rows),
        "rh_to_rl": sum(row.get("chronology_result") == "RH_TO_RL" for row in stable_rows),
        "bos_up": sum(row.get("bos_direction") == "BOS_UP" for row in stable_rows),
        "bos_down": sum(row.get("bos_direction") == "BOS_DOWN" for row in stable_rows),
        "pending": sum(row.get("processing_status") == "PENDING" for row in stable_rows),
        "needs_review": sum(row.get("processing_status") == "NEEDS_REVIEW" for row in stable_rows),
        "exact_touch_rejections": sum(int(row.get("exact_touch_count") or 0) for row in stable_rows),
        "aggregate_hash": hashlib.sha256(canonical_json(hashes).encode("utf-8")).hexdigest(),
        "result_hashes": hashes,
        "rows": stable_rows,
    }


def build_weekly_chronology_bos(
    db_path: str | Path,
    *,
    source_db: str | Path,
    case_ref: str,
    symbol: str = "XAUUSD",
    year: int | None = None,
) -> dict[str, Any]:
    db = require_existing_db(db_path)
    symbol = str(symbol).strip().upper()
    case_ref = str(case_ref or "").strip()
    if symbol != "XAUUSD":
        raise WeeklyChronologyBosError("Weekly Script 1 is intentionally scoped to XAUUSD.")
    if not case_ref:
        raise WeeklyChronologyBosError("Weekly Script 1 requires an explicit selected case_ref.")
    try:
        with closing(open_source_market_db(source_db, required_tables=("candles",))) as source, connect(db) as connection:
            master_map = load_master_map(connection, symbol)
            ensure_schema(connection)
            structural_hash = str(master_map.get("structural_content_hash") or "") or None
            existing = connection.execute(
                f"SELECT * FROM {RUN_TABLE} WHERE analysis_version=? AND script_content_hash=? "
                "AND input_structural_content_hash=? AND case_ref=? AND symbol=? ORDER BY executed_at DESC LIMIT 1",
                (VERSION, SCRIPT_CONTENT_HASH, structural_hash, case_ref, symbol),
            ).fetchone()
            if existing is not None:
                run_id = str(existing["run_id"])
                results = load_stored_results(connection, symbol, case_ref)
                project_run_metadata(connection, master_map, run_id)
                persist_projection(connection, symbol=symbol, master_map=master_map, results=results)
                connection.commit()
                return summarize(results, symbol=symbol, year=year, run_id=run_id,
                                 executed_at=str(existing["executed_at"]), structural_hash=structural_hash)
            run_id = hashlib.sha256(canonical_json([
                VERSION, SCRIPT_CONTENT_HASH, structural_hash, case_ref, symbol
            ]).encode("utf-8")).hexdigest()
            executed_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
            nodes = trusted_weeklies(master_map, year, case_ref)
            if not nodes:
                raise WeeklyChronologyBosError("Selected case contains no trusted Weekly records.")
            results = [
                evaluate_weekly(source, node, structural_hash=structural_hash, case_ref=case_ref, run_id=run_id)
                for node in nodes
            ]
            for result in results:
                insert_result(connection, result)
            connection.execute(
                f"INSERT INTO {RUN_TABLE} (run_id,pipeline_name,analysis_version,executed_at,"
                "input_structural_content_hash,case_ref,symbol,eligible_count,analysed_count,"
                "pending_count,needs_review_count,approval_state,approved_at,script_content_hash,sample_count,"
                "approval_count,publication_status,publication_version,published_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (run_id, "Weekly analysis", VERSION, executed_at, structural_hash, case_ref, symbol,
                 len(nodes), len(results), sum(row["processing_status"] == "PENDING" for row in results),
                 sum(row["processing_status"] == "NEEDS_REVIEW" for row in results), "PENDING", None,
                 SCRIPT_CONTENT_HASH, min(5, len(results)), 0, "UNPUBLISHED", None, None),
            )
            for order, sample in enumerate(select_validation_samples(results)):
                connection.execute(
                    f"INSERT INTO {SAMPLE_TABLE} (run_id,canonical_range_id,sample_order,decision,decided_at) "
                    "VALUES (?,?,?,'PENDING',NULL)", (run_id, sample["canonical_range_id"], order),
                )
            project_run_metadata(connection, master_map, run_id)
            persist_projection(
                connection,
                symbol=symbol,
                master_map=master_map,
                results=results,
            )
            connection.commit()
    except SourceMarketDbError as exc:
        raise WeeklyChronologyBosError(str(exc)) from exc
    return summarize(results, symbol=symbol, year=year, run_id=run_id, executed_at=executed_at, structural_hash=structural_hash)


def concise_summary(summary: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in summary.items() if key not in {"rows", "result_hashes"}}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build Weekly Script 1 chronology/BOS derived rows.")
    parser.add_argument("--db-path", type=Path, required=True, help="Explicit Range Library SQLite path.")
    parser.add_argument("--source-db", type=Path, required=True, help="Explicit read-only candle SQLite path.")
    parser.add_argument("--symbol", default="XAUUSD", choices=("XAUUSD",))
    parser.add_argument("--case-ref", required=True)
    parser.add_argument("--year", type=int, default=None, help="Optional anchor year; omitted means all trusted Weekly rows.")
    parser.add_argument("--json", action="store_true", help="Emit a concise deterministic JSON summary.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = build_weekly_chronology_bos(
        args.db_path,
        source_db=args.source_db,
        case_ref=args.case_ref,
        symbol=args.symbol,
        year=args.year,
    )
    if args.json:
        print(deterministic_json(concise_summary(summary)))
    else:
        for key, value in concise_summary(summary).items():
            print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
