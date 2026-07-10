"""Offline export of local FXTM case data into analyst_input_v1 JSON files."""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ExportedCase:
    case_ref: str
    output_path: Path
    ranges: int
    events: int
    ledgers: int


def export_cases(
    *,
    source_db: str | Path,
    output_dir: str | Path,
    symbol: str | None = None,
    limit: int | None = None,
) -> list[ExportedCase]:
    source = Path(source_db)
    if not source.exists():
        raise FileNotFoundError(f"Source DB does not exist: {source}")
    if not source.is_file():
        raise ValueError(f"Source DB is not a file: {source}")

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        cases = discover_cases(connection, symbol=symbol)
        if limit is not None:
            cases = cases[: max(limit, 0)]

        exported: list[ExportedCase] = []
        for case in cases:
            package = build_case_package(connection, case)
            file_name = deterministic_file_name(case)
            output_path = output / file_name
            output_path.write_text(json.dumps(package, indent=2, sort_keys=True), encoding="utf-8")
            data = package["data"]
            exported.append(
                ExportedCase(
                    case_ref=case["case_ref"],
                    output_path=output_path,
                    ranges=len(data["ranges"]),
                    events=len(data["events"]),
                    ledgers=len(data["raw_ledgers"]),
                )
            )
    return exported


def discover_cases(connection: sqlite3.Connection, *, symbol: str | None = None) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    symbol_filter = symbol.upper() if symbol else None

    if table_exists(connection, "mos_seed_ideas"):
        query = "SELECT * FROM mos_seed_ideas"
        params: tuple[Any, ...] = ()
        if symbol_filter and column_exists(connection, "mos_seed_ideas", "symbol"):
            query += " WHERE UPPER(symbol) = ?"
            params = (symbol_filter,)
        query += " ORDER BY id ASC"
        for row in connection.execute(query, params).fetchall():
            row_dict = dict(row)
            case_id = row_dict.get("id")
            if case_id is None:
                continue
            cases.append(
                {
                    "case_ref": f"case:{case_id}",
                    "kind": "legacy",
                    "case_id": int(case_id),
                    "raw_case_id": None,
                    "symbol": str(row_dict.get("symbol") or symbol_filter or "UNKNOWN").upper(),
                    "label": str(row_dict.get("seed_name") or row_dict.get("name") or f"case_{case_id}"),
                    "case": row_dict,
                }
            )

    if table_exists(connection, "raw_mapping_cases"):
        query = "SELECT * FROM raw_mapping_cases"
        params = ()
        if symbol_filter:
            query += " WHERE UPPER(symbol) = ?"
            params = (symbol_filter,)
        query += " ORDER BY case_id ASC"
        for row in connection.execute(query, params).fetchall():
            row_dict = dict(row)
            case_id = str(row_dict.get("case_id") or "")
            if not case_id:
                continue
            cases.append(
                {
                    "case_ref": f"raw:{case_id}",
                    "kind": "raw",
                    "case_id": None,
                    "raw_case_id": case_id,
                    "symbol": str(row_dict.get("symbol") or symbol_filter or "UNKNOWN").upper(),
                    "label": str(row_dict.get("case_name") or f"raw_{case_id}"),
                    "case": row_dict,
                }
            )

    if not cases:
        cases.extend(discover_map_only_cases(connection, symbol_filter=symbol_filter))

    return sorted(cases, key=lambda item: item["case_ref"])


def discover_map_only_cases(connection: sqlite3.Connection, *, symbol_filter: str | None) -> list[dict[str, Any]]:
    discovered: dict[str, dict[str, Any]] = {}
    for table in ("map_ranges", "map_events"):
        if not table_exists(connection, table):
            continue
        columns = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}
        if not columns.intersection({"case_ref", "raw_case_id", "case_id"}):
            continue
        select_columns = sorted(columns)
        clauses: list[str] = []
        params: list[Any] = []
        if symbol_filter and "symbol" in columns:
            clauses.append("UPPER(symbol) = ?")
            params.append(symbol_filter)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        for row in connection.execute(f"SELECT {', '.join(select_columns)} FROM {table}{where}", tuple(params)).fetchall():
            row_dict = dict(row)
            case_ref, raw_case_id, case_id = map_only_case_identity(row_dict)
            if case_ref is None:
                continue
            if case_ref not in discovered:
                discovered[case_ref] = {
                    "case_ref": case_ref,
                    "kind": "map_only",
                    "case_id": case_id,
                    "raw_case_id": raw_case_id,
                    "symbol": str(row_dict.get("symbol") or symbol_filter or "UNKNOWN").upper(),
                    "label": case_ref.replace(":", "_"),
                    "case": {
                        "case_ref": case_ref,
                        "raw_case_id": raw_case_id,
                        "case_id": case_id,
                        "source": "map_rows",
                    },
                }
    return list(discovered.values())


def map_only_case_identity(row: dict[str, Any]) -> tuple[str | None, str | None, int | None]:
    case_ref = text_or_none(row.get("case_ref"))
    raw_case_id = text_or_none(row.get("raw_case_id"))
    case_id = int_or_none(row.get("case_id"))
    if case_ref:
        if case_ref.startswith("raw:") and raw_case_id is None:
            raw_case_id = case_ref.removeprefix("raw:")
        if case_ref.startswith("case:") and case_id is None:
            case_id = int_or_none(case_ref.removeprefix("case:"))
        return case_ref, raw_case_id, case_id
    if raw_case_id:
        return f"raw:{raw_case_id}", raw_case_id, case_id
    if case_id is not None:
        return f"case:{case_id}", raw_case_id, case_id
    return None, None, None


