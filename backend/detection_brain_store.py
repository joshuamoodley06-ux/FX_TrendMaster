"""Phase 1 Detection Brain storage helpers.

CRUD foundations only — no detector logic, no promotion workflow, no API routes.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from detection_brain_schema import DETECTION_BRAIN_SCHEMA

RANGE_SCALES = frozenset({"MAJOR", "MINOR"})
RANGE_ROLES = frozenset({"ACTIVE_CONTAINER", "INTERNAL_LEG", "EXPANSION_LEG"})
INTERNAL_STRUCTURE_STATUSES = frozenset({"HAS_MINORS", "NO_MINOR_STRUCTURE", "UNKNOWN"})
ENGINE_SOURCES = frozenset({"python_detector", "electron_legacy", "manual", "import"})
SUGGESTION_STATUSES = frozenset({"PENDING", "APPROVED", "REJECTED", "EDITED", "SUPERSEDED", "EXPIRED"})
USER_ACTIONS = frozenset({"APPROVE", "EDIT", "REJECT", "SKIP"})
ERROR_CATEGORIES = frozenset({
    "NO_ERROR",
    "MISSED_SWING",
    "FALSE_SWING",
    "WRONG_BOS",
    "MISSED_RECLAIM",
    "FALSE_RECLAIM",
    "WRONG_RH",
    "WRONG_RL",
    "MAJOR_MINOR_ERROR",
    "WRONG_REF_CANDLE",
    "WRONG_PROFILE",
    "OTHER",
})
RETRACEMENT_DIRECTIONS = frozenset({"INTO_OLD_RANGE_UP", "INTO_OLD_RANGE_DOWN"})
BOUNDARY_TOUCHED = frozenset({"HIGH", "LOW", "BOTH", "NONE"})
MEASUREMENT_STATUSES = frozenset({"SUGGESTED", "CONFIRMED", "REJECTED"})
WORKFLOW_MODES = frozenset({"GUIDED", "MANUAL", "AUTOPILOT_PAUSED"})
SESSION_STATUSES = frozenset({"ACTIVE", "PAUSED", "COMPLETED", "ARCHIVED"})


def utc_now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def new_uuid() -> str:
    return str(uuid.uuid4())


def _row_dict(row: sqlite3.Row | dict[str, Any] | None) -> dict[str, Any]:
    if row is None:
        return {}
    if isinstance(row, dict):
        return row
    return dict(row)


def _json_dumps(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def _json_loads(value: Any) -> Any:
    if value in (None, ""):
        return None
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except json.JSONDecodeError:
        return None


def normalise_range_scale(value: Any, *, row: dict[str, Any] | None = None) -> str:
    """Canonical range_scale with legacy range_scope fallback for old rows."""
    raw = value
    if raw in (None, "") and row is not None:
        raw = row.get("range_scale") or row.get("range_scope")
    scale = str(raw or "MAJOR").strip().upper()
    return scale if scale in RANGE_SCALES else "MAJOR"


def normalise_enum(value: Any, allowed: frozenset[str], default: str) -> str:
    text = str(value or default).strip().upper()
    return text if text in allowed else default


def normalise_engine_source(value: Any) -> str:
    text = str(value or "manual").strip().lower()
    return text if text in ENGINE_SOURCES else "manual"


class DetectionBrainStoreError(Exception):
    pass


class DuplicateOpenSuggestionError(DetectionBrainStoreError):
    pass


@dataclass
class DetectorSuggestion:
    suggestion_id: str
    detector_version: str
    engine_source: str
    candidate_kind: str
    symbol: str
    structure_layer: str
    source_timeframe: str
    chart_timeframe: str
    candle_time_utc_ms: int
    created_at_utc_ms: int
    schema_version: str = DETECTION_BRAIN_SCHEMA
    candidate_index: int = 0
    status: str = "PENDING"
    case_id: int | None = None
    case_ref: str | None = None
    raw_case_id: str | None = None
    parent_range_id: int | None = None
    active_range_id: int | None = None
    old_range_id: int | None = None
    candle_index: int | None = None
    suggested_rh: float | None = None
    suggested_rl: float | None = None
    suggested_rh_time_ms: int | None = None
    suggested_rl_time_ms: int | None = None
    suggested_rh_price_int: int | None = None
    suggested_rl_price_int: int | None = None
    price_scale: int | None = None
    range_scale: str | None = None
    range_role: str | None = None
    internal_structure_status: str | None = None
    event_side: str | None = None
    event_price: float | None = None
    event_price_int: int | None = None
    break_rule: str | None = None
    movement_rule: str | None = None
    primitive: str | None = None
    derived_event_code: str | None = None
    confidence: str = "MEDIUM"
    reason_text: str = ""
    meta_json: dict[str, Any] | None = None
    user_action: str | None = None
    reviewed_at_utc_ms: int | None = None
    reviewed_by: str = "josh"
    promoted_range_id: int | None = None
    promoted_event_id: int | None = None
    promoted_raw_event_id: str | None = None
    session_id: str | None = None
    supersedes_suggestion_id: str | None = None
    correction_id: str | None = None
    updated_at_utc_ms: int | None = None


@dataclass
class DetectorCorrection:
    correction_id: str
    suggestion_id: str
    candidate_kind: str
    detector_version: str
    symbol: str
    structure_layer: str
    source_timeframe: str
    user_action: str
    error_category: str
    suggested_snapshot_json: dict[str, Any]
    created_at_utc_ms: int
    schema_version: str = DETECTION_BRAIN_SCHEMA
    session_id: str | None = None
    notes: str = ""
    final_snapshot_json: dict[str, Any] | None = None
    promoted_range_id: int | None = None
    promoted_event_id: int | None = None
    promoted_raw_event_id: str | None = None


@dataclass
class RetracementMeasurement:
    measurement_id: str
    detector_version: str
    old_range_id: int
    new_range_id: int
    bos_event_id: int
    symbol: str
    structure_layer: str
    source_timeframe: str
    bos_direction: str
    retracement_direction: str
    old_range_boundary_touched: str
    retrace_start_time_ms: int
    created_at_utc_ms: int
    schema_version: str = DETECTION_BRAIN_SCHEMA
    measurement_status: str = "SUGGESTED"
    case_ref: str | None = None
    case_id: int | None = None
    suggestion_id: str | None = None
    session_id: str | None = None
    retrace_end_time_ms: int | None = None
    retrace_high: float | None = None
    retrace_low: float | None = None
    deepest_retrace_price: float | None = None
    max_retrace_percent: float | None = None
    retrace_depth_percent: float | None = None
    respected_level: float | None = None
    breached_618: int = 0
    breached_70: int = 0
    breached_75: int = 0
    profile_classification: str | None = None
    meta_json: dict[str, Any] | None = None
    user_action: str | None = None
    reviewed_at_utc_ms: int | None = None
    updated_at_utc_ms: int | None = None


@dataclass
class MappingSession:
    session_id: str
    symbol: str
    structure_layer: str
    source_timeframe: str
    chart_timeframe: str
    created_at_utc_ms: int
    schema_version: str = DETECTION_BRAIN_SCHEMA
    case_id: int | None = None
    case_ref: str | None = None
    raw_case_id: str | None = None
    replay_candle_time_utc_ms: int | None = None
    replay_candle_index: int | None = None
    current_parent_range_id: int | None = None
    current_active_range_id: int | None = None
    current_old_range_id: int | None = None
    workflow_mode: str = "GUIDED"
    autopilot_step: str | None = None
    target_range_scale: str = "MAJOR"
    internal_structure_status: str | None = None
    path_outcome: str | None = None
    active_suggestion_id: str | None = None
    active_candidate_kind: str | None = None
    detector_versions_json: dict[str, str] = field(default_factory=dict)
    state_json: dict[str, Any] | None = None
    status: str = "ACTIVE"
    updated_at_utc_ms: int | None = None
    last_resumed_at_utc_ms: int | None = None


@dataclass
class DetectorVersionRecord:
    detector_version: str
    domain: str
    major_number: int
    created_at_utc_ms: int
    release_notes: str = ""
    rule_summary_json: dict[str, Any] | None = None
    supersedes_version: str | None = None


def _validate_suggestion(record: DetectorSuggestion) -> None:
    if not record.suggestion_id:
        raise DetectionBrainStoreError("suggestion_id is required")
    if not record.detector_version:
        raise DetectionBrainStoreError("detector_version is required")
    if not record.candidate_kind:
        raise DetectionBrainStoreError("candidate_kind is required")
    normalise_engine_source(record.engine_source)
    if record.range_scale is not None:
        normalise_range_scale(record.range_scale)
    if record.status not in SUGGESTION_STATUSES:
        raise DetectionBrainStoreError(f"invalid suggestion status: {record.status}")


def _validate_correction(record: DetectorCorrection) -> None:
    action = str(record.user_action).strip().upper()
    if action not in USER_ACTIONS - {"SKIP"}:
        raise DetectionBrainStoreError(f"invalid user_action: {record.user_action}")
    category = str(record.error_category).strip().upper()
    if category not in ERROR_CATEGORIES:
        raise DetectionBrainStoreError(f"invalid error_category: {record.error_category}")
    if action == "APPROVE" and category != "NO_ERROR":
        raise DetectionBrainStoreError("APPROVE requires error_category = NO_ERROR")
    if action in {"EDIT", "REJECT"} and category == "NO_ERROR":
        raise DetectionBrainStoreError("EDIT/REJECT cannot use error_category = NO_ERROR")


def insert_suggestion(conn: sqlite3.Connection, record: DetectorSuggestion) -> dict[str, Any]:
    _validate_suggestion(record)
    now_ms = record.created_at_utc_ms or utc_now_ms()
    payload = DetectorSuggestion(
        **{
            **asdict(record),
            "created_at_utc_ms": now_ms,
            "engine_source": normalise_engine_source(record.engine_source),
            "range_scale": normalise_range_scale(record.range_scale) if record.range_scale else None,
            "schema_version": record.schema_version or DETECTION_BRAIN_SCHEMA,
        }
    )
    try:
        conn.execute(
            """
            INSERT INTO detector_suggestions (
                suggestion_id, schema_version, detector_version, engine_source, candidate_kind,
                candidate_index, status, symbol, structure_layer, source_timeframe, chart_timeframe,
                case_id, case_ref, raw_case_id, parent_range_id, active_range_id, old_range_id,
                candle_time_utc_ms, candle_index, suggested_rh, suggested_rl, suggested_rh_time_ms,
                suggested_rl_time_ms, suggested_rh_price_int, suggested_rl_price_int, price_scale,
                range_scale, range_role, internal_structure_status, event_side, event_price,
                event_price_int, break_rule, movement_rule, primitive, derived_event_code,
                confidence, reason_text, meta_json, user_action, reviewed_at_utc_ms, reviewed_by,
                promoted_range_id, promoted_event_id, promoted_raw_event_id, session_id,
                supersedes_suggestion_id, correction_id, created_at_utc_ms, updated_at_utc_ms
            ) VALUES (
                ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
            )
            """,
            (
                payload.suggestion_id,
                payload.schema_version,
                payload.detector_version,
                payload.engine_source,
                payload.candidate_kind,
                payload.candidate_index,
                payload.status,
                payload.symbol.upper(),
                payload.structure_layer.upper(),
                payload.source_timeframe.upper(),
                payload.chart_timeframe.upper(),
                payload.case_id,
                payload.case_ref,
                payload.raw_case_id,
                payload.parent_range_id,
                payload.active_range_id,
                payload.old_range_id,
                payload.candle_time_utc_ms,
                payload.candle_index,
                payload.suggested_rh,
                payload.suggested_rl,
                payload.suggested_rh_time_ms,
                payload.suggested_rl_time_ms,
                payload.suggested_rh_price_int,
                payload.suggested_rl_price_int,
                payload.price_scale,
                payload.range_scale,
                payload.range_role,
                payload.internal_structure_status,
                payload.event_side,
                payload.event_price,
                payload.event_price_int,
                payload.break_rule,
                payload.movement_rule,
                payload.primitive,
                payload.derived_event_code,
                payload.confidence,
                payload.reason_text,
                _json_dumps(payload.meta_json),
                payload.user_action,
                payload.reviewed_at_utc_ms,
                payload.reviewed_by,
                payload.promoted_range_id,
                payload.promoted_event_id,
                payload.promoted_raw_event_id,
                payload.session_id,
                payload.supersedes_suggestion_id,
                payload.correction_id,
                payload.created_at_utc_ms,
                payload.updated_at_utc_ms,
            ),
        )
    except sqlite3.IntegrityError as exc:
        if "uq_detector_suggestions_open_slot" in str(exc).lower() or "unique" in str(exc).lower():
            raise DuplicateOpenSuggestionError(str(exc)) from exc
        raise
    return get_suggestion(conn, payload.suggestion_id) or {}


def supersede_pending_suggestion(conn: sqlite3.Connection, suggestion_id: str) -> bool:
    now_ms = utc_now_ms()
    cur = conn.execute(
        """
        UPDATE detector_suggestions
        SET status = 'SUPERSEDED', updated_at_utc_ms = ?
        WHERE suggestion_id = ? AND status = 'PENDING'
        """,
        (now_ms, suggestion_id),
    )
    return cur.rowcount > 0


def get_suggestion(conn: sqlite3.Connection, suggestion_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM detector_suggestions WHERE suggestion_id = ?",
        (suggestion_id,),
    ).fetchone()
    if not row:
        return None
    out = _row_dict(row)
    out["meta_json"] = _json_loads(out.get("meta_json"))
    out["range_scale"] = normalise_range_scale(out.get("range_scale"), row=out)
    return out


def list_suggestions(
    conn: sqlite3.Connection,
    *,
    status: str | None = "PENDING",
    symbol: str | None = None,
    structure_layer: str | None = None,
    source_timeframe: str | None = None,
    parent_range_id: int | None = None,
    session_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    clauses = ["1=1"]
    params: list[Any] = []
    if status:
        clauses.append("status = ?")
        params.append(status.upper())
    if symbol:
        clauses.append("symbol = ?")
        params.append(symbol.upper())
    if structure_layer:
        clauses.append("structure_layer = ?")
        params.append(structure_layer.upper())
    if source_timeframe:
        clauses.append("source_timeframe = ?")
        params.append(source_timeframe.upper())
    if parent_range_id is not None:
        if int(parent_range_id) < 0:
            clauses.append("parent_range_id IS NULL")
        else:
            clauses.append("parent_range_id = ?")
            params.append(int(parent_range_id))
    if session_id:
        clauses.append("session_id = ?")
        params.append(session_id)
    params.append(max(1, min(limit, 500)))
    rows = conn.execute(
        f"""
        SELECT * FROM detector_suggestions
        WHERE {' AND '.join(clauses)}
        ORDER BY created_at_utc_ms DESC
        LIMIT ?
        """,
        params,
    ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        item = _row_dict(row)
        item["meta_json"] = _json_loads(item.get("meta_json"))
        item["range_scale"] = normalise_range_scale(item.get("range_scale"), row=item)
        out.append(item)
    return out


def insert_correction(conn: sqlite3.Connection, record: DetectorCorrection) -> dict[str, Any]:
    _validate_correction(record)
    conn.execute(
        """
        INSERT INTO detector_corrections (
            correction_id, schema_version, suggestion_id, session_id, candidate_kind,
            detector_version, symbol, structure_layer, source_timeframe, user_action,
            error_category, notes, suggested_snapshot_json, final_snapshot_json,
            promoted_range_id, promoted_event_id, promoted_raw_event_id, created_at_utc_ms
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            record.correction_id,
            record.schema_version,
            record.suggestion_id,
            record.session_id,
            record.candidate_kind,
            record.detector_version,
            record.symbol.upper(),
            record.structure_layer.upper(),
            record.source_timeframe.upper(),
            record.user_action.upper(),
            record.error_category.upper(),
            record.notes,
            _json_dumps(record.suggested_snapshot_json) or "{}",
            _json_dumps(record.final_snapshot_json),
            record.promoted_range_id,
            record.promoted_event_id,
            record.promoted_raw_event_id,
            record.created_at_utc_ms,
        ),
    )
    row = conn.execute(
        "SELECT * FROM detector_corrections WHERE correction_id = ?",
        (record.correction_id,),
    ).fetchone()
    out = _row_dict(row)
    out["suggested_snapshot_json"] = _json_loads(out.get("suggested_snapshot_json"))
    out["final_snapshot_json"] = _json_loads(out.get("final_snapshot_json"))
    return out


