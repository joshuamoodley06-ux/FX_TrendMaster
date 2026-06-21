#!/usr/bin/env python3
"""Local research weekly seed helpers — map_ranges only, no detector changes."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from typing import Any

import candle_store
from detection_brain_schema import init_detection_brain_schema


def _open_research_conn(db_path: str | None) -> sqlite3.Connection:
    if db_path:
        candle_store.DB_PATH = db_path  # type: ignore[assignment]
    candle_store.init_db()
    conn = sqlite3.connect(str(candle_store.ensure_db_path()), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA journal_mode = WAL")
    init_detection_brain_schema(conn)
    return conn


def _connect(db_path: str | None) -> sqlite3.Connection:
    return _open_research_conn(db_path)


def _weekly_scope(symbol: str) -> tuple[str, str, str]:
    return str(symbol).upper(), "WEEKLY", "W1"


def has_active_weekly_seed(conn: sqlite3.Connection, symbol: str) -> dict[str, Any]:
    sym, layer, tf = _weekly_scope(symbol)
    row = conn.execute(
        """
        SELECT id, range_high_price, range_low_price, range_scale, status, source, user_action_at_confirm
        FROM map_ranges
        WHERE symbol = ?
          AND UPPER(COALESCE(status, 'ACTIVE')) = 'ACTIVE'
          AND LOWER(COALESCE(status, '')) != 'archived'
          AND COALESCE(structure_layer, layer) = ?
          AND COALESCE(source_timeframe, timeframe) = ?
        ORDER BY id ASC
        LIMIT 2
        """,
        (sym, layer, tf),
    ).fetchall()
    if not row:
        return {"ok": True, "has_seed": False, "count": 0, "seed": None}
    if len(row) > 1:
        return {
            "ok": True,
            "has_seed": False,
            "count": len(row),
            "error": "MULTIPLE_ACTIVE_RANGES",
            "seed": None,
        }
    seed = dict(row[0])
    rh = seed.get("range_high_price")
    rl = seed.get("range_low_price")
    valid = rh is not None and rl is not None and float(rh) > float(rl)
    return {
        "ok": True,
        "has_seed": valid,
        "count": 1,
        "seed": {
            "id": seed["id"],
            "range_high_price": rh,
            "range_low_price": rl,
            "range_scale": seed.get("range_scale"),
            "status": seed.get("status"),
            "source": seed.get("source"),
            "user_action_at_confirm": seed.get("user_action_at_confirm"),
        },
    }


def list_weekly_ranges(conn: sqlite3.Connection, symbol: str, *, limit: int = 100) -> list[dict[str, Any]]:
    sym, layer, tf = _weekly_scope(symbol)
    rows = conn.execute(
        """
        SELECT id, status, range_high_price, range_low_price, range_high_time, range_low_time,
               range_scale, source, user_action_at_confirm, created_at, updated_at
        FROM map_ranges
        WHERE symbol = ?
          AND COALESCE(structure_layer, layer) = ?
          AND COALESCE(source_timeframe, timeframe) = ?
          AND LOWER(COALESCE(status, '')) != 'archived'
        ORDER BY id DESC
        LIMIT ?
        """,
        (sym, layer, tf, max(1, min(int(limit), 500))),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        rh = item.get("range_high_price")
        rl = item.get("range_low_price")
        item["selectable"] = rh is not None and rl is not None and float(rh) > float(rl)
        out.append(item)
    return out


def _deactivate_other_weekly_seeds(conn: sqlite3.Connection, symbol: str, keep_id: int) -> int:
    sym, layer, tf = _weekly_scope(symbol)
    cur = conn.execute(
        """
        UPDATE map_ranges
        SET status = 'INACTIVE', updated_at = ?
        WHERE symbol = ?
          AND COALESCE(structure_layer, layer) = ?
          AND COALESCE(source_timeframe, timeframe) = ?
          AND id != ?
          AND UPPER(COALESCE(status, 'ACTIVE')) = 'ACTIVE'
        """,
        (candle_store.now_iso(), sym, layer, tf, int(keep_id)),
    )
    conn.commit()
    return int(cur.rowcount or 0)


def create_manual_weekly_seed(
    *,
    symbol: str,
    range_high_price: float,
    range_low_price: float,
    range_high_time: str | None = None,
    range_low_time: str | None = None,
    db_path: str | None = None,
) -> dict[str, Any]:
    sym, layer, tf = _weekly_scope(symbol)
    rh = float(range_high_price)
    rl = float(range_low_price)
    if not (rh > rl):
        return {"ok": False, "error": "range_high_price must be greater than range_low_price"}

    meta = {
        "engine_source": "manual",
        "weekly_research_seed": True,
    }
    conn = _open_research_conn(db_path)
    try:
        now = candle_store.now_iso()
        meta_json = json.dumps(meta, ensure_ascii=False)
        conn.execute(
            """
            INSERT INTO map_ranges (
                symbol, timeframe, source_timeframe, structure_layer, layer, chart_timeframe,
                range_high, range_low, range_high_price, range_low_price,
                range_high_time, range_low_time,
                status, range_key, range_scope, range_scale,
                source, user_action_at_confirm, meta_json,
                structure_version, parent_link_status,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sym,
                tf,
                tf,
                layer,
                layer,
                tf,
                rh,
                rl,
                rh,
                rl,
                range_high_time,
                range_low_time,
                "ACTIVE",
                "weekly_research_seed",
                "UNKNOWN",
                "UNKNOWN",
                "manual",
                "MANUAL_SEED",
                meta_json,
                "STRUCTURE_ONLY_V1",
                "NEEDS_REVIEW",
                now,
                now,
            ),
        )
        range_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        conn.commit()
        _deactivate_other_weekly_seeds(conn, sym, range_id)
        check = has_active_weekly_seed(conn, sym)
        return {
            "ok": True,
            "action": "create_manual",
            "range_id": range_id,
            "deactivated_others": True,
            "seed": check.get("seed"),
            "has_seed": check.get("has_seed"),
        }
    finally:
        conn.close()


