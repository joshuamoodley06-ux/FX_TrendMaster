"""Export detector run audit bundles for offline review and tuning."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from detection_brain_random_audit import RandomAuditFilters, _query_suggestion_pool, _suggestion_audit_row


def _json_loads(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else {}
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def _final_rh_rl_for_suggestion(
    conn: sqlite3.Connection,
    suggestion_id: str,
    promoted_range_id: Any,
) -> tuple[float | None, float | None]:
    """Resolved RH/RL after user review — corrections final snapshot, else map_ranges."""
    corr = conn.execute(
        """
        SELECT final_snapshot_json
        FROM detector_corrections
        WHERE suggestion_id = ?
          AND user_action IN ('APPROVE', 'BATCH_APPROVE', 'EDIT')
          AND final_snapshot_json IS NOT NULL
        ORDER BY created_at_utc_ms DESC
        LIMIT 1
        """,
        (suggestion_id,),
    ).fetchone()
    if corr:
        final = _json_loads(corr["final_snapshot_json"])
        rh = final.get("suggested_rh")
        rl = final.get("suggested_rl")
        if rh is not None and rl is not None:
            try:
                return float(rh), float(rl)
            except (TypeError, ValueError):
                pass
    if promoted_range_id not in (None, ""):
        try:
            row = conn.execute(
                """
                SELECT range_high_price, range_low_price, range_high, range_low
                FROM map_ranges WHERE id = ? LIMIT 1
                """,
                (int(promoted_range_id),),
            ).fetchone()
            if row:
                rh = row["range_high_price"] if row["range_high_price"] is not None else row["range_high"]
                rl = row["range_low_price"] if row["range_low_price"] is not None else row["range_low"]
                if rh is not None and rl is not None:
                    return float(rh), float(rl)
        except (TypeError, ValueError):
            pass
    return None, None


def list_suggestions_for_run(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    structure_layer: str,
    source_timeframe: str,
    detection_run_id: str,
    candidate_kind: str = "RANGE_CANDIDATE",
) -> list[dict[str, Any]]:
    filters = RandomAuditFilters(
        symbol=str(symbol).upper(),
        structure_layer=str(structure_layer).upper(),
        source_timeframe=str(source_timeframe).upper(),
        detection_run_id=str(detection_run_id),
        candidate_kind=str(candidate_kind or "RANGE_CANDIDATE").upper(),
        limit=500,
    )
    pool = _query_suggestion_pool(conn, filters)
    rows: list[dict[str, Any]] = []
    for item in pool:
        row = dict(item)
        row["meta_json"] = _json_loads(row.get("meta_json"))
        audit = _suggestion_audit_row(row)
        audit["status"] = row.get("status")
        audit["promoted_range_id"] = row.get("promoted_range_id")
        audit["reason_text"] = row.get("reason_text")
        sid = str(row.get("suggestion_id") or audit.get("suggestion_id") or "")
        status = str(row.get("status") or "").upper()
        if sid and status in {"APPROVED", "EDITED"}:
            final_rh, final_rl = _final_rh_rl_for_suggestion(
                conn, sid, row.get("promoted_range_id"),
            )
            if final_rh is not None and final_rl is not None:
                audit["rh"] = final_rh
                audit["rl"] = final_rl
                audit["range_high_price"] = final_rh
                audit["range_low_price"] = final_rl
                meta = audit.get("meta_json") if isinstance(audit.get("meta_json"), dict) else {}
                meta = dict(meta)
                if row.get("suggested_rh") is not None:
                    meta.setdefault("detector_suggested_rh", row.get("suggested_rh"))
                if row.get("suggested_rl") is not None:
                    meta.setdefault("detector_suggested_rl", row.get("suggested_rl"))
                audit["meta_json"] = meta
        rows.append(audit)
    rows.sort(
        key=lambda r: (
            int(r.get("replay_until_time_ms") or 0),
            str(r.get("suggestion_id") or r.get("id") or ""),
        ),
    )
    return rows


def _corrections_for_suggestions(
    conn: sqlite3.Connection,
    suggestion_ids: list[str],
) -> list[dict[str, Any]]:
    if not suggestion_ids:
        return []
    placeholders = ",".join("?" for _ in suggestion_ids)
    rows = conn.execute(
        f"""
        SELECT *
        FROM detector_corrections
        WHERE suggestion_id IN ({placeholders})
        ORDER BY created_at_utc_ms ASC
        """,
        suggestion_ids,
    ).fetchall()
    return [dict(row) for row in rows]


def find_latest_detection_run_id(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    structure_layer: str,
    source_timeframe: str,
    candidate_kind: str = "RANGE_CANDIDATE",
) -> str | None:
    rows = conn.execute(
        """
        SELECT meta_json, created_at_utc_ms
        FROM detector_suggestions
        WHERE symbol = ?
          AND structure_layer = ?
          AND source_timeframe = ?
          AND candidate_kind = ?
        ORDER BY created_at_utc_ms DESC
        LIMIT 500
        """,
        (
            str(symbol).upper(),
            str(structure_layer).upper(),
            str(source_timeframe).upper(),
            str(candidate_kind or "RANGE_CANDIDATE").upper(),
        ),
    ).fetchall()
    latest_run: str | None = None
    latest_ms = -1
    for row in rows:
        meta = _json_loads(row["meta_json"])
        run_id = str(meta.get("detection_run_id") or "").strip()
        if not run_id:
            continue
        created_ms = int(row["created_at_utc_ms"] or 0)
        if created_ms >= latest_ms:
            latest_ms = created_ms
            latest_run = run_id
    return latest_run


def build_detection_run_audit_export(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    structure_layer: str,
    source_timeframe: str,
    detection_run_id: str,
    candidate_kind: str = "RANGE_CANDIDATE",
) -> dict[str, Any]:
    suggestions = list_suggestions_for_run(
        conn,
        symbol=symbol,
        structure_layer=structure_layer,
        source_timeframe=source_timeframe,
        detection_run_id=detection_run_id,
        candidate_kind=candidate_kind,
    )
    suggestion_ids = [
        str(s.get("suggestion_id") or s.get("id") or "")
        for s in suggestions
        if s.get("suggestion_id") or s.get("id")
    ]
    corrections = _corrections_for_suggestions(conn, suggestion_ids)

    status_counts: dict[str, int] = {}
    for row in conn.execute(
        """
        SELECT status, COUNT(*) AS n
        FROM detector_suggestions
        WHERE symbol = ? AND structure_layer = ? AND source_timeframe = ?
        GROUP BY status
        """,
        (symbol.upper(), structure_layer.upper(), source_timeframe.upper()),
    ):
        status_counts[str(row["status"] or "UNKNOWN")] = int(row["n"])

    lifecycle_counts: dict[str, int] = {}
    for s in suggestions:
        state = str(s.get("lifecycle_state") or "UNKNOWN")
        lifecycle_counts[state] = lifecycle_counts.get(state, 0) + 1

    error_counts: dict[str, int] = {}
    for c in corrections:
        if str(c.get("user_action") or "").upper() != "REJECT":
            continue
        cat = str(c.get("error_category") or "OTHER")
        error_counts[cat] = error_counts.get(cat, 0) + 1

    return {
        "ok": True,
        "schema": "detection_run_audit_v1",
        "symbol": symbol.upper(),
        "structure_layer": structure_layer.upper(),
        "source_timeframe": source_timeframe.upper(),
        "detection_run_id": detection_run_id,
        "candidate_kind": candidate_kind.upper(),
        "counts": {
            "suggestions_in_run": len(suggestions),
            "corrections": len(corrections),
            "status_all_symbol_tf": status_counts,
            "lifecycle_in_run": lifecycle_counts,
            "reject_error_categories": error_counts,
        },
        "suggestions": suggestions,
        "corrections": corrections,
    }
