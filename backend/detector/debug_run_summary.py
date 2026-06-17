"""Read-only debug summary for a detector run (no detector logic)."""

from __future__ import annotations

import json
from typing import Any

from detector.models import DetectionContext, SuggestionDraft
from detector.pipeline import DetectionResult
from detector.range_seed import SeedResolutionResult


def _parse_meta(value: Any) -> dict[str, Any]:
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    try:
        return json.loads(str(value))
    except json.JSONDecodeError:
        return {}


def build_run_debug_summary(
    result: DetectionResult,
    ctx: DetectionContext,
    *,
    detection_run_id: str | None,
    seed_resolution: SeedResolutionResult | None = None,
    saved_suggestions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Assemble inspectable fields for the latest detector run."""
    drafts = list(result.drafts or [])
    kinds = [d.candidate_kind for d in drafts]
    versions = sorted({d.detector_version for d in drafts})

    range_draft = next(
        (
            d
            for d in drafts
            if d.detector_version == "RANGE_V2"
            or d.candidate_kind
            in {"RANGE_MAJOR", "RANGE_MINOR", "NO_VALID_RANGE", "NO_MINOR_STRUCTURE"}
        ),
        None,
    )
    range_meta = dict(range_draft.meta_json or {}) if range_draft else {}

    seed_meta = dict(ctx.range_seed_meta or {})
    if seed_resolution is not None:
        seed_meta.setdefault("seed_source", seed_resolution.seed_source)
        seed_meta["no_seed_context"] = seed_resolution.no_seed_context
        if seed_resolution.seed_lookup_error:
            seed_meta["seed_lookup_error"] = seed_resolution.seed_lookup_error
        if seed_resolution.seed is not None:
            seed_meta.setdefault("active_range_id", seed_resolution.seed.active_range_id)
            seed_meta.setdefault("seed_rh", seed_resolution.seed.range_high)
            seed_meta.setdefault("seed_rl", seed_resolution.seed.range_low)
            seed_meta.setdefault("seed_status", seed_resolution.seed.status)

    window = dict(ctx.detection_window_meta or {})

    bos_count = sum(1 for d in drafts if d.candidate_kind in {"BOS_UP", "BOS_DOWN"})
    reclaim_count = sum(1 for d in drafts if d.candidate_kind in {"RECLAIM_UP", "RECLAIM_DOWN"})

    saved_rows = list(saved_suggestions or [])
    saved_kinds = [str(r.get("candidate_kind")) for r in saved_rows]
    saved_versions = sorted({str(r.get("detector_version")) for r in saved_rows if r.get("detector_version")})

    classification_hint = _classify_outcome(
        range_draft=range_draft,
        range_meta=range_meta,
        seed_meta=seed_meta,
        written_count=len(saved_rows),
        draft_count=len(drafts),
        range_mode=result.range_mode,
    )

    return {
        "detection_run_id": detection_run_id or window.get("detection_run_id"),
        "range_mode": result.range_mode,
        "draft_count": len(drafts),
        "written_count": len(saved_rows),
        "candidate_kinds": kinds,
        "detector_versions": versions,
        "saved_candidate_kinds": saved_kinds,
        "saved_detector_versions": saved_versions,
        "seed_source": seed_meta.get("seed_source"),
        "active_range_id": seed_meta.get("active_range_id") or ctx.active_range_id,
        "seed_rh": seed_meta.get("seed_rh"),
        "seed_rl": seed_meta.get("seed_rl"),
        "no_seed_context": seed_meta.get("no_seed_context"),
        "seed_lookup_error": seed_meta.get("seed_lookup_error"),
        "lifecycle_state": range_meta.get("lifecycle_state"),
        "broken_boundary": range_meta.get("broken_boundary"),
        "boundary_selection_reason": range_meta.get("boundary_selection_reason"),
        "opposite_swing_index": range_meta.get("opposite_swing_index"),
        "bos_candidate_count": bos_count,
        "reclaim_candidate_count": reclaim_count,
        "first_candle_time": window.get("first_candle_time"),
        "last_candle_time": window.get("last_candle_time"),
        "first_candle_time_ms": window.get("first_candle_time_ms"),
        "last_candle_time_ms": window.get("last_candle_time_ms"),
        "candle_count_used": window.get("candle_count_used"),
        "structure_layer": ctx.structure_layer,
        "source_timeframe": ctx.source_timeframe,
        "range_candidate_kind": range_draft.candidate_kind if range_draft else None,
        "range_detector_version": range_draft.detector_version if range_draft else None,
        "classification_hint": classification_hint,
        "range_meta_sample": {
            k: range_meta.get(k)
            for k in (
                "lifecycle_state",
                "seed_source",
                "no_seed_context",
                "seed_lookup_error",
                "active_range_id",
                "seed_rh",
                "seed_rl",
                "broken_boundary",
                "boundary_selection_reason",
                "detection_run_id",
                "replay_until_time",
                "replay_until_time_ms",
            )
            if k in range_meta or range_meta.get(k) is not None
        },
    }


def _classify_outcome(
    *,
    range_draft: SuggestionDraft | None,
    range_meta: dict[str, Any],
    seed_meta: dict[str, Any],
    written_count: int,
    draft_count: int,
    range_mode: str,
    range_kind: str | None = None,
) -> str:
    if written_count == 0 and draft_count == 0:
        return "E"
    if written_count == 0 and draft_count > 0:
        return "E_WRITER"
    if range_mode != "doctrine_v2":
        return "OTHER_MODE"
    kind = range_kind or (range_draft.candidate_kind if range_draft else None)
    if kind is None:
        return "E"
    if kind in {"RANGE_MAJOR", "RANGE_MINOR"}:
        return "OK_RANGE"
    if kind == "NO_VALID_RANGE":
        if seed_meta.get("no_seed_context") is True:
            return "A"
        life = str(range_meta.get("lifecycle_state") or "")
        if life in {"BREACHED_UP", "BREACHED_DOWN"}:
            return "C"
        if range_meta.get("boundary_selection_reason") == "UNCLEAR_OPPOSITE_SWING":
            return "CASE_5_UNCLEAR_SWING"
        if life in {"ACTIVE_RANGE", "SEEDED", "NO_VALID_RANGE"}:
            return "B"
        return "A"
    return "UNKNOWN"


def inspect_db_run(
    conn,
    *,
    detection_run_id: str,
    symbol: str = "XAUUSD",
) -> dict[str, Any]:
    """Load PENDING RANGE_V2 rows for a detection_run_id from detector_suggestions."""
    rows = conn.execute(
        """
        SELECT suggestion_id, candidate_kind, detector_version, engine_source, status,
               structure_layer, source_timeframe, parent_range_id, active_range_id,
               suggested_rh, suggested_rl, meta_json, created_at_utc_ms
        FROM detector_suggestions
        WHERE symbol = ? AND status = 'PENDING'
        ORDER BY created_at_utc_ms DESC
        LIMIT 200
        """,
        (symbol.upper(),),
    ).fetchall()

    matched: list[dict[str, Any]] = []
    all_pending_kinds: list[str] = []
    for row in rows:
        item = dict(row)
        meta = _parse_meta(item.get("meta_json"))
        item["meta_json"] = meta
        all_pending_kinds.append(str(item.get("candidate_kind")))
        if str(meta.get("detection_run_id") or "") == detection_run_id:
            matched.append(item)

    range_rows = [
        r
        for r in matched
        if r.get("detector_version") == "RANGE_V2"
        or str(r.get("candidate_kind")) in {"RANGE_MAJOR", "RANGE_MINOR", "NO_VALID_RANGE", "NO_MINOR_STRUCTURE"}
    ]
    range_row = range_rows[0] if range_rows else (matched[0] if matched else None)
    range_meta = _parse_meta(range_row.get("meta_json")) if range_row else {}

    bos_count = sum(1 for r in matched if str(r.get("candidate_kind", "")).startswith("BOS_"))
    reclaim_count = sum(1 for r in matched if "RECLAIM" in str(r.get("candidate_kind", "")))

    hint = _classify_outcome(
        range_draft=None,
        range_meta=range_meta,
        seed_meta=range_meta,
        written_count=len(matched),
        draft_count=len(matched),
        range_mode="doctrine_v2",
        range_kind=str(range_row.get("candidate_kind")) if range_row else None,
    )
    if len(rows) > 0 and len(matched) == 0:
        hint = "D"

    return {
        "detection_run_id": detection_run_id,
        "db_pending_total_for_symbol": len(rows),
        "db_matched_run_count": len(matched),
        "candidate_kinds": [r.get("candidate_kind") for r in matched],
        "detector_versions": sorted({str(r.get("detector_version")) for r in matched}),
        "seed_source": range_meta.get("seed_source"),
        "active_range_id": range_meta.get("active_range_id"),
        "seed_rh": range_meta.get("seed_rh"),
        "seed_rl": range_meta.get("seed_rl"),
        "no_seed_context": range_meta.get("no_seed_context"),
        "seed_lookup_error": range_meta.get("seed_lookup_error"),
        "lifecycle_state": range_meta.get("lifecycle_state"),
        "broken_boundary": range_meta.get("broken_boundary"),
        "bos_candidate_count": bos_count,
        "reclaim_candidate_count": reclaim_count,
        "first_candle_time": range_meta.get("first_candle_time"),
        "last_candle_time": range_meta.get("last_candle_time"),
        "candle_count_used": range_meta.get("candle_count_used"),
        "range_meta_sample": range_meta,
        "classification_hint": hint,
        "note": (
            "D_suspected: PENDING rows exist for symbol but none match detection_run_id — panel filter mismatch"
            if len(rows) > 0 and len(matched) == 0
            else None
        ),
    }
