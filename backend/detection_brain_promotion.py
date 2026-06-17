"""Promotion: suggestion review → confirmed structure + correction log."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

import candle_store
from detection_brain_store import (
    DetectorCorrection,
    ERROR_CATEGORIES,
    insert_correction,
    get_suggestion,
    utc_now_ms,
)
from detector.versions import ENGINE_SOURCE

RANGE_KINDS = frozenset({"RANGE_MAJOR", "RANGE_MINOR", "RANGE_CANDIDATE"})
BOS_KINDS = frozenset({"BOS_UP", "BOS_DOWN"})
CONFIRMED_RANGE_SCALE = "UNKNOWN"


class PromotionError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _ms_to_time_text(ms: int | None) -> str | None:
    if ms is None:
        return None
    try:
        dt = datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError, OSError):
        return None


def _snapshot_from_suggestion(row: dict[str, Any]) -> dict[str, Any]:
    return {
        k: row.get(k)
        for k in (
            "suggestion_id",
            "candidate_kind",
            "detector_version",
            "engine_source",
            "suggested_rh",
            "suggested_rl",
            "range_scale",
            "range_role",
            "event_side",
            "event_price",
            "movement_rule",
            "derived_event_code",
            "confidence",
            "meta_json",
        )
    }


def _final_values(
    suggestion: dict[str, Any],
    edits: dict[str, Any] | None,
) -> dict[str, Any]:
    edits = edits or {}
    return {
        "suggested_rh": edits.get("suggested_rh", suggestion.get("suggested_rh")),
        "suggested_rl": edits.get("suggested_rl", suggestion.get("suggested_rl")),
        "suggested_rh_time_ms": edits.get("suggested_rh_time_ms", suggestion.get("suggested_rh_time_ms")),
        "suggested_rl_time_ms": edits.get("suggested_rl_time_ms", suggestion.get("suggested_rl_time_ms")),
        "range_scale": edits.get("range_scale", suggestion.get("range_scale") or "UNKNOWN"),
        "range_role": edits.get("range_role", suggestion.get("range_role")),
        "event_price": edits.get("event_price", suggestion.get("event_price")),
        "event_side": edits.get("event_side", suggestion.get("event_side")),
    }


def _confirmed_range_fields(
    suggestion: dict[str, Any],
    final: dict[str, Any],
) -> tuple[str, str | None]:
    """
    Review confirms range validity only — never manual MAJOR/MINOR on promote.
    Derived labels come from analytics classifier later.
    """
    kind = str(suggestion.get("candidate_kind") or "").upper()
    if kind in RANGE_KINDS:
        return CONFIRMED_RANGE_SCALE, None
    return str(final.get("range_scale") or CONFIRMED_RANGE_SCALE).upper(), final.get("range_role")


def _patch_range_detection_fields(
    conn: sqlite3.Connection,
    range_id: int,
    *,
    suggestion_id: str,
    detector_version: str,
    user_action: str,
    range_scale: str | None,
    range_role: str | None,
) -> None:
    conn.execute(
        """
        UPDATE map_ranges SET
            range_scale = COALESCE(?, range_scale),
            range_scope = COALESCE(?, range_scope),
            range_role = COALESCE(?, range_role),
            confirmed_from_suggestion_id = ?,
            detector_version_at_confirm = ?,
            user_action_at_confirm = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            range_scale,
            range_scale,
            range_role,
            suggestion_id,
            detector_version,
            user_action,
            candle_store.now_iso(),
            range_id,
        ),
    )


