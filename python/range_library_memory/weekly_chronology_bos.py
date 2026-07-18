"""Weekly Script 1: canonical anchor chronology and first BOS breach.

This derived analysis reads the persisted XAUUSD Master Map plus read-only W1
candles. It never mutates raw_ranges, raw_events, mapping identity, parent links,
or candle truth. Results are stored separately and projected into the persisted
Master Map output so Electron can display one verified hierarchy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

from .db import connect
from .inspection import deterministic_json, require_existing_db
from .source_market_db import (
    SourceCandle,
    SourceMarketDbError,
    latest_candle_time,
    load_candles,
    open_source_market_db,
)

VERSION = "weekly_chronology_bos_v0.1"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS weekly_chronology_bos (
    canonical_range_id TEXT PRIMARY KEY,
    analysis_version TEXT NOT NULL,
    symbol TEXT NOT NULL,
    structure_layer TEXT NOT NULL,
    source_timeframe TEXT NOT NULL,
    chronology_start_side TEXT,
    chronology_end_side TEXT,
    chronology_start_time TEXT,
    chronology_end_time TEXT,
    chronology_start_price REAL,
    chronology_end_price REAL,
    ending_boundary_price REAL,
    analysis_status TEXT NOT NULL,
    bos_direction TEXT,
    reclaim_direction TEXT,
    bos_candle_time TEXT,
    bos_candle_open REAL,
    bos_candle_high REAL,
    bos_candle_low REAL,
    bos_candle_close REAL,
    bos_breach_price REAL,
    candles_scanned INTEGER NOT NULL DEFAULT 0,
    reason_codes_json TEXT NOT NULL,
    source_candle_latest_time TEXT,
    result_hash TEXT NOT NULL,
    built_at_utc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_weekly_chronology_scope
ON weekly_chronology_bos(symbol, analysis_status, chronology_end_time);
"""


class WeeklyChronologyBosError(RuntimeError):
    """Raised when Script 1 cannot run safely."""


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def load_master_map(connection: sqlite3.Connection, symbol: str) -> dict[str, Any]:
    row = connection.execute(
        "SELECT output_json FROM master_map_outputs WHERE UPPER(symbol) = ?",
        (symbol.upper(),),
    ).fetchone()
    if row is None:
        raise WeeklyChronologyBosError(
            "Persisted Master Map is missing. Build the XAUUSD Master Map before Script 1."
        )
    try:
        output = json.loads(row["output_json"])
    except (TypeError, json.JSONDecodeError) as exc:
        raise WeeklyChronologyBosError("Persisted Master Map output_json is invalid.") from exc
    if str(output.get("symbol") or "").upper() != symbol.upper():
        raise WeeklyChronologyBosError("Persisted Master Map symbol does not match Script 1 scope.")
    return output