def _top_counts(counts: dict[str, int], n: int = 5) -> dict[str, int]:
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return {key: value for key, value in ordered[: max(1, int(n))]}


def _diagnose_hint(
    lifecycle_counts: dict[str, int],
    reason_counts: dict[str, int],
    *,
    has_seed: bool,
) -> str:
    if not has_seed:
        return (
            "No ACTIVE W1 seed was found in map_ranges. RANGE_V2 needs a seed RH/RL box "
            "before it can evaluate BOS → reclaim cycles."
        )
    top_lifecycle = max(lifecycle_counts, key=lifecycle_counts.get) if lifecycle_counts else ""
    top_reason = max(reason_counts, key=reason_counts.get) if reason_counts else ""
    if top_lifecycle in {"BREACHED_UP", "BREACHED_DOWN"} or "reclaim not yet confirmed" in top_reason.lower():
        return (
            "Most weeks broke the seed boundary but reclaim has not completed yet. "
            "On W1/D1/H4/H1 a wick tag back to the old RH/RL completes reclaim; "
            "M15 requires a body close back inside the box."
        )
    if top_lifecycle in {"RECLAIMED_UP", "RECLAIMED_DOWN"} or "opposite swing" in top_reason.lower():
        return (
            "Some weeks completed BOS → reclaim, but RANGE_V2 could not pick a clear opposite swing "
            "for the new RH/RL. That is the step after reclaim — eyeball structure can look valid "
            "while the detector still marks the boundary as unclear."
        )
    if top_lifecycle in {"SEEDED", "ACTIVE_RANGE", "SEED_ONLY_NO_BOS"}:
        return (
            "At most replay steps the seed box never saw a qualifying BOS inside the scan window. "
            "Check that your seed RH/RL wraps the structure you are watching — if the box is too tight "
            "or too wide, breaks may not register the way you expect on W1."
        )
    if top_lifecycle == "NO_VALID_RANGE" and "no seed" in top_reason.lower():
        return "Scan steps reported missing seed context even though a seed may exist now — re-run after saving seed."
    return (
        "RANGE_V2 only promotes when seed RH/RL → BOS → weekly close reclaim → opposite swing boundaries "
        "all complete in the same cycle. Visual structure on the chart can be ahead of what the detector "
        "has confirmed at each weekly replay step."
    )