def build_case_package(connection: sqlite3.Connection, case: dict[str, Any]) -> dict[str, Any]:
    ranges = fetch_rows(connection, "map_ranges", case)
    events = fetch_rows(connection, "map_events", case)
    raw_ledgers = {}
    if case["kind"] == "raw":
        raw_ledgers[case["case_ref"]] = raw_ledger(connection, case)

    generated = datetime.now(UTC).replace(microsecond=0)
    return {
        "schema_version": "analyst_input_v1",
        "symbol": case["symbol"],
        "year": None,
        "label": sanitize_label(f"{case['symbol']}_{case['label']}"),
        "case_refs": [case["case_ref"]],
        "generated_at_utc_ms": int(generated.timestamp() * 1000),
        "source": {
            "source_db": source_db_label(),
            "exported_at": generated.isoformat().replace("+00:00", "Z"),
            "offline_export": True,
        },
        "data": {
            "ranges": ranges,
            "events": events,
            "candles": {},
            "raw_ledgers": raw_ledgers,
        },
        "warnings": [],
    }


def fetch_rows(connection: sqlite3.Connection, table: str, case: dict[str, Any]) -> list[dict[str, Any]]:
    if not table_exists(connection, table):
        return []
    clauses: list[str] = []
    params: list[Any] = []
    if case["case_ref"] is not None and column_exists(connection, table, "case_ref"):
        clauses.append("case_ref = ?")
        params.append(case["case_ref"])
    if case["case_id"] is not None and column_exists(connection, table, "case_id"):
        clauses.append("case_id = ?")
        params.append(case["case_id"])
    if case["raw_case_id"] is not None:
        if column_exists(connection, table, "raw_case_id"):
            clauses.append("raw_case_id = ?")
            params.append(case["raw_case_id"])
    if not clauses:
        return []
    order = order_clause(connection, table)
    sql = f"SELECT DISTINCT * FROM {table} WHERE {' OR '.join(f'({clause})' for clause in clauses)} {order}"
    return [decode_json_columns(dict(row)) for row in connection.execute(sql, tuple(params)).fetchall()]


def raw_ledger(connection: sqlite3.Connection, case: dict[str, Any]) -> dict[str, Any]:
    case_id = case["raw_case_id"]
    rows: list[dict[str, Any]] = []
    if table_exists(connection, "raw_mapping_events"):
        rows = [
            decode_json_columns(dict(row))
            for row in connection.execute(
                "SELECT * FROM raw_mapping_events WHERE case_id = ? ORDER BY created_order ASC, event_id ASC",
                (case_id,),
            ).fetchall()
        ]
    by_timeline = sorted(rows, key=lambda row: (row.get("candle_time_utc_ms") or 0, row.get("created_order") or 0, row.get("event_id") or ""))
    return {
        "ok": True,
        "meta": {
            "case_id": case_id,
            "schema_version": "raw_mapping_v1",
            "total_records": len(rows),
            "case": case["case"],
        },
        "sequence_by_intent": rows,
        "sequence_by_timeline": by_timeline,
    }


def table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


def column_exists(connection: sqlite3.Connection, table: str, column: str) -> bool:
    return any(row["name"] == column for row in connection.execute(f"PRAGMA table_info({table})").fetchall())


def order_clause(connection: sqlite3.Connection, table: str) -> str:
    if table == "map_ranges":
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(map_ranges)").fetchall()}
        preferred = [name for name in ("source_timeframe", "timeframe", "active_from_time", "range_start_time", "id") if name in columns]
        return "ORDER BY " + ", ".join(preferred) if preferred else "ORDER BY rowid ASC"
    if table == "map_events":
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(map_events)").fetchall()}
        preferred = [name for name in ("source_timeframe", "timeframe", "event_time", "time", "id") if name in columns]
        return "ORDER BY " + ", ".join(preferred) if preferred else "ORDER BY rowid ASC"
    return "ORDER BY rowid ASC"


def decode_json_columns(row: dict[str, Any]) -> dict[str, Any]:
    for key in ("meta_json", "raw_payload_json", "state_json", "mos_payload_json", "anchors_json"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            try:
                row[key] = json.loads(value)
            except json.JSONDecodeError:
                pass
    return row


def sanitize_label(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip()).strip("._")
    return sanitized[:80] or "case_export"


def text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def int_or_none(value: Any) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def deterministic_file_name(case: dict[str, Any]) -> str:
    return f"{sanitize_label(case['case_ref'].replace(':', '_') + '_' + case['label'])}.json"


def source_db_label() -> str:
    return "local_source_db"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="range_library_memory.export_cases")
    parser.add_argument("--source-db", type=Path, required=True, help="Local SQLite source DB path.")
    parser.add_argument("--output-dir", type=Path, required=True, help="Folder for exported JSON files.")
    parser.add_argument("--symbol", default=None, help="Optional symbol filter.")
    parser.add_argument("--limit", type=int, default=None, help="Optional maximum number of cases to export.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    exported = export_cases(source_db=args.source_db, output_dir=args.output_dir, symbol=args.symbol, limit=args.limit)
    print(f"Exported {len(exported)} case JSON files to {args.output_dir}")
    for item in exported:
        print(f"- {item.case_ref}: {item.output_path} ranges={item.ranges} events={item.events} ledgers={item.ledgers}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