def insert_retracement_measurement(conn: sqlite3.Connection, record: RetracementMeasurement) -> dict[str, Any]:
    direction = str(record.retracement_direction).strip().upper()
    if direction not in RETRACEMENT_DIRECTIONS:
        raise DetectionBrainStoreError(f"invalid retracement_direction: {record.retracement_direction}")
    boundary = str(record.old_range_boundary_touched).strip().upper()
    if boundary not in BOUNDARY_TOUCHED:
        raise DetectionBrainStoreError(f"invalid old_range_boundary_touched: {record.old_range_boundary_touched}")
    conn.execute(
        """
        INSERT INTO retracement_measurements (
            measurement_id, schema_version, detector_version, measurement_status,
            case_ref, case_id, old_range_id, new_range_id, bos_event_id, suggestion_id,
            session_id, symbol, structure_layer, source_timeframe, bos_direction,
            retracement_direction, old_range_boundary_touched, retrace_start_time_ms,
            retrace_end_time_ms, retrace_high, retrace_low, deepest_retrace_price,
            max_retrace_percent, retrace_depth_percent, respected_level, breached_618,
            breached_70, breached_75, profile_classification, meta_json, user_action,
            reviewed_at_utc_ms, created_at_utc_ms, updated_at_utc_ms
        ) VALUES (
            ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
        )
        """,
        (
            record.measurement_id,
            record.schema_version,
            record.detector_version,
            record.measurement_status,
            record.case_ref,
            record.case_id,
            record.old_range_id,
            record.new_range_id,
            record.bos_event_id,
            record.suggestion_id,
            record.session_id,
            record.symbol.upper(),
            record.structure_layer.upper(),
            record.source_timeframe.upper(),
            record.bos_direction.upper(),
            direction,
            boundary,
            record.retrace_start_time_ms,
            record.retrace_end_time_ms,
            record.retrace_high,
            record.retrace_low,
            record.deepest_retrace_price,
            record.max_retrace_percent,
            record.retrace_depth_percent,
            record.respected_level,
            int(record.breached_618),
            int(record.breached_70),
            int(record.breached_75),
            record.profile_classification,
            _json_dumps(record.meta_json),
            record.user_action,
            record.reviewed_at_utc_ms,
            record.created_at_utc_ms,
            record.updated_at_utc_ms,
        ),
    )
    row = conn.execute(
        "SELECT * FROM retracement_measurements WHERE measurement_id = ?",
        (record.measurement_id,),
    ).fetchone()
    out = _row_dict(row)
    out["meta_json"] = _json_loads(out.get("meta_json"))
    return out


