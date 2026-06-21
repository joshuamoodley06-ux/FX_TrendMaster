"""Random visual audit sampler for suggestions and confirmed ranges."""

from __future__ import annotations

import random
import sqlite3
from dataclasses import dataclass
from typing import Any, Literal

AuditSource = Literal["suggestions", "confirmed_ranges"]


@dataclass
class RandomAuditFilters:
    symbol: str
    source_timeframe: str
    structure_layer: str
    date_from_ms: int | None = None
    date_to_ms: int | None = None
    limit: int = 5
    source: AuditSource = "suggestions"
    candidate_kind: str = "RANGE_CANDIDATE"
    detector_version: str | None = None
    detection_run_id: str | None = None


def _json_loads(raw: Any) -> dict[str, Any]:
    import json

    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else {}
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def _ms_to_time_text(ms: int | None) -> str | None:
    if ms is None:
        return None
    from datetime import datetime, timezone

    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError, OSError):
        return None


def _suggestion_audit_row(row: dict[str, Any]) -> dict[str, Any]:
    meta = row.get("meta_json") or {}
    rh = row.get("suggested_rh")
    rl = row.get("suggested_rl")
    replay_until = meta.get("replay_until_time") or _ms_to_time_text(meta.get("replay_until_time_ms"))
    rl_time = _ms_to_time_text(row.get("suggested_rl_time_ms"))
    rh_time = _ms_to_time_text(row.get("suggested_rh_time_ms"))
    range_start = rl_time or replay_until or meta.get("first_candle_time")
    range_end = rh_time or replay_until or meta.get("last_candle_time")
    return {
        "source": "suggestions",
        "id": row.get("suggestion_id"),
        "suggestion_id": row.get("suggestion_id"),
        "range_id": row.get("promoted_range_id"),
        "candidate_kind": row.get("candidate_kind"),
        "rh": rh,
        "rl": rl,
        "range_high_price": rh,
        "range_low_price": rl,
        "symbol": row.get("symbol"),
        "structure_layer": row.get("structure_layer"),
        "source_timeframe": row.get("source_timeframe"),
        "chart_timeframe": row.get("chart_timeframe") or row.get("source_timeframe"),
        "detector_version": row.get("detector_version"),
        "replay_until_time": replay_until,
        "replay_until_time_ms": meta.get("replay_until_time_ms"),
        "first_candle_time": meta.get("first_candle_time"),
        "last_candle_time": meta.get("last_candle_time"),
        "lifecycle_state": meta.get("lifecycle_state"),
        "boundary_selection_reason": meta.get("boundary_selection_reason"),
        "range_start_time": range_start,
        "range_end_time": range_end,
        "retracement_percent": meta.get("retracement_percent"),
        "retracement_class": meta.get("retracement_class"),
        "retracement_price": meta.get("retracement_price"),
        "retracement_time_ms": meta.get("retracement_time_ms"),
        "bos_candle_index": meta.get("bos_candle_index"),
        "reclaim_candle_index": meta.get("reclaim_candle_index"),
        "status": row.get("status"),
        "meta_json": meta,
    }


def _confirmed_range_audit_row(row: dict[str, Any]) -> dict[str, Any]:
    meta = _json_loads(row.get("meta_json"))
    return {
        "source": "confirmed_ranges",
        "id": row.get("id"),
        "range_id": row.get("id"),
        "suggestion_id": row.get("confirmed_from_suggestion_id"),
        "candidate_kind": "RANGE_CANDIDATE",
        "rh": row.get("range_high_price"),
        "rl": row.get("range_low_price"),
        "range_high_price": row.get("range_high_price"),
        "range_low_price": row.get("range_low_price"),
        "symbol": row.get("symbol"),
        "structure_layer": row.get("structure_layer"),
        "source_timeframe": row.get("timeframe") or row.get("source_timeframe"),
        "chart_timeframe": row.get("chart_timeframe") or row.get("timeframe"),
        "detector_version": row.get("detector_version_at_confirm"),
        "replay_until_time": meta.get("replay_until_time"),
        "replay_until_time_ms": meta.get("replay_until_time_ms"),
        "lifecycle_state": meta.get("lifecycle_state"),
        "boundary_selection_reason": meta.get("boundary_selection_reason"),
        "range_start_time": row.get("range_start_time") or row.get("range_high_time") or row.get("active_from_time"),
        "range_end_time": row.get("range_end_time") or row.get("range_low_time"),
        "range_scale": row.get("range_scale"),
        "status": row.get("status"),
        "meta_json": meta,
    }