def diagnose_historical_scan(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    detection_run_id: str,
) -> dict[str, Any]:
    run_id = str(detection_run_id or "").strip()
    if not run_id:
        return {"ok": False, "error": "detection_run_id is required"}

    rows = conn.execute(
        """
        SELECT candidate_kind, reason_text, meta_json, candle_time_utc_ms
        FROM detector_suggestions
        WHERE json_extract(meta_json, '$.detection_run_id') = ?
          AND (
            json_extract(meta_json, '$.historical_scan') = 1
            OR json_extract(meta_json, '$.historical_chain') = 1
          )
        ORDER BY created_at_utc_ms ASC
        """,
        (run_id,),
    ).fetchall()
    if not rows:
        return {"ok": False, "error": f"No historical_scan suggestions for run {run_id}"}

    lifecycle_counts: dict[str, int] = {}
    reason_counts: dict[str, int] = {}
    boundary_counts: dict[str, int] = {}
    seed_source_counts: dict[str, int] = {}
    range_candidates = 0
    no_valid_range = 0
    closest_week: dict[str, Any] | None = None
    closest_rank = -1

    def _rank_lifecycle(state: str) -> int:
        order = {
            "RECLAIMED_UP": 5,
            "RECLAIMED_DOWN": 5,
            "BREACHED_UP": 4,
            "BREACHED_DOWN": 4,
            "SEEDED": 2,
            "ACTIVE_RANGE": 2,
            "SEED_ONLY_NO_BOS": 1,
        }
        return order.get(state, 0)

    for row in rows:
        kind = str(row["candidate_kind"] or "").upper()
        if kind == "RANGE_CANDIDATE":
            range_candidates += 1
        if kind == "NO_VALID_RANGE":
            no_valid_range += 1

        meta_raw = row["meta_json"]
        try:
            meta = json.loads(meta_raw) if isinstance(meta_raw, str) else (meta_raw or {})
        except json.JSONDecodeError:
            meta = {}

        life = str(meta.get("lifecycle_state") or "UNKNOWN")
        lifecycle_counts[life] = lifecycle_counts.get(life, 0) + 1

        reason = str(row["reason_text"] or "unknown").strip() or "unknown"
        reason_counts[reason] = reason_counts.get(reason, 0) + 1

        boundary = str(meta.get("boundary_selection_reason") or "").strip() or "none"
        boundary_counts[boundary] = boundary_counts.get(boundary, 0) + 1

        seed_src = str(meta.get("seed_source") or "unknown")
        seed_source_counts[seed_src] = seed_source_counts.get(seed_src, 0) + 1

        if kind == "NO_VALID_RANGE":
            rank = _rank_lifecycle(life)
            if rank > closest_rank:
                closest_rank = rank
                closest_week = {
                    "lifecycle_state": life,
                    "reason_text": reason,
                    "replay_until_time": meta.get("replay_until_time"),
                    "replay_until_time_ms": meta.get("replay_until_time_ms"),
                    "broken_boundary": meta.get("broken_boundary"),
                    "bos_candle_index": meta.get("bos_candle_index"),
                    "reclaim_candle_index": meta.get("reclaim_candle_index"),
                    "boundary_selection_reason": meta.get("boundary_selection_reason"),
                    "seed_source": meta.get("seed_source"),
                }

    seed_check = has_active_weekly_seed(conn, symbol)
    has_seed = bool(seed_check.get("has_seed"))
    return {
        "ok": True,
        "action": "diagnose-scan",
        "symbol": str(symbol).upper(),
        "detection_run_id": run_id,
        "total_suggestions": len(rows),
        "range_candidate_count": range_candidates,
        "no_valid_range_count": no_valid_range,
        "lifecycle_state_counts": lifecycle_counts,
        "reason_text_counts": _top_counts(reason_counts),
        "boundary_selection_counts": _top_counts(boundary_counts),
        "seed_source_counts": seed_source_counts,
        "has_seed": has_seed,
        "seed": seed_check.get("seed"),
        "closest_week": closest_week,
        "hint": _diagnose_hint(lifecycle_counts, reason_counts, has_seed=has_seed),
    }