def insert_mapping_session(conn: sqlite3.Connection, record: MappingSession) -> dict[str, Any]:
    if record.workflow_mode not in WORKFLOW_MODES:
        raise DetectionBrainStoreError(f"invalid workflow_mode: {record.workflow_mode}")
    if record.status not in SESSION_STATUSES:
        raise DetectionBrainStoreError(f"invalid session status: {record.status}")
    conn.execute(
        """
        INSERT INTO mapping_sessions (
            session_id, schema_version, symbol, case_id, case_ref, raw_case_id,
            structure_layer, source_timeframe, chart_timeframe, replay_candle_time_utc_ms,
            replay_candle_index, current_parent_range_id, current_active_range_id,
            current_old_range_id, workflow_mode, autopilot_step, target_range_scale,
            internal_structure_status, path_outcome, active_suggestion_id,
            active_candidate_kind, detector_versions_json, state_json, status,
            created_at_utc_ms, updated_at_utc_ms, last_resumed_at_utc_ms
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            record.session_id,
            record.schema_version,
            record.symbol.upper(),
            record.case_id,
            record.case_ref,
            record.raw_case_id,
            record.structure_layer.upper(),
            record.source_timeframe.upper(),
            record.chart_timeframe.upper(),
            record.replay_candle_time_utc_ms,
            record.replay_candle_index,
            record.current_parent_range_id,
            record.current_active_range_id,
            record.current_old_range_id,
            record.workflow_mode,
            record.autopilot_step,
            normalise_range_scale(record.target_range_scale),
            record.internal_structure_status,
            record.path_outcome,
            record.active_suggestion_id,
            record.active_candidate_kind,
            _json_dumps(record.detector_versions_json) or "{}",
            _json_dumps(record.state_json),
            record.status,
            record.created_at_utc_ms,
            record.updated_at_utc_ms,
            record.last_resumed_at_utc_ms,
        ),
    )
    return get_mapping_session(conn, record.session_id) or {}


def get_mapping_session(conn: sqlite3.Connection, session_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM mapping_sessions WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    if not row:
        return None
    out = _row_dict(row)
    out["detector_versions_json"] = _json_loads(out.get("detector_versions_json")) or {}
    out["state_json"] = _json_loads(out.get("state_json"))
    out["target_range_scale"] = normalise_range_scale(out.get("target_range_scale"), row=out)
    return out


def register_detector_version(conn: sqlite3.Connection, record: DetectorVersionRecord) -> dict[str, Any]:
    conn.execute(
        """
        INSERT OR IGNORE INTO detector_version_registry (
            detector_version, domain, major_number, release_notes,
            rule_summary_json, supersedes_version, created_at_utc_ms
        ) VALUES (?,?,?,?,?,?,?)
        """,
        (
            record.detector_version,
            record.domain.upper(),
            record.major_number,
            record.release_notes,
            _json_dumps(record.rule_summary_json),
            record.supersedes_version,
            record.created_at_utc_ms,
        ),
    )
    row = conn.execute(
        "SELECT * FROM detector_version_registry WHERE detector_version = ?",
        (record.detector_version,),
    ).fetchone()
    out = _row_dict(row)
    out["rule_summary_json"] = _json_loads(out.get("rule_summary_json"))
    return out


def map_range_phase1_view(conn: sqlite3.Connection, range_id: int) -> dict[str, Any] | None:
    """Read map_ranges with canonical range_scale (legacy range_scope fallback)."""
    row = conn.execute("SELECT * FROM map_ranges WHERE id = ?", (range_id,)).fetchone()
    if not row:
        return None
    out = _row_dict(row)
    out["range_scale"] = normalise_range_scale(out.get("range_scale"), row=out)
    return out