def _patch_event_detection_fields(
    conn: sqlite3.Connection,
    event_row_id: int,
    *,
    suggestion_id: str,
    detector_version: str,
    user_action: str,
) -> None:
    conn.execute(
        """
        UPDATE map_events SET
            engine_source = ?,
            logic_version = ?,
            candidate_id = ?,
            confirmed_from_suggestion_id = ?,
            detector_version_at_confirm = ?,
            candidate_status = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            ENGINE_SOURCE,
            detector_version,
            suggestion_id,
            suggestion_id,
            detector_version,
            "ACCEPTED" if user_action in {"APPROVE", "BATCH_APPROVE"} else "EDITED",
            candle_store.now_iso(),
            event_row_id,
        ),
    )


def _promote_range(
    conn: sqlite3.Connection,
    suggestion: dict[str, Any],
    final: dict[str, Any],
    user_action: str,
) -> int:
    rh = final.get("suggested_rh")
    rl = final.get("suggested_rl")
    if rh is None or rl is None or float(rh) <= float(rl):
        raise PromotionError("Range promotion requires valid suggested_rh > suggested_rl")

    range_scale, range_role = _confirmed_range_fields(suggestion, final)
    payload = {
        "symbol": suggestion["symbol"],
        "structure_layer": suggestion["structure_layer"],
        "source_timeframe": suggestion["source_timeframe"],
        "chart_timeframe": suggestion.get("chart_timeframe") or suggestion["source_timeframe"],
        "range_scope": range_scale,
        "range_scale": range_scale,
        "parent_range_id": suggestion.get("parent_range_id"),
        "case_ref": suggestion.get("case_ref"),
        "case_id": suggestion.get("case_id"),
        "raw_case_id": suggestion.get("raw_case_id"),
        "range_high_price": float(rh),
        "range_low_price": float(rl),
        "range_high_time": _ms_to_time_text(final.get("suggested_rh_time_ms")),
        "range_low_time": _ms_to_time_text(final.get("suggested_rl_time_ms")),
        "range_start_time": _ms_to_time_text(final.get("suggested_rh_time_ms")),
        "range_end_time": _ms_to_time_text(final.get("suggested_rl_time_ms")),
        "active_from_time": _ms_to_time_text(final.get("suggested_rh_time_ms")),
        "status": "ACTIVE",
        "source": "python_detector",
        "range_key": f"detector_{suggestion['suggestion_id']}",
        "meta_json": {
            "promoted_from": "detector_suggestions",
            "suggestion_id": suggestion["suggestion_id"],
            "detector_version": suggestion["detector_version"],
            "user_action": user_action,
        },
    }
    result = candle_store.upsert_map_range(payload)
    if not result.get("ok"):
        raise PromotionError(str(result.get("error") or "range promotion failed"), int(result.get("status") or 400))

    range_id = int(result.get("range_id") or result.get("id") or (result.get("range") or {}).get("id") or 0)
    if not range_id:
        raise PromotionError("range promotion returned no range_id")

    _patch_range_detection_fields(
        conn,
        range_id,
        suggestion_id=str(suggestion["suggestion_id"]),
        detector_version=str(suggestion["detector_version"]),
        user_action=user_action,
        range_scale=range_scale,
        range_role=range_role,
    )
    return range_id


def _promote_bos(
    conn: sqlite3.Connection,
    suggestion: dict[str, Any],
    final: dict[str, Any],
    user_action: str,
) -> int:
    kind = str(suggestion["candidate_kind"]).upper()
    direction = "UP" if kind == "BOS_UP" else "DOWN"
    event_type = kind
    break_level_type = "BH" if direction == "UP" else "BL"
    event_price = final.get("event_price") or suggestion.get("event_price")
    if event_price is None:
        raise PromotionError("BOS promotion requires event_price")

    event_time = _ms_to_time_text(suggestion.get("candle_time_utc_ms")) or candle_store.now_iso()
    payload = {
        "event_id": str(uuid.uuid4()),
        "symbol": suggestion["symbol"],
        "structure_layer": suggestion["structure_layer"],
        "source_timeframe": suggestion["source_timeframe"],
        "chart_timeframe": suggestion.get("chart_timeframe") or suggestion["source_timeframe"],
        "active_range_id": suggestion.get("active_range_id"),
        "parent_range_id": suggestion.get("parent_range_id"),
        "case_ref": suggestion.get("case_ref"),
        "case_id": suggestion.get("case_id"),
        "raw_case_id": suggestion.get("raw_case_id"),
        "event_type": event_type,
        "structural_event": event_type,
        "break_level_type": break_level_type,
        "break_level_price": float(event_price),
        "break_level_time": event_time,
        "event_time": event_time,
        "event_price": float(event_price),
        "candle_time": event_time,
        "direction": direction,
        "engine_source": ENGINE_SOURCE,
        "logic_version": suggestion.get("detector_version"),
        "candidate_id": suggestion.get("suggestion_id"),
        "meta_json": {
            "promoted_from": "detector_suggestions",
            "suggestion_id": suggestion["suggestion_id"],
            "movement_rule": suggestion.get("movement_rule"),
            "derived_event_code": suggestion.get("derived_event_code"),
            "break_rule": suggestion.get("break_rule"),
            "user_action": user_action,
        },
    }
    result = candle_store.save_structural_map_event(payload)
    if not result.get("ok"):
        raise PromotionError(str(result.get("error") or "BOS promotion failed"), int(result.get("status") or 400))
    if result.get("duplicate"):
        event_row_id = int((result.get("event") or {}).get("id") or result.get("id") or 0)
    else:
        event_row_id = int(result.get("id") or (result.get("event") or {}).get("id") or 0)
    if not event_row_id:
        raise PromotionError("BOS promotion returned no event id")

    _patch_event_detection_fields(
        conn,
        event_row_id,
        suggestion_id=str(suggestion["suggestion_id"]),
        detector_version=str(suggestion["detector_version"]),
        user_action=user_action,
    )
    return event_row_id


def _mark_suggestion_reviewed(
    conn: sqlite3.Connection,
    suggestion_id: str,
    *,
    status: str,
    user_action: str,
    promoted_range_id: int | None = None,
    promoted_event_id: int | None = None,
    correction_id: str | None = None,
) -> bool:
    now_ms = utc_now_ms()
    cur = conn.execute(
        """
        UPDATE detector_suggestions
        SET status = ?,
            user_action = ?,
            reviewed_at_utc_ms = ?,
            promoted_range_id = COALESCE(?, promoted_range_id),
            promoted_event_id = COALESCE(?, promoted_event_id),
            correction_id = COALESCE(?, correction_id),
            updated_at_utc_ms = ?
        WHERE suggestion_id = ? AND status = 'PENDING'
        """,
        (
            status,
            user_action,
            now_ms,
            promoted_range_id,
            promoted_event_id,
            correction_id,
            now_ms,
            suggestion_id,
        ),
    )
    return cur.rowcount > 0


def review_suggestion(
    conn: sqlite3.Connection,
    suggestion_id: str,
    *,
    action: str,
    edits: dict[str, Any] | None = None,
    error_category: str | None = None,
    notes: str = "",
) -> dict[str, Any]:
    """APPROVE | BATCH_APPROVE | EDIT | REJECT | AUDIT_PASS | AUDIT_FAIL a suggestion."""
    action_u = str(action or "").strip().upper()
    if action_u not in {"APPROVE", "BATCH_APPROVE", "EDIT", "REJECT", "AUDIT_PASS", "AUDIT_FAIL"}:
        raise PromotionError(f"invalid action: {action}")

    suggestion = get_suggestion(conn, suggestion_id)
    if not suggestion:
        raise PromotionError("suggestion not found", 404)

    if action_u in {"AUDIT_PASS", "AUDIT_FAIL"}:
        return _record_audit_only(conn, suggestion, action_u, notes=notes)

    if action_u in {"APPROVE", "BATCH_APPROVE", "EDIT", "REJECT"} and suggestion.get("status") in {"APPROVED", "EDITED", "REJECTED"}:
        return {
            "ok": True,
            "duplicate": True,
            "suggestion": suggestion,
            "message": "suggestion already reviewed",
        }

    if action_u in {"APPROVE", "BATCH_APPROVE", "EDIT"}:
        existing = conn.execute(
            "SELECT id FROM map_ranges WHERE confirmed_from_suggestion_id = ? LIMIT 1",
            (suggestion_id,),
        ).fetchone()
        if existing:
            return {
                "ok": True,
                "duplicate": True,
                "promoted_range_id": int(existing["id"]),
                "suggestion": suggestion,
                "message": "range already promoted for suggestion",
            }

    if suggestion.get("status") != "PENDING":
        raise PromotionError(f"suggestion status {suggestion.get('status')} is not reviewable")

    suggested_snapshot = _snapshot_from_suggestion(suggestion)
    final = _final_values(suggestion, edits)
    final_snapshot = {**suggested_snapshot, **final}

    promoted_range_id: int | None = None
    promoted_event_id: int | None = None
    status = "REJECTED" if action_u == "REJECT" else ("EDITED" if action_u == "EDIT" else "APPROVED")

    if action_u in {"APPROVE", "BATCH_APPROVE", "EDIT"}:
        kind = str(suggestion.get("candidate_kind") or "").upper()
        if kind in RANGE_KINDS:
            promoted_range_id = _promote_range(conn, suggestion, final, action_u)
        elif kind in BOS_KINDS:
            promoted_event_id = _promote_bos(conn, suggestion, final, action_u)
        else:
            status = "APPROVED" if action_u == "APPROVE" else "EDITED"

    if action_u in {"APPROVE", "BATCH_APPROVE"}:
        category = "NO_ERROR"
    else:
        category = str(error_category or "OTHER").strip().upper()
        if category not in ERROR_CATEGORIES or category == "NO_ERROR":
            if action_u == "EDIT":
                category = "WRONG_RH" if suggestion.get("candidate_kind", "").startswith("RANGE") else "WRONG_BOS"
            else:
                category = "OTHER"
        if not notes and category == "OTHER":
            notes = "rejected by user"

    correction_id = str(uuid.uuid4())
    insert_correction(
        conn,
        DetectorCorrection(
            correction_id=correction_id,
            suggestion_id=suggestion_id,
            session_id=suggestion.get("session_id"),
            candidate_kind=str(suggestion.get("candidate_kind")),
            detector_version=str(suggestion.get("detector_version")),
            symbol=str(suggestion.get("symbol")),
            structure_layer=str(suggestion.get("structure_layer")),
            source_timeframe=str(suggestion.get("source_timeframe")),
            user_action=action_u,
            error_category=category,
            notes=notes,
            suggested_snapshot_json=suggested_snapshot,
            final_snapshot_json=final_snapshot if action_u in {"APPROVE", "BATCH_APPROVE", "EDIT"} else None,
            promoted_range_id=promoted_range_id,
            promoted_event_id=promoted_event_id,
            created_at_utc_ms=utc_now_ms(),
        ),
    )

    updated = _mark_suggestion_reviewed(
        conn,
        suggestion_id,
        status=status,
        user_action=action_u,
        promoted_range_id=promoted_range_id,
        promoted_event_id=promoted_event_id,
        correction_id=correction_id,
    )
    if not updated:
        raise PromotionError("suggestion was already reviewed by another request", 409)

    conn.commit()
    refreshed = get_suggestion(conn, suggestion_id)
    return {
        "ok": True,
        "action": action_u,
        "status": status,
        "correction_id": correction_id,
        "promoted_range_id": promoted_range_id,
        "promoted_event_id": promoted_event_id,
        "suggestion": refreshed,
    }


def _record_audit_only(
    conn: sqlite3.Connection,
    suggestion: dict[str, Any],
    action_u: str,
    *,
    notes: str = "",
) -> dict[str, Any]:
    """Visual audit pass/fail — correction log only, no promotion."""
    import uuid

    suggested_snapshot = _snapshot_from_suggestion(suggestion)
    category = "NO_ERROR" if action_u == "AUDIT_PASS" else "OTHER"
    if action_u == "AUDIT_FAIL" and not notes:
        notes = "visual audit failed"
    correction_id = str(uuid.uuid4())
    insert_correction(
        conn,
        DetectorCorrection(
            correction_id=correction_id,
            suggestion_id=str(suggestion["suggestion_id"]),
            session_id=suggestion.get("session_id"),
            candidate_kind=str(suggestion.get("candidate_kind")),
            detector_version=str(suggestion.get("detector_version")),
            symbol=str(suggestion.get("symbol")),
            structure_layer=str(suggestion.get("structure_layer")),
            source_timeframe=str(suggestion.get("source_timeframe")),
            user_action=action_u,
            error_category=category,
            notes=notes,
            suggested_snapshot_json=suggested_snapshot,
            final_snapshot_json=None,
            promoted_range_id=suggestion.get("promoted_range_id"),
            promoted_event_id=suggestion.get("promoted_event_id"),
            created_at_utc_ms=utc_now_ms(),
        ),
    )
    conn.commit()
    return {
        "ok": True,
        "action": action_u,
        "audit_only": True,
        "correction_id": correction_id,
        "suggestion": get_suggestion(conn, str(suggestion["suggestion_id"])),
    }


def reject_suggestion(
    conn: sqlite3.Connection,
    suggestion_id: str,
    *,
    error_category: str = "OTHER",
    notes: str = "",
) -> dict[str, Any]:
    return review_suggestion(
        conn,
        suggestion_id,
        action="REJECT",
        error_category=error_category,
        notes=notes,
    )