def activate_weekly_seed(conn: sqlite3.Connection, *, symbol: str, range_id: int) -> dict[str, Any]:
    sym, layer, tf = _weekly_scope(symbol)
    row = conn.execute(
        """
        SELECT id, range_high_price, range_low_price
        FROM map_ranges
        WHERE id = ? AND symbol = ?
          AND COALESCE(structure_layer, layer) = ?
          AND COALESCE(source_timeframe, timeframe) = ?
        """,
        (int(range_id), sym, layer, tf),
    ).fetchone()
    if row is None:
        return {"ok": False, "error": "Range not found for WEEKLY/W1 scope"}
    rh = row["range_high_price"]
    rl = row["range_low_price"]
    if rh is None or rl is None or float(rh) <= float(rl):
        return {"ok": False, "error": "Selected range has invalid RH/RL"}

    conn.execute(
        """
        UPDATE map_ranges
        SET status = 'ACTIVE', inactive_from_time = NULL, broken_by_event_id = NULL,
            direction_of_break = NULL, updated_at = ?
        WHERE id = ?
        """,
        (candle_store.now_iso(), int(range_id)),
    )
    conn.commit()
    _deactivate_other_weekly_seeds(conn, sym, int(range_id))
    check = has_active_weekly_seed(conn, sym)
    return {
        "ok": True,
        "action": "activate",
        "range_id": int(range_id),
        "has_seed": check.get("has_seed"),
        "seed": check.get("seed"),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local research weekly seed setup")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common_args(cmd: argparse.ArgumentParser) -> None:
        cmd.add_argument("--db", default=None)
        cmd.add_argument("--json", action="store_true")
        cmd.add_argument("--symbol", default="XAUUSD")

    check = sub.add_parser("check", help="Check ACTIVE WEEKLY/W1 seed")
    add_common_args(check)

    listing = sub.add_parser("list", help="List WEEKLY/W1 ranges")
    add_common_args(listing)
    listing.add_argument("--limit", type=int, default=100)

    create = sub.add_parser("create-manual", help="Create manual weekly seed from RH/RL")
    add_common_args(create)
    create.add_argument("--range-high", type=float, required=True)
    create.add_argument("--range-low", type=float, required=True)
    create.add_argument("--range-high-time", default=None)
    create.add_argument("--range-low-time", default=None)

    activate = sub.add_parser("activate", help="Activate existing weekly range as seed")
    add_common_args(activate)
    activate.add_argument("--range-id", type=int, required=True)

    diagnose = sub.add_parser("diagnose-scan", help="Summarize NO_VALID_RANGE reasons for a scan run")
    add_common_args(diagnose)
    diagnose.add_argument("--detection-run-id", required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "create-manual":
        out = create_manual_weekly_seed(
            symbol=args.symbol,
            range_high_price=args.range_high,
            range_low_price=args.range_low,
            range_high_time=args.range_high_time,
            range_low_time=args.range_low_time,
            db_path=args.db,
        )
    else:
        conn = _connect(args.db)
        try:
            if args.command == "check":
                out = has_active_weekly_seed(conn, args.symbol)
            elif args.command == "list":
                ranges = list_weekly_ranges(conn, args.symbol, limit=args.limit)
                out = {"ok": True, "symbol": str(args.symbol).upper(), "count": len(ranges), "ranges": ranges}
            elif args.command == "activate":
                out = activate_weekly_seed(conn, symbol=args.symbol, range_id=args.range_id)
            elif args.command == "diagnose-scan":
                out = diagnose_historical_scan(
                    conn,
                    symbol=args.symbol,
                    detection_run_id=args.detection_run_id,
                )
            else:
                out = {"ok": False, "error": f"Unknown command: {args.command}"}
        finally:
            conn.close()

    if args.json:
        print(json.dumps(out, indent=2, default=str))
    else:
        print(out)
    return 0 if out.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