def walk_ranges(root: Mapping[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []

    def visit(node: Mapping[str, Any]) -> None:
        if str(node.get("node_type") or "").upper() == "RANGE":
            result.append(dict(node))
        for key in ("children", "unlinked_review_children"):
            for child in node.get(key) or []:
                if isinstance(child, Mapping):
                    visit(child)

    visit(root)
    return result


def unique_weeklies(master_map: Mapping[str, Any], year: int | None) -> list[dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for root_key in ("root", "trusted_root", "review_root"):
        root = master_map.get(root_key)
        if not isinstance(root, Mapping):
            continue
        for node in walk_ranges(root):
            if str(node.get("structure_layer") or "").upper() != "WEEKLY":
                continue
            canonical_id = str(node.get("id") or "").strip()
            if not canonical_id:
                continue
            if year is not None:
                anchor_years = {
                    parsed.year
                    for parsed in (
                        parse_time(node.get("range_high_time")),
                        parse_time(node.get("range_low_time")),
                    )
                    if parsed is not None
                }
                if year not in anchor_years:
                    continue
            index.setdefault(canonical_id, node)
    return sorted(
        index.values(),
        key=lambda item: (
            str(item.get("range_low_time") or item.get("range_high_time") or ""),
            str(item.get("id") or ""),
        ),
    )


def base_result(node: Mapping[str, Any], built_at: str) -> dict[str, Any]:
    return {
        "canonical_range_id": str(node.get("id") or ""),
        "analysis_version": VERSION,
        "symbol": str(node.get("symbol") or "XAUUSD").upper(),
        "structure_layer": "WEEKLY",
        "source_timeframe": str(node.get("source_timeframe") or "W1").upper(),
        "chronology_start_side": None,
        "chronology_end_side": None,
        "chronology_start_time": None,
        "chronology_end_time": None,
        "chronology_start_price": None,
        "chronology_end_price": None,
        "ending_boundary_price": None,
        "analysis_status": "NEEDS_REVIEW",
        "bos_direction": None,
        "reclaim_direction": None,
        "bos_candle_time": None,
        "bos_candle_open": None,
        "bos_candle_high": None,
        "bos_candle_low": None,
        "bos_candle_close": None,
        "bos_breach_price": None,
        "candles_scanned": 0,
        "reason_codes": [],
        "source_candle_latest_time": None,
        "result_hash": "",
        "built_at_utc": built_at,
    }


def finish(row: dict[str, Any], status: str, reasons: set[str]) -> dict[str, Any]:
    row["analysis_status"] = status
    row["reason_codes"] = sorted(reasons)
    stable = {key: value for key, value in row.items() if key not in {"built_at_utc", "result_hash"}}
    row["result_hash"] = hashlib.sha256(canonical_json(stable).encode("utf-8")).hexdigest()
    return row


def candle_breaches(candle: SourceCandle, end_side: str, boundary: float) -> bool:
    if end_side == "RH":
        return candle.high > boundary
    if end_side == "RL":
        return candle.low < boundary
    return False


def evaluate_weekly(
    source: sqlite3.Connection,
    node: Mapping[str, Any],
    *,
    built_at: str,
) -> dict[str, Any]:
    row = base_result(node, built_at)
    reasons: set[str] = set()
    high_time = parse_time(node.get("range_high_time"))
    low_time = parse_time(node.get("range_low_time"))
    high = number(node.get("range_high"))
    low = number(node.get("range_low"))

    if high is None or low is None or high <= low:
        return finish(row, "NEEDS_REVIEW", {"INVALID_RANGE_PRICES"})
    if high_time is None or low_time is None:
        return finish(row, "NEEDS_REVIEW", {"MISSING_ANCHOR_TIME"})
    if high_time == low_time:
        return finish(row, "NEEDS_REVIEW", {"ANCHOR_ORDER_AMBIGUOUS"})

    if low_time < high_time:
        start_side, end_side = "RL", "RH"
        start_time, end_time = node.get("range_low_time"), node.get("range_high_time")
        start_price, end_price = low, high
        direction, reclaim_direction = "UP", "DOWN"
    else:
        start_side, end_side = "RH", "RL"
        start_time, end_time = node.get("range_high_time"), node.get("range_low_time")
        start_price, end_price = high, low
        direction, reclaim_direction = "DOWN", "UP"

    row.update({
        "chronology_start_side": start_side,
        "chronology_end_side": end_side,
        "chronology_start_time": start_time,
        "chronology_end_time": end_time,
        "chronology_start_price": start_price,
        "chronology_end_price": end_price,
        "ending_boundary_price": end_price,
        "bos_direction": direction,
        "reclaim_direction": reclaim_direction,
    })

    timeframe = row["source_timeframe"]
    if timeframe != "W1":
        reasons.add("SOURCE_TIMEFRAME_NORMALIZED_TO_W1")
        timeframe = "W1"
        row["source_timeframe"] = timeframe

    latest = latest_candle_time(source, symbol=row["symbol"], timeframe=timeframe)
    row["source_candle_latest_time"] = latest
    if latest is None:
        return finish(row, "MISSING_DATA", reasons | {"MISSING_W1_CANDLES"})
    latest_dt = parse_time(latest)
    parsed_end = parse_time(end_time)
    if latest_dt is None or parsed_end is None or latest_dt <= parsed_end:
        return finish(row, "MISSING_DATA", reasons | {"NO_CANDLES_AFTER_ENDING_ANCHOR"})

    candles = load_candles(
        source,
        symbol=row["symbol"],
        timeframe=timeframe,
        start_time=str(end_time),
        end_time=latest,
    )
    candidates: list[SourceCandle] = []
    for candle in candles:
        candle_time = parse_time(candle.time)
        if candle_time is not None and candle_time > parsed_end:
            candidates.append(candle)
    row["candles_scanned"] = len(candidates)
    if not candidates:
        return finish(row, "MISSING_DATA", reasons | {"NO_CANDLES_AFTER_ENDING_ANCHOR"})

    breach = next((candle for candle in candidates if candle_breaches(candle, end_side, end_price)), None)
    if breach is None:
        return finish(row, "NOT_BREACHED", reasons | {"ENDING_BOUNDARY_NOT_BREACHED"})

    breach_price = breach.high if direction == "UP" else breach.low
    row.update({
        "bos_candle_time": breach.time,
        "bos_candle_open": breach.open,
        "bos_candle_high": breach.high,
        "bos_candle_low": breach.low,
        "bos_candle_close": breach.close,
        "bos_breach_price": breach_price,
    })

    existing = str(node.get("direction_of_break") or "").strip().upper()
    if existing in {"UP", "DOWN"} and existing != direction:
        return finish(row, "NEEDS_REVIEW", reasons | {"SCRIPT1_DIRECTION_CONFLICTS_WITH_MASTER_MAP"})
    return finish(row, "COMPLETE", reasons)


def ensure_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA_SQL)


def insert_result(connection: sqlite3.Connection, row: Mapping[str, Any]) -> None:
    columns = [
        "canonical_range_id", "analysis_version", "symbol", "structure_layer", "source_timeframe",
        "chronology_start_side", "chronology_end_side", "chronology_start_time", "chronology_end_time",
        "chronology_start_price", "chronology_end_price", "ending_boundary_price", "analysis_status",
        "bos_direction", "reclaim_direction", "bos_candle_time", "bos_candle_open", "bos_candle_high",
        "bos_candle_low", "bos_candle_close", "bos_breach_price", "candles_scanned",
        "reason_codes_json", "source_candle_latest_time", "result_hash", "built_at_utc",
    ]
    values = dict(row)
    values["reason_codes_json"] = canonical_json(values.pop("reason_codes"))
    placeholders = ",".join("?" for _ in columns)
    connection.execute(
        f"INSERT OR REPLACE INTO weekly_chronology_bos ({','.join(columns)}) VALUES ({placeholders})",
        tuple(values[column] for column in columns),
    )


def project_result_into_node(node: dict[str, Any], result: Mapping[str, Any]) -> None:
    node["chronology_start_side"] = result.get("chronology_start_side")
    node["chronology_end_side"] = result.get("chronology_end_side")
    node["chronology_start_time"] = result.get("chronology_start_time")
    node["chronology_end_time"] = result.get("chronology_end_time")
    node["chronology_status"] = result.get("analysis_status")
    node["script1_bos_direction"] = result.get("bos_direction")
    node["script1_bos_time"] = result.get("bos_candle_time")
    node["script1_bos_price"] = result.get("bos_breach_price")
    node["script1_reclaim_direction"] = result.get("reclaim_direction")
    node["script1_analysis_version"] = VERSION
    node["script1_reason_codes"] = list(result.get("reason_codes") or [])
    if result.get("analysis_status") == "COMPLETE":
        existing = str(node.get("direction_of_break") or "").strip().upper()
        if existing:
            node["lifecycle_direction_of_break"] = existing
        node["direction_of_break"] = result.get("bos_direction")
        node["direction_of_break_source"] = "WEEKLY_SCRIPT_1"


def project_results(master_map: dict[str, Any], results: list[dict[str, Any]]) -> None:
    index = {str(row["canonical_range_id"]): row for row in results}

    def visit(node: dict[str, Any]) -> None:
        canonical_id = str(node.get("id") or "")
        if canonical_id in index:
            project_result_into_node(node, index[canonical_id])
        for key in ("children", "unlinked_review_children"):
            for child in node.get(key) or []:
                if isinstance(child, dict):
                    visit(child)

    for root_key in ("root", "trusted_root", "review_root"):
        root = master_map.get(root_key)
        if isinstance(root, dict):
            visit(root)

    stable_results = [
        {key: value for key, value in row.items() if key != "built_at_utc"}
        for row in sorted(results, key=lambda item: str(item["canonical_range_id"]))
    ]
    analysis_hash = hashlib.sha256(canonical_json(stable_results).encode("utf-8")).hexdigest()
    analysis = master_map.setdefault("analysis", {})
    analysis["weekly_chronology_bos"] = {
        "schema_version": VERSION,
        "analysis_hash": analysis_hash,
        "total": len(results),
        "complete": sum(row["analysis_status"] == "COMPLETE" for row in results),
        "not_breached": sum(row["analysis_status"] == "NOT_BREACHED" for row in results),
        "needs_review": sum(row["analysis_status"] == "NEEDS_REVIEW" for row in results),
        "missing_data": sum(row["analysis_status"] == "MISSING_DATA" for row in results),
    }


def update_persisted_master_map(
    connection: sqlite3.Connection,
    *,
    symbol: str,
    master_map: dict[str, Any],
    results: list[dict[str, Any]],
) -> None:
    project_results(master_map, results)
    connection.execute(
        "UPDATE master_map_outputs SET output_json = ? WHERE UPPER(symbol) = ?",
        (json.dumps(master_map, sort_keys=True), symbol.upper()),
    )
    for result in results:
        row = connection.execute(
            "SELECT canonical_payload_json FROM master_map_ranges WHERE canonical_range_id = ?",
            (result["canonical_range_id"],),
        ).fetchone()
        if row is None:
            continue
        try:
            payload = json.loads(row["canonical_payload_json"])
        except (TypeError, json.JSONDecodeError):
            continue
        project_result_into_node(payload, result)
        connection.execute(
            "UPDATE master_map_ranges SET canonical_payload_json = ? WHERE canonical_range_id = ?",
            (json.dumps(payload, sort_keys=True), result["canonical_range_id"]),
        )


def build_weekly_chronology_bos(
    db_path: str | Path,
    *,
    source_db: str | Path,
    symbol: str = "XAUUSD",
    year: int | None = 2026,
) -> dict[str, Any]:
    db = require_existing_db(db_path)
    symbol = str(symbol).strip().upper()
    if symbol != "XAUUSD":
        raise WeeklyChronologyBosError("Script 1 v0.1 is intentionally scoped to XAUUSD.")
    built_at = utc_now()
    try:
        with closing(open_source_market_db(source_db)) as source, connect(db) as connection:
            ensure_schema(connection)
            master_map = load_master_map(connection, symbol)
            weeklies = unique_weeklies(master_map, year)
            results = [evaluate_weekly(source, node, built_at=built_at) for node in weeklies]
            if year is None:
                connection.execute("DELETE FROM weekly_chronology_bos WHERE symbol = ?", (symbol,))
            else:
                ids = [row["canonical_range_id"] for row in results]
                if ids:
                    placeholders = ",".join("?" for _ in ids)
                    connection.execute(
                        f"DELETE FROM weekly_chronology_bos WHERE symbol = ? AND canonical_range_id IN ({placeholders})",
                        (symbol, *ids),
                    )
            for result in results:
                insert_result(connection, result)
            update_persisted_master_map(
                connection,
                symbol=symbol,
                master_map=master_map,
                results=results,
            )
            connection.commit()
    except SourceMarketDbError as exc:
        raise WeeklyChronologyBosError(str(exc)) from exc

    counts: dict[str, int] = {}
    for row in results:
        counts[row["analysis_status"]] = counts.get(row["analysis_status"], 0) + 1
    return {
        "script": VERSION,
        "symbol": symbol,
        "year": year,
        "total": len(results),
        "status_counts": dict(sorted(counts.items())),
        "rows": results,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build Weekly Script 1 chronology and BOS analysis.")
    parser.add_argument("--db-path", required=True)
    parser.add_argument("--source-db", required=True)
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--all-years", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = build_weekly_chronology_bos(
        args.db_path,
        source_db=args.source_db,
        symbol=args.symbol,
        year=None if args.all_years else args.year,
    )
    if args.json:
        print(deterministic_json(summary))
    else:
        print(f"script: {summary['script']}")
        print(f"symbol: {summary['symbol']}")
        print(f"year: {summary['year'] if summary['year'] is not None else 'ALL'}")
        print(f"total: {summary['total']}")
        for status, count in summary["status_counts"].items():
            print(f"{status}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