def _query_suggestion_pool(conn: sqlite3.Connection, filters: RandomAuditFilters) -> list[dict[str, Any]]:
    clauses = [
        "symbol = ?",
        "structure_layer = ?",
        "source_timeframe = ?",
        "candidate_kind = ?",
    ]
    params: list[Any] = [
        filters.symbol.upper(),
        filters.structure_layer.upper(),
        filters.source_timeframe.upper(),
        str(filters.candidate_kind or "RANGE_CANDIDATE").upper(),
    ]
    if filters.date_from_ms is not None:
        clauses.append("candle_time_utc_ms >= ?")
        params.append(int(filters.date_from_ms))
    if filters.date_to_ms is not None:
        clauses.append("candle_time_utc_ms <= ?")
        params.append(int(filters.date_to_ms))
    if filters.detector_version:
        clauses.append("detector_version = ?")
        params.append(str(filters.detector_version))

    rows = conn.execute(
        f"""
        SELECT *
        FROM detector_suggestions
        WHERE {' AND '.join(clauses)}
        ORDER BY candle_time_utc_ms ASC
        """,
        params,
    ).fetchall()

    out: list[dict[str, Any]] = []
    run_id = str(filters.detection_run_id or "").strip() or None
    for row in rows:
        item = dict(row)
        item["meta_json"] = _json_loads(item.get("meta_json"))
        if run_id and str((item.get("meta_json") or {}).get("detection_run_id") or "") != run_id:
            continue
        rh = item.get("suggested_rh")
        rl = item.get("suggested_rl")
        try:
            if rh is None or rl is None or float(rh) <= float(rl):
                continue
        except (TypeError, ValueError):
            continue
        out.append(item)
    return out


def _parse_time_ms(value: Any) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    from datetime import datetime, timezone

    text = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(text[: len(fmt.replace("%", "0"))], fmt).replace(tzinfo=timezone.utc)
            return int(dt.timestamp() * 1000)
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    except ValueError:
        return None


def _query_confirmed_pool(conn: sqlite3.Connection, filters: RandomAuditFilters) -> list[dict[str, Any]]:
    tf = filters.source_timeframe.upper()
    clauses = [
        "symbol = ?",
        "structure_layer = ?",
        "(timeframe = ? OR source_timeframe = ?)",
        "confirmed_from_suggestion_id IS NOT NULL",
        "confirmed_from_suggestion_id != ''",
    ]
    params: list[Any] = [
        filters.symbol.upper(),
        filters.structure_layer.upper(),
        tf,
        tf,
    ]
    if filters.detector_version:
        clauses.append("detector_version_at_confirm = ?")
        params.append(str(filters.detector_version))

    rows = conn.execute(
        f"""
        SELECT *
        FROM map_ranges
        WHERE {' AND '.join(clauses)}
        ORDER BY id ASC
        """,
        params,
    ).fetchall()

    out: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        if filters.date_from_ms is not None or filters.date_to_ms is not None:
            time_ms = (
                _parse_time_ms(item.get("range_start_time"))
                or _parse_time_ms(item.get("range_high_time"))
                or _parse_time_ms(item.get("active_from_time"))
            )
            if time_ms is None:
                continue
            if filters.date_from_ms is not None and time_ms < int(filters.date_from_ms):
                continue
            if filters.date_to_ms is not None and time_ms > int(filters.date_to_ms):
                continue
        try:
            rh = float(item.get("range_high_price") or 0)
            rl = float(item.get("range_low_price") or 0)
            if rh <= rl:
                continue
        except (TypeError, ValueError):
            continue
        out.append(item)
    return out


def sample_random_audit_rows(
    conn: sqlite3.Connection,
    filters: RandomAuditFilters,
) -> dict[str, Any]:
    limit = max(1, min(int(filters.limit or 5), 100))
    if filters.source == "confirmed_ranges":
        pool = _query_confirmed_pool(conn, filters)
        mapper = _confirmed_range_audit_row
    else:
        pool = _query_suggestion_pool(conn, filters)
        mapper = _suggestion_audit_row

    if not pool:
        return {
            "ok": True,
            "count": 0,
            "pool_size": 0,
            "samples": [],
            "filters": {
                "symbol": filters.symbol.upper(),
                "source_timeframe": filters.source_timeframe.upper(),
                "structure_layer": filters.structure_layer.upper(),
                "source": filters.source,
                "limit": limit,
            },
        }

    n = min(limit, len(pool))
    if filters.detection_run_id:
        picked = pool[:n]
    else:
        picked = random.sample(pool, n)
    samples = [mapper(item) for item in picked]
    return {
        "ok": True,
        "count": len(samples),
        "pool_size": len(pool),
        "samples": samples,
        "filters": {
            "symbol": filters.symbol.upper(),
            "source_timeframe": filters.source_timeframe.upper(),
            "structure_layer": filters.structure_layer.upper(),
            "source": filters.source,
            "candidate_kind": filters.candidate_kind,
            "detector_version": filters.detector_version,
            "detection_run_id": filters.detection_run_id,
            "limit": limit,
            "date_from_ms": filters.date_from_ms,
            "date_to_ms": filters.date_to_ms,
        },
    }
